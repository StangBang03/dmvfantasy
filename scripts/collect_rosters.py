import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

LEAGUE_ID = 112536
START_YEAR = 2011
END_YEAR = 2026

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

RAW_DIR = Path("data/raw/roster")
RAW_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv()

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError(
        "Missing ESPN_S2 or ESPN_SWID in .env"
    )

cookies = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}

headers = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def get_url(year):
    if year >= 2018:
        return (
            f"{BASE_URL}/seasons/{year}/segments/0/"
            f"leagues/{LEAGUE_ID}"
        )

    return (
        f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
        f"?seasonId={year}"
    )


def unwrap(data):
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]

    if isinstance(data, dict):
        return data

    return {}


def main():
    print("=" * 70)
    print("COLLECT ESPN mRoster DATA")
    print("=" * 70)
    print(f"League:       {LEAGUE_ID}")
    print(f"Seasons:      {START_YEAR}-{END_YEAR}")
    print()

    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(headers)

    successes = 0
    failures = 0

    for year in range(START_YEAR, END_YEAR + 1):
        print(f"Processing {year}...")

        url = get_url(year)

        try:
            response = session.get(
                url,
                params={"view": "mRoster"},
                timeout=60,
            )

            print(
                f"  HTTP {response.status_code}"
                f"  {len(response.content):,} bytes"
            )

            response.raise_for_status()

            raw = response.json()
            data = unwrap(raw)

            if not data:
                raise RuntimeError(
                    "Response did not contain a usable league object"
                )

            teams = data.get("teams", [])

            if not teams:
                raise RuntimeError(
                    "mRoster response contains no teams"
                )

            output_dir = RAW_DIR / str(year)
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / "mRoster.json"

            with output_file.open(
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    raw,
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            roster_entries = 0

            for team in teams:
                roster = (
                    team.get("roster", {})
                    if isinstance(team, dict)
                    else {}
                )

                entries = roster.get("entries", [])

                if isinstance(entries, list):
                    roster_entries += len(entries)

            print(
                f"  Teams:        {len(teams)}"
            )
            print(
                f"  Roster rows:  {roster_entries}"
            )
            print(
                f"  Wrote:        {output_file}"
            )

            successes += 1

        except Exception as exc:
            failures += 1
            print(
                f"  ERROR: {type(exc).__name__}: {exc}"
            )

        print()

        # Be polite to ESPN.
        time.sleep(0.5)

    print("=" * 70)
    print("COLLECTION COMPLETE")
    print("=" * 70)
    print(f"Successful: {successes}")
    print(f"Failed:     {failures}")

    if failures:
        print()
        print(
            "Some seasons failed. Do not build analytics yet; "
            "paste the failed-season output."
        )
    else:
        print()
        print(
            "All seasons collected successfully."
        )


if __name__ == "__main__":
    main()
