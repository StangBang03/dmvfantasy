import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory"
OUT = Path("artifacts/weekly_semantics")
# Include the known conflict season and representative seasons with playoff mapping.
CASES = [(2014, week) for week in range(13, 18)] + [
    (2011, 15), (2011, 16), (2011, 17),
    (2015, 15), (2015, 16), (2015, 17),
    (2017, 15), (2017, 16), (2017, 17),
]
TARGET_PLAYER_IDS = {-16033}

load_dotenv()
s2, swid = os.getenv("ESPN_S2"), os.getenv("ESPN_SWID")
if not s2 or not swid:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID")

session = requests.Session()
session.cookies.update({"espn_s2": s2, "SWID": swid})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    for index, (season, week) in enumerate(CASES, 1):
        params = {
            "view": "mBoxscore",
            "seasonId": season,
            "scoringPeriodId": week,
            "matchupPeriodId": week,
        }
        response = session.get(BASE_URL + f"/{LEAGUE_ID}", params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        data = payload[0] if isinstance(payload, list) and payload else payload
        schedule = data.get("schedule") or []
        targeted = []
        field_counts = {"appliedStat": 0, "appliedStatTotal": 0, "player_stats": 0}
        for matchup in schedule:
            for side in ("home", "away"):
                team = matchup.get(side) or {}
                for roster_key in ("rosterForMatchupPeriod", "rosterForCurrentScoringPeriod"):
                    roster = team.get(roster_key) or {}
                    for entry in roster.get("entries") or []:
                        pool = entry.get("playerPoolEntry") or {}
                        player = pool.get("player") or {}
                        pid = entry.get("playerId") or player.get("id") or pool.get("id")
                        if pool.get("appliedStat") is not None:
                            field_counts["appliedStat"] += 1
                        if pool.get("appliedStatTotal") is not None:
                            field_counts["appliedStatTotal"] += 1
                        stats = player.get("stats") or []
                        if stats:
                            field_counts["player_stats"] += 1
                        if pid in TARGET_PLAYER_IDS or player.get("fullName") == "Ravens D/ST":
                            targeted.append({
                                "season": season,
                                "requested_scoring_period": week,
                                "returned_matchup_period": matchup.get("matchupPeriodId"),
                                "matchup_id": matchup.get("id"),
                                "side": side,
                                "fantasy_team_id": team.get("teamId"),
                                "roster_key": roster_key,
                                "player_id": pid,
                                "player_name": player.get("fullName") or player.get("full"),
                                "lineup_slot_id": entry.get("lineupSlotId"),
                                "appliedStat": pool.get("appliedStat"),
                                "appliedStatTotal": pool.get("appliedStatTotal"),
                                "entry_appliedStat": entry.get("appliedStat"),
                                "actual_stats": [
                                    {
                                        "scoringPeriodId": s.get("scoringPeriodId"),
                                        "statSplitTypeId": s.get("statSplitTypeId"),
                                        "statSourceId": s.get("statSourceId"),
                                        "appliedTotal": s.get("appliedTotal"),
                                        "appliedAverage": s.get("appliedAverage"),
                                    }
                                    for s in stats
                                    if isinstance(s, dict) and s.get("statSourceId") == 0
                                ],
                            })
        result = {
            "season": season,
            "requested_scoring_period": week,
            "http_status": response.status_code,
            "response_bytes": len(response.content),
            "schedule_count": len(schedule),
            "returned_matchup_periods": sorted({m.get("matchupPeriodId") for m in schedule if m.get("matchupPeriodId") is not None}),
            "roster_field_counts": field_counts,
            "targeted_rows": targeted,
        }
        report.append(result)
        print(f"[{index}/{len(CASES)}] {season} week {week}: HTTP {response.status_code}; schedule={len(schedule)}; periods={result['returned_matchup_periods']}; roster fields={field_counts}; target rows={len(targeted)}")
        for row in targeted:
            print("TARGET " + json.dumps(row, separators=(",", ":")))
        time.sleep(0.25)

    path = OUT / "weekly_semantics_diagnostic.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
