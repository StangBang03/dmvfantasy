import gzip
import json
import os
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

PLAYER_CARD_DIR=Path("data/raw/playercard_history")
GAMELOG_DIR=Path("data/raw/legacy_player_gamelogs")
RAW_OUT=Path("data/raw/legacy_game_summaries")
ARTIFACT_OUT=Path("artifacts/legacy_game_summaries")
YEARS=range(2011,2018)
MAX_WORKERS=8
SUMMARY_URL="https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"
SCHEDULE_URL="https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"
thread_local=threading.local()


def session_for_thread():
    if not hasattr(thread_local,"session"):
        s=requests.Session()
        s.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0","Referer":"https://www.espn.com/"})
        thread_local.session=s
    return thread_local.session


def compact_summary(year,event_id,meta):
    s=session_for_thread()
    error=None
    for attempt in range(4):
        try:
            response=s.get(SUMMARY_URL,params={"event":str(event_id)},timeout=60)
            if response.status_code==429 or response.status_code>=500:
                time.sleep(1.5*(attempt+1)); continue
            if response.status_code!=200:
                return {"event_id":str(event_id),"season":year,"http_status":response.status_code,"error":response.text[:250]}
            data=response.json()
            header=data.get("header") or {}
            competition=((header.get("competitions") or [{}])[0])
            week=meta.get("week")
            if week is None:
                w=competition.get("week") or {}
                week=w.get("number") if isinstance(w,dict) else w
            teams=[]
            for team in (data.get("boxscore",{}).get("teams") or []):
                t=team.get("team") or {}
                stats={}
                for st in team.get("statistics") or []:
                    name=st.get("name")
                    if name:
                        stats[name]=st.get("displayValue",st.get("value"))
                teams.append({
                    "team_id":int(t.get("id")) if t.get("id") is not None else None,
                    "abbreviation":t.get("abbreviation"),
                    "display_name":t.get("displayName"),
                    "statistics":stats,
                })
            scores={}
            for comp in competition.get("competitors") or []:
                team=comp.get("team") or {}
                tid=comp.get("id") or team.get("id")
                if tid is not None:
                    scores[str(tid)]={
                        "score":comp.get("score"),
                        "home_away":comp.get("homeAway"),
                        "winner":comp.get("winner"),
                        "abbreviation":team.get("abbreviation"),
                    }
            players={}
            for team_group in (data.get("boxscore",{}).get("players") or []):
                team=team_group.get("team") or {}
                team_id=int(team.get("id")) if team.get("id") is not None else None
                for stat_group in team_group.get("statistics") or []:
                    group_name=stat_group.get("name") or "unknown"
                    keys=stat_group.get("keys") or []
                    for athlete_row in stat_group.get("athletes") or []:
                        athlete=athlete_row.get("athlete") or {}
                        pid=athlete.get("id")
                        if pid is None: continue
                        pid=int(pid)
                        player=players.setdefault(pid,{
                            "player_id":pid,
                            "name":athlete.get("displayName") or athlete.get("fullName"),
                            "team_id":team_id,
                            "position":(athlete.get("position") or {}).get("abbreviation") if isinstance(athlete.get("position"),dict) else athlete.get("position"),
                            "groups":{},
                        })
                        vals=athlete_row.get("stats") or []
                        player_stats=player["groups"].setdefault(group_name,{})
                        for idx,key in enumerate(keys):
                            if idx<len(vals):
                                player_stats[key]=vals[idx]
            scoring_plays=[]
            for play in data.get("scoringPlays") or []:
                scoring_team=play.get("team") or {}
                scoring_plays.append({
                    "team_id":int(scoring_team.get("id")) if scoring_team.get("id") is not None else None,
                    "type":(play.get("type") or {}).get("text"),
                    "text":play.get("text"),
                    "score_value":play.get("scoreValue"),
                    "scoring_type":play.get("scoringType"),
                })
            return {
                "event_id":str(event_id),
                "season":year,
                "week":week,
                "date":competition.get("date") or meta.get("date"),
                "http_status":200,
                "scores":scores,
                "teams":teams,
                "players":list(players.values()),
                "scoring_plays":scoring_plays,
            }
        except Exception as exc:
            error=f"{type(exc).__name__}: {exc}"
            time.sleep(1.0*(attempt+1))
    return {"event_id":str(event_id),"season":year,"http_status":None,"error":error}


def team_schedule_events(year,team_id):
    url=SCHEDULE_URL.format(team_id=team_id)
    response=requests.get(url,params={"season":year},headers={"Accept":"application/json","User-Agent":"Mozilla/5.0"},timeout=60)
    response.raise_for_status()
    events={}
    for event in response.json().get("events") or []:
        event_id=str(event.get("id"))
        week=(event.get("week") or {}).get("number")
        events[event_id]={"week":week,"date":event.get("date"),"source":"dst_team_schedule"}
    return events


def main():
    RAW_OUT.mkdir(parents=True,exist_ok=True)
    ARTIFACT_OUT.mkdir(parents=True,exist_ok=True)
    audit={"seasons":{},"errors":[]}
    for year in YEARS:
        player_path=PLAYER_CARD_DIR/f"playercard_{year}.json.gz"
        gamelog_path=GAMELOG_DIR/f"legacy_player_gamelogs_{year}.json.gz"
        if not player_path.exists() or not gamelog_path.exists():
            audit["errors"].append({"season":year,"error":"Missing player-card or legacy gamelog archive"})
            continue
        with gzip.open(player_path,"rt",encoding="utf-8") as f: player_archive=json.load(f)
        with gzip.open(gamelog_path,"rt",encoding="utf-8") as f: gamelog_archive=json.load(f)
        event_meta={}
        for player in gamelog_archive.get("players") or []:
            for event in player.get("events") or []:
                eid=str(event.get("event_id"))
                if eid and eid!="None":
                    event_meta.setdefault(eid,{"week":event.get("week"),"date":event.get("game_date"),"source":"player_gamelog"})
        dst_team_ids=sorted({
            int(p["pro_team_id"])
            for p in player_archive.get("players") or []
            if (int(p.get("player_id",0))<0 or int(p.get("position_id") or 0)==16) and p.get("pro_team_id") is not None and int(p["pro_team_id"])>0
        })
        schedule_errors=[]
        for team_id in dst_team_ids:
            try:
                for eid,meta in team_schedule_events(year,team_id).items():
                    if eid not in event_meta:
                        event_meta[eid]=meta
                    else:
                        event_meta[eid]["dst_team_schedule"]=True
            except Exception as exc:
                schedule_errors.append({"team_id":team_id,"error":f"{type(exc).__name__}: {exc}"})
            time.sleep(0.1)
        ids=sorted(event_meta)
        results=[]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures={executor.submit(compact_summary,year,eid,event_meta[eid]):eid for eid in ids}
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda x:(int(x.get("week") or 0),x["event_id"]))
        status_counts=Counter(str(x.get("http_status")) for x in results)
        failed=[{"event_id":x["event_id"],"week":x.get("week"),"status":x.get("http_status"),"error":x.get("error")} for x in results if x.get("http_status")!=200]
        output={"meta":{"season":year,"event_count":len(ids),"dst_team_ids":dst_team_ids,"source":"ESPN NFL game summaries"},"events":results}
        raw_path=RAW_OUT/f"legacy_game_summaries_{year}.json.gz"
        with gzip.open(raw_path,"wt",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,separators=(",",":"))
        with gzip.open(ARTIFACT_OUT/raw_path.name,"wt",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,separators=(",",":"))
        audit["seasons"][str(year)]={
            "player_gamelog_event_ids":sum(1 for v in event_meta.values() if v.get("source")=="player_gamelog"),
            "dst_team_ids":dst_team_ids,
            "unique_event_ids":len(ids),
            "http_status_counts":dict(status_counts),
            "failed_events":failed,
            "schedule_errors":schedule_errors,
            "events_by_week":dict(sorted(Counter(str(x.get("week")) for x in results).items())),
            "players_in_summaries":sum(len(x.get("players") or []) for x in results if x.get("http_status")==200),
        }
        print(f"{year}: events={len(ids)} statuses={dict(status_counts)} failed={len(failed)} DST teams={len(dst_team_ids)}")
    (ARTIFACT_OUT/"legacy_game_summary_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
    (RAW_OUT/"legacy_game_summary_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")


if __name__=="__main__":main()
