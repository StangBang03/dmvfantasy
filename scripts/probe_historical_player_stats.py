import os
import time

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
SEASONS = [2017, 2016, 2015, 2014, 2013, 2012, 2011]
WEEKS_TO_TEST = [1, 8, 17]
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

load_dotenv()
ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID environment variables")

session = requests.Session()
session.cookies.update({"espn_s2": ESPN_S2, "SWID": ESPN_SWID})
session.headers.update({
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
})


def season_request(year, week):
    if year >= 2018:
        url = f"{BASE_URL}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
        params = {"view": "mRoster", "scoringPeriodId": week}
    else:
        url = f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
        params = {
            "seasonId": year,
            "view": "mRoster",
            "scoringPeriodId": week,
        }
    return url, params


def unwrap(payload):
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    return payload if isinstance(payload, dict) else {}


def main():
    print("Historical ESPN weekly-player-data probe")
    print("Read-only requests; no repository data is changed.\n")

    for year in SEASONS:
        for week in WEEKS_TO_TEST:
            try:
                url, params = season_request(year, week)
                response = session.get(url, params=params, timeout=45)
                print(f"{year} week {week}: HTTP {response.status_code}, {len(response.content):,} bytes")
                response.raise_for_status()
                data = unwrap(response.json())
                teams = data.get("teams", [])
                players = 0
                weekly_rows = 0
                matching_week_rows = 0
                sample = None

                for team in teams:
                    roster = team.get("roster") or {}
                    for entry in roster.get("entries", []) or []:
                        player = ((entry.get("playerPoolEntry") or {}).get("player") or {})
                        if player:
                            players += 1
                        for stat in player.get("stats", []) or []:
                            if stat.get("statSourceId") != 0 or stat.get("statSplitTypeId") != 1:
                                continue
                            weekly_rows += 1
                            if int(stat.get("scoringPeriodId", -1)) == week:
                                matching_week_rows += 1
                                if sample is None:
                                    sample = {
                                        "player": player.get("fullName"),
                                        "scoringPeriodId": stat.get("scoringPeriodId"),
                                        "appliedTotal": stat.get("appliedTotal"),
                                        "statKeys": len(stat.get("stats") or {}),
                                    }

                print(
                    f"  teams={len(teams)}, roster entries={players}, "
                    f"weekly stat rows={weekly_rows}, rows for requested week={matching_week_rows}"
                )
                if sample:
                    print(f"  sample={sample}")
            except Exception as exc:
                print(f"{year} week {week}: ERROR {type(exc).__name__}: {exc}")

            time.sleep(0.35)
        print()

    print("Compare requested-week row counts. Nonzero counts for older seasons mean")
    print("we can test collecting each scoring period instead of only the default roster response.")


if __name__ == "__main__":
    main()
