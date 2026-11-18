import json
import os
import time
from pathlib import Path

import requests

LEAGUE_ID=112536
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT=Path("artifacts/season_2026_status")
IDS=[2971573,-16003,-16004,2991662,3052587]
s=requests.Session()
s.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
s.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})
if not s.cookies.get("espn_s2") or not s.cookies.get("SWID"): raise RuntimeError("Missing ESPN credentials")


def one_view(view,params=None,filter_ids=None):
    p=[("view",view)]
    for k,v in (params or {}).items(): p.append((k,str(v)))
    if filter_ids:
        s.headers["X-Fantasy-Filter"]=json.dumps({"players":{"filterIds":{"value":filter_ids},"filterStatsForTopScoringPeriodIds":{"value":18,"additionalValue":["002026"]}}},separators=(",",":"))
    else:
        s.headers.pop("X-Fantasy-Filter",None)
    r=s.get(f"{BASE}/seasons/2026/segments/0/leagues/{LEAGUE_ID}",params=p,timeout=90)
    out={"view":view,"params":params,"http_status":r.status_code,"bytes":len(r.content)}
    if r.status_code==200:
        payload=r.json()
        data=payload[0] if isinstance(payload,list) and payload and isinstance(payload[0],dict) else payload
        if view=="mStatus":
            out["status"]=data.get("status")
            out["keys"]=list(data.keys())
        elif view=="mMatchupScore":
            periods={}
            for m in data.get("schedule") or []:
                for side in ("home","away"):
                    t=m.get(side) or {}
                    for k,v in (t.get("pointsByScoringPeriod") or {}).items():
                        periods[k]=periods.get(k,0)+1
            out["periods"]=periods
            out["schedule_count"]=len(data.get("schedule") or [])
        elif view=="kona_playercard":
            players=data.get("players") or []
            out["players"]=[]
            for item in players:
                pl=item.get("player") or item
                arr=pl.get("stats") or item.get("stats") or []
                out["players"].append({
                    "id":pl.get("id") or item.get("id"),
                    "name":pl.get("fullName"),
                    "onTeamId":item.get("onTeamId"),
                    "stats":[{k:st.get(k) for k in ("id","seasonId","scoringPeriodId","statSourceId","statSplitTypeId","appliedTotal")} for st in arr],
                })
    else: out["body"]=r.text[:500]
    return out


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for view,params,ids in [
        ("mStatus",{},None),
        ("mMatchupScore",{},None),
        ("kona_playercard",{"scoringPeriodId":0},IDS),
    ]:
        item=one_view(view,params,ids)
        results.append(item)
        print(json.dumps(item,indent=2)[:12000])
        time.sleep(0.2)
    path=OUT/"season_2026_status.json"
    path.write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(f"Wrote {path}")


if __name__=="__main__": main()
