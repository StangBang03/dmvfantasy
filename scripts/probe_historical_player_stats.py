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
    if year >= 2018:
        url = f"{BASE_URL}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
        params = {"view": view, "scoringPeriodId": week}
    else:
        url = f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
        params = {"seasonId": year, "view": view, "scoringPeriodId": week}
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
    roster_entries = 0
    player_objects = []
    stat_objects = []
    weekly_stat_rows = 0
    matching_week_rows = 0
    sample = None

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

    for team in teams:
        roster = team.get("roster") or {}
        roster_entries += len(roster.get("entries") or [])

    player_sample = None
    for player in player_objects:
        if player.get("stats") or player.get("points") is not None:
            player_sample = {
                "name": player.get("fullName") or player.get("playerName"),
                "keys": list(player.keys())[:35],
                "stats_type": type(player.get("stats")).__name__,
                "stats_sample": str(player.get("stats"))[:450],
                "points": player.get("points"),
            }
            break

    return len(teams), roster_entries, len(player_objects), weekly_stat_rows, matching_week_rows, sample, player_sample, len(stat_objects)


def main():
    print("ESPN historical player-stat endpoint probe")
    print("Read-only requests; no repository data is changed.")
    print("Tests roster, matchup and boxscore views for 2011-2017.")
    print("Includes a small sample of boxscore player-object structure.\n")

    for year in SEASONS:
        for week in WEEKS_TO_TEST:
            for view in VIEWS_TO_TEST:
                try:
                    url, params = request_details(year, week, view)
                    response = session.get(url, params=params, timeout=45)
                    print(f"{year} week {week} view {view}: HTTP {response.status_code}, {len(response.content):,} bytes")
                    response.raise_for_status()
                    result = inspect_payload(response.json(), week)
                    teams, roster_entries, player_count, weekly_rows, matching_rows, sample, player_sample, stat_count = result
                    print(
                        f"  teams={teams}, roster_entries={roster_entries}, "
                        f"player_objects={player_count}, stat_objects={stat_count}, "
                        f"weekly_stat_rows={weekly_rows}, requested_week_rows={matching_rows}"
                    )
                    if sample:
                        print(f"  weekly_sample={sample}")
                    if view == "mBoxscore" and week == 1:
                        print(f"  boxscore_player_sample={player_sample}")
                except Exception as exc:
                    print(f"{year} week {week} view {view}: ERROR {type(exc).__name__}: {exc}")
                time.sleep(0.2)
        print()

    print("Use player-object samples to identify the actual scoring fields exposed by old boxscore responses.")


if __name__ == "__main__":
    main()
