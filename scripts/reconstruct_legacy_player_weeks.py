import csv
import gzip
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import requests

PLAYER_CARD_DIR=Path("data/raw/playercard_history")
SUMMARY_DIR=Path("data/raw/legacy_game_summaries")
DEFENSIVE_DIR=Path("data/raw/legacy_defensive_gamelogs")
RAW_OUT=Path("data/processed/legacy_weekly_reconstruction")
ARTIFACT_OUT=Path("artifacts/legacy_weekly_reconstruction")
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
LEAGUE_ID=112536
YEARS=range(2011,2018)
session=requests.Session()
session.cookies.update({"espn_s2":os.getenv("ESPN_S2",""),"SWID":os.getenv("ESPN_SWID","")})
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})
if not session.cookies.get("espn_s2") or not session.cookies.get("SWID"):
    raise RuntimeError("Missing ESPN credentials")


def get_scoring_items(year):
    response=session.get(f"{BASE}/leagueHistory/{LEAGUE_ID}",params=[("view","mSettings"),("seasonId",str(year))],timeout=90)
    response.raise_for_status()
    payload=response.json()
    data=payload[0] if isinstance(payload,list) and payload else payload
    return ((data.get("settings") or {}).get("scoringSettings") or {}).get("scoringItems") or []


def n(value):
    if value is None: return 0.0
    if isinstance(value,(int,float)): return float(value)
    s=str(value).strip().replace(",","")
    if not s or s in ("-","--","N/A"): return 0.0
    try: return float(s)
    except ValueError: return 0.0


def pair(value):
    s=str(value or "").strip()
    if not s: return 0.0,0.0
    sep="/" if "/" in s else "-" if "-" in s else None
    if sep is None: return n(s),n(s)
    a,b=s.split(sep,1)
    return n(a),n(b)


def normalize_name(value):
    s=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]","",s)


def resolve_player(team_id,name,lookup):
    if not name: return None
    target=normalize_name(name)
    candidates=lookup.get(int(team_id),[])
    exact=[x for x in candidates if x[0]==target]
    if len(exact)==1: return exact[0][1]
    if not candidates: return None
    target_tokens=re.findall(r"[a-z0-9]+",str(name).lower())
    target_last=target_tokens[-1] if target_tokens else ""
    target_initial=target_tokens[0][0] if target_tokens and target_tokens[0] else ""
    scored=[]
    for norm,pid,display in candidates:
        tokens=re.findall(r"[a-z0-9]+",display.lower())
        last=tokens[-1] if tokens else ""
        initial=tokens[0][0] if tokens and tokens[0] else ""
        score=SequenceMatcher(None,target,norm).ratio()
        if target_last and last==target_last and target_initial and initial==target_initial:
            score=max(score,0.94)
        elif target_last and last==target_last:
            score=max(score,0.84)
        scored.append((score,pid))
    scored.sort(reverse=True)
    if scored and scored[0][0]>=0.82 and (len(scored)==1 or scored[0][0]-scored[1][0]>=0.04):
        return scored[0][1]
    return None


def parse_yardage(text):
    m=re.search(r"\b(\d+)\s+Yd\b",str(text or ""),re.I)
    return int(m.group(1)) if m else None


def extract_player_values(groups):
    groups=groups or {}
    passing=groups.get("passing") or {}
    rushing=groups.get("rushing") or {}
    receiving=groups.get("receiving") or {}
    fumbles=groups.get("fumbles") or {}
    kicking=groups.get("kicking") or {}
    kick_returns=groups.get("kickReturns") or {}
    punt_returns=groups.get("puntReturns") or {}
    values={}
    passing_yards=n(passing.get("passingYards"))
    rushing_yards=n(rushing.get("rushingYards"))
    receiving_yards=n(receiving.get("receivingYards"))
    values[4]=n(passing.get("passingTouchdowns"))
    values[8]=int(passing_yards/25)
    values[17]=1 if 300<=passing_yards<400 else 0
    values[18]=1 if passing_yards>=400 else 0
    values[20]=n(passing.get("interceptions"))
    values[25]=n(rushing.get("rushingTouchdowns"))
    values[28]=max(0,int(rushing_yards/10))
    values[37]=1 if 100<=rushing_yards<200 else 0
    values[38]=1 if rushing_yards>=200 else 0
    receptions=n(receiving.get("receptions"))
    values[41]=receptions
    values[43]=n(receiving.get("receivingTouchdowns"))
    values[48]=int(receiving_yards/10)
    values[53]=receptions
    values[56]=1 if 100<=receiving_yards<200 else 0
    values[57]=1 if receiving_yards>=200 else 0
    if "fumblesLost" in fumbles:
        values[72]=n(fumbles.get("fumblesLost"))
    # Return yards and return touchdowns are also scored for individual players in some league seasons.
    kick_yards=n(kick_returns.get("kickReturnYards"))
    punt_yards=n(punt_returns.get("puntReturnYards"))
    values[101]=n(kick_returns.get("kickReturnTouchdowns"))
    values[102]=n(punt_returns.get("puntReturnTouchdowns"))
    values[117]=int(kick_yards/25)
    values[119]=int(punt_yards/25)
    # Kicking: support ESPN's combined made-attempted fields across historical naming variants.
    def fg_value(names):
        for name in names:
            if name in kicking:
                return pair(kicking[name])
        return 0.0,0.0
    made_1_19,att_1_19=fg_value(["fieldGoalsMade1_19-fieldGoalAttempts1_19"])
    made_20_29,att_20_29=fg_value(["fieldGoalsMade20_29-fieldGoalAttempts20_29"])
    made_30_39,att_30_39=fg_value(["fieldGoalsMade30_39-fieldGoalAttempts30_39"])
    made_40_49,att_40_49=fg_value(["fieldGoalsMade40_49-fieldGoalAttempts40_49"])
    made_50,att_50=fg_value(["fieldGoalsMade50-fieldGoalAttempts50","fieldGoalsMade50_59-fieldGoalAttempts50_59"])
    made_60,att_60=fg_value(["fieldGoalsMade60Plus-fieldGoalAttempts60Plus"])
    made_total,att_total=fg_value(["fieldGoalsMade-fieldGoalAttempts"])
    if not att_total:
        made_total=made_1_19+made_20_29+made_30_39+made_40_49+made_50+made_60
        att_total=att_1_19+att_20_29+att_30_39+att_40_49+att_50+att_60
    values[74]=made_50+made_60
    values[75]=att_50+att_60
    values[77]=made_40_49
    values[80]=made_1_19+made_20_29+made_30_39
    values[85]=max(0,att_total-made_total)
    if "extraPointsMade-extraPointAttempts" in kicking:
        made_pat,att_pat=pair(kicking["extraPointsMade-extraPointAttempts"])
        values[86]=made_pat
        values[88]=max(0,att_pat-made_pat)
    return values


def apply_scoring_plays(event,player_values,dst_values,name_lookup,unmatched):
    for play in event.get("scoring_plays") or []:
        team_id=play.get("team_id")
        if team_id is None: continue
        team_id=int(team_id)
        typ=str(play.get("type") or "")
        low=typ.lower()
        text=str(play.get("text") or "")
        text_low=text.lower()
        yardage=parse_yardage(text)
        scoring_type=play.get("scoring_type") or {}
        scoring_name=(scoring_type.get("name") or "") if isinstance(scoring_type,dict) else str(scoring_type)
        is_td="touchdown" in low or "touchdown" in text_low

        if "pass from" in text_low and is_td:
            m=re.match(r"^(.*?)\s+(\d+)\s+Yd pass from (.*?)(?:\s+\(|$)",text,re.I)
            if m:
                receiver_name,yd,passer_name=m.group(1),int(m.group(2)),m.group(3)
                passer=resolve_player(team_id,passer_name,name_lookup)
                receiver=resolve_player(team_id,receiver_name,name_lookup)
                if passer is not None and yd>=40: player_values[passer][15]+=1
                if passer is not None and yd>=50: player_values[passer][16]+=1
                if receiver is not None and yd>=40: player_values[receiver][45]+=1
                if receiver is not None and yd>=50: player_values[receiver][46]+=1
                if passer is None or receiver is None:
                    unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"passing TD player match"})
        elif "rushing touchdown" in low or re.search(r"\bYd Run\b",text,re.I):
            m=re.match(r"^(.*?)\s+(\d+)\s+Yd Run",text,re.I)
            if m:
                player=resolve_player(team_id,m.group(1),name_lookup)
                yd=int(m.group(2))
                if player is not None and yd>=40: player_values[player][35]+=1
                if player is not None and yd>=50: player_values[player][36]+=1
                if player is None:
                    unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"rushing TD player match"})

        if "kickoff return touchdown" in low or "kickoff return" in text_low and is_td:
            m=re.match(r"^(.*?)\s+(\d+)\s+Yd Kickoff Return",text,re.I)
            if m:
                player=resolve_player(team_id,m.group(1),name_lookup)
                dst_values[team_id][101]+=1
                if player is not None: player_values[player][101]=max(player_values[player][101],1)
                else: unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"kick return TD player match"})
        if "punt return touchdown" in low or "punt return" in text_low and is_td:
            m=re.match(r"^(.*?)\s+(\d+)\s+Yd Punt Return",text,re.I)
            if m:
                player=resolve_player(team_id,m.group(1),name_lookup)
                dst_values[team_id][102]+=1
                if player is not None: player_values[player][102]=max(player_values[player][102],1)
                else: unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"punt return TD player match"})
        if "interception return touchdown" in low or "interception return" in text_low and is_td:
            dst_values[team_id][103]+=1
        if "fumble return touchdown" in low or "fumble return" in text_low and is_td:
            dst_values[team_id][104]+=1
            m=re.match(r"^(.*?)\s+(\d+)\s+Yd Fumble Return",text,re.I)
            if m:
                player=resolve_player(team_id,m.group(1),name_lookup)
                if player is not None: player_values[player][63]+=1
                else: unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"fumble return TD player match"})
        if ("blocked punt" in low or "blocked field goal" in low or "blocked kick" in low) and is_td:
            dst_values[team_id][93]+=1

        if "two-point" in low or "two point" in low or "two-point" in text_low or "two point" in text_low or "2pt" in text_low or "2-point" in text_low or "two-point-conversion" in str(scoring_name).lower():
            if "pass from" in text_low:
                m=re.match(r"^(.*?)\s+(?:\d+\s+Yd\s+)?pass from (.*?)(?:\s+\(|$)",text,re.I)
                if m:
                    receiver=resolve_player(team_id,m.group(1),name_lookup)
                    passer=resolve_player(team_id,m.group(2),name_lookup)
                    if passer is not None: player_values[passer][19]+=1
                    if receiver is not None: player_values[receiver][44]+=1
                    if passer is None or receiver is None: unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"passing 2pt player match"})
            elif re.search(r"\b(run|rush)\b",text_low) or "rushing" in low:
                m=re.match(r"^(.*?)\s+(?:\d+\s+Yd\s+)?(?:Run|Rush)",text,re.I)
                if m:
                    player=resolve_player(team_id,m.group(1),name_lookup)
                    if player is not None: player_values[player][26]+=1
                    else: unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"rushing 2pt player match"})
            elif "return" in low or "return" in text_low:
                dst_values[team_id][206]+=1
            else:
                unmatched.append({"event_id":event.get("event_id"),"type":typ,"text":text,"reason":"unclassified 2pt conversion"})

        if "safety" in low or "safety" in text_low:
            if "one-point" in low or "one point" in low or "one-point" in text_low or "one point" in text_low:
                dst_values[team_id][209]+=1
            else:
                dst_values[team_id][98]+=1


def dst_values_for_event(event,dst_team_ids,extra_defense):
    result={}
    teams=event.get("teams") or []
    scores=event.get("scores") or {}
    team_by_id={int(t["team_id"]):t for t in teams if t.get("team_id") is not None}
    players_by_team=defaultdict(list)
    for p in event.get("players") or []:
        if p.get("team_id") is not None: players_by_team[int(p["team_id"])].append(p)
    for team_id in dst_team_ids:
        if team_id not in team_by_id: continue
        opponent_ids=[tid for tid in team_by_id if tid!=team_id]
        if not opponent_ids: continue
        opponent_id=opponent_ids[0]
        opp=team_by_id[opponent_id].get("statistics") or {}
        points_allowed=n((scores.get(str(opponent_id)) or {}).get("score"))
        yards_allowed=n(opp.get("totalYards"))
        sacks,_=pair(opp.get("sacksYardsLost"))
        interceptions=n(opp.get("interceptions"))
        fumbles_recovered=n(opp.get("fumblesLost"))
        kick_yards=sum(n((p.get("groups") or {}).get("kickReturns",{}).get("kickReturnYards")) for p in players_by_team[team_id])
        punt_yards=sum(n((p.get("groups") or {}).get("puntReturns",{}).get("puntReturnYards")) for p in players_by_team[team_id])
        extra=(extra_defense.get(f"{team_id}:{int(event.get('week') or 0)}") or {})
        values={
            95:interceptions,
            96:fumbles_recovered,
            97:n(extra.get("kicks_blocked")),
            99:sacks,
            106:n(extra.get("fumbles_forced")),
            117:int(kick_yards/25),
            119:int(punt_yards/25),
        }
        # Points-allowed buckets: 89=0, 90=1-6, 91=7-13, 92=14-17,
        # 121=18-21, 122=22-27, 123=28-34, 124=35-45, 125=46+.
        buckets=[(89,0,0),(90,1,6),(91,7,13),(92,14,17),(121,18,21),(122,22,27),(123,28,34),(124,35,45),(125,46,10**9)]
        for sid,lo,hi in buckets:
            if lo<=points_allowed<=hi: values[sid]=1
        # Yards-allowed buckets: 128=<100, 129=100-199, 130=200-299,
        # 131=300-349, 132=350-399, 133=400-449, 134=450-499,
        # 135=500-549, 136=550+.
        yard_buckets=[(128,0,99),(129,100,199),(130,200,299),(131,300,349),(132,350,399),(133,400,449),(134,450,499),(135,500,549),(136,550,10**9)]
        for sid,lo,hi in yard_buckets:
            if lo<=yards_allowed<=hi: values[sid]=1
        result[team_id]=values
    return result


def calculate_points(values,items,is_dst=False):
    total=0.0
    for item in items:
        sid=int(item["statId"])
        points=item.get("points",0)
        overrides=item.get("pointsOverrides") or {}
        if is_dst and "16" in overrides: points=overrides["16"]
        total+=n(values.get(sid,0))*n(points)
    return round(total,4)


def main():
    RAW_OUT.mkdir(parents=True,exist_ok=True)
    ARTIFACT_OUT.mkdir(parents=True,exist_ok=True)
    audit={"seasons":{},"errors":[]}
    for year in YEARS:
        pc_path=PLAYER_CARD_DIR/f"playercard_{year}.json.gz"
        sm_path=SUMMARY_DIR/f"legacy_game_summaries_{year}.json.gz"
        if not pc_path.exists() or not sm_path.exists():
            audit["errors"].append({"season":year,"error":"Missing player-card or game-summary archive"})
            continue
        with gzip.open(pc_path,"rt",encoding="utf-8") as f: pc=json.load(f)
        with gzip.open(sm_path,"rt",encoding="utf-8") as f: summaries=json.load(f)
        items=get_scoring_items(year)
        players={int(p["player_id"]):p for p in pc.get("players") or []}
        dst_player_by_team={}
        for pid,p in players.items():
            if pid<0 and p.get("pro_team_id") is not None: dst_player_by_team[int(p["pro_team_id"])]=pid
        dst_team_ids=set(dst_player_by_team)
        extra_defense={}
        def_path=DEFENSIVE_DIR/f"legacy_defensive_gamelogs_{year}.json.gz"
        if def_path.exists():
            with gzip.open(def_path,"rt",encoding="utf-8") as f: defense=json.load(f)
            extra_defense=defense.get("team_week_counts") or {}
        player_week_values=defaultdict(lambda:defaultdict(float))
        dst_week_values=defaultdict(lambda:defaultdict(float))
        unmatched=[]
        failed_events=[]
        summary_player_presence=Counter()
        for event in summaries.get("events") or []:
            if event.get("http_status")!=200:
                failed_events.append({"event_id":event.get("event_id"),"status":event.get("http_status")})
                continue
            week=int(event.get("week") or 0)
            if not 1<=week<=17:
                continue
            name_lookup=defaultdict(list)
            for p in event.get("players") or []:
                if p.get("team_id") is not None:
                    name_lookup[int(p["team_id"])].append((normalize_name(p.get("name")),int(p["player_id"]),p.get("name") or ""))
            for p in event.get("players") or []:
                pid=int(p["player_id"])
                if pid not in players or pid<0: continue
                vals=extract_player_values(p.get("groups") or {})
                target=player_week_values[(pid,week)]
                for sid,value in vals.items(): target[sid]+=value
                summary_player_presence[pid]+=1
            # Scoring-play extras (long TD bonuses, two-point conversions, defensive return TDs).
            player_extra=defaultdict(lambda:defaultdict(float))
            dst_extra=defaultdict(lambda:defaultdict(float))
            apply_scoring_plays(event,player_extra,dst_extra,name_lookup,unmatched)
            for pid,vals in player_extra.items():
                for sid,value in vals.items(): player_week_values[(pid,week)][sid]+=value
            for tid,vals in dst_extra.items():
                if tid not in dst_player_by_team:
                    unmatched.append({"event_id":event.get("event_id"),"team_id":tid,"reason":"scoring play team has no fantasy DST player-season record"})
                    continue
                for sid,value in vals.items(): dst_week_values[(dst_player_by_team[tid],week)][sid]+=value
            # Team defense stats and points/yards allowed.
            for tid,vals in dst_values_for_event(event,dst_team_ids,extra_defense).items():
                pid=dst_player_by_team[tid]
                for sid,value in vals.items(): dst_week_values[(pid,week)][sid]+=value
        season_records=[]
        all_mismatches=[]
        stat_gap_counts=Counter()
        total_week_rows=0
        for pid,player in players.items():
            is_dst=pid<0
            week_values=dst_week_values if is_dst else player_week_values
            weeks={}
            stat_sums=defaultdict(float)
            for week in range(1,18):
                vals=dict(week_values.get((pid,week),{}))
                points=calculate_points(vals,items,is_dst=is_dst)
                for sid,value in vals.items(): stat_sums[int(sid)]+=n(value)
                weeks[str(week)]={"week":week,"fantasy_points":points,"stats":{str(k):v for k,v in sorted(vals.items()) if v}}
                total_week_rows+=1
            calculated=round(sum(x["fantasy_points"] for x in weeks.values()),4)
            expected=player.get("season_total")
            mismatch=None
            if expected is not None and abs(calculated-float(expected))>0.02:
                mismatch={"player_id":pid,"name":player.get("player_name"),"position_id":player.get("position_id"),"season_total":expected,"weekly_sum":calculated,"difference":round(float(expected)-calculated,4)}
            gaps=[]
            season_stats=player.get("season_stats") or {}
            for item in items:
                sid=int(item["statId"])
                points=item.get("points",0)
                overrides=item.get("pointsOverrides") or {}
                if is_dst: points=overrides.get("16",points)
                if n(points)==0: continue
                expected_stat=n(season_stats.get(str(sid),0))
                actual_stat=stat_sums.get(sid,0)
                if abs(expected_stat-actual_stat)>0.01:
                    gaps.append({"stat_id":sid,"expected_stat":expected_stat,"weekly_stat_sum":actual_stat,"points":n(points)})
                    stat_gap_counts[sid]+=1
            if mismatch:
                mismatch["stat_gaps"]=gaps
                all_mismatches.append(mismatch)
            season_records.append({
                "season":year,
                "player_id":pid,
                "player_name":player.get("player_name"),
                "position_id":player.get("position_id"),
                "pro_team_id":player.get("pro_team_id"),
                "season_fantasy_points":expected,
                "calculated_weekly_points":calculated,
                "season_total_match":mismatch is None,
                "weeks":weeks,
                "season_stats":season_stats,
                "data_source":"ESPN NFL game summaries + ESPN league scoring settings",
            })
        season_records.sort(key=lambda x:x["player_id"])
        output={"meta":{"season":year,"player_count":len(season_records),"source":"ESPN historical game summaries","weeks":17},"players":season_records}
        raw_path=RAW_OUT/f"legacy_weekly_reconstruction_{year}.json.gz"
        with gzip.open(raw_path,"wt",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,separators=(",",":"))
        csv_path=ARTIFACT_OUT/f"legacy_weekly_points_{year}.csv"
        with csv_path.open("w",newline="",encoding="utf-8") as f:
            writer=csv.writer(f)
            writer.writerow(["season","player_id","player_name","position_id","week","fantasy_points"])
            for record in season_records:
                for week,entry in record["weeks"].items():
                    writer.writerow([year,record["player_id"],record["player_name"],record["position_id"],week,entry["fantasy_points"]])
        audit["seasons"][str(year)]={
            "player_seasons_reconstructed":len(season_records),
            "positive_player_seasons":sum(1 for x in season_records if x["player_id"]>0),
            "dst_seasons":sum(1 for x in season_records if x["player_id"]<0),
            "weekly_rows":total_week_rows,
            "season_total_matches":sum(1 for x in season_records if x["season_total_match"]),
            "season_total_mismatches":len(all_mismatches),
            "stat_gap_counts":dict(stat_gap_counts),
            "unmatched_scoring_plays":len(unmatched),
            "unmatched_scoring_play_sample":unmatched[:60],
            "failed_summary_events":failed_events,
            "mismatch_sample":all_mismatches[:80],
            "defensive_gamelog_available":def_path.exists(),
        }
        print(f"{year}: players={len(season_records)} matched={audit['seasons'][str(year)]['season_total_matches']} mismatches={len(all_mismatches)} stat_gaps={dict(stat_gap_counts)} unmatched_plays={len(unmatched)}")
    (ARTIFACT_OUT/"legacy_weekly_reconstruction_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
    (RAW_OUT/"legacy_weekly_reconstruction_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")


if __name__=="__main__":main()
