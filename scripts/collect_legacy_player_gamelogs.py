import gzip
import json
import os
import shutil
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ARCHIVE_DIR = Path("data/raw/playercard_history")
OUT = Path("artifacts/legacy_player_gamelogs")
RAW_OUT = Path("data/raw/legacy_player_gamelogs")
GAMEL0G_BASE = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes"
YEARS = range(2011, 2018)
MAX_WORKERS = 6
thread_local = threading.local()


def get_session():
    if not hasattr(thread_local, "session"):
        sess = requests.Session()
        sess.headers.update({
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.espn.com/",
        })
        if os.getenv("ESPN_S2") and os.getenv("ESPN_SWID"):
            sess.cookies.update({"espn_s2": os.getenv("ESPN_S2"), "SWID": os.getenv("ESPN_SWID")})
        thread_local.session = sess
    return thread_local.session


def parse_week(meta):
    week = meta.get("week")
    return week.get("number") if isinstance(week, dict) else week


def fetch_player(year, player):
    pid = int(player["player_id"])
    result = {
        "season": year,
        "player_id": pid,
        "player_name": player.get("player_name"),
        "position_id": player.get("position_id"),
        "pro_team_id": player.get("pro_team_id"),
        "season_total": player.get("season_total"),
        "season_stats": player.get("season_stats") or {},
        "http_status": None,
        "events": [],
        "error": None,
    }
    sess = get_session()
    for attempt in range(4):
        try:
            response = sess.get(
                f"{GAMEL0G_BASE}/{pid}/gamelog",
                params={"region": "us", "lang": "en", "season": year},
                timeout=60,
            )
            result["http_status"] = response.status_code
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code != 200:
                result["error"] = f"HTTP {response.status_code}: {response.text[:250]}"
                return result
            data = response.json()
            meta_by_id = data.get("events") or {}
            names = data.get("names") or []
            merged = {}
            for season_type in data.get("seasonTypes") or []:
                if "Regular Season" not in (season_type.get("displayName") or ""):
                    continue
                for category in season_type.get("categories") or []:
                    for item in category.get("events") or []:
                        event_id = str(item.get("eventId"))
                        meta = meta_by_id.get(event_id) or {}
                        row = merged.setdefault(event_id, {
                            "event_id": event_id,
                            "week": parse_week(meta),
                            "game_date": meta.get("gameDate"),
                            "team": (meta.get("team") or {}).get("abbreviation"),
                            "opponent": (meta.get("opponent") or {}).get("abbreviation"),
                            "stats": {},
                        })
                        values = item.get("stats") or []
                        for i, name in enumerate(names):
                            if i < len(values):
                                row["stats"][name] = values[i]
            result["events"] = sorted(
                merged.values(),
                key=lambda x: (int(x["week"] or 0), str(x["game_date"] or "")),
            )
            result["top_keys"] = list(data.keys())
            result["stat_names"] = names
            return result
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            time.sleep(1.0 * (attempt + 1))
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW_OUT.mkdir(parents=True, exist_ok=True)
    audit = {"source": str(ARCHIVE_DIR), "seasons": {}, "errors": []}
    for year in YEARS:
        archive_path = ARCHIVE_DIR / f"playercard_{year}.json.gz"
        if not archive_path.exists():
            audit["errors"].append({"season": year, "error": f"Missing archive {archive_path}"})
            continue
        with gzip.open(archive_path, "rt", encoding="utf-8") as f:
            archive = json.load(f)
        players = [
            {
                "player_id": int(p["player_id"]),
                "player_name": p.get("player_name"),
                "position_id": p.get("position_id"),
                "pro_team_id": p.get("pro_team_id"),
                "season_total": p.get("season_total"),
                "season_stats": p.get("season_stats") or {},
            }
            for p in archive.get("players") or []
            if int(p.get("player_id", 0)) > 0
        ]
        if not players:
            audit["errors"].append({"season": year, "error": "No positive player IDs in player-card archive"})
            continue
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_player, year, p) for p in players]
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda x: x["player_id"])
        status_counts = Counter(str(x.get("http_status")) for x in results)
        empty = [x["player_id"] for x in results if x.get("http_status") == 200 and not x.get("events")]
        failed = [
            {"player_id": x["player_id"], "name": x["player_name"], "status": x.get("http_status"), "error": x.get("error")}
            for x in results if x.get("http_status") != 200
        ]
        week_counts = Counter()
        total_events = 0
        for player in results:
            for event in player.get("events") or []:
                if event.get("week") is not None:
                    week_counts[int(event["week"])] += 1
                total_events += 1
        output = {
            "meta": {
                "season": year,
                "source": "ESPN common athlete gamelog",
                "players_requested": len(players),
                "players_returned": sum(1 for x in results if x.get("http_status") == 200),
            },
            "players": results,
        }
        raw_path = RAW_OUT / f"legacy_player_gamelogs_{year}.json.gz"
        with gzip.open(raw_path, "wt", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
        shutil.copy2(raw_path, OUT / raw_path.name)
        audit["seasons"][str(year)] = {
            "player_ids_requested": len(players),
            "http_status_counts": dict(status_counts),
            "players_with_no_regular_season_events": empty,
            "failed_players": failed,
            "event_rows": total_events,
            "event_rows_by_week": dict(sorted(week_counts.items())),
        }
        print(f"{year}: players={len(players)} statuses={dict(status_counts)} event rows={total_events} empty={len(empty)} failed={len(failed)}")
    audit_text = json.dumps(audit, indent=2)
    (OUT / "legacy_player_gamelog_audit.json").write_text(audit_text, encoding="utf-8")
    (RAW_OUT / "legacy_player_gamelog_audit.json").write_text(audit_text, encoding="utf-8")


if __name__ == "__main__":
    main()
