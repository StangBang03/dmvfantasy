import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

LEAGUE_ID=112536
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory"
OUT=Path("artifacts/matchup_split")
CASES=[
    (2014,1428,"Peyton Manning",[(14,14),(15,14),(16,15),(17,15),(16,16),(17,17),(16,None),(17,None)]),
    (2014,5941,"Wes Welker",[(14,14),(15,14),(16,15),(17,15)]),
    (2017,2576434,"Melvin Gordon",[(14,14),(15,15),(16,16),(17,16)]),
]
load_dotenv()
s2,swid=os.getenv("ESPN_S2"),os.getenv("ESPN_SWID")
if not s2 or not swid: raise RuntimeError("Missing ESPN credentials")
session=requests.Session()
session.cookies.update({"espn_s2":s2,"SWID":swid})
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for year,pid,name,combos in CASES:
        for sp,mp in combos:
            params=[("view","mBoxscore"),("seasonId",str(year)),("scoringPeriodId",str(sp))]
            if mp is not None: params.append(("matchupPeriodId",str(mp)))
            response=session.get(f"{BASE}/{LEAGUE_ID}",params=params,timeout=60)
            item={"season":year,"player_id":pid,"player_name":name,"scoring_period":sp,"matchup_period_param":mp,"http_status":response.status_code}
            if response.status_code==200:
                payload=response.json()
                data=payload[0] if isinstance(payload,list) and payload else payload
                matches=[]
                for m in data.get("schedule") or []:
                    for side_name in ("home","away"):
                        side=m.get(side_name) or {}
                        roster=side.get("rosterForMatchupPeriod") or {}
                        for entry in roster.get("entries") or []:
                            pool=entry.get("playerPoolEntry") or {}
                            player=pool.get("player") or {}
                            if (entry.get("playerId") or player.get("id"))==pid:
                                matches.append({
                                    "matchup_id":m.get("id"),
                                    "returned_matchup_period":m.get("matchupPeriodId"),
                                    "team_id":side.get("teamId"),
                                    "side":side_name,
                                    "lineup_slot_id":entry.get("lineupSlotId"),
                                    "appliedStat":pool.get("appliedStat"),
                                    "appliedStatTotal":pool.get("appliedStatTotal"),
                                    "entry_appliedStat":entry.get("appliedStat"),
                                })
                item["returned_periods"]=sorted({m.get("matchupPeriodId") for m in data.get("schedule") or [] if m.get("matchupPeriodId") is not None})
                item["player_rows"]=matches
            else:
                item["body_sample"]=response.text[:300]
            results.append(item)
            print(f"{year} {name} SP{sp}/MP{mp}: HTTP {response.status_code}; periods={item.get('returned_periods')}; rows={item.get('player_rows')}")
            time.sleep(0.2)
    path=OUT/"matchup_split_probe.json"
    path.write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(f"Wrote {path}")


if __name__=="__main__": main()
