import gzip
import json
import os
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

PLAYER_CARD_DIR=Path("data/raw/playercard_history")
SUMMARY_DIR=Path("data/raw/legacy_game_summaries")
EXISTING_GAMELOG_DIR=Path("data/raw/legacy_player_gamelogs")
RAW_OUT=Path("data/raw/legacy_defensive_gamelogs")
ARTIFACT_OUT=Path("artifacts/legacy_defensive_gamelogs")
YEARS=range(2011,2018)
MAX_WORKERS=6
BASE="https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes"
thread_local=threading.local()


def session_for_thread():
    if not hasattr(thread_local,"session"):
        s=requests.Session()
        s.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0","Referer":"https://www.espn.com/"})
        thread_local.session=s
    return thread_local.session


def num(value):
    try: return float(value or 0)
    except (TypeError,ValueError): return 0.0


def fetch_defender(year,player_id,player_name):
    s=session_for_thread()
    url=f"{BASE}/{player_id}/gamelog"
    last_error=None
    for attempt in range(4):
        try:
            r=s.get(url,params={"region":"us","lang":"en","season":year},timeout=60)
            if r.status_code==429 or r.status_code>=500:
                time.sleep(1.5*(attempt+1)); continue
            if r.status_code!=200:
                return {"player_id":player_id,"player_name":player_name,"http_status":r.status_code,"error":r.text[:200],"events":[]}
            data=r.json()
            names=data.get("names") or []
            event_meta=data.get("events") or {}
            events={}
            for season_type in data.get("seasonTypes") or []:
                if "Regular Season" not in (season_type.get("displayName") or ""): continue
                for category in season_type.get("categories") or []:
                    for item in category.get("events") or []:
                        eid=str(item.get("eventId"))
                        meta=event_meta.get(eid) or {}
                        vals=item.get("stats") or []
                        stats={names[i]:vals[i] for i in range(min(len(names),len(vals)))}
                        events[eid]={
                            "event_id":eid,
                            "week":(meta.get("week") or {}).get("number") if isinstance(meta.get("week"),dict) else meta.get("week"),
                            "stats":stats,
                        }
            time.sleep(0.1)
            return {"player_id":player_id,"player_name":player_name,"http_status":200,"stat_names":names,"events":list(events.values())}
        except Exception as exc:
            last_error=f"{type(exc).__name__}: {exc}"
            time.sleep(1.0*(attempt+1))
    return {"player_id":player_id,"player_name":player_name,"http_status":None,"error":last_error,"events":[]}


def main():
    RAW_OUT.mkdir(parents=True,exist_ok=True)
    ARTIFACT_OUT.mkdir(parents=True,exist_ok=True)
    audit={"seasons":{},"errors":[]}
    for year in YEARS:
        pc_path=PLAYER_CARD_DIR/f"playercard_{year}.json.gz"
        sm_path=SUMMARY_DIR/f"legacy_game_summaries_{year}.json.gz"
        if not pc_path.exists() or not sm_path.exists():
            audit["errors"].append({"season":year,"error":"Missing player-card or game-summary archive"})
            continue
        with gzip.open(pc_path,"rt",encoding="utf-8") as f: pc=json.load(f)
        with gzip.open(sm_path,"rt",encoding="utf-8") as f: summaries=json.load(f)
        dst_team_ids={
            int(p["pro_team_id"])
            for p in pc.get("players") or []
            if (int(p.get("player_id",0))<0 or int(p.get("position_id") or 0)==16)
            and p.get("pro_team_id") is not None and int(p["pro_team_id"])>0
        }
        existing_logs={}
        existing_path=EXISTING_GAMELOG_DIR/f"legacy_player_gamelogs_{year}.json.gz"
        if existing_path.exists():
            with gzip.open(existing_path,"rt",encoding="utf-8") as f: existing=json.load(f)
            existing_logs={int(p["player_id"]):p for p in existing.get("players") or []}
        player_map={}
        event_player_team={}
        for event in summaries.get("events") or []:
            if event.get("http_status")!=200: continue
            eid=str(event["event_id"])
            week=event.get("week")
            for player in event.get("players") or []:
                team_id=player.get("team_id")
                if team_id not in dst_team_ids: continue
                groups=player.get("groups") or {}
                if not any(g in groups for g in ("defensive","interceptions","fumbles","kickReturns","puntReturns","punting")):
                    continue
                pid=int(player["player_id"])
                player_map.setdefault(pid,player.get("name"))
                event_player_team[(pid,eid)]={"team_id":int(team_id),"week":week}
        requested=[(pid,name) for pid,name in sorted(player_map.items()) if pid not in existing_logs]
        results=[existing_logs[pid] for pid in sorted(player_map) if pid in existing_logs]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures=[executor.submit(fetch_defender,year,pid,name) for pid,name in requested]
            for future in as_completed(futures): results.append(future.result())
        results.sort(key=lambda x:x["player_id"])
        team_week=defaultdict(lambda:{"fumbles_forced":0,"kicks_blocked":0})
        nonzero=[]
        for player in results:
            if player.get("http_status")!=200: continue
            for event in player.get("events") or []:
                key=(int(player["player_id"]),str(event["event_id"]))
                mapping=event_player_team.get(key)
                if not mapping: continue
                stats=event.get("stats") or {}
                forced=num(stats.get("fumblesForced"))
                blocked=num(stats.get("kicksBlocked"))
                if forced or blocked:
                    tw=team_week[(mapping["team_id"],int(mapping["week"] or event.get("week") or 0))]
                    tw["fumbles_forced"]+=forced
                    tw["kicks_blocked"]+=blocked
                    nonzero.append({"player_id":player["player_id"],"player_name":player["player_name"],"event_id":event["event_id"],"team_id":mapping["team_id"],"week":mapping["week"],"fumbles_forced":forced,"kicks_blocked":blocked})
        team_totals={}
        expected={}
        for p in pc.get("players") or []:
            if int(p.get("player_id",0))<0 and p.get("pro_team_id") is not None:
                tid=int(p["pro_team_id"])
                stats=p.get("season_stats") or {}
                expected[str(tid)]={"fumbles_forced":num(stats.get("106")),"kicks_blocked":num(stats.get("97"))}
        for (tid,week),counts in team_week.items():
            target=team_totals.setdefault(str(tid),{"fumbles_forced":0,"kicks_blocked":0,"weeks":{}})
            target["fumbles_forced"]+=counts["fumbles_forced"]
            target["kicks_blocked"]+=counts["kicks_blocked"]
            target["weeks"][str(week)]=counts
        mismatches=[]
        for tid,expected_counts in expected.items():
            actual=team_totals.get(tid,{"fumbles_forced":0,"kicks_blocked":0})
            for field in ("fumbles_forced","kicks_blocked"):
                if abs(expected_counts[field]-actual[field])>0.01:
                    mismatches.append({"team_id":int(tid),"stat":field,"expected":expected_counts[field],"gamelog_sum":actual[field]})
        output={"meta":{"season":year,"dst_team_ids":sorted(dst_team_ids),"defensive_players_found":len(player_map),"defensive_players_queried":len(requested)},"team_week_counts":{f"{tid}:{week}":v for (tid,week),v in team_week.items()},"team_totals":team_totals,"player_nonzero_events":nonzero,"players":results}
        raw_path=RAW_OUT/f"legacy_defensive_gamelogs_{year}.json.gz"
        with gzip.open(raw_path,"wt",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,separators=(",",":"))
        with gzip.open(ARTIFACT_OUT/raw_path.name,"wt",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,separators=(",",":"))
        audit["seasons"][str(year)]={
            "dst_team_ids":sorted(dst_team_ids),
            "defensive_players_found":len(player_map),
            "defensive_players_already_in_player_gamelog_archive":len(player_map)-len(requested),
            "defensive_players_queried":len(requested),
            "http_status_counts":dict(Counter(str(x.get("http_status")) for x in results)),
            "nonzero_forced_fumble_or_block_events":len(nonzero),
            "team_totals":team_totals,
            "expected_dst_totals":expected,
            "season_total_mismatches":mismatches,
        }
        print(f"{year}: DST teams={len(dst_team_ids)} defenders={len(player_map)} queried={len(requested)} nonzero events={len(nonzero)} mismatches={len(mismatches)}")
    (ARTIFACT_OUT/"legacy_defensive_gamelog_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
    (RAW_OUT/"legacy_defensive_gamelog_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")


if __name__=="__main__":main()
