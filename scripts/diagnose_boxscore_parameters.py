import json
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

REPORT = Path("data/analytics/boxscore_reconciliation.json")

# Test the first few known failures from the reconciliation report.
MAX_TESTS = 5

load_dotenv()

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("ESPN_S2 / ESPN_SWID missing from .env")

cookies = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}

headers = {
    "User-Agent": "FantasyLeagueHistory/1.0",
    "Accept": "application/json",
}


def unwrap(data):
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


def league_url(year):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    return f"{BASE}/leagueHistory/{LEAGUE_ID}?seasonId={year}"


def find_matchup(data, matchup_id):
    for matchup in data.get("schedule", []):
        if str(matchup.get("id")) == str(matchup_id):
            return matchup
    return None


def summarize_side(side):
    roster = side.get("rosterForMatchupPeriod") or {}
    entries = roster.get("entries") or []

    total = 0.0
    for entry in entries:
        pool = entry.get("playerPoolEntry") or {}
        points = pool.get("appliedStatTotal")
        if points is not None:
            total += float(points)

    return len(entries), total


def main():
    if not REPORT.exists():
        raise FileNotFoundError(f"Missing {REPORT}")

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    failures = report.get("failures", [])

    if not failures:
        print("No failures found in reconciliation report.")
        return

    tests = failures[:MAX_TESTS]

    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(headers)

    print("=" * 70)
    print("ESPN BOXSCORE PARAMETER DIAGNOSTIC")
    print("=" * 70)
    print()
    print("Testing known failures with matchupPeriodId explicitly supplied.")
    print()

    results = []

    for i, failure in enumerate(tests, 1):
        year = int(failure["season"])
        scoring_period = int(failure["scoring_period"])
        matchup_period = int(failure["matchup_period"])
        matchup_id = failure["matchup_id"]
        team_id = failure["team_id"]

        print("=" * 70)
        print(
            f"TEST {i}: {year} SP{scoring_period} "
            f"matchupPeriod={matchup_period} "
            f"matchup={matchup_id} team={team_id}"
        )
        print("=" * 70)

        params = [
            ("view", "mBoxscore"),
            ("view", "mMatchupScore"),
            ("matchupPeriodId", str(matchup_period)),
            ("scoringPeriodId", str(scoring_period)),
        ]

        response = session.get(
            league_url(year),
            params=params,
            timeout=60,
        )

        print("HTTP:", response.status_code)
        print("URL:")
        print(response.url)
        print()

        response.raise_for_status()

        data = unwrap(response.json())

        print("Returned scoringPeriodId:", data.get("scoringPeriodId"))
        print("Schedule rows:", len(data.get("schedule", [])))

        matchup = find_matchup(data, matchup_id)

        if not matchup:
            print("ERROR: matchup ID not found in response")
            results.append({
                "year": year,
                "scoring_period": scoring_period,
                "matchup_period": matchup_period,
                "matchup_id": matchup_id,
                "team_id": team_id,
                "status": "MATCHUP_NOT_FOUND",
            })
            print()
            continue

        print("Matchup found:", matchup.get("id"))
        print()

        for side_name in ("home", "away"):
            side = matchup.get(side_name) or {}
            if side.get("teamId") != team_id:
                continue

            entries, player_sum = summarize_side(side)
            points = (
                side.get("pointsByScoringPeriod") or {}
            ).get(str(scoring_period))

            print(side_name.upper())
            print("  team:", side.get("teamId"))
            print("  roster entries:", entries)
            print("  player applied total:", round(player_sum, 4))
            print("  ESPN team score:", points)
            if points is not None:
                print("  difference:", round(player_sum - float(points), 4))

            roster = side.get("rosterForMatchupPeriod")
            current = side.get("rosterForCurrentScoringPeriod")

            print("  matchup roster:", "YES" if roster else "NO")
            print("  current roster:", "YES" if current else "NO")

            results.append({
                "year": year,
                "scoring_period": scoring_period,
                "matchup_period": matchup_period,
                "matchup_id": matchup_id,
                "team_id": team_id,
                "entries": entries,
                "player_sum": round(player_sum, 4),
                "espn_score": points,
                "difference": (
                    round(player_sum - float(points), 4)
                    if points is not None else None
                ),
            })

        print()

    output = Path("data/analytics/boxscore_parameter_diagnostic.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )

    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)
    print(f"Wrote: {output}")


if __name__ == "__main__":
    main()
