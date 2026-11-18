import json
import os
import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
TESTS = [
    (2011, 10, 10),
    (2017, 10, 10),
    (2018, 10, 10),
    (2025, 10, 10),
]

load_dotenv()

cookies = {
    "espn_s2": os.getenv("ESPN_S2"),
    "SWID": os.getenv("ESPN_SWID"),
}

headers = {
    "User-Agent": "FantasyLeagueHistory/1.0",
    "Accept": "application/json",
}

for year, matchup_period, scoring_period in TESTS:
    if year >= 2018:
        url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    else:
        url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory/{LEAGUE_ID}?seasonId={year}"

    params = [
        ("view", "mBoxscore"),
        ("view", "mMatchupScore"),
        ("view", "mScoreboard"),
        ("matchupPeriodId", str(matchup_period)),
        ("scoringPeriodId", str(scoring_period)),
    ]

    r = requests.get(url, params=params, cookies=cookies, headers=headers, timeout=60)
    print(f"\n{year}: HTTP {r.status_code}")

    if r.status_code != 200:
        print(r.text[:500])
        continue

    data = r.json()
    if isinstance(data, list):
        data = data[0] if data and isinstance(data[0], dict) else {}

    schedule = data.get("schedule", [])
    found = next(
        (m for m in schedule if m.get("matchupPeriodId") == matchup_period),
        None,
    )

    print("  scoringPeriodId:", data.get("scoringPeriodId"))
    print("  schedule rows:", len(schedule))
    print("  matchup found:", bool(found))

    if found:
        for side_name in ("home", "away"):
            side = found.get(side_name, {})
            roster = side.get("rosterForCurrentScoringPeriod")
            matchup_roster = side.get("rosterForMatchupPeriod")
            entries = roster.get("entries", []) if isinstance(roster, dict) else []
            matchup_entries = matchup_roster.get("entries", []) if isinstance(matchup_roster, dict) else []
            print(
                f"  {side_name}: team={side.get('teamId')} "
                f"current_entries={len(entries)} matchup_entries={len(matchup_entries)} "
                f"current_roster={'YES' if roster else 'NO'} "
                f"matchup_roster={'YES' if matchup_roster else 'NO'}"
            )
            if entries:
                e = entries[0]
                ppe = e.get("playerPoolEntry", {})
                print(
                    f"    first player={e.get('playerId')} "
                    f"slot={e.get('lineupSlotId')} "
                    f"applied={ppe.get('appliedStatTotal')}"
                )

print("\nDONE")
