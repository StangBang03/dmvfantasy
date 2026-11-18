import json
import os
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT = Path("artifacts/weekly_views")
# Probe the offset behavior (query SP = target SP + 1) on modern seasons,
# and the old leagueHistory route where weekly splits appear unavailable.
CASES = [
    (2014, 14), (2014, 15), (2014, 16), (2014, 17),
    (2017, 15), (2017, 16),
    (2018, 16), (2018, 17),
    (2021, 17), (2021, 18),
    (2025, 9), (2025, 10), (2025, 17), (2025, 18),
]
load_dotenv()
s2, swid = os.getenv("ESPN_S2"), os.getenv("ESPN_SWID")
if not s2 or not swid:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID")
session = requests.Session()
session.cookies.update({"espn_s2": s2, "SWID": swid})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})


def league_url(year):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    return f"{BASE}/leagueHistory/{LEAGUE_ID}"


def unwrap(value):
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], dict) else {}
    return value if isinstance(value, dict) else {}


def stat_summary(player, requested_period):
    stats = player.get("stats") or []
    actual = Counter()
    projected = Counter()
    samples = []
    for item in stats:
        if not isinstance(item, dict) or item.get("statSplitTypeId") != 1:
            continue
        source = item.get("statSourceId")
        period = item.get("scoringPeriodId")
        if source == 0:
            actual[period] += 1
            if period in (requested_period - 1, requested_period):
                samples.append({
                    "scoringPeriodId": period,
                    "statSourceId": source,
                    "appliedTotal": item.get("appliedTotal"),
                })
        elif source == 1:
            projected[period] += 1
    return actual, projected, samples


def roster_rows(roster, team_id, key, matchup=None, side=None):
    rows = []
    if not isinstance(roster, dict):
        return rows
    for entry in roster.get("entries") or []:
        pool = entry.get("playerPoolEntry") or {}
        player = pool.get("player") or {}
        actual, projected, stat_samples = stat_summary(player, 0)
        rows.append({
            "team_id": team_id,
            "roster_key": key,
            "matchup_id": matchup,
            "side": side,
            "player_id": entry.get("playerId") or player.get("id"),
            "player_name": player.get("fullName") or player.get("full"),
            "lineup_slot_id": entry.get("lineupSlotId"),
            "appliedStat": pool.get("appliedStat"),
            "appliedStatTotal": pool.get("appliedStatTotal"),
            "actual_week_stat_periods": sorted(int(x) for x in actual if x is not None),
            "projected_week_stat_periods": sorted(int(x) for x in projected if x is not None),
            "stat_samples": stat_samples,
        })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for index, (year, target_week) in enumerate(CASES, 1):
        query_period = target_week + 1
        params = [("view", "mRoster"), ("scoringPeriodId", str(query_period))]
        if year < 2018:
            params.append(("seasonId", str(year)))
        response = session.get(league_url(year), params=params, timeout=60)
        response.raise_for_status()
        data = unwrap(response.json())
        mroster_rows = []
        for team in data.get("teams") or []:
            mroster_rows.extend(roster_rows(team.get("roster"), team.get("id"), "mRoster"))
        actual_period_counts = Counter()
        for row in mroster_rows:
            for period in row["actual_week_stat_periods"]:
                actual_period_counts[period] += 1

        box_params = [("view", "mBoxscore"), ("view", "mMatchupScore"), ("scoringPeriodId", str(target_week))]
        if year < 2018:
            box_params.append(("seasonId", str(year)))
        box_response = session.get(league_url(year), params=box_params, timeout=60)
        box_response.raise_for_status()
        box_data = unwrap(box_response.json())
        box_rows = []
        roster_key_counts = Counter()
        for matchup in box_data.get("schedule") or []:
            for side_name in ("home", "away"):
                side = matchup.get(side_name) or {}
                for key in ("rosterForCurrentScoringPeriod", "rosterForMatchupPeriod"):
                    rows = roster_rows(side.get(key), side.get("teamId"), key, matchup.get("id"), side_name)
                    roster_key_counts[key] += len(rows)
                    box_rows.extend(rows)

        result = {
            "season": year,
            "target_week": target_week,
            "mRoster_query_scoring_period": query_period,
            "mRoster_http": response.status_code,
            "mRoster_rows": len(mroster_rows),
            "mRoster_actual_week_stat_counts": dict(sorted(actual_period_counts.items(), key=lambda x: int(x[0]))),
            "mRoster_sample": mroster_rows[:3],
            "mBoxscore_http": box_response.status_code,
            "mBoxscore_requested_scoring_period": target_week,
            "mBoxscore_roster_key_counts": dict(roster_key_counts),
            "mBoxscore_sample": box_rows[:3],
        }
        results.append(result)
        print(
            f"[{index}/{len(CASES)}] {year} target week {target_week}: "
            f"mRoster query SP{query_period}, rows={len(mroster_rows)}, "
            f"actual stats={dict(actual_period_counts)}; "
            f"mBoxscore roster keys={dict(roster_key_counts)}"
        )
        time.sleep(0.2)

    path = OUT / "weekly_views_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
