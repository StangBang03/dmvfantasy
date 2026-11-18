import gzip
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

import requests

ARCHIVE_DIR=Path("data/raw/playercard_history")
GAMELOG_DIR=Path("artifacts/legacy_player_gamelogs")
OUT=Path("artifacts/legacy_gamelog_reconciliation")
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
LEAGUE_ID=112536
session=requests.Session()
session.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})


def get_scoring_items(year):
    if year>=2018:
        url=f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
        params=[("view","mSettings")]
    else:
        url=f"{BASE}/leagueHistory/{LEAGUE_ID}"
        params=[("view","mSettings"),("seasonId",str(year))]
    r=session.get(url,params=params,timeout=90)
    r.raise_for_status()
    payload=r.json()
    data=payload[0] if isinstance(payload,list) and payload else payload
    return ((data.get("settings") or {}).get("scoringSettings") or {}).get("scoringItems") or []


def num(value):
    if value is None: return 0.0
    if isinstance(value,(int,float)): return float(value)
    s=str(value).strip().replace(",","")
    if not s or s in ("-","--","N/A"): return 0.0
    try: return float(s)
    except ValueError: return 0.0


def pair(value):
    s=str(value or "0-0").strip()
    if "/" in s: sep="/"
    elif "-" in s: sep="-"
    else: return num(s),num(s)
    a,b=s.split(sep,1)
    return num(a),num(b)


def stat_values(raw):
    pyd=num(raw.get("passingYards"))
    ryd=num(raw.get("rushingYards"))
    recyd=num(raw.get("receivingYards"))
    ptd=num(raw.get("passingTouchdowns"))
    rtd=num(raw.get("rushingTouchdowns"))
    rectd=num(raw.get("receivingTouchdowns"))
    receptions=num(raw.get("receptions"))
    fumbles_lost=num(raw.get("fumblesLost")) if "fumblesLost" in raw else None
    values={
        4:ptd, 8:int(pyd/25), 17:1 if 300<=pyd<400 else 0, 18:1 if pyd>=400 else 0,
        20:num(raw.get("interceptions")), 25:rtd, 28:int(ryd/10),
        37:1 if 100<=ryd<200 else 0, 38:1 if ryd>=200 else 0,
        41:receptions, 43:rectd, 48:int(recyd/10),
        53:receptions, 56:1 if 100<=recyd<200 else 0, 57:1 if recyd>=200 else 0,
    }
    if fumbles_lost is not None: values[72]=fumbles_lost
    fg_fields=[
        ("fieldGoalsMade1_19-fieldGoalAttempts1_19",1),
        ("fieldGoalsMade20_29-fieldGoalAttempts20_29",1),
        ("fieldGoalsMade30_39-fieldGoalAttempts30_39",1),
        ("fieldGoalsMade40_49-fieldGoalAttempts40_49",1),
        ("fieldGoalsMade50_59-fieldGoalAttempts50_59",1),
        ("fieldGoalsMade60Plus-fieldGoalAttempts60Plus",1),
    ]
    made={}; attempts={}
    for name,_ in fg_fields:
        if name in raw:
            m,a=pair(raw[name])
            stem=name.split("-")[0].replace("fieldGoalsMade","")
            made[stem]=m; attempts[stem]=a
    if made:
        values[74]=made.get("50_59",0)+made.get("60Plus",0)
        values[75]=attempts.get("50_59",0)+attempts.get("60Plus",0)
        values[77]=made.get("40_49",0)
        values[80]=made.get("1_19",0)+made.get("20_29",0)+made.get("30_39",0)
        values[85]=sum(attempts.values())-sum(made.values())
    if "extraPointsMade-extraPointAttempts" in raw:
        m,a=pair(raw["extraPointsMade-extraPointAttempts"])
        values[86]=m; values[88]=a-m
    return values


def calc_points(values,items):
    total=0.0
    used=set()
    for item in items:
        try: sid=int(item["statId"])
        except (KeyError,TypeError,ValueError): continue
        points=num(item.get("points"))
        total+=num(values.get(sid,0))*points
        used.add(sid)
    return round(total,4),used


def season_total_from_stats(player,items):
    stats=player.get("season_stats") or {}
    dst=int(player.get("position_id") or 0)==16
    total=0.0
    for item in items:
        try: sid=int(item["statId"])
        except (KeyError,TypeError,ValueError): continue
        points=item.get("points",0)
        overrides=item.get("pointsOverrides") or {}
        if dst and "16" in overrides: points=overrides["16"]
        total+=num(stats.get(str(sid),stats.get(sid,0)))*num(points)
    return round(total,4)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={"seasons":{},"errors":[]}
    for year in range(2011,2018):
        archive_path=ARCHIVE_DIR/f"playercard_{year}.json.gz"
        gamelog_path=GAMELOG_DIR/f"legacy_player_gamelogs_{year}.json.gz"
        if not archive_path.exists() or not gamelog_path.exists():
            report["errors"].append({"season":year,"error":"Missing playercard or gamelog archive"})
            continue
        with gzip.open(archive_path,"rt",encoding="utf-8") as f: archive=json.load(f)
        with gzip.open(gamelog_path,"rt",encoding="utf-8") as f: gamelog=json.load(f)
        items=get_scoring_items(year)
        players={int(p["player_id"]):p for p in archive.get("players") or []}
        logs={int(p["player_id"]):p for p in gamelog.get("players") or []}
        mismatches=[]
        exact=0
        no_gamelog=[]
        stat_gaps=Counter()
        unsupported=Counter()
        for pid,player in players.items():
            if pid<0 or int(player.get("position_id") or 0)==16: continue
            log=logs.get(pid)
            if not log or log.get("http_status")!=200:
                no_gamelog.append(pid); continue
            weekly_sum=0.0
            per_stat_totals=defaultdict(float)
            for event in log.get("events") or []:
                values=stat_values(event.get("stats") or {})
                points,_=calc_points(values,items)
                weekly_sum+=points
                for sid,val in values.items(): per_stat_totals[sid]+=val
            expected=num(player.get("season_total"))
            season_calc=season_total_from_stats(player,items)
            if abs(season_calc-expected)>0.02:
                stat_gaps["season_settings_mismatch"]+=1
            diff=round(expected-weekly_sum,4)
            if abs(diff)<=0.02:
                exact+=1
            else:
                season_stats=player.get("season_stats") or {}
                gaps=[]
                for item in items:
                    sid=int(item["statId"])
                    expected_stat=num(season_stats.get(str(sid),0))
                    actual_stat=per_stat_totals.get(sid,0)
                    if abs(expected_stat-actual_stat)>0.01:
                        gaps.append({"stat_id":sid,"expected_stat":expected_stat,"gamelog_stat":actual_stat,"points":item.get("points")})
                        stat_gaps[sid]+=1
                mismatches.append({
                    "player_id":pid,"name":player.get("player_name"),"position_id":player.get("position_id"),
                    "season_total":expected,"calculated_from_gamelog":weekly_sum,"difference":diff,
                    "season_total_from_scoring_items":season_calc,"stat_gaps":gaps,
                })
        report["seasons"][str(year)]={
            "player_count":len(players),
            "gamelog_player_count":len(logs),
            "exact_weekly_sum_matches":exact,
            "mismatch_count":len(mismatches),
            "players_without_gamelog":no_gamelog,
            "stat_gap_counts":dict(stat_gaps),
            "mismatch_sample":mismatches[:60],
        }
        print(f"{year}: exact weekly totals={exact}; mismatches={len(mismatches)}; no gamelog={len(no_gamelog)}; gaps={dict(stat_gaps)}")
    (OUT/"legacy_gamelog_reconciliation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


if __name__=="__main__":main()
