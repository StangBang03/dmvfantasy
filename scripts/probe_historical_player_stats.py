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
    player_names = 0
    weekly_stat_rows = 0
    matching_week_rows = 0
    sample = None

    for obj in walk(payload):
        if isinstance(obj.get("fullName"), str) or isinstance(obj.get("playerName"), str):
            player_names += 1
        stats = obj.get("stats")
        if not isinstance(stats, list):
            continue
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            if stat.get("statSourceId") != 0 or stat.get("statSplitTypeId") != 1:
                continue
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

    return len(teams), roster_entries, player_names, weekly_stat_rows, matching_week_rows, sample


def main():
    print("ESPN historical player-stat endpoint probe")
    print("Read-only requests; no repository data is changed.")
    print("Tests roster and matchup/boxscore views for 2011-2017.\n")

    for year in SEASONS:
        for week in WEEKS_TO_TEST:
            for view in VIEWS_TO_TEST:
                try:
                    url, params = request_details(year, week, view)
                    response = session.get(url, params=params, timeout=45)
                    print(f"{year} week {week} view {view}: HTTP {response.status_code}, {len(response.content):,} bytes")
                    response.raise_for_status()
                    result = inspect_payload(response.json(), week)
                    teams, roster_entries, player_names, weekly_rows, matching_rows, sample = result
                    print(
                        f"  teams={teams}, roster_entries={roster_entries}, "
                        f"player_name_objects={player_names}, weekly_stat_rows={weekly_rows}, "
                        f"requested_week_rows={matching_rows}"
                    )
                    if sample:
                        print(f"  sample={sample}")
                except Exception as exc:
                    print(f"{year} week {week} view {view}: ERROR {type(exc).__name__}: {exc}")
                time.sleep(0.2)
        print()

    print("Compare views for any nonzero weekly_stat_rows or requested_week_rows.")
    print("If all are zero, next step is to test a boxscore endpoint independent of leagueHistory.")


if __name__ == "__main__":
    main()
