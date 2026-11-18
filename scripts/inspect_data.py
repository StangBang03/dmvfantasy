import json
from pathlib import Path


RAW_DIR = Path("data/raw")
OUTPUT_FILE = Path("data/data_inventory.json")


def load_json(year, view):
    path = RAW_DIR / str(year) / f"{view}.json"

    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def unwrap(data):
    """
    ESPN historically returned some endpoints as a one-item list
    and newer versions as a dictionary.

    Normalize both into a dictionary.
    """
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]

    if isinstance(data, dict):
        return data

    return {}


def get_teams(data):
    data = unwrap(data)
    teams = data.get("teams", [])

    return teams if isinstance(teams, list) else []


def get_schedule(data):
    data = unwrap(data)
    schedule = data.get("schedule", [])

    return schedule if isinstance(schedule, list) else []


def get_draft_picks(data):
    data = unwrap(data)

    draft_detail = data.get("draftDetail", {})

    if isinstance(draft_detail, dict):
        picks = draft_detail.get("picks", [])

        if isinstance(picks, list):
            return picks

    return []


def inspect_team(team):
    return {
        "id": team.get("id"),
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "location": team.get("location"),
        "owners": team.get("owners"),
        "primaryOwner": team.get("primaryOwner"),
        "record": team.get("record"),
        "playoffSeed": team.get("playoffSeed"),
        "rankCalculatedFinal": team.get("rankCalculatedFinal"),
        "rankFinal": team.get("rankFinal"),
        "points": team.get("points"),
    }


def inspect_matchup(matchup):
    return {
        "id": matchup.get("id"),
        "matchupPeriodId": matchup.get("matchupPeriodId"),
        "home": matchup.get("home", {}),
        "away": matchup.get("away", {}),
        "winner": matchup.get("winner"),
        "playoffTierType": matchup.get("playoffTierType"),
    }


def inspect_draft_pick(pick):
    return {
        "overallPickNumber": pick.get("overallPickNumber"),
        "roundId": pick.get("roundId"),
        "roundPickNumber": pick.get("roundPickNumber"),
        "playerId": pick.get("playerId"),
        "teamId": pick.get("teamId"),
        "memberId": pick.get("memberId"),
        "keeper": pick.get("keeper"),
    }


def main():

    years = sorted(
        int(path.name)
        for path in RAW_DIR.iterdir()
        if path.is_dir() and path.name.isdigit()
    )

    inventory = {
        "seasons": {},
        "owner_summary": {},
        "team_summary": {},
        "anomalies": [],
    }

    print()
    print("=" * 80)
    print(" ESPN FANTASY LEAGUE DATA INVENTORY")
    print("=" * 80)
    print()

    print(
        f"{'YEAR':<8}"
        f"{'TEAMS':<10}"
        f"{'MATCHUPS':<12}"
        f"{'DRAFT PICKS':<14}"
        f"{'SETTINGS':<12}"
    )

    print("-" * 56)

    for year in years:

        settings = load_json(year, "mSettings")
        teams_data = load_json(year, "mTeam")
        matchup_data = load_json(year, "mMatchupScore")
        draft_data = load_json(year, "mDraftDetail")

        teams = get_teams(teams_data)
        matchups = get_schedule(matchup_data)
        picks = get_draft_picks(draft_data)

        print(
            f"{year:<8}"
            f"{len(teams):<10}"
            f"{len(matchups):<12}"
            f"{len(picks):<14}"
            f"{'YES' if settings else 'NO':<12}"
        )

        season = {
            "teams_count": len(teams),
            "matchups_count": len(matchups),
            "draft_picks_count": len(picks),
            "settings_present": settings is not None,

            "teams": [
                inspect_team(team)
                for team in teams
            ],

            "matchups": [
                inspect_matchup(matchup)
                for matchup in matchups
            ],

            "draft_picks": [
                inspect_draft_pick(pick)
                for pick in picks
            ],
        }

        inventory["seasons"][str(year)] = season

    print()
    print("=" * 80)
    print("OWNER / TEAM IDENTITY INVENTORY")
    print("=" * 80)
    print()

    team_history = {}
    owner_history = {}

    for year in years:

        season = inventory["seasons"][str(year)]

        for team in season["teams"]:

            team_id = team["id"]

            if team_id is not None:

                team_history.setdefault(
                    str(team_id),
                    []
                ).append({
                    "year": year,
                    "name": team["name"],
                    "location": team["location"],
                    "abbrev": team["abbrev"],
                    "owners": team["owners"],
                    "primaryOwner": team["primaryOwner"],
                })

            owners = team["owners"]

            if isinstance(owners, list):

                for owner in owners:

                    owner_id = str(owner)

                    owner_history.setdefault(
                        owner_id,
                        []
                    ).append({
                        "year": year,
                        "team_id": team_id,
                        "team_name": team["name"],
                    })

    inventory["team_summary"] = team_history
    inventory["owner_summary"] = owner_history

    print(
        f"Unique ESPN team IDs:  "
        f"{len(team_history)}"
    )

    print(
        f"Unique ESPN owner IDs: "
        f"{len(owner_history)}"
    )

    print()
    print("TEAM ID HISTORY")
    print("-" * 80)

    for team_id, seasons in sorted(
        team_history.items(),
        key=lambda x: int(x[0])
    ):

        years_seen = [
            x["year"]
            for x in seasons
        ]

        names = sorted(
            set(
                x["name"]
                for x in seasons
                if x["name"]
            )
        )

        print(
            f"Team {team_id:<4} "
            f"{min(years_seen)}-{max(years_seen)}  "
            f"{', '.join(names)}"
        )

    print()
    print("OWNER ID HISTORY")
    print("-" * 80)

    for owner_id, seasons in owner_history.items():

        years_seen = [
            x["year"]
            for x in seasons
        ]

        names = sorted(
            set(
                x["team_name"]
                for x in seasons
                if x["team_name"]
            )
        )

        print(
            f"{owner_id:<45} "
            f"{min(years_seen)}-{max(years_seen)}  "
            f"{min(years_seen)}-{max(years_seen)}  "
            f"{', '.join(names)}"
        )

    print()
    print("=" * 80)
    print("SAVING INVENTORY")
    print("=" * 80)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            inventory,
            f,
            indent=2
        )

    print()
    print(f"Saved: {OUTPUT_FILE}")
    print()


if __name__ == "__main__":
    main()