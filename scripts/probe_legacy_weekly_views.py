import json,os,time
from pathlib import Path
import requests
LEAGUE_ID=112536
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory"
CASES=[(2012,14),(2012,15),(2012,16),(2012,17),(2014,15),(2017,16)]
VIEWS=["mRoster","mMatchup","mTeam","mLiveScoring","mMatchupScore","mBoxscore"]
s=requests.Session()
s.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
s.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})
if not s.cookies.get("espn_s2") or not s.cookies.get("SWID"): raise RuntimeError("Missing ESPN credentials")
OUT=Path("artifacts/legacy_view_probe");OUT.mkdir(parents=True,exist_ok=True)

def unwrap(x): return x[0] if isinstance(x,list) and x and isinstance(x[0],dict) else x if isinstance(x,dict) else {}
def roster_summary(entries):
 out=[]
 for e in (entries or [])[:3]:
  pool=e.get("playerPoolEntry") or {};p=pool.get("player") or {}
  out.append({"id":p.get("id") or e.get("playerId"),"name":p.get("fullName") or p.get("full"),"slot":e.get("lineupSlotId"),"appliedStat":pool.get("appliedStat"),"appliedStatTotal":pool.get("appliedStatTotal"),"stats":p.get("stats")})
 return out
def main():
 results=[]
 for year,week in CASES:
  for view in VIEWS:
   params=[("view",view),("seasonId",str(year)),("scoringPeriodId",str(week)),("matchupPeriodId",str(week))]
   r=s.get(f"{BASE}/{LEAGUE_ID}",params=params,timeout=90)
   x={"season":year,"scoring_period":week,"view":view,"status":r.status_code,"bytes":len(r.content)}
   if r.status_code==200:
    d=unwrap(r.json());x["keys"]=list(d.keys())
    if isinstance(d.get("teams"),list):
     x["teams"]=[]
     for t in d["teams"][:2]:
      roster=(t.get("roster") or {}).get("entries") or []
      x["teams"].append({"team_id":t.get("id"),"keys":list(t.keys()),"roster_count":len(roster),"sample":roster_summary(roster)})
    if isinstance(d.get("schedule"),list):
     x["schedule_count"]=len(d["schedule"])
     x["matchup_samples"]=[]
     for m in d["schedule"]:
      if m.get("matchupPeriodId") in (week,week-1,14,15):
       sample={"matchup_period":m.get("matchupPeriodId"),"keys":list(m.keys())}
       for side in ("home","away"):
        team=m.get(side) or {}
        mp=(team.get("rosterForMatchupPeriod") or {}).get("entries") or []
        cp=(team.get("rosterForCurrentScoringPeriod") or {}).get("entries") or []
        sample[side]={"keys":list(team.keys()),"mp_count":len(mp),"cp_count":len(cp),"mp_sample":roster_summary(mp),"cp_sample":roster_summary(cp)}
       if sample["home"]["mp_count"] or sample["home"]["cp_count"] or sample["away"]["mp_count"] or sample["away"]["cp_count"]:
        x["matchup_samples"].append(sample)
       if len(x["matchup_samples"])>=2:break
   else:x["body"]=r.text[:300]
   results.append(x)
   print(year,week,view,r.status_code,x.get("keys"),x.get("teams",[])[:1],x.get("matchup_samples",[])[:1])
   time.sleep(.1)
 (OUT/"legacy_view_probe.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
if __name__=="__main__":main()
