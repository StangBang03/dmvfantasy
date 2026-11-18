import json
import os
import time
from collections import defaultdict
from pathlib import Path

import requests

LEAGUE_ID=112536
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT=Path("artifacts/roster_snapshots")
CASES={
    2014:[1,5,10,14,15,16,17],
    2017:[1,5,10,14,15,16,17],
    2018:[1,5,10,14,15,16,17],
    2025:[1,5,10,14,15,16,17,18],
    2026:[1,5,10],
}
s=requests.Session()
s.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
s.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})
if not s.cookies.get("espn_s2") or not s.cookies.get("SWID"): raise RuntimeError("Missing ESPN credentials")


def endpoint(year):
    if year>=2018: return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}",[]
    return f"{BASE}/leagueHistory/{LEAGUE_ID}",[("seasonId",str(year))]


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for year,weeks in CASES.items():
        by_week={}
        for week in weeks:
            url,base=endpoint(year)
            params=[("view","mRoster"),("scoringPeriodId",str(week))]+base
            r=s.get(url,params=params,timeout=90)
            item={"season":year,"scoring_period":week,"http_status":r.status_code,"bytes":len(r.content)}
            if r.status_code==200:
                payload=r.json()
                data=payload[0] if isinstance(payload,list) and payload else payload
                teams=[]
                player_map={}
                for team in data.get("teams") or []:
                    tid=team.get("id")
                    roster=team.get("roster") or {}
                    entries=[]
                    for entry in roster.get("entries") or []:
                        pool=entry.get("playerPoolEntry") or {}
                        player=pool.get("player") or {}
                        pid=player.get("id") or entry.get("playerId")
                        if pid is None: continue
                        row={
                            "player_id":int(pid),
                            "name":player.get("fullName") or player.get("full") or player.get("last"),
                            "team_id":tid,
                            "lineup_slot_id":entry.get("lineupSlotId"),
                            "pro_team_id":player.get("proTeamId"),
                            "position_id":player.get("defaultPositionId"),
                            "acquisition_type":entry.get("acquisitionType"),
                            "acquisition_date":entry.get("acquisitionDate"),
                        }
                        entries.append(row)
                        player_map[int(pid)]=row
                    teams.append({"team_id":tid,"entries":len(entries)})
                item["team_count"]=len(teams)
                item["roster_entries"]=sum(t["entries"] for t in teams)
                item["unique_players"]=len(player_map)
                item["teams"]=teams
                item["players"]=list(player_map.values())
                by_week[week]=player_map
            else:
                item["body"]=r.text[:500]
            results.append(item)
            print(f"{year} SP{week}: HTTP {r.status_code}; entries={item.get('roster_entries')}; unique={item.get('unique_players')}")
            time.sleep(0.15)
        if by_week:
            all_ids=set().union(*(set(m) for m in by_week.values()))
            comparisons={}
            weeks_sorted=sorted(by_week)
            for i,wa in enumerate(weeks_sorted):
                for wb in weeks_sorted[i+1:]:
                    a=set(by_week[wa]); b=set(by_week[wb])
                    comparisons[f"{wa}->{wb}"]={
                        "same_count":len(a&b),
                        "added_in_later":sorted(b-a),
                        "missing_in_later":sorted(a-b),
                        "team_changes":sum(1 for pid in a&b if by_week[wa][pid]["team_id"]!=by_week[wb][pid]["team_id"]),
                    }
            summary={
                "season":year,
                "union_player_count":len(all_ids),
                "periods":{str(w):len(m) for w,m in by_week.items()},
                "comparisons":comparisons,
            }
            (OUT/f"roster_snapshot_summary_{year}.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    (OUT/"roster_snapshots.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(f"Wrote {len(results)} roster snapshots")


if __name__=="__main__": main()
