import csv
import gzip
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
ROOT = Path("data/processed")
OUT = Path("artifacts/player_card_history")
BATCH_SIZE = 50
SEASON_TYPES = 18
CURRENT_SEASON = 2026

session = requests.Session()
session.cookies.update({
    "espn_s2": os.getenv("ESPN_S2", ""),
    "SWID": os.getenv("ESPN_SWID", ""),
})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
if not session.cookies.get("espn_s2") or not session.cookies.get("SWID"):
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID")


def load_json(name, default):
    path = ROOT / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def unwrap(payload):
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict):
        return payload[0]
    return payload if isinstance(payload, dict) else {}


def endpoint(year, view):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}", [("view", view)]
    return f"{BASE}/leagueHistory/{LEAGUE_ID}", [("view", view), ("seasonId", str(year))]


def get_status_window(year):
    url, params = endpoint(year, "mStatus")
    response = session.get(url, params=params, timeout=90)
    response.raise_for_status()
    status = unwrap(response.json()).get("status") or {}
    current = status.get("currentMatchupPeriod")
    latest = status.get("latestScoringPeriod")
    active = bool(status.get("isActive"))
    if active and current is not None:
        max_week = max(0, int(current) - 1)
    elif status.get("finalScoringPeriod") is not None:
        max_week = int(status["finalScoringPeriod"])
    elif latest is not None:
        max_week = int(latest)
    else:
        max_week = 18
    return {
        "current_matchup_period": current,
        "latest_scoring_period": latest,
        "final_scoring_period": status.get("finalScoringPeriod"),
        "is_active": active,
        "max_completed_week": max_week,
    }


def get_scoring_periods(year):
    url, params = endpoint(year, "mMatchupScore")
    response = session.get(url, params=params, timeout=90)
    response.raise_for_status()
    data = unwrap(response.json())
    periods = set()
    for matchup in data.get("schedule") or []:
        for side in ("home", "away"):
            team = matchup.get(side) or {}
            for key in (team.get("pointsByScoringPeriod") or {}):
                try:
                    periods.add(int(key))
                except (TypeError, ValueError):
                    pass
    return sorted(periods)


def get_roster_snapshot(year, scoring_period):
    url, base_params = endpoint(year, "mRoster")
    params = base_params + [("scoringPeriodId", str(scoring_period))]
    response = session.get(url, params=params, timeout=90)
    response.raise_for_status()
    data = unwrap(response.json())
    rows = []
    for team in data.get("teams") or []:
        team_id = team.get("id")
        roster = team.get("roster") or {}
        for entry in roster.get("entries") or []:
            pool = entry.get("playerPoolEntry") or {}
            player = pool.get("player") or {}
            pid = player.get("id") or entry.get("playerId")
            if pid is None:
                continue
            rows.append({
                "season": year,
                "scoring_period": scoring_period,
                "player_id": int(pid),
                "player_name": player.get("fullName") or player.get("full") or player.get("last"),
                "team_id": team_id,
                "pro_team_id": player.get("proTeamId"),
                "position_id": player.get("defaultPositionId"),
                "lineup_slot_id": entry.get("lineupSlotId"),
                "acquisition_type": entry.get("acquisitionType"),
                "acquisition_date": entry.get("acquisitionDate"),
            })
    return rows



def get_boxscore_roster_snapshot(year, scoring_period):
    """Return historical matchup lineup entries and distinguish weekly from multiweek totals."""
    url, base_params = endpoint(year, "mBoxscore")
    params = base_params + [
        ("scoringPeriodId", str(scoring_period)),
        ("matchupPeriodId", str(scoring_period)),
    ]
    response = session.get(url, params=params, timeout=90)
    response.raise_for_status()
    data = unwrap(response.json())
    rows = []
    matchup_count = 0
    single_week_periods = set()
    multiweek_periods = set()
    for matchup in data.get("schedule") or []:
        matchup_period = matchup.get("matchupPeriodId")
        for side in ("home", "away"):
            team = matchup.get(side) or {}
            entries = (team.get("rosterForMatchupPeriod") or {}).get("entries") or []
            if not entries:
                continue
            matchup_count += 1
            period_keys = sorted(
                int(key) for key in (team.get("pointsByScoringPeriod") or {}).keys()
                if str(key).isdigit()
            )
            is_single_week = len(period_keys) == 1
            if is_single_week:
                single_week_periods.add(period_keys[0])
            elif period_keys:
                multiweek_periods.add(int(matchup_period) if matchup_period is not None else -1)
            for entry in entries:
                pool = entry.get("playerPoolEntry") or {}
                player = pool.get("player") or {}
                pid = player.get("id") or entry.get("playerId")
                if pid is None:
                    continue
                rows.append({
                    "season": year,
                    "requested_scoring_period": scoring_period,
                    "scoring_period": period_keys[0] if is_single_week else None,
                    "matchup_period": matchup_period,
                    "matchup_scoring_periods": period_keys,
                    "points_type": "single_scoring_period" if is_single_week else "multi_scoring_period_matchup_total" if period_keys else "unknown",
                    "player_id": int(pid),
                    "player_name": player.get("fullName") or player.get("full") or player.get("last"),
                    "team_id": team.get("teamId"),
                    "pro_team_id": player.get("proTeamId"),
                    "position_id": player.get("defaultPositionId"),
                    "lineup_slot_id": entry.get("lineupSlotId"),
                    "matchup_points": pool.get("appliedStatTotal"),
                })
    return rows, {
        "matchup_team_rows": matchup_count,
        "single_week_scoring_periods": sorted(single_week_periods),
        "multiweek_matchup_periods": sorted(multiweek_periods),
    }

def parse_entry(item, year, max_week=None):
    player = item.get("player") or item
    stats = player.get("stats") or item.get("stats") or []
    season_total = None
    season_stats = {}
    weekly = []
    for stat in stats:
        if not isinstance(stat, dict) or stat.get("statSourceId") != 0:
            continue
        if stat.get("seasonId") is not None and int(stat.get("seasonId")) != year:
            continue
        split = stat.get("statSplitTypeId")
        scoring_period = stat.get("scoringPeriodId")
        stat_values = stat.get("stats") or stat.get("appliedStats") or {}
        if split == 0 and scoring_period == 0:
            season_total = stat.get("appliedTotal")
            season_stats = stat_values
        elif split == 1 and scoring_period is not None:
            scoring_period = int(scoring_period)
            if max_week is not None and scoring_period > max_week:
                continue
            weekly.append({
                "scoring_period": scoring_period,
                "points": stat.get("appliedTotal"),
                "stats": stat_values,
                "stat_id": stat.get("id"),
                "season_id": stat.get("seasonId"),
            })
    return {
        "season": year,
        "player_id": player.get("id") or item.get("id"),
        "player_name": player.get("fullName") or player.get("full"),
        "position": player.get("defaultPositionId") or player.get("position"),
        "pro_team_id": player.get("proTeamId"),
        "on_team_id": item.get("onTeamId"),
        "season_total": season_total,
        "season_stats": season_stats,
        "weekly": weekly,
    }


def add_ids(ids_by_year, sources_by_year, year, rows, source, id_key="player_id"):
    for row in rows or []:
        try:
            pid = int(row[id_key])
            y = int(row.get("season", year))
        except (KeyError, TypeError, ValueError):
            continue
        ids_by_year[y].add(pid)
        sources_by_year[y][pid].add(source)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    performance = load_json("player_performance.json", {})
    pp_rows = performance.get("player_seasons") or []
    ownership = load_json("ownership_ledger.json", [])
    transactions = load_json("transaction_events.json", [])
    drafts = load_json("draft_picks.json", [])
    supplemental = load_json("supplemental_trade_events.json", [])

    ids_by_year = defaultdict(set)
    sources_by_year = defaultdict(lambda: defaultdict(set))
    source_records = {}
    for record in pp_rows:
        year = int(record.get("season"))
        pid = int(record.get("player_id"))
        ids_by_year[year].add(pid)
        sources_by_year[year][pid].add("player_performance")
        source_records[(year, pid)] = record
    add_ids(ids_by_year, sources_by_year, None, ownership, "ownership_ledger")
    add_ids(ids_by_year, sources_by_year, None, transactions, "transaction_events")
    add_ids(ids_by_year, sources_by_year, None, drafts, "draft_picks")
    add_ids(ids_by_year, sources_by_year, None, supplemental, "supplemental_trade_events")

    roster_rows = []
    boxscore_rows = []
    roster_audit = {}
    for year in sorted(set(ids_by_year)):
        if year < 2018:
            # Legacy mRoster is a season-end snapshot; its period parameter
            # does not produce distinct historical roster states.
            periods = [1]
            max_week = None
            window = None
        else:
            window = get_status_window(year)
            periods = get_scoring_periods(year)
            max_week = window["max_completed_week"]
            periods = [p for p in periods if p <= max_week]
        snapshot_counts = {}
        boxscore_counts = {}
        boxscore_matchup_rows = 0
        boxscore_single_week_periods = set()
        boxscore_multiweek_periods = set()
        boxscore_periods = range(1, 18) if year < 2018 else []
        for period in periods:
            try:
                rows = get_roster_snapshot(year, period)
                roster_rows.extend(rows)
                snapshot_counts[str(period)] = len(rows)
                for row in rows:
                    pid = row["player_id"]
                    ids_by_year[year].add(pid)
                    sources_by_year[year][pid].add("mRoster_snapshot")
            except Exception as exc:
                roster_audit.setdefault(str(year), {}).setdefault("errors", []).append({
                    "scoring_period": period,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            time.sleep(0.1)
        for period in boxscore_periods:
            try:
                rows, detail = get_boxscore_roster_snapshot(year, period)
                boxscore_rows.extend(rows)
                boxscore_counts[str(period)] = len(rows)
                boxscore_matchup_rows += detail["matchup_team_rows"]
                boxscore_single_week_periods.update(detail["single_week_scoring_periods"])
                boxscore_multiweek_periods.update(detail["multiweek_matchup_periods"])
                for row in rows:
                    pid = row["player_id"]
                    ids_by_year[year].add(pid)
                    sources_by_year[year][pid].add("mBoxscore_weekly_roster")
            except Exception as exc:
                roster_audit.setdefault(str(year), {}).setdefault("boxscore_errors", []).append({
                    "scoring_period": period,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            time.sleep(0.1)

        roster_audit[str(year)] = {
            **roster_audit.get(str(year), {}),
            "periods_queried": periods,
            "snapshot_entry_counts": snapshot_counts,
            "snapshot_unique_players": len({r["player_id"] for r in roster_rows if r["season"] == year}),
            "boxscore_periods_queried": list(boxscore_periods),
            "boxscore_entry_counts": boxscore_counts,
            "boxscore_matchup_team_rows": boxscore_matchup_rows,
            "boxscore_unique_players": len({r["player_id"] for r in boxscore_rows if r["season"] == year}),
            "boxscore_single_week_periods": sorted(boxscore_single_week_periods),
            "boxscore_multiweek_matchup_periods": sorted(boxscore_multiweek_periods),
            "season_window": window,
        }
        print(
            f"{year}: mRoster periods={len(periods)}; "
            f"snapshot unique={roster_audit[str(year)]['snapshot_unique_players']}; "
            f"expanded IDs={len(ids_by_year[year])}"
        )

    season_totals = []
    weekly_rows = []
    audit = {
        "existing_player_performance_records": len(pp_rows),
        "source_record_counts": {
            "ownership_ledger": len(ownership),
            "transaction_events": len(transactions),
            "draft_picks": len(drafts),
            "supplemental_trade_events": len(supplemental),
        },
        "batch_size": BATCH_SIZE,
        "roster_snapshots": roster_audit,
        "seasons": {},
        "errors": [],
    }

    for year in sorted(ids_by_year):
        window = get_status_window(year) if year == CURRENT_SEASON else None
        max_week = window["max_completed_week"] if window else None
        ids = sorted(ids_by_year[year])
        url, base_params = endpoint(year, "kona_playercard")
        base_params.append(("scoringPeriodId", "0"))
        returned = {}
        requested_batches = 0
        for offset in range(0, len(ids), BATCH_SIZE):
            batch = ids[offset:offset + BATCH_SIZE]
            requested_batches += 1
            filters = {
                "players": {
                    "filterIds": {"value": batch},
                    "filterStatsForTopScoringPeriodIds": {
                        "value": SEASON_TYPES,
                        "additionalValue": [f"00{year}"],
                    },
                }
            }
            session.headers["X-Fantasy-Filter"] = json.dumps(filters, separators=(",", ":"))
            try:
                response = session.get(url, params=base_params, timeout=90)
                response.raise_for_status()
                for item in (unwrap(response.json()).get("players") or []):
                    parsed = parse_entry(item, year, max_week=max_week)
                    if parsed["player_id"] is not None:
                        returned[int(parsed["player_id"])] = parsed
            except Exception as exc:
                audit["errors"].append({
                    "season": year,
                    "batch_start": offset,
                    "batch_count": len(batch),
                    "error": f"{type(exc).__name__}: {exc}",
                })
            time.sleep(0.12)

        missing = sorted(set(ids) - set(returned))
        weekly_by_period = Counter()
        season_missing = []
        season_mismatches = []
        weekly_mismatches = []
        season_sum_mismatches = []
        for pid, parsed in returned.items():
            source_record = source_records.get((year, pid), {})
            source_names = sorted(sources_by_year[year].get(pid, set()))
            season_totals.append({
                "season": year,
                "player_id": pid,
                "player_name": parsed["player_name"] or source_record.get("name"),
                "pro_team_id": parsed["pro_team_id"],
                "on_team_id": parsed["on_team_id"],
                "sources": "|".join(source_names),
                "season_total": parsed["season_total"],
                "season_stats_json": json.dumps(parsed["season_stats"], separators=(",", ":")),
            })
            if parsed["season_total"] is None:
                season_missing.append(pid)
            else:
                existing = source_record.get("season_fantasy_points")
                if existing is not None and abs(float(existing) - float(parsed["season_total"])) > 0.01:
                    season_mismatches.append({
                        "player_id": pid,
                        "existing": existing,
                        "playercard": parsed["season_total"],
                    })
            weekly_sum = 0.0
            has_weekly = False
            for week in parsed["weekly"]:
                has_weekly = True
                weekly_sum += float(week["points"] or 0)
                weekly_by_period[week["scoring_period"]] += 1
                weekly_rows.append({
                    "season": year,
                    "scoring_period": week["scoring_period"],
                    "player_id": pid,
                    "player_name": parsed["player_name"] or source_record.get("name"),
                    "pro_team_id": parsed["pro_team_id"],
                    "sources": "|".join(source_names),
                    "points": week["points"],
                    "stat_id": week["stat_id"],
                    "season_id": week["season_id"],
                    "stats_json": json.dumps(week["stats"], separators=(",", ":")),
                })
                existing_weeks = source_record.get("weeks") or {}
                existing_week = existing_weeks.get(str(week["scoring_period"])) or existing_weeks.get(week["scoring_period"])
                if existing_week:
                    existing_points = existing_week.get("points")
                    if existing_points is not None and week["points"] is not None and abs(float(existing_points) - float(week["points"])) > 0.01:
                        weekly_mismatches.append({
                            "player_id": pid,
                            "week": week["scoring_period"],
                            "existing": existing_points,
                            "playercard": week["points"],
                        })
            if has_weekly and parsed["season_total"] is not None and abs(weekly_sum - float(parsed["season_total"])) > 0.02:
                season_sum_mismatches.append({
                    "player_id": pid,
                    "season_total": parsed["season_total"],
                    "weekly_sum": round(weekly_sum, 4),
                    "difference": round(float(parsed["season_total"]) - weekly_sum, 4),
                })

        archive_players = []
        for pid, parsed in sorted(returned.items()):
            source_record = source_records.get((year, pid), {})
            archive_players.append({
                "player_id": pid,
                "player_name": parsed["player_name"] or source_record.get("name"),
                "position_id": parsed["position"],
                "pro_team_id": parsed["pro_team_id"],
                "sources": sorted(sources_by_year[year].get(pid, set())),
                "season_total": parsed["season_total"],
                "season_stats": parsed["season_stats"],
                "weeks": {
                    str(week["scoring_period"]): {
                        "scoring_period": week["scoring_period"],
                        "fantasy_points": week["points"],
                        "stats": week["stats"],
                        "stat_id": week["stat_id"],
                        "season_id": week["season_id"],
                    }
                    for week in parsed["weekly"]
                },
            })
        archive = {
            "meta": {
                "league_id": LEAGUE_ID,
                "season": year,
                "source": "ESPN kona_playercard actual stats",
                "max_completed_week": max_week,
                "player_count": len(archive_players),
            },
            "players": archive_players,
            "roster_history": [row for row in roster_rows if int(row["season"]) == year],
            "boxscore_weekly_points": [row for row in boxscore_rows if int(row["season"]) == year],
        }
        raw_archive_dir = Path("data/raw/playercard_history")
        raw_archive_dir.mkdir(parents=True, exist_ok=True)
        with gzip.open(raw_archive_dir / f"playercard_{year}.json.gz", "wt", encoding="utf-8") as archive_file:
            json.dump(archive, archive_file, ensure_ascii=False, separators=(",", ":"))

        audit["seasons"][str(year)] = {
            "existing_player_performance_ids": len({int(r["player_id"]) for r in pp_rows if int(r["season"]) == year}),
            "expanded_requested_player_ids": len(ids),
            "id_source_counts": {
                source: sum(1 for pid in ids if source in sources_by_year[year].get(pid, set()))
                for source in ("player_performance", "ownership_ledger", "transaction_events", "draft_picks", "supplemental_trade_events", "mRoster_snapshot", "mBoxscore_weekly_roster")
            },
            "requested_batches": requested_batches,
            "returned_player_ids": len(returned),
            "missing_player_ids": missing,
            "max_completed_week": max_week,
            "season_window": window,
            "weekly_rows": sum(weekly_by_period.values()),
            "weeks_present": sorted(weekly_by_period),
            "weekly_rows_by_period": dict(sorted(weekly_by_period.items())),
            "players_missing_season_total": season_missing,
            "season_total_mismatch_count": len(season_mismatches),
            "season_total_mismatch_sample": season_mismatches[:20],
            "weekly_mismatch_count": len(weekly_mismatches),
            "weekly_mismatch_sample": weekly_mismatches[:20],
            "season_sum_mismatch_count": len(season_sum_mismatches),
            "season_sum_mismatch_sample": season_sum_mismatches[:20],
        }
        print(
            f"{year}: requested={len(ids)} returned={len(returned)} missing={len(missing)}; "
            f"weekly rows={sum(weekly_by_period.values())}; weeks={sorted(weekly_by_period)}; "
            f"season mismatches={len(season_mismatches)}; weekly mismatches={len(weekly_mismatches)}; "
            f"season-vs-weekly-sum mismatches={len(season_sum_mismatches)}"
        )

    with (OUT / "player_card_season_totals.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(season_totals[0]) if season_totals else [])
        if season_totals:
            writer.writeheader()
            writer.writerows(season_totals)
    with (OUT / "player_card_weekly_points.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(weekly_rows[0]) if weekly_rows else [])
        if weekly_rows:
            writer.writeheader()
            writer.writerows(weekly_rows)
    with (OUT / "roster_snapshot_rows.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(roster_rows[0]) if roster_rows else [])
        if roster_rows:
            writer.writeheader()
            writer.writerows(roster_rows)
    (OUT / "player_card_history_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Wrote {len(season_totals)} season totals, {len(weekly_rows)} weekly rows, {len(roster_rows)} roster snapshots")


if __name__ == "__main__":
    main()
