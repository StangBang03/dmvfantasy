#!/usr/bin/env python3
"""Refresh the current ESPN fantasy football season without touching history."""
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
RAW = DATA / "raw" / "2026"
LEAGUE_ID = 112536
YEAR = int(os.getenv("FFL_SEASON", "2026"))
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

S2 = os.getenv("ESPN_S2")
SWID = os.getenv("ESPN_SWID")
if not S2 or not SWID:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID GitHub Actions secrets.")

session = requests.Session()
session.cookies.update({"espn_s2": S2, "SWID": SWID})
session.headers.update({"Accept": "application/json", "User-Agent": "dmvfantasy-season-refresh/1.0"})

def read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")

def unwrap(value):
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return value if isinstance(value, dict) else {}

def fetch_view(view):
    url = f"{BASE}/seasons/{YEAR}/segments/0/leagues/{LEAGUE_ID}"
    response = session.get(url, params={"view": view}, timeout=60)
    response.raise_for_status()
    raw = response.json()
    data = unwrap(raw)
    if not data:
        raise RuntimeError(f"ESPN returned an empty/unusable response for {view}")
    write_json(RAW / f"{view}.json", raw)
    print(f"Fetched {view}: HTTP {response.status_code}, {len(response.content):,} bytes")
    time.sleep(0.25)
    return data

def norm_id(value):
    return str(value).strip() if value is not None else None

def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    people = read_json(PROCESSED / "people.json")
    teams_all = read_json(PROCESSED / "teams.json")
    matchups_all = read_json(PROCESSED / "matchups.json")
    standings_all = read_json(PROCESSED / "standings.json")
    drafts_all = read_json(PROCESSED / "draft_picks.json")
    seasons_all = read_json(PROCESSED / "seasons.json")

    settings = fetch_view("mSettings")
    team_view = fetch_view("mTeam")
    standings_view = fetch_view("mStandings")
    matchup_view = fetch_view("mMatchupScore")
    draft_view = fetch_view("mDraftDetail")

    owner_to_person = {}
    for person in people:
        for espn_id in person.get("espn_ids", []):
            owner_to_person[norm_id(espn_id).upper()] = person["person_id"]

    used_person_ids = {p["person_id"] for p in people}
    for member in team_view.get("members", []):
        owner_id = norm_id(member.get("id"))
        if not owner_id:
            continue
        key = owner_id.upper()
        if key not in owner_to_person:
            compact = re.sub(r"[^a-fA-F0-9]", "", owner_id).lower()
            person_id = f"espn_{compact}"
            if person_id in used_person_ids:
                person_id = f"espn_{compact}_{len(used_person_ids)}"
            people.append({
                "person_id": person_id,
                "name": member.get("displayName") or member.get("firstName") or owner_id,
                "espn_ids": [owner_id],
                "notes": "Added automatically from current-season ESPN data."
            })
            used_person_ids.add(person_id)
            owner_to_person[key] = person_id

    current_teams = []
    for team in team_view.get("teams", []):
        owners = team.get("owners") or []
        owner_id = norm_id(owners[0]) if owners else None
        record = team.get("record", {}).get("overall", {})
        current_teams.append({
            "season": YEAR,
            "team_id": team.get("id"),
            "team_name": team.get("name") or team.get("location") or f"Team {team.get('id')}",
            "abbrev": team.get("abbrev"),
            "espn_owner_id": owner_id,
            "person_id": owner_to_person.get(owner_id.upper()) if owner_id else None,
            "division_id": team.get("divisionId"),
            "draft_day": team.get("draftDay"),
            "draft_slot": team.get("draftSlot"),
            "playoff_seed": team.get("playoffSeed"),
            "rank": team.get("rank"),
            "wins": record.get("wins"),
            "losses": record.get("losses"),
            "ties": record.get("ties"),
            "points_for": record.get("pointsFor"),
            "points_against": record.get("pointsAgainst"),
        })
    if not current_teams:
        raise RuntimeError("No teams found in current-season ESPN response.")
    team_person = {t["team_id"]: t["person_id"] for t in current_teams}

    # mStandings can return a different/partial shape than mTeam for this league.
    # The mTeam view above already contains the authoritative current overall records
    # and cumulative points, so use it to build the standings rows instead of writing nulls.
    current_standings = []
    for team in current_teams:
        current_standings.append({
            "season": YEAR,
            "team_id": team.get("team_id"),
            "person_id": team.get("person_id"),
            "wins": team.get("wins"),
            "losses": team.get("losses"),
            "ties": team.get("ties"),
            "points_for": team.get("points_for"),
            "points_against": team.get("points_against"),
            "rank": team.get("rank"),
            "playoff_seed": team.get("playoff_seed"),
            "final_standing": None,
        })

    current_matchups = []
    for matchup in matchup_view.get("schedule", []):
        home = matchup.get("home") or {}
        away = matchup.get("away") or {}
        home_id, away_id = home.get("teamId"), away.get("teamId")
        winner = matchup.get("winner")
        current_matchups.append({
            "season": YEAR,
            "matchup_id": matchup.get("id"),
            "matchup_period_id": matchup.get("matchupPeriodId"),
            "scoring_period_id": matchup.get("scoringPeriodId"),
            "playoff_tier_type": matchup.get("playoffTierType") or "NONE",
            "winner": winner,
            "winner_team_id": home_id if winner == "HOME" else away_id if winner == "AWAY" else None,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "home_person_id": team_person.get(home_id),
            "away_person_id": team_person.get(away_id),
            "home_score": home.get("totalPoints"),
            "away_score": away.get("totalPoints"),
        })

    current_drafts = []
    for pick in (draft_view.get("draftDetail") or {}).get("picks", []):
        team_id = pick.get("teamId")
        current_drafts.append({
            "season": YEAR,
            "team_id": team_id,
            "person_id": team_person.get(team_id),
            "player_id": pick.get("playerId"),
            "overall_pick": pick.get("overallPickNumber"),
            "round": pick.get("roundId"),
            "round_pick": pick.get("roundPickNumber"),
            "keeper": pick.get("keeper"),
            "owning_team_ids": pick.get("owningTeamIds", []),
            "member_id": pick.get("memberId"),
        })

    if not current_matchups:
        raise RuntimeError("No matchups/schedule rows found; refusing to replace current-season data.")
    if not current_standings:
        raise RuntimeError("No standings rows found; refusing to replace current-season data.")

    def replace_season(rows, current):
        return [r for r in rows if r.get("season") != YEAR] + current

    seasons_all = replace_season(seasons_all, [{
        "season": YEAR,
        "league_id": LEAGUE_ID,
        "name": (settings.get("settings") or {}).get("name") or settings.get("name"),
        "raw_views": ["mSettings", "mTeam", "mStandings", "mMatchupScore", "mDraftDetail"],
    }])
    teams_all = replace_season(teams_all, current_teams)
    matchups_all = replace_season(matchups_all, current_matchups)
    standings_all = replace_season(standings_all, current_standings)
    drafts_all = replace_season(drafts_all, current_drafts)

    unmapped = [t for t in current_teams if not t.get("person_id")]
    if unmapped:
        raise RuntimeError(f"Unmapped current-season owners: {[t['team_id'] for t in unmapped]}")

    write_json(PROCESSED / "people.json", people)
    write_json(PROCESSED / "seasons.json", sorted(seasons_all, key=lambda x: x["season"]))
    write_json(PROCESSED / "teams.json", sorted(teams_all, key=lambda x: (x["season"], x["team_id"] or 0)))
    write_json(PROCESSED / "matchups.json", sorted(matchups_all, key=lambda x: (x["season"], x.get("matchup_period_id") or 0, x.get("matchup_id") or 0)))
    write_json(PROCESSED / "standings.json", sorted(standings_all, key=lambda x: (x["season"], x["team_id"] or 0)))
    write_json(PROCESSED / "draft_picks.json", sorted(drafts_all, key=lambda x: (x["season"], x.get("overall_pick") or 0)))

    print(f"Updated season {YEAR}: {len(current_teams)} teams, {len(current_matchups)} schedule rows, {len(current_standings)} standings rows, {len(current_drafts)} draft picks.")
    print("Historical seasons were preserved.")

if __name__ == "__main__":
    main()
