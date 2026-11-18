import csv
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
SEASONS = range(2011, 2018)
SCORING_PERIODS = range(1, 18)
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUTPUT_DIR = Path("artifacts/historical_weekly_audit")

load_dotenv()
ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")
if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID environment variables")

session = requests.Session()
session.cookies.update({"espn_s2": ESPN_S2, "SWID": ESPN_SWID})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})


def unwrap(payload):
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    return payload if isinstance(payload, dict) else {}


def as_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_players(payload, season, scoring_period, requested_matchup_period):
    data = unwrap(payload)
    schedule = data.get("schedule") or []
    rows = []
    if not isinstance(schedule, list):
        schedule = []

    for matchup in schedule:
        if not isinstance(matchup, dict):
            continue
        returned_matchup_period = matchup.get("matchupPeriodId")
        for side in ("home", "away"):
            team_box = matchup.get(side) or {}
            if not isinstance(team_box, dict):
                continue
            roster = (
                team_box.get("rosterForMatchupPeriod")
                or team_box.get("rosterForCurrentScoringPeriod")
                or {}
            )
            if not isinstance(roster, dict):
                continue
            for entry in roster.get("entries") or []:
                if not isinstance(entry, dict):
                    continue
                pool = entry.get("playerPoolEntry") or {}
                if not isinstance(pool, dict):
                    continue
                player = pool.get("player") or {}
                if not isinstance(player, dict):
                    player = {}

                points_raw = pool.get("appliedStat")
                points_field = "playerPoolEntry.appliedStat"
                if points_raw is None:
                    points_raw = pool.get("appliedStatTotal")
                    points_field = "playerPoolEntry.appliedStatTotal"
                if points_raw is None:
                    points_raw = entry.get("appliedStat")
                    points_field = "entry.appliedStat"

                player_id = entry.get("playerId") or player.get("id") or pool.get("id")
                if player_id is None:
                    continue

                first_name = player.get("firstName") or player.get("firs")
                last_name = player.get("lastName") or player.get("last")
                name = (
                    player.get("fullName")
                    or player.get("full")
                    or " ".join(x for x in (first_name, last_name) if x)
                    or None
                )
                team_id = team_box.get("teamId")

                rows.append({
                    "season": int(season),
                    "scoring_period": int(scoring_period),
                    "requested_matchup_period": int(requested_matchup_period),
                    "returned_matchup_period": returned_matchup_period,
                    "matchup_id": matchup.get("id"),
                    "side": side,
                    "fantasy_team_id": int(team_id) if team_id is not None else None,
                    "player_id": int(player_id),
                    "player_name": name,
                    "position_id": player.get("defaultPositionId") or player.get("defa"),
                    "nfl_team_id": player.get("proTeamId") or player.get("proT"),
                    "lineup_slot_id": entry.get("lineupSlotId"),
                    "fantasy_points": as_number(points_raw),
                    "points_field": points_field if points_raw is not None else None,
                })

    return data, rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    period_results = []
    failures = []
    duplicate_conflicts = []
    seen = {}

    total_requests = len(list(SEASONS)) * len(list(SCORING_PERIODS))
    completed = 0
    print("Full historical ESPN mBoxscore audit")
    print("Read-only: does not alter production datasets or deploy the site.")
    print(f"League {LEAGUE_ID}; seasons 2011-2017; scoring periods 1-17 ({total_requests} requests).")
    print("Uses the proven mBoxscore matchup roster path and appliedStat points field.\n")

    for season in SEASONS:
        for scoring_period in SCORING_PERIODS:
            completed += 1
            params = {
                "view": "mBoxscore",
                "seasonId": season,
                "scoringPeriodId": scoring_period,
                "matchupPeriodId": scoring_period,
            }
            url = f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
            try:
                response = session.get(url, params=params, timeout=60)
                response.raise_for_status()
                payload = response.json()
                data, rows = extract_players(payload, season, scoring_period, scoring_period)
                schedule = data.get("schedule") or []
                teams = set()
                for row in rows:
                    if row["fantasy_team_id"] is not None:
                        teams.add(row["fantasy_team_id"])
                    key = (season, scoring_period, row["player_id"])
                    if key in seen:
                        prior = seen[key]
                        if prior["fantasy_points"] != row["fantasy_points"]:
                            duplicate_conflicts.append({
                                "key": key,
                                "first_points": prior["fantasy_points"],
                                "duplicate_points": row["fantasy_points"],
                                "first_team": prior["fantasy_team_id"],
                                "duplicate_team": row["fantasy_team_id"],
                            })
                        continue
                    seen[key] = row
                    all_rows.append(row)

                points_count = sum(r["fantasy_points"] is not None for r in rows)
                matchups = len(schedule) if isinstance(schedule, list) else 0
                returned_periods = sorted({
                    r["returned_matchup_period"] for r in rows
                    if r["returned_matchup_period"] is not None
                })
                result = {
                    "season": season,
                    "scoring_period": scoring_period,
                    "http_status": response.status_code,
                    "response_bytes": len(response.content),
                    "matchups": matchups,
                    "fantasy_teams": len(teams),
                    "raw_player_rows": len(rows),
                    "unique_player_rows": len({
                        r["player_id"] for r in rows
                    }),
                    "rows_with_points": points_count,
                    "rows_without_points": len(rows) - points_count,
                    "returned_matchup_periods": returned_periods,
                }
                period_results.append(result)
                print(
                    f"[{completed:03d}/{total_requests}] {season} week {scoring_period:02d}: "
                    f"HTTP {response.status_code}; matchups={matchups}; "
                    f"players={result['unique_player_rows']}; points={points_count}; "
                    f"returned matchup periods={returned_periods}"
                )
            except Exception as exc:
                failure = {
                    "season": season,
                    "scoring_period": scoring_period,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                failures.append(failure)
                print(f"[{completed:03d}/{total_requests}] {season} week {scoring_period:02d}: ERROR {failure['error']}")
            time.sleep(0.30)

    # Preserve one record per season/scoring-period/player, and emit auditable outputs.
    all_rows.sort(key=lambda r: (r["season"], r["scoring_period"], r["player_id"]))
    csv_path = OUTPUT_DIR / "historical_weekly_player_points.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "season", "scoring_period", "requested_matchup_period",
            "returned_matchup_period", "matchup_id", "side",
            "fantasy_team_id", "player_id", "player_name", "position_id",
            "nfl_team_id", "lineup_slot_id", "fantasy_points", "points_field",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    by_season = defaultdict(lambda: {"periods": 0, "player_rows": 0, "periods_with_points": 0})
    for result in period_results:
        bucket = by_season[result["season"]]
        bucket["periods"] += 1
        bucket["player_rows"] += result["unique_player_rows"]
        if result["rows_with_points"]:
            bucket["periods_with_points"] += 1

    report = {
        "league_id": LEAGUE_ID,
        "seasons_requested": list(SEASONS),
        "scoring_periods_requested": list(SCORING_PERIODS),
        "request_count": total_requests,
        "successful_requests": len(period_results),
        "failed_requests": failures,
        "total_unique_player_week_rows": len(all_rows),
        "rows_with_points": sum(r["fantasy_points"] is not None for r in all_rows),
        "duplicate_conflicts": duplicate_conflicts,
        "season_summary": {str(k): v for k, v in sorted(by_season.items())},
        "period_results": period_results,
        "sample_rows": all_rows[:30],
        "csv_file": str(csv_path),
    }
    report_path = OUTPUT_DIR / "historical_weekly_audit.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nAUDIT SUMMARY")
    print(f"Requests: {len(period_results)}/{total_requests} successful; failures={len(failures)}")
    print(f"Unique player-week rows: {len(all_rows)}")
    print(f"Rows with fantasy points: {report['rows_with_points']}")
    print(f"Conflicting duplicate player-week rows: {len(duplicate_conflicts)}")
    for season, summary in report["season_summary"].items():
        print(
            f"{season}: periods={summary['periods']}/17; "
            f"player-week rows={summary['player_rows']}"
        )
    print(f"Wrote {csv_path} and {report_path}")

    if failures or len(period_results) != total_requests or duplicate_conflicts:
        raise SystemExit("Audit incomplete or contains conflicting duplicate player-week rows; do not promote data.")
    if report["rows_with_points"] != len(all_rows):
        raise SystemExit("Some player-week rows lack points; do not promote data.")
    print("PASS: every requested season/scoring period returned player rows with points and no conflicting duplicates.")


if __name__ == "__main__":
    main()
