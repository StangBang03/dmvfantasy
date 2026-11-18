import json, os, time
from pathlib import Path
import requests

LEAGUE_ID=112536
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
CASES=[(2012,w) for w in range(13,18)]+[(2013,w) for w in range(13,18)]+[(2014,w) for w in range(13,18)]+[(2015,w) for w in range(13,18)]+[(2016,w) for w in range(13,18)]+[(2017,w) for w in range(13,18)]
s=requests.Session()
s.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
s.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})
if not s.cookies.get("espn_s2") or not s.cookies.get("SWID"): raise RuntimeError("Missing ESPN credentials")
OUT=Path("artifacts/weekly_roster_semantics"); OUT.mkdir(parents=True,exist_ok=True)

def unwrap(x): return x[0] if isinstance(x,list) and x and isinstance(x[0],dict) else x if isinstance(x,dict) else {}
def summarize(entries):
    out=[]
    for e in entries or []:
        p=(e.get("playerPoolEntry") or {}).get("player") or {}
        pool=e.get("playerPoolEntry") or {}
        out.append({"player_id":e.get("playerId") or p.get("id"),"name":p.get("fullName") or p.get("full"),"slot":e.get("lineupSlotId"),"appliedStat":pool.get("appliedStat"),"appliedStatTotal":pool.get("appliedStatTotal"),"entry_appliedStat":e.get("appliedStat"),"stats":p.get("stats")})
    return out

def main():
    rows=[]
    for year,week in CASES:
        url=f"{BASE}/leagueHistory/{LEAGUE_ID}"
        r=s.get(url,params={"view":"mBoxscore","seasonId":year,"scoringPeriodId":week,"matchupPeriodId":week},timeout=90)
        item={"season":year,"scoring_period":week,"status":r.status_code}
        if r.status_code==200:
            d=unwrap(r.json()); schedule=d.get("schedule") or []
            item["matchup_periods"]=sorted({m.get("matchupPeriodId") for m in schedule if m.get("matchupPeriodId") is not None})
            item["schedule_count"]=len(schedule)
            if schedule:
                m=schedule[0]; item["matchup_keys"]=list(m.keys())
                for side in ("home","away"):
                    team=m.get(side) or {}
                    item[side]={
                        "keys":list(team.keys()),
                        "team_id":team.get("teamId"),
                        "points":team.get("points"),
                        "pointsByScoringPeriod":team.get("pointsByScoringPeriod"),
                        "rosterForMatchupPeriod":summarize((team.get("rosterForMatchupPeriod") or {}).get("entries")),
                        "rosterForCurrentScoringPeriod":summarize((team.get("rosterForCurrentScoringPeriod") or {}).get("entries")),
                    }
        else:item["body"]=r.text[:300]
        rows.append(item)
        print(year,week,r.status_code,item.get("matchup_periods"),item.get("home",{}).get("keys"))
        time.sleep(.12)
    (OUT/"weekly_roster_semantics.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
if __name__=="__main__":main()
