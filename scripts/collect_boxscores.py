import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
START_YEAR = 2011
END_YEAR = 2025

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
MATCHUP_RAW_DIR = Path("data/raw")
BOX_RAW_DIR = Path("data/raw/boxscore")

load_dotenv()

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID in .env")

COOKIES = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def unwrap(data):
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]
    if isinstance(data, dict):
        return data
    return {}


def season_url(year):
    if year < 2018:
        return f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
    return f"{BASE_URL}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"


def find_matchup_periods(year):
    """
    Read the already-collected mMatchupScore response and extract the actual
    matchupPeriodId values ESPN returned.

    This intentionally does not depend on our normalized schema.
    """
    path = MATCHUP_RAW_DIR / str(year) / "mMatchupScore.json"

    if not path.exists():
        raise FileNotFoundError(f"Missing raw matchup file: {path}")

    data = unwrap(load_json(path))
    schedule = data.get("schedule", [])

    if not isinstance(schedule, list):
        raise ValueError(f"{path} has no usable schedule list")

    periods = set()

    for matchup in schedule:
        period = matchup.get("matchupPeriodId")

        if period is None:
            continue

        # Only retain actual numeric matchup periods.
        try:
            periods.add(int(period))
        except (TypeError, ValueError):
            continue

    return sorted(periods)


def fetch_boxscore(session, year, matchup_period):
    url = season_url(year)

    # In fantasy football, a matchup period normally corresponds to one
    # scoring period. We explicitly pass both IDs rather than relying on
    # ESPN defaults.
    params = [
        ("view", "mBoxscore"),
        ("matchupPeriodId", str(matchup_period)),
        ("scoringPeriodId", str(matchup_period)),
    ]

    if year < 2018:
        params.append(("seasonId", str(year)))

    response = session.get(
        url,
        params=params,
        cookies=COOKIES,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def count_boxscore_teams(data):
    obj = unwrap(data)
    schedule = obj.get("schedule", [])

    teams = 0
    entries = 0

    for matchup in schedule:
        for side in ("home", "away"):
            team = matchup.get(side)
            if not isinstance(team, dict):
                continue

            if team.get("teamId") is not None:
                teams += 1

            roster = team.get("rosterForCurrentScoringPeriod", {})
            if isinstance(roster, dict):
                roster_entries = roster.get("entries", [])
                if isinstance(roster_entries, list):
                    entries += len(roster_entries)

    return teams, entries


def main():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "FantasyLeagueHistory/1.0"
    })

    BOX_RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("COLLECT ESPN mBOXSCORE DATA")
    print("=" * 70)
    print(f"League: {LEAGUE_ID}")
    print(f"Historical seasons: {START_YEAR}-{END_YEAR}")
    print()

    total_requests = 0
    successful = 0
    failed = 0
    total_teams = 0
    total_entries = 0

    for year in range(START_YEAR, END_YEAR + 1):
        periods = find_matchup_periods(year)

        season_dir = BOX_RAW_DIR / str(year)
        season_dir.mkdir(parents=True, exist_ok=True)

        print(f"Processing {year}: {len(periods)} matchup periods")

        season_success = 0
        season_failed = 0
        season_teams = 0
        season_entries = 0

        for period in periods:
            total_requests += 1

            output_file = (
                season_dir
                / f"matchup_{period}_scoring_{period}.json"
            )

            try:
                data = fetch_boxscore(session, year, period)

                # Preserve the exact ESPN response plus request metadata.
                payload = {
                    "season": year,
                    "matchup_period": period,
                    "scoring_period": period,
                    "response": unwrap(data),
                }

                with output_file.open("w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)

                teams, entries = count_boxscore_teams(data)

                successful += 1
                season_success += 1
                season_teams += teams
                season_entries += entries
                total_teams += teams
                total_entries += entries

                print(
                    f"  Period {period:2d}: "
                    f"HTTP 200 | teams={teams:2d} | entries={entries:3d}"
                )

            except Exception as exc:
                failed += 1
                season_failed += 1
                print(f"  Period {period:2d}: FAILED — {exc}")

            time.sleep(0.08)

        print(
            f"  Season total: success={season_success}, "
            f"failed={season_failed}, "
            f"team snapshots={season_teams}, "
            f"roster entries={season_entries}"
        )
        print()

    print("=" * 70)
    print("COLLECTION COMPLETE")
    print("=" * 70)
    print(f"Requests attempted: {total_requests}")
    print(f"Successful:         {successful}")
    print(f"Failed:             {failed}")
    print(f"Team snapshots:     {total_teams}")
    print(f"Roster entries:     {total_entries}")
    print(f"Raw output:         {BOX_RAW_DIR}")

    if failed:
        print()
        print("WARNING: Some boxscore requests failed.")
        print("Review the failed periods before building downstream analytics.")
    else:
        print()
        print("PASS: all historical matchup periods collected.")


if __name__ == "__main__":
    main()
