import json
import os
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT = Path("artifacts/player_card")
SAMPLE_IDS = {
    2014: [5941, 8444, 9329, 9597, 10467, -16029, -16017],
    2017: [4459, 5526, 9354, 9592, 9705, -16034, -16027],
    2018: [3116406, 3117251, 3051392],
    2025: [4429795, 3117251, 4362628],
}
load_dotenv()
s2, swid = os.getenv("ESPN_S2"), os.getenv("ESPN_SWID")
if not s2 or not swid:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID")
session = requests.Session()
session.cookies.update({"espn_s2": s2, "SWID": swid})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})


def unwrap(value):
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict) and "players" in value[0]:
        return value[0]
    return value if isinstance(value, dict) else {}


def player_rows(payload):
    data = unwrap(payload)
    if isinstance(payload, list) and payload and not (len(payload) == 1 and isinstance(payload[0], dict) and "players" in payload[0]):
        return payload, {}
    return data.get("players") or [], data


def inspect(payload):
    players, data = player_rows(payload)
    results = []
    periods = Counter()
    for item in players:
        if not isinstance(item, dict):
            continue
        player = item.get("player") or item
        stats = player.get("stats") or item.get("stats") or []
        weekly = []
        season_total = None
        for stat in stats:
            if not isinstance(stat, dict) or stat.get("statSourceId") != 0:
                continue
            if stat.get("statSplitTypeId") == 0 and stat.get("scoringPeriodId") == 0:
                season_total = stat.get("appliedTotal")
            if stat.get("statSplitTypeId") == 1:
                period = stat.get("scoringPeriodId")
                periods[period] += 1
                weekly.append({
                    "scoringPeriodId": period,
                    "appliedTotal": stat.get("appliedTotal"),
                    "stats": stat.get("stats") or {},
                })
        results.append({
            "id": player.get("id") or item.get("id"),
            "name": player.get("fullName"),
            "onTeamId": item.get("onTeamId"),
            "season_total": season_total,
            "stats_count": len(stats),
            "weekly_actual": weekly,
        })
    return {
        "top_keys": list(data.keys())[:30],
        "players_returned": len(players),
        "weekly_actual_period_counts": dict(periods),
        "players": results,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for year, player_ids in SAMPLE_IDS.items():
        filters = {
            "players": {
                "filterIds": {"value": player_ids},
                "filterStatsForTopScoringPeriodIds": {
                    "value": 18,
                    "additionalValue": [f"00{year}"],
                },
            }
        }
        session.headers["X-Fantasy-Filter"] = json.dumps(filters, separators=(",", ":"))
        endpoints = [
            ("league_playercard", f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}", [("view", "kona_playercard"), ("scoringPeriodId", "0")]),
        ]
        if year < 2018:
            endpoints.append(("history_playercard", f"{BASE}/leagueHistory/{LEAGUE_ID}", [("view", "kona_playercard"), ("seasonId", str(year)), ("scoringPeriodId", "0")]))
            for default_id in (1, 3, 4):
                endpoints.append((
                    f"leaguedefaults_{default_id}",
                    f"{BASE}/seasons/{year}/segments/0/leaguedefaults/{default_id}",
                    [("view", "kona_playercard"), ("scoringPeriodId", "0")],
                ))
        for label, url, params in endpoints:
            response = session.get(url, params=params, timeout=90)
            result = {
                "season": year,
                "test": label,
                "requested_player_ids": player_ids,
                "http_status": response.status_code,
                "response_bytes": len(response.content),
            }
            if response.status_code == 200:
                try:
                    result.update(inspect(response.json()))
                except Exception as exc:
                    result["parse_error"] = f"{type(exc).__name__}: {exc}"
                    result["body_sample"] = response.text[:500]
            else:
                result["body_sample"] = response.text[:1000]
            results.append(result)
            print(
                f"{year} {label}: HTTP {response.status_code}; "
                f"bytes={result['response_bytes']}; players={result.get('players_returned')}; "
                f"weekly={result.get('weekly_actual_period_counts')}"
            )
            for player in result.get("players", []):
                print("PLAYER " + json.dumps(player, separators=(",", ":"))[:1100])
            time.sleep(0.25)
    path = OUT / "kona_playercard_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
