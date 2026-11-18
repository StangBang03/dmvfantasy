import json
import time
from pathlib import Path

import requests

OUT = Path("artifacts/athlete_gamelog")
CASES = [
    (2014, 1428, "Peyton Manning"),
    (2014, 5941, "Wes Welker"),
    (2014, 8444, "Heath Miller"),
    (2017, 2576434, "Melvin Gordon"),
    (2017, 5526, "Eli Manning"),
    (2018, 3116406, "Tyreek Hill"),
    (2025, 4362628, "Ja'Marr Chase"),
]
BASE = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons"
session = requests.Session()
session.headers.update({
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.espn.com/",
})


def summarize(data):
    result = {"top_keys": list(data.keys())[:40]}
    events = data.get("events") or {}
    if isinstance(events, dict):
        result["events_count"] = len(events)
        result["events_sample"] = list(events.items())[:3]
    elif isinstance(events, list):
        result["events_count"] = len(events)
        result["events_sample"] = events[:3]
    result["season_types"] = data.get("seasonTypes")
    result["categories"] = data.get("categories")
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for year, player_id, name in CASES:
        tests = [
            ("common_gamelog", f"{BASE}/{player_id}/gamelog", {"region": "us", "lang": "en", "season": year}),
            ("core_eventlog", f"{CORE}/{year}/athletes/{player_id}/eventlog", {}),
        ]
        for label, url, params in tests:
            response = session.get(url, params=params, timeout=60)
            item = {
                "season": year,
                "player_id": player_id,
                "player_name": name,
                "test": label,
                "http_status": response.status_code,
                "response_bytes": len(response.content),
            }
            if response.status_code == 200:
                try:
                    data = response.json()
                    item.update(summarize(data))
                    item["raw_sample"] = data
                except Exception as exc:
                    item["parse_error"] = str(exc)
                    item["body_sample"] = response.text[:1000]
            else:
                item["body_sample"] = response.text[:1000]
            results.append(item)
            print(
                f"{year} {name} {label}: HTTP {response.status_code}; "
                f"bytes={item['response_bytes']}; keys={item.get('top_keys')}; "
                f"events={item.get('events_count')}"
            )
            time.sleep(0.25)
    path = OUT / "athlete_gamelog_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
