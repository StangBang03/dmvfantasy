from __future__ import annotations
import json
from collections import defaultdict
from statistics import mean
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"

def load(name):
    with (PROCESSED / name).open("r", encoding="utf-8") as f:
        return json.load(f)

def save(name, data):
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    with (ANALYTICS / name).open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

def pct(n, d):
    return round(n / d, 4) if d else None

def build_indexes(people, teams, matchups):
    people_by_id = {p["person_id"]: p for p in people}
    team_by_key = {(int(t["season"]), int(t["team_id"])): t for t in teams}
    h2h = []
    for m in matchups:
        home, away = m.get("home_team_id"), m.get("away_team_id")
        hs, aws = m.get("home_score"), m.get("away_score")
        if None in (home, away, hs, aws):
            continue
        ht = team_by_key.get((int(m["season"]), int(home)))
        at = team_by_key.get((int(m["season"]), int(away)))
        if not ht or not at:
            continue
        h2h.append({
            "season": m["season"], "matchup_id": m["matchup_id"],
            "matchup_period_id": m["matchup_period_id"],
            "home_team_id": home, "away_team_id": away,
            "home_person_id": ht["person_id"], "away_person_id": at["person_id"],
            "home_score": hs, "away_score": aws,
            "margin": round(abs(hs - aws), 2)
        })
    return people_by_id, h2h

def season_stats(teams):
    out = []
    for t in teams:
        w, l, ti = t.get("wins") or 0, t.get("losses") or 0, t.get("ties") or 0
        g = w + l + ti
        out.append({
            "season": t["season"], "person_id": t["person_id"],
            "team_id": t["team_id"], "team_name": t["team_name"],
            "wins": w, "losses": l, "ties": ti, "games": g,
            "win_pct": pct(w + ti * .5, g),
            "points_for": t.get("points_for"),
            "points_against": t.get("points_against"),
            "rank": t.get("rank"), "playoff_seed": t.get("playoff_seed")
        })
    return out

def career_stats(people, seasons):
    grouped = defaultdict(list)
    for r in seasons: grouped[r["person_id"]].append(r)
    out = []
    for p in people:
        rows = sorted(grouped.get(p["person_id"], []), key=lambda x: x["season"])
        w = sum(r["wins"] for r in rows); l = sum(r["losses"] for r in rows)
        ti = sum(r["ties"] for r in rows); g = w + l + ti
        pf = [r["points_for"] for r in rows if r["points_for"] is not None]
        pa = [r["points_against"] for r in rows if r["points_against"] is not None]
        out.append({
            "person_id": p["person_id"], "name": p["name"], "seasons": len(rows),
            "first_season": min((r["season"] for r in rows), default=None),
            "last_season": max((r["season"] for r in rows), default=None),
            "wins": w, "losses": l, "ties": ti, "games": g,
            "win_pct": pct(w + ti * .5, g),
            "points_for": round(sum(pf), 2) if pf else None,
            "points_against": round(sum(pa), 2) if pa else None,
            "avg_points_for": round(mean(pf), 2) if pf else None,
            "avg_points_against": round(mean(pa), 2) if pa else None,
            "best_win_pct": max((r["win_pct"] for r in rows if r["win_pct"] is not None), default=None),
            "best_rank": min((r["rank"] for r in rows if r["rank"] is not None), default=None)
        })
    return out

def head_to_head(people_by_id, games):
    pairs = {}
    for g in games:
        a, b = g["home_person_id"], g["away_person_id"]
        if not a or not b or a == b: continue
        pair = tuple(sorted((a, b)))
        r = pairs.setdefault(pair, {
            "person_a": pair[0], "person_b": pair[1], "games": 0,
            "a_wins": 0, "b_wins": 0, "ties": 0, "a_points": 0,
            "b_points": 0, "largest_margin": 0, "seasons": set()
        })
        r["games"] += 1; r["seasons"].add(g["season"])
        if a == pair[0]: ap, bp = g["home_score"], g["away_score"]
        else: ap, bp = g["away_score"], g["home_score"]
        r["a_points"] += ap; r["b_points"] += bp
        r["largest_margin"] = max(r["largest_margin"], g["margin"])
        if ap > bp: r["a_wins"] += 1
        elif bp > ap: r["b_wins"] += 1
        else: r["ties"] += 1
    out = []
    for r in pairs.values():
        r["seasons"] = sorted(r["seasons"])
        r["a_name"] = people_by_id[r["person_a"]]["name"]
        r["b_name"] = people_by_id[r["person_b"]]["name"]
        r["a_win_pct"] = pct(r["a_wins"] + r["ties"]*.5, r["games"])
        r["b_win_pct"] = pct(r["b_wins"] + r["ties"]*.5, r["games"])
        r["point_differential"] = round(r["a_points"] - r["b_points"], 2)
        out.append(r)
    return sorted(out, key=lambda x: (-x["games"], x["a_name"], x["b_name"]))

def league_records(games, people_by_id):
    records = {}
    for label, key in [
        ("highest_scoring_game", lambda g: -(g["home_score"] + g["away_score"])),
        ("largest_blowout", lambda g: -g["margin"]),
        ("closest_game", lambda g: g["margin"])
    ]:
        if not games: records[label] = None; continue
        g = sorted(games, key=key)[0]
        records[label] = {**g, "total_score": round(g["home_score"] + g["away_score"], 2)}
    return records

def main():
    people, teams, matchups = load("people.json"), load("teams.json"), load("matchups.json")
    print("Loading normalized data...")
    people_by_id, games = build_indexes(people, teams, matchups)
    print("Calculating season stats...")
    ss = season_stats(teams)
    print("Calculating career stats...")
    cs = career_stats(people, ss)
    print("Calculating head-to-head...")
    hh = head_to_head(people_by_id, games)
    print("Calculating league records...")
    lr = league_records(games, people_by_id)
    save("season_stats.json", ss); save("career_stats.json", cs)
    save("head_to_head.json", hh); save("league_records.json", lr)
    audit = {"people": len(people), "season_stats": len(ss),
             "career_stats": len(cs), "head_to_head_pairs": len(hh),
             "scored_h2h_games": len(games)}
    save("analytics_audit.json", audit)
    print("\nANALYTICS COMPLETE\n==================")
    for k, v in audit.items(): print(f"{k:24} {v}")
    print(f"\nOutput: {ANALYTICS}")

if __name__ == "__main__":
    main()
