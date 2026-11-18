import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
START_YEAR = 2011
END_YEAR = 2025

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
RAW_MATCHUP_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/raw/boxscore_v2")
OUTPUT_FILE = Path("data/processed/boxscore_lineups.json")

load_dotenv()

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("ESPN_S2 / ESPN_SWID missing from .env")

COOKIES = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}

HEADERS = {
    "User-Agent": "FantasyLeagueHistory/1.0",
    "Accept": "application/json",
}


def unwrap(data):
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def league_url(year):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    return f"{BASE}/leagueHistory/{LEAGUE_ID}?seasonId={year}"


def get_existing_scoring_periods(year):
    """
    Derive scoring periods from the already-collected mMatchupScore archive.
    This avoids hard-coding playoff lengths or making an unnecessary settings call.
    """
    path = RAW_MATCHUP_DIR / str(year) / "mMatchupScore.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}")

    data = unwrap(load_json(path))
    periods = set()

    for matchup in data.get("schedule", []):
        for side_name in ("home", "away"):
            side = matchup.get(side_name) or {}
            for period in (side.get("pointsByScoringPeriod") or {}).keys():
                try:
                    periods.add(int(period))
                except (TypeError, ValueError):
                    pass

    return sorted(periods)


def get_matchup_period_for_scoring_period(data, scoring_period):
    """
    Build the scoring-period -> matchup-period mapping from the returned schedule.
    Multiple matchups can share the same matchup period in playoff weeks.
    """
    pairs = set()

    for matchup in data.get("schedule", []):
        matchup_period = matchup.get("matchupPeriodId")
        if matchup_period is None:
            continue

        for side_name in ("home", "away"):
            side = matchup.get(side_name) or {}
            points = side.get("pointsByScoringPeriod") or {}

            if str(scoring_period) in points:
                pairs.add(int(matchup_period))
                break

    return sorted(pairs)


def extract_lineup_entries(side, season, scoring_period, matchup_period):
    """
    Historical-safe source:
      rosterForMatchupPeriod.entries[]

    For 2011-2017 this is the roster data ESPN exposes.
    For 2018+ it is the actual matchup lineup (typically starters).
    """
    roster = side.get("rosterForMatchupPeriod") or {}
    entries = roster.get("entries") or []

    output = []

    for entry in entries:
        pool = entry.get("playerPoolEntry") or {}
        player = pool.get("player") or {}

        output.append({
            "season": season,
            "scoring_period": scoring_period,
            "matchup_period": matchup_period,
            "team_id": side.get("teamId"),
            "player_id": entry.get("playerId"),
            "player_name": player.get("fullName"),
            "lineup_slot_id": entry.get("lineupSlotId"),
            "applied_points": pool.get("appliedStatTotal"),
            "status": entry.get("status"),
            "injury_status": entry.get("injuryStatus"),
            "player_pro_team_id": player.get("proTeamId"),
            "default_position_id": player.get("defaultPositionId"),
        })

    return output


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.cookies.update(COOKIES)
    session.headers.update(HEADERS)

    all_rows = []
    audit = []

    print("=" * 70)
    print("ESPN HISTORICAL BOXSCORE / LINEUP COLLECTOR V2")
    print("=" * 70)

    for year in range(START_YEAR, END_YEAR + 1):
        periods = get_existing_scoring_periods(year)

        year_rows = 0
        year_requests = 0
        year_failures = 0
        year_matchups = 0

        print()
        print(f"{year}: scoring periods {periods}")

        for scoring_period in periods:
            # We use the league-level response and select the requested
            # scoring period's matchup rows from it.
            params = [
                ("view", "mBoxscore"),
                ("view", "mMatchupScore"),
                ("scoringPeriodId", str(scoring_period)),
            ]

            url = league_url(year)

            for attempt in range(3):
                try:
                    response = session.get(
                        url,
                        params=params,
                        timeout=60,
                    )
                    year_requests += 1

                    if response.status_code == 200:
                        break

                    if attempt == 2:
                        raise RuntimeError(
                            f"HTTP {response.status_code}: {response.text[:300]}"
                        )

                    time.sleep(1.5 * (attempt + 1))

                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(1.5 * (attempt + 1))

            data = unwrap(response.json())

            returned_period = data.get("scoringPeriodId")
            if returned_period is not None and int(returned_period) != scoring_period:
                raise RuntimeError(
                    f"{year} scoring period mismatch: "
                    f"requested={scoring_period}, returned={returned_period}"
                )

            for matchup in data.get("schedule", []):
                matchup_period = matchup.get("matchupPeriodId")
                if matchup_period is None:
                    continue

                sides = []
                for side_name in ("home", "away"):
                    side = matchup.get(side_name) or {}

                    points = side.get("pointsByScoringPeriod") or {}
                    if str(scoring_period) not in points:
                        continue

                    # Only collect completed/meaningful matchup roster data.
                    entries = side.get("rosterForMatchupPeriod", {}).get("entries", [])

                    row_entries = extract_lineup_entries(
                        side,
                        year,
                        scoring_period,
                        matchup_period,
                    )

                    if row_entries:
                        year_rows += len(row_entries)

                    sides.append({
                        "side": side_name,
                        "team_id": side.get("teamId"),
                        "matchup_period": matchup_period,
                        "scoring_period": scoring_period,
                        "total_points": side.get("totalPoints"),
                        "points_for_scoring_period": points.get(str(scoring_period)),
                        "lineup_entries": row_entries,
                    })

                if sides:
                    year_matchups += 1

                    out_path = (
                        OUTPUT_DIR
                        / str(year)
                        / f"scoring_period_{scoring_period}"
                        / f"matchup_{matchup.get('id')}.json"
                    )
                    out_path.parent.mkdir(parents=True, exist_ok=True)

                    payload = {
                        "season": year,
                        "scoring_period": scoring_period,
                        "matchup_period": matchup_period,
                        "matchup_id": matchup.get("id"),
                        "sides": sides,
                    }

                    with out_path.open("w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2)

            print(
                f"  scoring {scoring_period}: "
                f"{len(data.get('schedule', []))} schedule rows"
            )

        audit.append({
            "season": year,
            "scoring_periods": periods,
            "requests": year_requests,
            "failures": year_failures,
            "matchups_with_data": year_matchups,
            "lineup_rows": year_rows,
        })

        print(
            f"  TOTAL: requests={year_requests} "
            f"matchups={year_matchups} lineup_rows={year_rows}"
        )

    # Build one convenient processed file for analytics.
    for year in range(START_YEAR, END_YEAR + 1):
        year_dir = OUTPUT_DIR / str(year)
        if not year_dir.exists():
            continue

        for path in year_dir.rglob("matchup_*.json"):
            payload = load_json(path)
            for side in payload.get("sides", []):
                for entry in side.get("lineup_entries", []):
                    all_rows.append(entry)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "league_id": LEAGUE_ID,
                "historical_seasons": list(range(START_YEAR, END_YEAR + 1)),
                "lineups": all_rows,
                "audit": audit,
            },
            f,
            indent=2,
        )

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print(f"Lineup rows: {len(all_rows):,}")
    print(f"Wrote raw lineup data: {OUTPUT_DIR}")
    print(f"Wrote processed data: {OUTPUT_FILE}")

    # Basic sanity checks.
    errors = []

    if not all_rows:
        errors.append("No lineup rows collected.")

    for row in all_rows:
        if row["player_id"] is None:
            errors.append(
                f"Missing player_id: "
                f"{row['season']} SP{row['scoring_period']} "
                f"team={row['team_id']}"
            )
            break

        if row["team_id"] is None:
            errors.append(
                f"Missing team_id: "
                f"{row['season']} SP{row['scoring_period']}"
            )
            break

    if errors:
        print("SANITY CHECK: FAIL")
        for error in errors:
            print("  " + error)
    else:
        print("SANITY CHECK: PASS")
        print("  all lineup rows have team_id and player_id")
        print("  historical rosterForMatchupPeriod source is populated")


if __name__ == "__main__":
    main()
