import csv
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
INPUT = Path("data/processed/player_performance.json")
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


def endpoint(year):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}", [("view", "kona_playercard"), ("scoringPeriodId", "0")]
    return f"{BASE}/leagueHistory/{LEAGUE_ID}", [("view", "kona_playercard"), ("seasonId", str(year)), ("scoringPeriodId", "0")]


def unwrap(payload):
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict) and "players" in payload[0]:
        return payload[0]
    return payload if isinstance(payload, dict) else {}


def player_rows(payload):
    return unwrap(payload).get("players") or []


def get_season_window(year):
    if year != CURRENT_SEASON:
        return None
    url = f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    response = session.get(url, params=[("view", "mStatus")], timeout=90)
    response.raise_for_status()
    payload = response.json()
    data = unwrap(payload)
    status = data.get("status") or {}
    current = status.get("currentMatchupPeriod")
    latest = status.get("latestScoringPeriod")
    active = bool(status.get("isActive"))
    if active and current is not None:
        max_week = max(0, int(current) - 1)
    elif latest is not None:
        max_week = int(latest)
    else:
        max_week = int(status.get("finalScoringPeriod") or 18)
    return {
        "current_matchup_period": current,
        "latest_scoring_period": latest,
        "final_scoring_period": status.get("finalScoringPeriod"),
        "is_active": active,
        "max_completed_week": max_week,
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
        # Player-card responses can contain the prior season's weekly splits too.
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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    records = source.get("player_seasons") or []
    ids_by_year = defaultdict(set)
    source_records = {}
    for record in records:
        year = int(record.get("season"))
        pid = int(record.get("player_id"))
        ids_by_year[year].add(pid)
        source_records[(year, pid)] = record

    season_totals = []
    weekly_rows = []
    audit = {
        "source_player_seasons": len(records),
        "batch_size": BATCH_SIZE,
        "seasons": {},
        "errors": [],
    }

    for year in sorted(ids_by_year):
        window = get_season_window(year)
        max_week = window["max_completed_week"] if window else None
        ids = sorted(ids_by_year[year])
        url, base_params = endpoint(year)
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
                payload = response.json()
                for item in player_rows(payload):
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
            season_totals.append({
                "season": year,
                "player_id": pid,
                "player_name": parsed["player_name"] or source_record.get("name"),
                "pro_team_id": parsed["pro_team_id"],
                "on_team_id": parsed["on_team_id"],
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

        audit["seasons"][str(year)] = {
            "source_player_ids": len(ids),
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
    (OUT / "player_card_history_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Wrote {len(season_totals)} season totals and {len(weekly_rows)} weekly rows")


if __name__ == "__main__":
    main()
