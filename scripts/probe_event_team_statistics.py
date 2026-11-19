import json
from pathlib import Path

import requests

EVENT = 400554445
TEAMS = [33, 17]
BASES = [
    "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{event}/competitions/{event}/competitors/{team}/statistics",
    "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{event}/competitions/{event}/competitors/{team}/statistics/0",
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team}/statistics",
]
OUT = Path("artifacts/event_team_statistics_probe")
OUT.mkdir(parents=True, exist_ok=True)
session = requests.Session()
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0","Referer":"https://www.espn.com/"})


def main():
    results=[]
    for team in TEAMS:
        for template in BASES:
            url=template.format(event=EVENT,team=team)
            params={} if "sports.core.api" in url else {"season":2014,"event":EVENT}
            try:
                r=session.get(url,params=params,timeout=45)
                item={"team_id":team,"url":r.url,"status":r.status_code,"bytes":len(r.content)}
                if r.status_code==200:
                    data=r.json()
                    item["top_keys"]=list(data.keys())
                    item["sample"]=data
                else:
                    item["body"]=r.text[:500]
            except Exception as exc:
                item={"team_id":team,"url":url,"error":f"{type(exc).__name__}: {exc}"}
            results.append(item)
            print(team,item.get("status"),url,item.get("top_keys"))
    (OUT/"event_team_statistics_probe.json").write_text(json.dumps(results,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
