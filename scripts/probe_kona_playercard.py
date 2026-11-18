import json
import os
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
AUDIT = Path("data/processed/player_performance_audit.json")
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


def league_url(year):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    return f"{BASE}/leagueHistory/{LEAGUE_ID}"


def unwrap(value):
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], dict) else {}
    return value if isinstance(value, dict) else {}


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
        params = [("view", "kona_playercard"), ("scoringPeriodId", "0")]
        if year < 2018:
            params.append(("seasonId", str(year)))
        response = session.get(league_url(year), params=params, timeout=90)
        result = {
            "season": year,
            "requested_player_ids": player_ids,
            "http_status": response.status_code,
            "response_bytes": len(response.content),
        }
        if response.status_code == 200:
            payload = response.json()
            data = unwrap(payload)
            players = data.get("players") or []
            samples = []
            period_counts = Counter()
            for item in players:
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
                        period_counts[period] += 1
                        weekly.append({
                            "scoringPeriodId": period,
                            "appliedTotal": stat.get("appliedTotal"),
                            "stats": stat.get("stats") or {},
                        })
                samples.append({
                    "id": player.get("id") or item.get("id"),
                    "name": player.get("fullName"),
                    "onTeamId": item.get("onTeamId"),
                    "season_total": season_total,
                    "stats_count": len(stats),
                    "weekly_actual": weekly,
                })
            result.update({
                "top_keys": list(data.keys())[:30],
                "players_returned": len(players),
                "weekly_actual_period_counts": dict(period_counts),
                "players": samples,
            })
        else:
            result["body_sample"] = response.text[:1000]
        results.append(result)
        print(
            f"{year}: HTTP {response.status_code}; bytes={result['response_bytes']}; "
            f"players={result.get('players_returned')}; weekly={result.get('weekly_actual_period_counts')}"
        )
        for player in result.get("players", []):
            print("PLAYER " + json.dumps(player, separators=(",", ":"))[:1600])
        time.sleep(0.3)
    path = OUT / "kona_playercard_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
