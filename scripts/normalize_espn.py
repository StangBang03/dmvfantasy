from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
ALIASES_FILE = ROOT / "data" / "identity_aliases.json"

YEARS = range(2011, 2027)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename: str, data: Any) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    path = PROCESSED / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def unwrap(data: Any) -> dict:
    """
    ESPN returned a one-item list wrapper for some older seasons.
    Newer seasons return the object directly.
    """
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


def load_view(year: int, view: str) -> dict:
    path = RAW / str(year) / f"{view}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return unwrap(load_json(path))


def normalize_id(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def owner_id_from_team(team: dict) -> str | None:
    owners = team.get("owners") or []
    if not owners:
        return None
    return normalize_id(owners[0])


def team_name(team: dict) -> str | None:
    return team.get("name") or team.get("location") or None


def build_people_and_alias_map() -> tuple[dict, dict]:
    """
    Returns:
      people: canonical person_id -> person record
      espn_to_person: ESPN owner ID -> canonical person_id

    Any ESPN owner ID not explicitly merged is treated as its own person.
    """
    aliases = load_json(ALIASES_FILE) if ALIASES_FILE.exists() else {"people": {}}

    people: dict[str, dict] = {}
    espn_to_person: dict[str, str] = {}

    # Explicit/manual merges first.
    for person_id, record in aliases.get("people", {}).items():
        people[person_id] = {
            "person_id": person_id,
            "name": record.get("name"),
            "espn_ids": record.get("espn_ids", []),
            "notes": record.get("notes"),
        }
        for espn_id in record.get("espn_ids", []):
            espn_to_person[normalize_id(espn_id)] = person_id

    # Discover all ESPN owner IDs and display names from mTeam.
    discovered: dict[str, dict] = {}

    for year in YEARS:
        view = load_view(year, "mTeam")
        for member in view.get("members", []):
            owner_id = normalize_id(member.get("id"))
            if not owner_id:
                continue
            discovered.setdefault(owner_id, {
                "display_name": member.get("displayName"),
                "first_name": member.get("firstName"),
                "last_name": member.get("lastName"),
                "seasons": [],
            })
            discovered[owner_id]["seasons"].append(year)

    # Any owner not manually mapped gets its own canonical person.
    next_num = 1
    while f"person_{next_num:03d}" in people:
        next_num += 1

    for espn_id, info in sorted(discovered.items()):
        if espn_id in espn_to_person:
            continue

        person_id = f"person_{next_num:03d}"
        next_num += 1

        people[person_id] = {
            "person_id": person_id,
            "name": info.get("display_name"),
            "espn_ids": [espn_id],
            "notes": None,
        }
        espn_to_person[espn_id] = person_id

    # Add observed season coverage.
    for person_id, person in people.items():
        seasons = set()
        for espn_id in person["espn_ids"]:
            seasons.update(discovered.get(espn_id, {}).get("seasons", []))
        person["seasons"] = sorted(seasons)

    return people, espn_to_person


def normalize_seasons() -> list[dict]:
    seasons = []

    for year in YEARS:
        settings = load_view(year, "mSettings")
        season = {
            "season": year,
            "league_id": 112536,
            "name": settings.get("settings", {}).get("name")
                    or settings.get("name"),
            "raw_views": [
                "mSettings",
                "mTeam",
                "mStandings",
                "mSchedule",
                "mMatchupScore",
                "mDraftDetail",
            ],
        }
        seasons.append(season)

    return seasons


def normalize_teams(espn_to_person: dict) -> list[dict]:
    rows = []

    for year in YEARS:
        view = load_view(year, "mTeam")

        for team in view.get("teams", []):
            team_id = team.get("id")
            owner_id = owner_id_from_team(team)

            rows.append({
                "season": year,
                "team_id": team_id,
                "team_name": team_name(team),
                "abbrev": team.get("abbrev"),
                "location": team.get("location"),
                "nickname": team.get("nickname"),
                "primary_owner_espn_id": owner_id,
                "person_id": espn_to_person.get(owner_id),
                "playoff_seed": team.get("playoffSeed"),
                "rank": team.get("rank"),
                "wins": team.get("record", {}).get("overall", {}).get("wins"),
                "losses": team.get("record", {}).get("overall", {}).get("losses"),
                "ties": team.get("record", {}).get("overall", {}).get("ties"),
                "points_for": team.get("record", {}).get("overall", {}).get("pointsFor"),
                "points_against": team.get("record", {}).get("overall", {}).get("pointsAgainst"),
            })

    return rows


def normalize_matchups() -> list[dict]:
    """
    Prefer mMatchupScore because it is the explicit matchup-score view.
    Preserve the raw matchup object so we don't throw away ESPN fields
    while we learn the exact semantics of every historical field.
    """
    rows = []

    for year in YEARS:
        view = load_view(year, "mMatchupScore")
        schedule = view.get("schedule", [])

        for matchup in schedule:
            rows.append({
                "season": year,
                "matchup_id": matchup.get("id"),
                "matchup_period_id": matchup.get("matchupPeriodId"),
                "home_team_id": matchup.get("home", {}).get("teamId"),
                "away_team_id": matchup.get("away", {}).get("teamId"),
                "home_score": matchup.get("home", {}).get("totalPoints"),
                "away_score": matchup.get("away", {}).get("totalPoints"),
                "raw": matchup,
            })

    return rows


def normalize_standings() -> list[dict]:
    rows = []

    for year in YEARS:
        view = load_view(year, "mStandings")

        for team in view.get("teams", []):
            record = team.get("record", {})
            overall = record.get("overall", {})

            rows.append({
                "season": year,
                "team_id": team.get("id"),
                "rank": team.get("rank"),
                "playoff_seed": team.get("playoffSeed"),
                "wins": overall.get("wins"),
                "losses": overall.get("losses"),
                "ties": overall.get("ties"),
                "points_for": overall.get("pointsFor"),
                "points_against": overall.get("pointsAgainst"),
                "raw": team,
            })

    return rows


def normalize_draft_picks() -> list[dict]:
    rows = []

    for year in YEARS:
        view = load_view(year, "mDraftDetail")
        picks = view.get("draftDetail", {}).get("picks", [])

        for pick in picks:
            # IMPORTANT:
            # teamId is the authoritative fantasy-team relationship.
            # memberId is preserved only as raw ESPN metadata.
            rows.append({
                "season": year,
                "team_id": pick.get("teamId"),
                "player_id": pick.get("playerId"),
                "overall_pick": pick.get("overallPickNumber"),
                "round": pick.get("roundId"),
                "round_pick": pick.get("roundPickNumber"),
                "keeper": pick.get("keeper"),
                "owning_team_ids": pick.get("owningTeamIds", []),
                "member_id": pick.get("memberId"),
                "reserved_for_waiver": pick.get("reservedForWaiver"),
                "raw": pick,
            })

    return rows


def validate(people, teams, matchups, standings, draft_picks):
    errors = []
    warnings = []

    team_keys = {(r["season"], r["team_id"]) for r in teams}

    # Every season team should map to a canonical person.
    for row in teams:
        if not row["person_id"]:
            errors.append(
                f"TEAM_OWNER_UNMAPPED: {row['season']} team {row['team_id']} "
                f"owner={row['primary_owner_espn_id']}"
            )

    # Draft team references should resolve to a team in that season.
    for row in draft_picks:
        key = (row["season"], row["team_id"])
        if key not in team_keys:
            errors.append(
                f"DRAFT_TEAM_NOT_FOUND: season={row['season']} team_id={row['team_id']}"
            )

    # Expected draft counts: 16 picks per team in the historical data we fetched.
    draft_counts = {}
    for row in draft_picks:
        key = (row["season"], row["team_id"])
        draft_counts[key] = draft_counts.get(key, 0) + 1

    for row in teams:
        key = (row["season"], row["team_id"])
        count = draft_counts.get(key, 0)
        if count != 16:
            warnings.append(
                f"DRAFT_COUNT: {key[0]} team {key[1]} has {count} picks"
            )

    return errors, warnings


def main():
    print("Building canonical people...")
    people, espn_to_person = build_people_and_alias_map()

    print("Normalizing seasons...")
    seasons = normalize_seasons()

    print("Normalizing teams...")
    teams = normalize_teams(espn_to_person)

    print("Normalizing matchups...")
    matchups = normalize_matchups()

    print("Normalizing standings...")
    standings = normalize_standings()

    print("Normalizing draft picks...")
    draft_picks = normalize_draft_picks()

    errors, warnings = validate(
        people, teams, matchups, standings, draft_picks
    )

    save_json("people.json", list(people.values()))
    save_json("seasons.json", seasons)
    save_json("teams.json", teams)
    save_json("matchups.json", matchups)
    save_json("standings.json", standings)
    save_json("draft_picks.json", draft_picks)

    audit = {
        "league_id": 112536,
        "years": [*YEARS],
        "counts": {
            "people": len(people),
            "seasons": len(seasons),
            "teams": len(teams),
            "matchups": len(matchups),
            "standings": len(standings),
            "draft_picks": len(draft_picks),
        },
        "errors": errors,
        "warnings": warnings,
    }
    save_json("normalization_audit.json", audit)

    print()
    print("NORMALIZATION COMPLETE")
    print("======================")
    for key, value in audit["counts"].items():
        print(f"{key:15} {value}")

    print()
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    if errors:
        print("\nERRORS:")
        for error in errors:
            print(f"  - {error}")

    if warnings:
        print("\nWARNINGS:")
        for warning in warnings[:25]:
            print(f"  - {warning}")
        if len(warnings) > 25:
            print(f"  ... {len(warnings) - 25} more")

    print("\nOutput:")
    print(f"  {PROCESSED}")


if __name__ == "__main__":
    main()
