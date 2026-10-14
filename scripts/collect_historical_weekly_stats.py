import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
SEASONS = range(2011, 2018)
WEEKS = range(1, 18)
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
RAW_DIR = Path("data/raw/weekly_boxscore")

load_dotenv()
ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")
if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID environment variables")

session = requests.Session()
session.cookies.update({"espn_s2": ESPN_S2, "SWID": ESPN_SWID})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})


def request_details(year, week):
    params = {
        "view": "mBoxscore",
        "scoringPeriodId": week,
        "matchupPeriodId": week,
    }
    if year >= 2018:
        url = f"{BASE_URL}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    else:
        url = f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
        params["seasonId"] = year
    return url, params


def unwrap(payload):
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    return payload if isinstance(payload, dict) else {}


def extract_player_points(payload):
    """Find playerPoolEntry-like objects with ESPN's appliedStatTotal."""
    found = {}
    for obj in walk(payload):
        player = obj.get("player")
        points = obj.get("appliedStatTotal")
        if not isinstance(player, dict) or points is None:
            continue
        player_id = player.get("id", obj.get("id"))
        if player_id is None:
            continue
        try:
            points = float(points)
        except (TypeError, ValueError):
            continue
        found[int(player_id)] = {
            "player_id": int(player_id),
            "player_name": player.get("fullName"),
            "fantasy_points": points,
            "player": player,
        }
    return found


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    failed = []
    print("Collect historical weekly fantasy points from ESPN mBoxscore")
    print("Seasons: 2011-2017 | scoring periods: 1-17")
    print("Raw responses are kept in ignored data/raw/weekly_boxscore/.")

    for year in SEASONS:
        year_dir = RAW_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        season_rows = 0
        for week in WEEKS:
            url, params = request_details(year, week)
            output_file = year_dir / f"week-{week:02d}.json"
            try:
                response = session.get(url, params=params, timeout=60)
                response.raise_for_status()
                payload = response.json()
                data = unwrap(payload)
                if not data or not data.get("teams"):
                    raise RuntimeError("Response contains no league teams")
                players = extract_player_points(payload)
                if not players:
                    raise RuntimeError("No player appliedStatTotal values found")
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                season_rows += len(players)
                total_rows += len(players)
                print(f"{year} week {week:02d}: {len(players)} players with points")
            except Exception as exc:
                failed.append({"season": year, "week": week, "error": f"{type(exc).__name__}: {exc}"})
                print(f"{year} week {week:02d}: ERROR {type(exc).__name__}: {exc}")
            time.sleep(0.25)
        print(f"{year}: {season_rows} player-week rows collected")

    print(f"TOTAL: {total_rows} player-week rows; failures={len(failed)}")
    if failed:
        print(json.dumps(failed, indent=2))
        raise SystemExit("Historical weekly collection incomplete; refusing to continue to build/deploy.")


if __name__ == "__main__":
    main()
