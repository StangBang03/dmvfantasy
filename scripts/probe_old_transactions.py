import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

LEAGUE_ID=112536
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory"
OUT=Path("artifacts/old_transactions")
s=requests.Session()
s.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
s.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})
if not s.cookies.get("espn_s2") or not s.cookies.get("SWID"): raise RuntimeError("Missing ESPN credentials")


def unwrap(payload):
    if isinstance(payload,list) and len(payload)==1 and isinstance(payload[0],dict): return payload[0]
    return payload if isinstance(payload,dict) else {}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for year in range(2011,2018):
        for view in ("mTransactions","mTransactions2"):
            periods=[None,1,5,10,14,17]
            for sp in periods:
                params=[("view",view),("seasonId",str(year))]
                if sp is not None: params.append(("scoringPeriodId",str(sp)))
                url=f"{BASE}/{LEAGUE_ID}"
                r=s.get(url,params=params,timeout=60)
                item={"season":year,"view":view,"scoring_period":sp,"http_status":r.status_code,"bytes":len(r.content)}
                if r.status_code==200:
                    data=unwrap(r.json())
                    txs=data.get("transactions") or []
                    ids=set()
                    type_counts=Counter()
                    status_counts=Counter()
                    for tx in txs:
                        type_counts[tx.get("type")]+=1
                        status_counts[tx.get("status")]+=1
                        for it in tx.get("items") or []:
                            if it.get("playerId") is not None: ids.add(int(it["playerId"]))
                    item.update({
                        "transactions":len(txs),
                        "unique_player_ids":len(ids),
                        "player_ids":sorted(ids),
                        "transaction_types":dict(type_counts),
                        "statuses":dict(status_counts),
                        "top_keys":list(data.keys())[:20],
                    })
                else:
                    item["body_sample"]=r.text[:500]
                results.append(item)
                print(f"{year} {view} SP{sp}: HTTP {r.status_code}; tx={item.get('transactions')}; players={item.get('unique_player_ids')}")
                time.sleep(0.12)
    path=OUT/"old_transaction_probe.json"
    path.write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(f"Wrote {path}")


if __name__=="__main__": main()
