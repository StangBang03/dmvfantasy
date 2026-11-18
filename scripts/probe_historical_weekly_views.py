import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT = Path("artifacts/weekly_views")
CASES = [
    {"season": 2014, "scoring_period": 14},
    {"season": 2014, "scoring_period": 15},
    {"season": 2014, "scoring_period": 16},
    {"season": 2014, "scoring_period": 17},
    {"season": 2017, "scoring_period": 16},
    {"season": 2018, "scoring_period": 17},
    {"season": 2025, "scoring_period": 10},
]
COMBOS = [
    ("mBoxscore", "scoring_only", None),
    ("mBoxscore", "matchup_14", 14),
    ("mBoxscore", "matchup_15", 15),
    ("mBoxscore", "matchup_16", 16),
    ("mBoxscore", "matchup_17", 17),
    ("mRoster", "scoring_only", None),
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


def summarize_player(player, pool, entry):
    stats = player.get("stats") or []
    return {
        "player_id": entry.get("playerId") or player.get("id"),
        "player_name": player.get("fullName") or player.get("full"),
        "slot": entry.get("lineupSlotId"),
        "appliedStat": pool.get("appliedStat"),
        "appliedStatTotal": pool.get("appliedStatTotal"),
        "stats": [
            {
                "scoringPeriodId": x.get("scoringPeriodId"),
                "statSplitTypeId": x.get("statSplitTypeId"),
                "statSourceId": x.get("statSourceId"),
                "appliedTotal": x.get("appliedTotal"),
                "appliedAverage": x.get("appliedAverage"),
            }
            for x in stats if isinstance(x, dict)
        ],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for case in CASES:
        year, sp = case["season"], case["scoring_period"]
        for view, label, mp in COMBOS:
            params = [("view", view), ("scoringPeriodId", str(sp))]
            if year < 2018:
                params.append(("seasonId", str(year)))
            if mp is not None:
                params.append(("matchupPeriodId", str(mp)))
            response = session.get(league_url(year), params=params, timeout=60)
            response.raise_for_status()
            data = unwrap(response.json())
            rows = []
            if view == "mRoster":
                teams = data.get("teams") or []
                for team in teams:
                    roster = team.get("roster") or {}
                    for entry in roster.get("entries") or []:
                        pool = entry.get("playerPoolEntry") or {}
                        player = pool.get("player") or {}
                        rows.append({"team_id": team.get("id"), **summarize_player(player, pool, entry)})
            else:
                for matchup in data.get("schedule") or []:
                    for side_name in ("home", "away"):
                        side = matchup.get(side_name) or {}
                        roster = side.get("rosterForMatchupPeriod") or side.get("rosterForCurrentScoringPeriod") or {}
                        for entry in roster.get("entries") or []:
                            pool = entry.get("playerPoolEntry") or {}
                            player = pool.get("player") or {}
                            rows.append({
                                "team_id": side.get("teamId"),
                                "matchup_id": matchup.get("id"),
                                "returned_matchup_period": matchup.get("matchupPeriodId"),
                                "side": side_name,
                                **summarize_player(player, pool, entry),
                            })
            result = {
                "season": year, "requested_scoring_period": sp,
                "view": view, "label": label, "requested_matchup_period": mp,
                "http_status": response.status_code,
                "response_bytes": len(response.content),
                "top_keys": list(data.keys()),
                "returned_scoring_period": data.get("scoringPeriodId"),
                "teams": len(data.get("teams") or []),
                "rows": len(rows),
                "rows_with_appliedStat": sum(r["appliedStat"] is not None for r in rows),
                "rows_with_appliedStatTotal": sum(r["appliedStatTotal"] is not None for r in rows),
                "rows_with_weekly_actual_stats": sum(any(s.get("statSplitTypeId") == 1 and s.get("scoringPeriodId") == sp and s.get("statSourceId") == 0 for s in r["stats"]) for r in rows),
                "sample_rows": rows[:3],
            }
            results.append(result)
            print(
                f"{year} SP{sp} {view}/{label}: HTTP {response.status_code}; "
                f"rows={len(rows)} appliedStat={result['rows_with_appliedStat']} "
                f"appliedStatTotal={result['rows_with_appliedStatTotal']} "
                f"weekly_actual={result['rows_with_weekly_actual_stats']} "
                f"returnedSP={result['returned_scoring_period']}"
            )
            time.sleep(0.15)
    path = OUT / "weekly_views_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
