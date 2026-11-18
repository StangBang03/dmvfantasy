import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

OUT = Path("artifacts/athlete_gamelog")
PLAYER_CASES = [
    (2014, 1428, "Peyton Manning"),
    (2014, 5941, "Wes Welker"),
    (2014, 8444, "Heath Miller"),
    (2017, 2576434, "Melvin Gordon"),
    (2017, 5526, "Eli Manning"),
    (2018, 3116406, "Tyreek Hill"),
    (2025, 4362628, "Ja'Marr Chase"),
]
TEAM_CASES = [(2014, 33, "Baltimore Ravens"), (2014, 17, "New England Patriots"), (2017, 29, "Carolina Panthers")]
GAMEL0G_BASE = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl"
LEAGUE_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
load_dotenv()
session = requests.Session()
session.headers.update({
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.espn.com/",
})
if os.getenv("ESPN_S2") and os.getenv("ESPN_SWID"):
    session.cookies.update({"espn_s2": os.getenv("ESPN_S2"), "SWID": os.getenv("ESPN_SWID")})


def summarize_gamelog(data):
    events = data.get("events") or {}
    names = data.get("names") or []
    result = []
    for season_type in data.get("seasonTypes") or []:
        type_name = season_type.get("displayName")
        for category in season_type.get("categories") or []:
            for item in category.get("events") or []:
                event_id = str(item.get("eventId"))
                meta = events.get(event_id) or {}
                values = item.get("stats") or []
                result.append({
                    "season_type": type_name,
                    "event_id": event_id,
                    "week": meta.get("week"),
                    "game_date": meta.get("gameDate"),
                    "opponent": (meta.get("opponent") or {}).get("abbreviation"),
                    "team": (meta.get("team") or {}).get("abbreviation"),
                    "stats": {name: values[i] for i, name in enumerate(names) if i < len(values)},
                })
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for year in sorted({x[0] for x in PLAYER_CASES}):
        params = [("view", "mSettings"), ("seasonId", str(year))]
        url = f"{LEAGUE_BASE}/leagueHistory/112536"
        response = session.get(url, params=params, timeout=60)
        item = {"season": year, "test": "league_settings", "http_status": response.status_code}
        if response.status_code == 200:
            payload = response.json()
            data = payload[0] if isinstance(payload, list) and payload else payload
            settings = data.get("settings") or {}
            scoring = settings.get("scoringSettings") or {}
            item["scoring_settings"] = scoring
            item["schedule_settings"] = settings.get("scheduleSettings")
        else:
            item["body_sample"] = response.text[:500]
        results.append(item)
        print(f"{year} settings HTTP {response.status_code}; scoring items={len(item.get('scoring_settings',{}).get('scoringItems',[]))}")
        time.sleep(0.2)

    for year, player_id, name in PLAYER_CASES:
        url = f"{GAMEL0G_BASE}/athletes/{player_id}/gamelog"
        response = session.get(url, params={"region": "us", "lang": "en", "season": year}, timeout=60)
        item = {
            "season": year, "player_id": player_id, "player_name": name,
            "test": "common_gamelog", "http_status": response.status_code,
            "response_bytes": len(response.content),
        }
        if response.status_code == 200:
            data = response.json()
            item["top_keys"] = list(data.keys())
            item["names"] = data.get("names")
            item["events"] = summarize_gamelog(data)
            item["season_types"] = [x.get("displayName") for x in data.get("seasonTypes") or []]
        else:
            item["body_sample"] = response.text[:500]
        results.append(item)
        regular = [x for x in item.get("events", []) if "Regular Season" in (x.get("season_type") or "")]
        print(f"{year} {name}: HTTP {response.status_code}; regular games={len(regular)}; sample={regular[:1]}")
        time.sleep(0.2)

    for year, team_id, name in TEAM_CASES:
        url = f"{GAMEL0G_BASE}/teams/{team_id}/gamelog"
        response = session.get(url, params={"region": "us", "lang": "en", "season": year}, timeout=60)
        item = {
            "season": year, "team_id": team_id, "team_name": name,
            "test": "team_gamelog", "http_status": response.status_code,
            "response_bytes": len(response.content),
        }
        if response.status_code == 200:
            data = response.json()
            item["top_keys"] = list(data.keys())
            item["names"] = data.get("names")
            item["events"] = summarize_gamelog(data)
            item["season_types"] = [x.get("displayName") for x in data.get("seasonTypes") or []]
        else:
            item["body_sample"] = response.text[:500]
        results.append(item)
        print(f"{year} {name} team gamelog: HTTP {response.status_code}; events={len(item.get('events', []))}")
        time.sleep(0.2)

    path = OUT / "athlete_gamelog_probe.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
