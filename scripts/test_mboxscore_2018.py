
    
  
import json
import os
import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
YEAR = 2018
MATCHUP_PERIOD = 10
SCORING_PERIOD = 10

BASE_URL = (
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
    f"seasons/{YEAR}/segments/0/leagues/{LEAGUE_ID}"
)

load_dotenv()

cookies = {
    "espn_s2": os.getenv("ESPN_S2"),
    "SWID": os.getenv("ESPN_SWID"),
}

params = [
    ("view", "mBoxscore"),
    ("view", "mMatchupScore"),
    ("view", "mScoreboard"),
    ("matchupPeriodId", str(MATCHUP_PERIOD)),
    ("scoringPeriodId", str(SCORING_PERIOD)),
]

headers = {
    "User-Agent": "FantasyLeagueHistory/1.0",
    "Accept": "application/json",
}

print("=" * 70)
print("ESPN mBOXSCORE TEST")
print("=" * 70)
print()
print("REQUEST:")
print(BASE_URL)
print()
print("PARAMETERS:")
print(params)
print()

r = requests.get(
    BASE_URL,
    params=params,
    cookies=cookies,
    headers=headers,
    timeout=60,
)

print("HTTP:", r.status_code)
print()
print("FINAL URL:")
print(r.url)
print()

r.raise_for_status()

data = r.json()

with open("boxscore_test_2018.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("Top-level keys:")
print(", ".join(data.keys()))
print()

print("Returned scoringPeriodId:", data.get("scoringPeriodId"))
print("Returned seasonId:", data.get("seasonId"))
print()

schedule = data.get("schedule", [])

print("Schedule rows:", len(schedule))
print()

found = False

for matchup in schedule:
    if matchup.get("matchupPeriodId") == MATCHUP_PERIOD:
        found = True

        print("=" * 70)
        print("FOUND MATCHUP PERIOD", MATCHUP_PERIOD)
        print("=" * 70)
        print("Matchup ID:", matchup.get("id"))

        for side_name in ("home", "away"):
            side = matchup.get(side_name, {})

            print()
            print(side_name.upper())
            print("-" * 30)
            print("Team:", side.get("teamId"))
            print("Keys:", ", ".join(side.keys()))

            roster = side.get("rosterForCurrentScoringPeriod")

            if roster:
                entries = roster.get("entries", [])
                print("ROSTER ENTRIES:", len(entries))

                if entries:
                    print()
                    print("FIRST ENTRY:")
                    print(json.dumps(entries[0], indent=2))
            else:
                print("NO rosterForCurrentScoringPeriod")

        break

if not found:
    print("WARNING: requested matchup period was not found.")

print()
print("=" * 70)
print("Saved: boxscore_test_2018.json")
print("=" * 70)

