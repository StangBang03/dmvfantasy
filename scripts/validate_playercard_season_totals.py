import gzip
import json
import os
from collections import Counter
from pathlib import Path

import requests

LEAGUE_ID=112536
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
ARCHIVE_DIR=Path("data/raw/playercard_history")
OUT=Path("artifacts/playercard_scoring_validation")
session=requests.Session()
session.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})
if not session.cookies.get("espn_s2") or not session.cookies.get("SWID"): raise RuntimeError("Missing ESPN credentials")


def settings_for(year):
    if year>=2018:
        url=f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
        params=[("view","mSettings")]
    else:
        url=f"{BASE}/leagueHistory/{LEAGUE_ID}"
        params=[("view","mSettings"),("seasonId",str(year))]
    response=session.get(url,params=params,timeout=90)
    response.raise_for_status()
    payload=response.json()
    data=payload[0] if isinstance(payload,list) and payload else payload
    settings=data.get("settings") or {}
    return settings.get("scoringSettings") or {}


def calculate(record,items):
    stats=record.get("season_stats") or {}
    is_dst=int(record.get("position_id") or 0)==16
    total=0.0
    details=[]
    for item in items:
        try: stat_id=int(item["statId"])
        except (KeyError,TypeError,ValueError): continue
        value=stats.get(str(stat_id),stats.get(stat_id,0))
        try: value=float(value or 0)
        except (TypeError,ValueError): value=0.0
        points=item.get("points",0)
        overrides=item.get("pointsOverrides") or {}
        if is_dst and "16" in overrides:
            points=overrides["16"]
        try: points=float(points or 0)
        except (TypeError,ValueError): points=0.0
        contribution=value*points
        total+=contribution
        if value:
            details.append({"stat_id":stat_id,"value":value,"points":points,"contribution":contribution})
    return round(total,4),details


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={"seasons":{},"errors":[]}
    for path in sorted(ARCHIVE_DIR.glob("playercard_*.json.gz")):
        year=int(path.stem.split("_")[-1].split(".")[0])
        try:
            with gzip.open(path,"rt",encoding="utf-8") as f: archive=json.load(f)
            scoring=settings_for(year)
            items=scoring.get("scoringItems") or []
            mismatches=[]
            missing_totals=[]
            weekly_mismatches=[]
            matched=0
            weekly_matched=0
            position_counts=Counter()
            for player in archive.get("players") or []:
                position=int(player.get("position_id") or 0)
                position_counts[position]+=1
                expected=player.get("season_total")
                if expected is None:
                    missing_totals.append(player.get("player_id"))
                    continue
                calculated,details=calculate(player,items)
                if abs(calculated-float(expected))<=0.02:
                    matched+=1
                else:
                    mismatches.append({
                        "player_id":player.get("player_id"),
                        "name":player.get("player_name"),
                        "position_id":position,
                        "season_total":expected,
                        "calculated":calculated,
                        "difference":round(float(expected)-calculated,4),
                        "nonzero_scoring_items":details,
                    })
                weeks=player.get("weeks") or {}
                if weeks:
                    weekly_sum=sum(float((week or {}).get("fantasy_points") or 0) for week in weeks.values())
                    if abs(weekly_sum-float(expected))<=0.02:
                        weekly_matched+=1
                    else:
                        weekly_mismatches.append({
                            "player_id":player.get("player_id"),
                            "name":player.get("player_name"),
                            "season_total":expected,
                            "weekly_sum":round(weekly_sum,4),
                            "difference":round(float(expected)-weekly_sum,4),
                        })
            report["seasons"][str(year)]={
                "player_count":len(archive.get("players") or []),
                "roster_history_rows":len(archive.get("roster_history") or []),
                "players_with_weekly_stats":sum(1 for p in archive.get("players") or [] if p.get("weeks")),
                "scoring_items":len(items),
                "matched_totals":matched,
                "mismatch_count":len(mismatches),
                "weekly_sum_matches":weekly_matched,
                "weekly_sum_mismatch_count":len(weekly_mismatches),
                "weekly_sum_mismatch_sample":weekly_mismatches[:30],
                "missing_season_totals":missing_totals,
                "position_counts":dict(position_counts),
                "mismatch_sample":mismatches[:30],
            }
            print(f"{year}: players={len(archive.get('players') or [])}; scoring items={len(items)}; matched={matched}; mismatches={len(mismatches)}; weekly matches={weekly_matched}; weekly mismatches={len(weekly_mismatches)}; missing totals={len(missing_totals)}")
        except Exception as exc:
            report["errors"].append({"season":year,"error":f"{type(exc).__name__}: {exc}"})
            print(f"{year}: ERROR {type(exc).__name__}: {exc}")
    (OUT/"playercard_scoring_validation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


if __name__=="__main__": main()
