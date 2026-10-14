import os
import time

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
SEASONS = [2017, 2016, 2015, 2014, 2013, 2012, 2011]
WEEKS_TO_TEST = [1, 8, 17]
VIEWS_TO_TEST = ["mRoster", "mBoxscore", "mMatchupScore"]
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

load_dotenv()
ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID environment variables")

session = requests.Session()
session.cookies.update({"espn_s2": ESPN_S2, "SWID": ESPN_SWID})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})


def request_details(year, week, view):
    # ESPN's mBoxscore view needs both period parameters. For football,
    # matchup periods and scoring periods are usually the same week.
    params = {
        "view": view,
        "scoringPeriodId": week,
        "matchupPeriodId": week,
    }
    if year >= 2018:
        url = f"{BASE_URL}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    else:
        url = f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
        params["seasonId"] = year
    return url, params


def unwrap(payload):
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    return payload if isinstance(payload, dict) else {}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def inspect_payload(payload, requested_week):
    data = unwrap(payload)
    teams = data.get("teams", []) if isinstance(data, dict) else []
    schedule = data.get("schedule", []) if isinstance(data, dict) else []
    roster_entries = 0
    player_objects = []
    stat_objects = []
    weekly_stat_rows = 0
    matching_week_rows = 0
    applied_total_objects = []
    boxscore_entries = []
    sample = None

    for team in teams:
        roster = team.get("roster") or {}
        roster_entries += len(roster.get("entries") or [])

    # mBoxscore stores weekly player scoring under schedule[].home/away
    # .rosterForCurrentScoringPeriod.entries[].playerPoolEntry.
    for matchup in schedule:
        if not isinstance(matchup, dict):
            continue
        for side in ("home", "away"):
            team_box = matchup.get(side) or {}
            current_roster = team_box.get("rosterForCurrentScoringPeriod") or {}
            for entry in current_roster.get("entries") or []:
                pool = entry.get("playerPoolEntry") or {}
                player = pool.get("player") or {}
                points = pool.get("appliedStatTotal")
                if player or points is not None:
                    boxscore_entries.append({
                        "name": player.get("fullName"),
                        "playerId": entry.get("playerId") or player.get("id"),
                        "appliedStatTotal": points,
                        "stats": pool.get("stats"),
                        "lineupSlotId": entry.get("lineupSlotId"),
                    })

    for obj in walk(payload):
        if isinstance(obj.get("fullName"), str) or isinstance(obj.get("playerName"), str):
            player_objects.append(obj)
        stats = obj.get("stats")
        if isinstance(stats, list):
            for stat in stats:
                if not isinstance(stat, dict):
                    continue
                stat_objects.append(stat)
                if stat.get("statSourceId") == 0 and stat.get("statSplitTypeId") == 1:
                    weekly_stat_rows += 1
                    if int(stat.get("scoringPeriodId", -1)) == requested_week:
                        matching_week_rows += 1
                        if sample is None:
                            sample = {
                                "scoringPeriodId": stat.get("scoringPeriodId"),
                                "appliedTotal": stat.get("appliedTotal"),
                                "statKeys": len(stat.get("stats") or {}),
                            }
        if "appliedStatTotal" in obj:
            applied_total_objects.append(obj.get("appliedStatTotal"))

    return {
        "teams": len(teams),
        "roster_entries": roster_entries,
        "player_objects": len(player_objects),
        "stat_objects": len(stat_objects),
        "weekly_stat_rows": weekly_stat_rows,
        "requested_week_rows": matching_week_rows,
        "weekly_sample": sample,
        "boxscore_entries": len(boxscore_entries),
        "boxscore_points_count": sum(x["appliedStatTotal"] is not None for x in boxscore_entries),
        "boxscore_points_sum": round(sum(x["appliedStatTotal"] for x in boxscore_entries if isinstance(x["appliedStatTotal"], (int, float))), 2),
        "boxscore_player_samples": boxscore_entries[:4],
        "applied_total_objects": len(applied_total_objects),
        "applied_total_sample": applied_total_objects[:10],
    }


def main():
    print("ESPN historical player-stat endpoint probe")
    print("Read-only requests; no repository data is changed.")
    print("Tests roster, matchup and boxscore views for 2011-2017.")
    print("Uses BOTH scoringPeriodId and matchupPeriodId; inspects matchup boxscore entries.\n")

    for year in SEASONS:
        for week in WEEKS_TO_TEST:
            for view in VIEWS_TO_TEST:
                try:
                    url, params = request_details(year, week, view)
                    response = session.get(url, params=params, timeout=45)
                    print(f"{year} week {week} view {view}: HTTP {response.status_code}, {len(response.content):,} bytes")
                    response.raise_for_status()
                    result = inspect_payload(response.json(), week)
                    print(
                        f"  teams={result['teams']}, roster_entries={result['roster_entries']}, "
                        f"player_objects={result['player_objects']}, stat_objects={result['stat_objects']}, "
                        f"weekly_stat_rows={result['weekly_stat_rows']}, requested_week_rows={result['requested_week_rows']}, "
                        f"boxscore_entries={result['boxscore_entries']}, "
                        f"boxscore_points_count={result['boxscore_points_count']}, "
                        f"boxscore_points_sum={result['boxscore_points_sum']}, "
                        f"applied_total_objects={result['applied_total_objects']}"
                    )
                    if result["weekly_sample"]:
                        print(f"  weekly_sample={result['weekly_sample']}")
                    if view == "mBoxscore" and week in (1, 8):
                        print(f"  boxscore_player_samples={result['boxscore_player_samples']}")
                        print(f"  applied_total_sample={result['applied_total_sample']}")
                except Exception as exc:
                    print(f"{year} week {week} view {view}: ERROR {type(exc).__name__}: {exc}")
                time.sleep(0.2)
        print()

    print("If boxscore_entries and applied points are populated, the endpoint exposes weekly scoring for extraction.")


if __name__ == "__main__":
    main()
