import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"

load_dotenv(ROOT / ".env")

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")
LEAGUE_ID = "112536"

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("ESPN_S2 and ESPN_SWID were not found in .env")

cookies = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"


def fetch(year):
    if year >= 2018:
        url = f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    else:
        url = f"{BASE}/leagueHistory/{LEAGUE_ID}"

    params = {
        "seasonId": year,
        "view": "mRoster",
    }

    r = requests.get(
        url,
        params=params,
        cookies=cookies,
        timeout=60,
    )

    print(f"{year}: HTTP {r.status_code}")

    r.raise_for_status()

    return r.json()


def unwrap(data):
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]

    if isinstance(data, dict):
        return data

    return {}


for year in (2011, 2018):

    print("=" * 70)
    print(f"TESTING SEASON {year}")
    print("=" * 70)

    data = fetch(year)
    obj = unwrap(data)

    teams = obj.get("teams", [])

    print(f"Teams: {len(teams)}")

    roster_entries = 0
    players_with_stats = 0
    players_with_names = 0
    sample = None

    for team in teams:

        roster = team.get("roster", {})

        entries = roster.get("entries", [])

        roster_entries += len(entries)

        for entry in entries:

            player_pool = entry.get(
                "playerPoolEntry",
                {}
            )

            player = player_pool.get(
                "player",
                {}
            )

            if player.get("fullName"):
                players_with_names += 1

            if player.get("stats"):
                players_with_stats += 1

            if sample is None and player:

                sample = {
                    "team_id": team.get("id"),
                    "player_id": entry.get("playerId"),
                    "lineup_slot_id": entry.get("lineupSlotId"),
                    "acquisition_type": entry.get(
                        "acquisitionType"
                    ),
                    "player": player,
                    "player_pool_entry_keys": sorted(
                        player_pool.keys()
                    ),
                    "stats_count": len(
                        player.get("stats", [])
                    ),
                    "first_stats_entry": player.get(
                        "stats",
                        [None]
                    )[0],
                }

    print(f"Roster entries: {roster_entries}")
    print(f"Players with names: {players_with_names}")
    print(f"Players with stats: {players_with_stats}")

    if sample:

        print()
        print("SAMPLE PLAYER:")
        print("-" * 70)

        print(
            json.dumps(
                sample,
                indent=2
            )[:6000]
        )

    else:

        print()
        print("No player sample found.")

    out_dir = RAW / str(year)

    out_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    out = out_dir / "mRoster_probe.json"

    with open(
        out,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2
        )

    print()
    print("Saved raw response:")
    print(out)
    print()