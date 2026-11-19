import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

RAW = Path("data/raw/playercard_history")
PROCESSED = Path("data/processed/player_performance.json")
LEGACY_OUT = Path("artifacts/legacy_weekly_reconstruction")
SCORING_AUDIT = Path("artifacts/playercard_scoring_validation/playercard_scoring_validation.json")
COVERAGE_AUDIT = Path("artifacts/player_card_history/player_card_history_audit.json")
OUT = Path("artifacts/player_performance_candidate")
YEARS = range(2011, 2027)


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_gzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    existing = read_json(PROCESSED, {}) or {}
    existing_rows = existing.get("player_seasons") or []
    existing_map = {
        (int(row["season"]), int(row["player_id"])): row
        for row in existing_rows
        if row.get("season") is not None and row.get("player_id") is not None
    }

    legacy_audit = read_json(LEGACY_OUT / "legacy_weekly_reconstruction_audit.json", {}) or {}
    scoring_audit = read_json(SCORING_AUDIT, {}) or {}
    coverage_audit = read_json(COVERAGE_AUDIT, {}) or {}

    player_seasons = []
    weekly_rows = []
    season_audit = {}
    source_errors = []
    missing_legacy_weeks = []
    duplicate_player_seasons = []

    for year in YEARS:
        archive_path = RAW / f"playercard_{year}.json.gz"
        if not archive_path.exists():
            source_errors.append({"season": year, "error": f"Missing {archive_path}"})
            continue
        archive = read_gzip(archive_path)
        archive_players = archive.get("players") or []
        roster_history = archive.get("roster_history") or []
        boxscore_rows = archive.get("boxscore_weekly_points") or []

        reconstructed = {}
        if year < 2018:
            legacy_path = LEGACY_OUT / f"legacy_weekly_reconstruction_{year}.json.gz"
            if legacy_path.exists():
                legacy_archive = read_gzip(legacy_path)
                reconstructed = {
                    int(row["player_id"]): row
                    for row in legacy_archive.get("players") or []
                }
            else:
                missing_legacy_weeks.append(year)

        roster_by_player = defaultdict(list)
        for row in roster_history:
            try:
                roster_by_player[int(row["player_id"])].append(row)
            except (KeyError, TypeError, ValueError):
                continue
        for row in boxscore_rows:
            try:
                roster_by_player[int(row["player_id"])].append(row)
            except (KeyError, TypeError, ValueError):
                continue

        player_count = 0
        weekly_count = 0
        missing_weekly_players = []
        source_counts = Counter()
        season_total_mismatches = []
        seen_ids = set()

        for player in archive_players:
            try:
                pid = int(player["player_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if pid in seen_ids:
                duplicate_player_seasons.append({"season": year, "player_id": pid})
                continue
            seen_ids.add(pid)

            name = player.get("player_name") or player.get("name")
            position_id = player.get("position_id")
            pro_team_id = player.get("pro_team_id")
            season_total = player.get("season_total")
            season_stats = player.get("season_stats") or {}
            sources = player.get("sources") or []

            roster_rows = roster_by_player.get(pid, [])
            roster_team_ids = sorted({
                int(row["team_id"]) for row in roster_rows
                if row.get("team_id") is not None
            })
            acquisition_types = sorted({
                str(row["acquisition_type"]) for row in roster_rows
                if row.get("acquisition_type")
            })
            started_weeks = sorted({
                int(row["scoring_period"]) for row in boxscore_rows
                if int(row.get("player_id", -999999)) == pid
                and row.get("scoring_period") is not None
            })

            weeks = {}
            if year < 2018:
                legacy_player = reconstructed.get(pid)
                if legacy_player:
                    for key, week in (legacy_player.get("weeks") or {}).items():
                        scoring_period = int(week.get("week") or key)
                        weeks[str(scoring_period)] = {
                            "scoring_period": scoring_period,
                            "fantasy_points": week.get("fantasy_points"),
                            "stats": week.get("stats") or {},
                            "points_source": week.get("points_source") or "ESPN game-summary reconstruction",
                            "reconstructed_fantasy_points": week.get("reconstructed_fantasy_points", week.get("fantasy_points")),
                        }
                elif season_total not in (None, 0, 0.0):
                    missing_weekly_players.append(pid)
            else:
                weekly_data = player.get("weeks") or {}
                if isinstance(weekly_data, dict):
                    iterable = weekly_data.items()
                elif isinstance(weekly_data, list):
                    iterable = [(week.get("scoring_period"), week) for week in weekly_data]
                else:
                    iterable = []
                for week_key, week in iterable:
                    try:
                        scoring_period = int(week.get("scoring_period", week_key))
                    except (AttributeError, TypeError, ValueError):
                        continue
                    weeks[str(scoring_period)] = {
                        "scoring_period": scoring_period,
                        "fantasy_points": week.get("fantasy_points", week.get("points")),
                        "stats": week.get("stats") or {},
                        "points_source": "ESPN kona_playercard",
                        "stat_id": week.get("stat_id"),
                        "season_id": week.get("season_id"),
                    }
                if not weeks and season_total not in (None, 0, 0.0):
                    missing_weekly_players.append(pid)

            for key, week in weeks.items():
                if week.get("fantasy_points") is None:
                    continue
                weekly_rows.append({
                    "season": year,
                    "scoring_period": int(key),
                    "player_id": pid,
                    "player_name": name,
                    "fantasy_points": week["fantasy_points"],
                    "points_source": week.get("points_source"),
                })
                weekly_count += 1

            if year < 2018 and pid in reconstructed:
                legacy_total = reconstructed[pid].get("season_fantasy_points")
                if season_total is not None and legacy_total is not None and abs(float(season_total) - float(legacy_total)) > 0.02:
                    season_total_mismatches.append({
                        "player_id": pid,
                        "playercard_total": season_total,
                        "legacy_archive_total": legacy_total,
                    })

            record = {
                "season": year,
                "player_id": pid,
                "name": name,
                "player_name": name,
                "default_position_id": position_id,
                "position_id": position_id,
                "pro_team_id": pro_team_id,
                "season_fantasy_points": season_total,
                "season_applied_average": None,
                "roster_team_ids": roster_team_ids,
                "acquisition_types": acquisition_types,
                "data_sources": sorted(set(sources)),
                "started_scoring_periods": started_weeks,
                "season_stats": season_stats,
                "weeks": weeks,
            }
            player_seasons.append(record)
            player_count += 1
            for source in sources:
                source_counts[source] += 1

        legacy_season = legacy_audit.get("seasons", {}).get(str(year), {}) if year < 2018 else {}
        scoring_season = scoring_audit.get("seasons", {}).get(str(year), {}) if year >= 2018 else {}
        season_audit[str(year)] = {
            "player_seasons": player_count,
            "weekly_rows": weekly_count,
            "players_missing_weekly_data": len(missing_weekly_players),
            "missing_weekly_player_ids_sample": missing_weekly_players[:50],
            "source_counts": dict(source_counts),
            "legacy_season_total_mismatches": legacy_season.get("season_total_mismatches", 0),
            "legacy_stat_gap_count": sum((legacy_season.get("stat_gap_counts") or {}).values()),
            "legacy_boxscore_multiweek_mismatches": legacy_season.get("boxscore_multiweek_mismatches", 0),
            "modern_scoring_mismatches": scoring_season.get("mismatch_count", 0),
            "modern_weekly_sum_mismatches": scoring_season.get("weekly_sum_mismatch_count", 0),
            "player_ids_in_archive": len(archive_players),
            "boxscore_roster_rows": len(boxscore_rows),
        }

    player_seasons.sort(key=lambda row: (row["season"], row["player_id"]))
    weekly_rows.sort(key=lambda row: (row["season"], row["scoring_period"], row["player_id"]))

    existing_keys = set(existing_map)
    candidate_keys = {(int(row["season"]), int(row["player_id"])) for row in player_seasons}
    added_keys = sorted(candidate_keys - existing_keys)
    missing_keys = sorted(existing_keys - candidate_keys)
    season_total_changes = []
    candidate_map = {
        (int(row["season"]), int(row["player_id"])): row
        for row in player_seasons
    }
    for key in sorted(candidate_keys & existing_keys):
        new = candidate_map[key]
        old = existing_map[key]
        old_total = old.get("season_fantasy_points")
        new_total = new.get("season_fantasy_points")
        if old_total is not None and new_total is not None and abs(float(old_total) - float(new_total)) > 0.02:
            season_total_changes.append({
                "season": key[0],
                "player_id": key[1],
                "existing_total": old_total,
                "candidate_total": new_total,
            })

    legacy_years = [str(y) for y in range(2011, 2018)]
    modern_years = [str(y) for y in range(2018, 2027)]
    legacy_audit_seasons = legacy_audit.get("seasons") or {}
    scoring_audit_seasons = scoring_audit.get("seasons") or {}
    legacy_audit_complete = all(y in legacy_audit_seasons for y in legacy_years)
    scoring_audit_complete = all(y in scoring_audit_seasons for y in modern_years)
    legacy_ready = legacy_audit_complete and all(
        season_audit.get(y, {}).get("legacy_season_total_mismatches", 999) == 0
        and season_audit.get(y, {}).get("legacy_stat_gap_count", 999) == 0
        and season_audit.get(y, {}).get("players_missing_weekly_data", 999) == 0
        for y in legacy_years
    ) and not missing_legacy_weeks
    modern_ready = scoring_audit_complete and all(
        season_audit.get(y, {}).get("modern_scoring_mismatches", 999) == 0
        and season_audit.get(y, {}).get("modern_weekly_sum_mismatches", 999) == 0
        and season_audit.get(y, {}).get("players_missing_weekly_data", 0) == 0
        for y in modern_years
    )
    coverage_seasons = coverage_audit.get("seasons") or {}
    coverage_complete = all(
        not (value.get("missing_player_ids") or [])
        and int(value.get("returned_player_ids", 0)) == int(value.get("expanded_requested_player_ids", 0))
        for value in coverage_seasons.values()
    )
    coverage_ready = (
        len(coverage_seasons) == len(YEARS)
        and not coverage_audit.get("errors")
        and not source_errors
        and coverage_complete
    )
    production_ready = legacy_ready and modern_ready and coverage_ready and not duplicate_player_seasons

    candidate = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "ESPN player-card history, legacy player gamelogs, game summaries, and matchup boxscores",
            "league_id": 112536,
            "schema_version": 2,
            "seasons": list(YEARS),
            "player_season_records": len(player_seasons),
            "weekly_records": len(weekly_rows),
            "production_ready": production_ready,
        },
        "player_seasons": player_seasons,
        "weekly": weekly_rows,
        "audit": {
            "production_ready": production_ready,
            "legacy_ready": legacy_ready,
            "modern_ready": modern_ready,
            "coverage_ready": coverage_ready,
            "season_audit": season_audit,
        },
    }

    audit = {
        "production_ready": production_ready,
        "legacy_ready": legacy_ready,
        "modern_ready": modern_ready,
        "coverage_ready": coverage_ready,
        "player_seasons": len(player_seasons),
        "weekly_rows": len(weekly_rows),
        "added_player_seasons_vs_current": len(added_keys),
        "added_player_seasons_sample": [{"season": y, "player_id": pid} for y, pid in added_keys[:100]],
        "missing_player_seasons_vs_current": len(missing_keys),
        "missing_player_seasons_sample": [{"season": y, "player_id": pid} for y, pid in missing_keys[:100]],
        "season_total_changes_vs_current": len(season_total_changes),
        "season_total_change_sample": season_total_changes[:100],
        "duplicate_player_seasons": duplicate_player_seasons,
        "missing_legacy_week_archives": missing_legacy_weeks,
        "source_errors": source_errors,
        "season_audit": season_audit,
    }

    (OUT / "player_performance_candidate.json").write_text(json.dumps(candidate, separators=(",", ":")), encoding="utf-8")
    (OUT / "player_performance_candidate_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Candidate player seasons={len(player_seasons)} weekly rows={len(weekly_rows)} production_ready={production_ready}")
    print(f"Added player seasons={len(added_keys)} missing={len(missing_keys)} total changes={len(season_total_changes)}")


if __name__ == "__main__":
    build()
