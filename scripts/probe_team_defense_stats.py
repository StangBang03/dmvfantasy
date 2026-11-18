import json
import time
from pathlib import Path

import requests

OUT = Path("artifacts/team_defense")
TESTS = [
    ("negative_dst_gamelog", "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/-16033/gamelog", {"region":"us","lang":"en","season":2014}),
    ("team_gamelog_common", "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/teams/33/gamelog", {"region":"us","lang":"en","season":2014}),
    ("team_schedule", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/33/schedule", {"season":2014}),
    ("team_statistics", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/33/statistics", {"season":2014}),
    ("game_summary", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary", {"event":400554445}),
]
session = requests.Session()
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0","Referer":"https://www.espn.com/"})


def brief(data):
    result = {"top_keys": list(data.keys())[:50]}
    for key in ("events","schedule","boxscore","teams","statistics","header"):
        value = data.get(key)
        if isinstance(value, dict):
            result[key] = {"keys":list(value.keys())[:50]}
        elif isinstance(value, list):
            result[key] = {"count":len(value),"sample":value[:2]}
    if isinstance(data.get("boxscore"),dict):
        bx=data["boxscore"]
        result["boxscore_teams"]=bx.get("teams")
        result["boxscore_players_sample"]=(bx.get("players") or [])[:2]
    if isinstance(data.get("events"),list):
        result["events_sample"]=data["events"][:5]
    if isinstance(data.get("schedule"),dict):
        result["schedule_events"]=(data["schedule"].get("events") or [])[:5]
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for name,url,params in TESTS:
        response=session.get(url,params=params,timeout=60)
        item={"test":name,"url":response.url,"http_status":response.status_code,"response_bytes":len(response.content)}
        if response.status_code==200:
            try:
                data=response.json()
                item["brief"]=brief(data)
                item["raw"]=data
            except Exception as exc:
                item["parse_error"]=str(exc)
                item["body_sample"]=response.text[:1000]
        else:
            item["body_sample"]=response.text[:1000]
        results.append(item)
        print(f"{name}: HTTP {response.status_code}; bytes={item['response_bytes']}; keys={item.get('brief',{}).get('top_keys')}")
        time.sleep(0.2)
    path=OUT/"team_defense_probe.json"
    path.write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(f"Wrote {path}")


if __name__=="__main__":
    main()
