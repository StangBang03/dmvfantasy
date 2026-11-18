import json
import os
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT = Path("artifacts/player_stats_endpoint")
CASES = [(2014, 16), (2017, 16), (2018, 17), (2025, 10)]
FILTER = {
    "players": {
        "limit": 30,
        "sortPercOwned": {"sortPriority": 4, "sortAsc": False},
    }
}
load_dotenv()
s2, swid = os.getenv("ESPN_S2"), os.getenv("ESPN_SWID")
if not s2 or not swid:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID")
session = requests.Session()
session.cookies.update({"espn_s2": s2, "SWID": swid})
session.headers.update({
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "X-Fantasy-Filter": json.dumps(FILTER, separators=(",", ":")),
})


def unwrap(value):
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], dict) else {}
    return value if isinstance(value, dict) else {}


def inspect_players(payload):
    data = unwrap(payload)
    players = data.get("players") or []
    out = []
    periods = Counter()
    for item in players[:30]:
        if not isinstance(item, dict):
            continue
        player = item.get("player") or item
        stats = player.get("stats") or item.get("stats") or []
        weekly = []
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            if stat.get("statSplitTypeId") == 1 and stat.get("statSourceId") == 0:
                periods[stat.get("scoringPeriodId")] += 1
                weekly.append({
                    "scoringPeriodId": stat.get("scoringPeriodId"),
                    "appliedTotal": stat.get("appliedTotal"),
                    "statSourceId": stat.get("statSourceId"),
                    "statSplitTypeId": stat.get("statSplitTypeId"),
                })
        out.append({
            "pool_entry_id": item.get("id"),
            "on_team_id": item.get("onTeamId"),
            "player_id": player.get("id"),
            "name": player.get("fullName"),
            "appliedStatTotal": item.get("appliedStatTotal"),
            "stats_count": len(stats),
            "weekly_actual": weekly,
            "sample_stats": stats[:3],
            "top_keys": list(item.keys())[:20],
            "player_keys": list(player.keys())[:20],
        })
    return {
        "top_keys": list(data.keys())[:40],
        "players_count": len(players),
        "weekly_actual_period_counts": dict(periods),
        "samples": out[:5],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for year, target_week in CASES:
        query_period = target_week + 1
        tests = [
            ("players_wl_subpath", f"{BASE}/seasons/{year}/players", [("view", "players_wl"), ("scoringPeriodId", str(query_period))]),
            ("kona_players_subpath", f"{BASE}/seasons/{year}/players", [("view", "kona_player_info"), ("scoringPeriodId", str(query_period))]),
            ("kona_league_context", f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}", [("view", "kona_player_info"), ("scoringPeriodId", str(query_period))]),
        ]
        if year < 2018:
            tests.append(("kona_history_context", f"{BASE}/leagueHistory/{LEAGUE_ID}", [("view", "kona_player_info"), ("seasonId", str(year)), ("scoringPeriodId", str(query_period))]))
        for label, url, params in tests:
            response = session.get(url, params=params, timeout=90)
            result = {
                "season": year,
                "target_week": target_week,
                "query_scoring_period": query_period,
                "test": label,
                "http_status": response.status_code,
                "response_bytes": len(response.content),
            }
            if response.status_code == 200:
                try:
                    result.update(inspect_players(response.json()))
                except Exception as exc:
                    result["parse_error"] = f"{type(exc).__name__}: {exc}"
                    result["body_sample"] = response.text[:500]
            else:
                result["body_sample"] = response.text[:500]
            results.append(result)
            print(
                f"{year} target week {target_week} {label}: HTTP {response.status_code}; "
                f"bytes={result['response_bytes']}; players={result.get('players_count')}; "
                f"weekly_actual={result.get('weekly_actual_period_counts')}"
            )
            time.sleep(0.25)
    path = OUT / "player_stats_endpoint_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
