import json
import os
import time

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# Small, read-only validation set. Matchup period and scoring period are
# separate inputs because they are not guaranteed to map 1:1 in playoffs.
TEST_CASES = [
    (2011, 1, 1),
    (2011, 2, 2),
    (2012, 1, 1),
    (2017, 1, 1),
]

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


def unwrap(payload):
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    return payload if isinstance(payload, dict) else {}


def as_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_boxscore_players(payload, season, scoring_period, requested_matchup_period):
    """Extract player rows from mBoxscore schedule home/away rosters.

    The supplied Power BI export shows:
      schedule[].home|away.rosterForMatchupPeriod.entries[]
        .playerPoolEntry.appliedStat and .player

    ESPN abbreviates some player properties in this view (for example,
    'full' instead of 'fullName'), so both forms are supported.
    """
    data = unwrap(payload)
    schedule = data.get("schedule") or []
    rows = []
    matchup_count = 0
    teams_seen = set()

    if not isinstance(schedule, list):
        schedule = []

    for matchup in schedule:
        if not isinstance(matchup, dict):
            continue

        matchup_count += 1
        matchup_period = matchup.get("matchupPeriodId", requested_matchup_period)

        for side in ("home", "away"):
            team_box = matchup.get(side) or {}
            if not isinstance(team_box, dict):
                continue

            team_id = team_box.get("teamId")
            if team_id is not None:
                teams_seen.add(int(team_id))

            roster = (
                team_box.get("rosterForMatchupPeriod")
                or team_box.get("rosterForCurrentScoringPeriod")
                or {}
            )
            if not isinstance(roster, dict):
                continue

            entries = roster.get("entries") or []
            if not isinstance(entries, list):
                continue

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                pool = entry.get("playerPoolEntry") or {}
                if not isinstance(pool, dict):
                    continue

                player = pool.get("player") or {}
                if not isinstance(player, dict):
                    player = {}

                points_raw = pool.get("appliedStat")
                if points_raw is None:
                    points_raw = pool.get("appliedStatTotal")
                if points_raw is None:
                    points_raw = entry.get("appliedStat")

                player_id = (
                    entry.get("playerId")
                    or player.get("id")
                    or pool.get("id")
                )
                if player_id is None:
                    continue

                first_name = player.get("firstName") or player.get("firs")
                last_name = player.get("lastName") or player.get("last")
                player_name = (
                    player.get("fullName")
                    or player.get("full")
                    or " ".join(x for x in (first_name, last_name) if x)
                    or None
                )

                rows.append({
                    "season": int(season),
                    "scoring_period": int(scoring_period),
                    "matchup_period": int(matchup_period),
                    "matchup_id": matchup.get("id"),
                    "side": side,
                    "fantasy_team_id": int(team_id) if team_id is not None else None,
                    "player_id": int(player_id),
                    "player_name": player_name,
                    "position_id": player.get("defaultPositionId") or player.get("defa"),
                    "nfl_team_id": player.get("proTeamId") or player.get("proT"),
                    "lineup_slot_id": entry.get("lineupSlotId"),
                    "fantasy_points": as_number(points_raw),
                    "points_field": (
                        "appliedStat" if pool.get("appliedStat") is not None
                        else "appliedStatTotal" if pool.get("appliedStatTotal") is not None
                        else "entry.appliedStat" if entry.get("appliedStat") is not None
                        else None
                    ),
                })

    return {
        "league_keys": sorted(data.keys()),
        "schedule_matchups": matchup_count,
        "teams_in_schedule": sorted(teams_seen),
        "players": rows,
    }


def main():
    print("ESPN historical mBoxscore validation")
    print("Read-only: no production datasets or website files are changed.")
    print("Parser follows rosterForMatchupPeriod -> entries -> playerPoolEntry.")
    print("Player points are read from playerPoolEntry.appliedStat.\n")

    total_rows = 0
    failures = []

    for season, scoring_period, matchup_period in TEST_CASES:
        params = {
            "view": "mBoxscore",
            "seasonId": season,
            "scoringPeriodId": scoring_period,
            "matchupPeriodId": matchup_period,
        }
        url = f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"

        try:
            response = session.get(url, params=params, timeout=60)
            print(
                f"{season} scoring period {scoring_period} / "
                f"matchup period {matchup_period}: "
                f"HTTP {response.status_code}, {len(response.content):,} bytes"
            )
            response.raise_for_status()

            result = extract_boxscore_players(
                response.json(), season, scoring_period, matchup_period
            )
            rows = result["players"]
            total_rows += len(rows)

            unique_players = len({r["player_id"] for r in rows})
            points_count = sum(r["fantasy_points"] is not None for r in rows)
            print(
                f"  matchups={result['schedule_matchups']}, "
                f"teams={len(result['teams_in_schedule'])}, "
                f"player_rows={len(rows)}, unique_players={unique_players}, "
                f"rows_with_points={points_count}"
            )

            for row in rows[:12]:
                print(
                    "  PLAYER "
                    f"team={row['fantasy_team_id']} "
                    f"side={row['side']} "
                    f"id={row['player_id']} "
                    f"name={row['player_name']!r} "
                    f"points={row['fantasy_points']}"
                )

            if not rows:
                print(f"  top-level keys={result['league_keys']}")
                print("  WARNING: response had no player rows at the expected path.")
            elif points_count == 0:
                print("  WARNING: player rows found, but no applied fantasy points.")

        except Exception as exc:
            failures.append({
                "season": season,
                "scoring_period": scoring_period,
                "matchup_period": matchup_period,
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"  ERROR: {type(exc).__name__}: {exc}")

        time.sleep(0.35)

    print("\nSUMMARY")
    print(f"Player rows extracted: {total_rows}")
    print(f"Failed requests: {len(failures)}")
    if failures:
        print(json.dumps(failures, indent=2))
        raise SystemExit("Historical mBoxscore validation had failed requests.")


if __name__ == "__main__":
    main()
