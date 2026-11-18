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
CASES = [
    (2014, 16),
    (2017, 16),
    (2018, 17),
    (2025, 10),
]
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


def unwrap(v):
    if isinstance(v, list):
        return v[0] if v and isinstance(v[0], dict) else {}
    return v if isinstance(v, dict) else {}


def inspect_players(payload):
    data = unwrap(payload)
    if isinstance(payload, list):
        players = payload
    else:
        players = data.get("players") or data.get("playerPool") or []
    out = []
    periods = Counter()
    for item in players[:30]:
        if not isinstance(item, dict):
            continue
        pool = item.get("playerPoolEntry") or {}
        player = pool.get("player") or item
        stats = player.get("stats") or pool.get("stats") or []
        weekly = []
        for st in stats:
            if not isinstance(st, dict):
                continue
            if st.get("statSplitTypeId") == 1 and st.get("statSourceId") == 0:
                periods[st.get("scoringPeriodId")] += 1
                weekly.append({
                    "scoringPeriodId": st.get("scoringPeriodId"),
                    "appliedTotal": st.get("appliedTotal"),
                    "statSourceId": st.get("statSourceId"),
                    "statSplitTypeId": st.get("statSplitTypeId"),
                })
        out.append({
            "id": player.get("id"),
            "name": player.get("fullName"),
            "pool_appliedStatTotal": pool.get("appliedStatTotal"),
            "stats_count": len(stats),
            "weekly_actual": weekly,
            "sample_stats": stats[:2],
            "top_keys": list(item.keys())[:20],
        })
    return {
        "payload_type": type(payload).__name__,
        "top_keys": list(data.keys())[:40] if isinstance(data, dict) else [],
        "players_count": len(players) if isinstance(players, list) else None,
        "weekly_actual_period_counts": dict(periods),
        "samples": out[:5],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for year, sp in CASES:
        tests = [
            ("players_wl_subpath", f"{BASE}/seasons/{year}/players", [("view", "players_wl"), ("scoringPeriodId", str(sp))]),
            ("kona_league_context", f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}", [("view", "kona_player_info"), ("scoringPeriodId", str(sp))]),
        ]
        if year < 2018:
            tests.append(("kona_history_context", f"{BASE}/leagueHistory/{LEAGUE_ID}", [("view", "kona_player_info"), ("seasonId", str(year)), ("scoringPeriodId", str(sp))]))
        for label, url, params in tests:
            response = session.get(url, params=params, timeout=90)
            result = {
                "season": year,
                "scoring_period": sp,
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
                f"{year} SP{sp} {label}: HTTP {response.status_code}; "
                f"bytes={result['response_bytes']}; "
                f"weekly_actual={result.get('weekly_actual_period_counts')}"
            )
            time.sleep(0.25)
    path = OUT / "player_stats_endpoint_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
