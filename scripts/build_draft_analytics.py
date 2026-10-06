import json
import math
import statistics
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ANALYTICS = DATA / "analytics"

DRAFT_FILE = DATA / "processed" / "draft_picks.json"
PEOPLE_FILE = DATA / "processed" / "people.json"
SEASONS_FILE = DATA / "processed" / "seasons.json"

# Also support running the script beside the normalized JSON files.
if not DRAFT_FILE.exists():
    DRAFT_FILE = ROOT / "draft_picks.json"
if not PEOPLE_FILE.exists():
    PEOPLE_FILE = ROOT / "people.json"
if not SEASONS_FILE.exists():
    SEASONS_FILE = ROOT / "seasons.json"

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

drafts = load(DRAFT_FILE)
people = load(PEOPLE_FILE)
seasons = load(SEASONS_FILE)

people_by_id = {p["person_id"]: p["name"] for p in people}

# Completed seasons are everything before the current season in seasons.json.
season_years = [s["season"] for s in seasons]
current_season = max(season_years)
historical_seasons = [y for y in season_years if y < current_season]

drafts = [d for d in drafts if d["season"] in historical_seasons]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pct(n, d):
    return round(n / d, 6) if d else None

def avg(values):
    return round(statistics.mean(values), 4) if values else None

def median(values):
    return round(statistics.median(values), 4) if values else None

def stdev(values):
    return round(statistics.stdev(values), 4) if len(values) > 1 else 0.0

def name_for(pid):
    return people_by_id.get(pid, pid)

# ---------------------------------------------------------------------------
# League draft shape by season
# ---------------------------------------------------------------------------

season_info = {}
for season in historical_seasons:
    rows = [d for d in drafts if d["season"] == season]
    picks = sorted({d["overall_pick"] for d in rows})
    teams = sorted({d["team_id"] for d in rows})
    rounds = sorted({d["round"] for d in rows})
    season_info[season] = {
        "season": season,
        "teams": len(teams),
        "picks": len(rows),
        "rounds": len(rounds),
        "picks_per_team": round(len(rows) / len(teams), 4) if teams else None,
        "max_pick": max(picks) if picks else None,
        "keepers": sum(bool(d["keeper"]) for d in rows),
        "unique_players": len({d["player_id"] for d in rows}),
    }

# ---------------------------------------------------------------------------
# Career owner draft profiles
# ---------------------------------------------------------------------------

owner_rows = defaultdict(list)
for d in drafts:
    owner_rows[d["person_id"]].append(d)

career = []
for pid, rows in owner_rows.items():
    rows = sorted(rows, key=lambda x: (x["season"], x["overall_pick"]))
    seasons_played = sorted({d["season"] for d in rows})
    picks = [d["overall_pick"] for d in rows]
    rounds = [d["round"] for d in rows]
    round_picks = [d["round_pick"] for d in rows]
    max_pick_by_season = {s: season_info[s]["max_pick"] for s in seasons_played}

    early = sum(d["round"] <= 3 for d in rows)
    middle = sum(4 <= d["round"] <= 8 for d in rows)
    late = sum(d["round"] >= 9 for d in rows)
    keepers = sum(bool(d["keeper"]) for d in rows)

    capital_scores = []
    for d in rows:
        max_pick = max_pick_by_season[d["season"]]
        capital_scores.append(
            1.0 - ((d["overall_pick"] - 1) / (max_pick - 1))
            if max_pick and max_pick > 1 else None
        )
    capital_scores = [x for x in capital_scores if x is not None]

    # Draft-slot tendencies.
    first_half = sum(
        d["overall_pick"] <= season_info[d["season"]]["max_pick"] / 2
        for d in rows
    )

    first_round = [d for d in rows if d["round"] == 1]
    first_round_picks = [d["overall_pick"] for d in first_round]

    # First-round draft position is more informative than total draft volume.
    # Each owner normally has one first-round selection per season, so these
    # metrics describe where the owner actually drafted rather than how long
    # they have been in the league.
    first_round_avg = avg(first_round_picks)
    first_round_median = median(first_round_picks)
    first_round_top3 = sum(p <= 3 for p in first_round_picks)
    first_round_top5 = sum(p <= 5 for p in first_round_picks)
    first_round_top10 = sum(p <= 10 for p in first_round_picks)
    first_overall = sum(p == 1 for p in first_round_picks)

    career.append({
        "person_id": pid,
        "person_name": name_for(pid),
        "seasons": len(seasons_played),
        "first_season": min(seasons_played),
        "last_season": max(seasons_played),
        "draft_picks": len(rows),
        "picks_per_season": round(len(rows) / len(seasons_played), 4),
        "avg_overall_pick": avg(picks),
        "median_overall_pick": median(picks),
        "draft_slot_std_dev": stdev(picks),
        "avg_round": avg(rounds),
        "avg_round_pick": avg(round_picks),
        "first_round_picks": len(first_round),
        "avg_first_round_pick": first_round_avg,
        "median_first_round_pick": first_round_median,
        "first_round_top3": first_round_top3,
        "first_round_top5": first_round_top5,
        "first_round_top10": first_round_top10,
        "first_overall_picks": first_overall,
        "best_first_round_pick": min(first_round_picks) if first_round_picks else None,
        "worst_first_round_pick": max(first_round_picks) if first_round_picks else None,
        "early_round_picks_1_3": early,
        "middle_round_picks_4_8": middle,
        "late_round_picks_9_plus": late,
        "early_round_pct": pct(early, len(rows)),
        "middle_round_pct": pct(middle, len(rows)),
        "late_round_pct": pct(late, len(rows)),
        "first_half_picks": first_half,
        "first_half_pct": pct(first_half, len(rows)),
        "second_half_picks": len(rows) - first_half,
        "second_half_pct": pct(len(rows) - first_half, len(rows)),
        "keepers": keepers,
        "keeper_pct": pct(keepers, len(rows)),
    })

career.sort(key=lambda x: x["person_name"].lower())

# ---------------------------------------------------------------------------
# Season-by-owner profiles
# ---------------------------------------------------------------------------

season_owner = []
grouped = defaultdict(list)
for d in drafts:
    grouped[(d["season"], d["person_id"])].append(d)

for (season, pid), rows in sorted(grouped.items()):
    rows = sorted(rows, key=lambda x: x["overall_pick"])
    max_pick = season_info[season]["max_pick"]
    capital = [
        1.0 - ((d["overall_pick"] - 1) / (max_pick - 1))
        for d in rows
    ] if max_pick > 1 else []

    season_owner.append({
        "season": season,
        "person_id": pid,
        "person_name": name_for(pid),
        "team_id": rows[0]["team_id"],
        "draft_picks": len(rows),
        "avg_overall_pick": avg([d["overall_pick"] for d in rows]),
        "avg_round": avg([d["round"] for d in rows]),
        "avg_round_pick": avg([d["round_pick"] for d in rows]),
        "first_pick": min(d["overall_pick"] for d in rows),
        "last_pick": max(d["overall_pick"] for d in rows),
        "early_round_picks_1_3": sum(d["round"] <= 3 for d in rows),
        "late_round_picks_9_plus": sum(d["round"] >= 9 for d in rows),
        "keepers": sum(bool(d["keeper"]) for d in rows),
        "first_half_picks": sum(d["overall_pick"] <= max_pick / 2 for d in rows),
    })

# ---------------------------------------------------------------------------
# Round-by-round league tendencies and owner round profiles
# ---------------------------------------------------------------------------

round_league = []
for season in historical_seasons:
    season_rows = [d for d in drafts if d["season"] == season]
    for rnd in sorted({d["round"] for d in season_rows}):
        rows = [d for d in season_rows if d["round"] == rnd]
        round_league.append({
            "season": season,
            "round": rnd,
            "picks": len(rows),
            "avg_overall_pick": avg([d["overall_pick"] for d in rows]),
            "keeper_picks": sum(bool(d["keeper"]) for d in rows),
            "unique_owners": len({d["person_id"] for d in rows}),
            "unique_players": len({d["player_id"] for d in rows}),
        })

owner_round = []
for pid, rows in owner_rows.items():
    for rnd in sorted({d["round"] for d in rows}):
        rr = [d for d in rows if d["round"] == rnd]
        owner_round.append({
            "person_id": pid,
            "person_name": name_for(pid),
            "round": rnd,
            "picks": len(rr),
            "avg_overall_pick": avg([d["overall_pick"] for d in rr]),
            "keepers": sum(bool(d["keeper"]) for d in rr),
        })

# ---------------------------------------------------------------------------
# Player draft history
# ---------------------------------------------------------------------------

player_rows = defaultdict(list)
for d in drafts:
    player_rows[d["player_id"]].append(d)

player_history = []
for player_id, rows in player_rows.items():
    owners = Counter(d["person_id"] for d in rows)
    seasons = sorted({d["season"] for d in rows})
    player_history.append({
        "player_id": player_id,
        "drafts": len(rows),
        "seasons": len(seasons),
        "first_season": min(seasons),
        "last_season": max(seasons),
        "avg_overall_pick": avg([d["overall_pick"] for d in rows]),
        "best_draft_pick": min(d["overall_pick"] for d in rows),
        "latest_draft_pick": max(rows, key=lambda x: x["season"])["overall_pick"],
        "keeper_count": sum(bool(d["keeper"]) for d in rows),
        "owners": [
            {"person_id": pid, "person_name": name_for(pid), "drafts": count}
            for pid, count in owners.most_common()
        ],
    })

player_history.sort(key=lambda x: (-x["drafts"], x["player_id"]))

# ---------------------------------------------------------------------------
# Repeat-player behavior by owner
# ---------------------------------------------------------------------------

owner_player = defaultdict(list)
for d in drafts:
    owner_player[(d["person_id"], d["player_id"])].append(d)

repeat_player_rows = []
for (pid, player_id), rows in owner_player.items():
    if len(rows) >= 2:
        repeat_player_rows.append({
            "person_id": pid,
            "person_name": name_for(pid),
            "player_id": player_id,
            "drafts": len(rows),
            "seasons": sorted(d["season"] for d in rows),
            "avg_overall_pick": avg([d["overall_pick"] for d in rows]),
            "keeper_count": sum(bool(d["keeper"]) for d in rows),
        })

repeat_player_rows.sort(
    key=lambda x: (-x["drafts"], x["person_name"].lower(), x["player_id"])
)

# ---------------------------------------------------------------------------
# Draft-slot consistency by owner and season
# ---------------------------------------------------------------------------

slot_profile = []
for pid, rows in owner_rows.items():
    by_season = defaultdict(list)
    for d in rows:
        by_season[d["season"]].append(d)

    first_picks = [min(r["overall_pick"] for r in rs) for rs in by_season.values()]
    last_picks = [max(r["overall_pick"] for r in rs) for rs in by_season.values()]

    slot_profile.append({
        "person_id": pid,
        "person_name": name_for(pid),
        "drafts": len(by_season),
        "avg_first_pick": avg(first_picks),
        "median_first_pick": median(first_picks),
        "first_pick_std_dev": stdev(first_picks),
        "avg_last_pick": avg(last_picks),
        "median_last_pick": median(last_picks),
        "draft_slot_consistency": stdev(first_picks),
    })

slot_profile.sort(key=lambda x: x["person_name"].lower())

# ---------------------------------------------------------------------------
# Useful league-wide records — descriptive, not a "draft skill" ranking.
# ---------------------------------------------------------------------------

def top(rows, key, reverse=True, n=10):
    return sorted(rows, key=lambda x: x[key], reverse=reverse)[:n]

repeat_counts = Counter(x["person_id"] for x in repeat_player_rows)
repeat_records = [
    {
        "person_id": pid,
        "person_name": name_for(pid),
        "repeat_player_targets": count,
    }
    for pid, count in repeat_counts.items()
]
repeat_records.sort(key=lambda x: (-x["repeat_player_targets"], x["person_name"].lower()))

records = {
    "most_keepers": top(career, "keepers"),
    "most_early_round_picks": top(career, "early_round_picks_1_3"),
    "most_late_round_picks": top(career, "late_round_picks_9_plus"),
    "most_first_half_picks": top(career, "first_half_picks"),
    "most_draft_picks": top(career, "draft_picks"),
    "most_repeat_player_targets": repeat_records[:10],
}

# Validation
assert len(drafts) == 2816 - sum(
    1 for d in load(DATA / "draft_picks.json") if d["season"] == current_season
) if (DATA / "draft_picks.json").exists() else True

for season, info in season_info.items():
    rows = [d for d in drafts if d["season"] == season]
    assert len(rows) == info["picks"]
    assert len({d["overall_pick"] for d in rows}) == info["picks"]
    assert len({d["team_id"] for d in rows}) == info["teams"]

output = {
    "meta": {
        "historical_seasons": historical_seasons,
        "current_season": current_season,
        "historical_excludes_current": True,
        "total_historical_picks": len(drafts),
        "definitions": {
            "early_rounds": "Rounds 1-3.",
            "middle_rounds": "Rounds 4-8.",
            "late_rounds": "Rounds 9+.",
            "first_half_pick": "Pick number in the first half of that season's draft.",
            "repeat_player": "Same ESPN player_id drafted by the same canonical person in multiple seasons.",
            "player_value_not_included": "No player-season fantasy production is present in the normalized draft data, so this engine does not assign draft-hit/value scores.",
            "draft_slot_note": "Because this is a snake draft, total draft capital is not treated as a skill metric; each owner receives essentially the same aggregate pick distribution.",
        },
    },
    "season": [season_info[y] for y in historical_seasons],
    "career": career,
    "season_owner": season_owner,
    "round_league": round_league,
    "owner_round": owner_round,
    "player_history": player_history,
    "repeat_player_drafts": repeat_player_rows,
    "slot_profile": slot_profile,
    "records": {
        **records,
        "best_avg_first_round_pick": top(
            [x for x in career if x["first_round_picks"] >= 5],
            "avg_first_round_pick",
            reverse=False
        ),
        "most_first_round_top3": top(career, "first_round_top3"),
        "most_first_round_top5": top(career, "first_round_top5"),
        "most_first_overall_picks": top(career, "first_overall_picks"),
    },
}

ANALYTICS.mkdir(parents=True, exist_ok=True)
out = ANALYTICS / "draft_analytics.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("=== DRAFT ANALYTICS ENGINE ===")
print(f"Historical seasons: {historical_seasons[0]}-{historical_seasons[-1]} ({len(historical_seasons)})")
print(f"Current season excluded: {current_season}")
print(f"Historical draft picks: {len(drafts)}")
print(f"Owners: {len(career)}")
print(f"Player IDs: {len(player_history)}")
print(f"Repeat owner/player combinations: {len(repeat_player_rows)}")
print(f"Season-owner rows: {len(season_owner)}")
print()
print("Wrote:")
print(f"  {out}")
print()
print("=== SANITY CHECKS ===")
print("PASS: current season excluded")
print("PASS: draft pick counts and unique overall picks reconcile")
print("PASS: team counts reconcile by season")
print("PASS: player history built")
print("PASS: draft analytics engine completed")
