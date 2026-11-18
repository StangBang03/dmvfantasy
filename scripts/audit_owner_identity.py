import json
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

RAW_DIR = Path("data/raw")
OUTPUT_FILE = Path("data/owner_identity_audit.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def unwrap(data):
    """ESPN used a one-item list wrapper for older seasons."""
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]
        return {}

    if isinstance(data, dict):
        return data

    return {}


def get_years():
    return sorted(
        int(p.name)
        for p in RAW_DIR.iterdir()
        if p.is_dir() and p.name.isdigit()
    )


def clean_id(value):
    if value is None:
        return None

    if isinstance(value, str):
        return value.strip()

    return str(value)


def main():
    owner_history = defaultdict(lambda: {
        "seasons": [],
        "teams": {},
        "display_names": {},
        "member_names": {},
    })

    team_history = defaultdict(lambda: {
        "seasons": [],
        "owners": {},
        "names": {},
    })

    anomalies = []

    season_summary = {}

    for year in get_years():
        team_data = unwrap(load_json(RAW_DIR / str(year) / "mTeam.json"))
        draft_data = unwrap(load_json(RAW_DIR / str(year) / "mDraftDetail.json"))

        teams = team_data.get("teams", [])
        members = team_data.get("members", [])

        # ---------------------------------------------------------
        # Build member lookup
        # ---------------------------------------------------------
        member_lookup = {}

        for member in members:
            member_id = clean_id(member.get("id"))

            if not member_id:
                continue

            display_name = member.get("displayName")

            full_name_parts = [
                member.get("firstName"),
                member.get("lastName"),
            ]

            full_name = " ".join(
                part for part in full_name_parts if part
            ).strip()

            member_lookup[member_id] = {
                "displayName": display_name,
                "fullName": full_name,
            }

        # ---------------------------------------------------------
        # Draft member IDs by team
        # ---------------------------------------------------------
        draft_member_ids_by_team = defaultdict(set)

        draft_detail = draft_data.get("draftDetail", {})
        picks = draft_detail.get("picks", [])

        for pick in picks:
            team_id = pick.get("teamId")
            member_id = clean_id(pick.get("memberId"))

            if team_id is not None and member_id:
                draft_member_ids_by_team[int(team_id)].add(member_id)

        # ---------------------------------------------------------
        # Process teams
        # ---------------------------------------------------------
        owners_this_season = defaultdict(list)

        for team in teams:
            team_id = team.get("id")
            team_name = team.get("name")

            if team_id is None:
                continue

            team_id = int(team_id)

            owners = [
                clean_id(owner)
                for owner in team.get("owners", [])
                if clean_id(owner)
            ]

            primary_owner = clean_id(team.get("primaryOwner"))

            # ---------------------------------------------
            # Basic team ownership validation
            # ---------------------------------------------
            if not owners:
                anomalies.append({
                    "year": year,
                    "type": "TEAM_HAS_NO_OWNERS",
                    "team_id": team_id,
                    "team_name": team_name,
                })

            if primary_owner and primary_owner not in owners:
                anomalies.append({
                    "year": year,
                    "type": "PRIMARY_OWNER_NOT_IN_OWNERS",
                    "team_id": team_id,
                    "team_name": team_name,
                    "primary_owner": primary_owner,
                    "owners": owners,
                })

            if len(owners) > 1:
                anomalies.append({
                    "year": year,
                    "type": "TEAM_HAS_MULTIPLE_OWNERS",
                    "team_id": team_id,
                    "team_name": team_name,
                    "owners": owners,
                })

            # ---------------------------------------------
            # Track team history
            # ---------------------------------------------
            team_history[team_id]["seasons"].append(year)
            team_history[team_id]["names"][str(year)] = team_name
            team_history[team_id]["owners"][str(year)] = owners

            # ---------------------------------------------
            # Track owners
            # ---------------------------------------------
            for owner_id in owners:
                owners_this_season[owner_id].append(team_id)

                owner_history[owner_id]["seasons"].append(year)
                owner_history[owner_id]["teams"][str(year)] = {
                    "team_id": team_id,
                    "team_name": team_name,
                }

                member = member_lookup.get(owner_id)

                if member:
                    owner_history[owner_id]["display_names"][str(year)] = (
                        member.get("displayName")
                    )

                    owner_history[owner_id]["member_names"][str(year)] = (
                        member.get("fullName")
                    )
                else:
                    anomalies.append({
                        "year": year,
                        "type": "OWNER_NOT_IN_MEMBERS",
                        "owner_id": owner_id,
                        "team_id": team_id,
                        "team_name": team_name,
                    })

            # ---------------------------------------------
            # Validate draft member IDs
            # ---------------------------------------------
            draft_members = draft_member_ids_by_team.get(team_id, set())

            if draft_members:
                owner_set = set(owners)

                if not draft_members.issubset(owner_set):
                    anomalies.append({
                        "year": year,
                        "type": "DRAFT_MEMBER_DOES_NOT_MATCH_TEAM_OWNER",
                        "team_id": team_id,
                        "team_name": team_name,
                        "owners": owners,
                        "draft_member_ids": sorted(draft_members),
                    })

        # ---------------------------------------------------------
        # Same owner on multiple teams in same season
        # ---------------------------------------------------------
        for owner_id, team_ids in owners_this_season.items():
            unique_team_ids = sorted(set(team_ids))

            if len(unique_team_ids) > 1:
                anomalies.append({
                    "year": year,
                    "type": "OWNER_ON_MULTIPLE_TEAMS",
                    "owner_id": owner_id,
                    "team_ids": unique_team_ids,
                })

        season_summary[year] = {
            "teams": len(teams),
            "members": len(members),
            "draft_picks": len(picks),
        }

    # -------------------------------------------------------------
    # Analyze owner timelines
    # -------------------------------------------------------------
    for owner_id, data in owner_history.items():
        seasons = sorted(set(data["seasons"]))

        if not seasons:
            continue

        gaps = []

        for previous, current in zip(seasons, seasons[1:]):
            if current - previous > 1:
                gaps.append({
                    "left_after": previous,
                    "returned": current,
                    "missing_seasons": list(
                        range(previous + 1, current)
                    ),
                })

        data["seasons"] = seasons
        data["gaps"] = gaps

        # A gap means the owner disappeared and later returned.
        data["returned_after_gap"] = len(gaps) > 0

        # Check if their team ID changed over time.
        team_ids = sorted({
            value["team_id"]
            for value in data["teams"].values()
        })

        data["team_ids_used"] = team_ids
        data["changed_team_id"] = len(team_ids) > 1

    # -------------------------------------------------------------
    # Analyze team ownership changes
    # -------------------------------------------------------------
    for team_id, data in team_history.items():
        owner_by_year = data["owners"]

        all_owner_ids = sorted({
            owner_id
            for owners in owner_by_year.values()
            for owner_id in owners
        })

        data["owner_ids_used"] = all_owner_ids
        data["changed_owner"] = len(all_owner_ids) > 1

    # -------------------------------------------------------------
    # Build useful lists
    # -------------------------------------------------------------
    returning_owners = []
    continuous_owners = []
    departed_owners = []

    all_years = get_years()
    first_year = min(all_years)
    last_year = max(all_years)

    for owner_id, data in owner_history.items():
        seasons = data["seasons"]

        if data["returned_after_gap"]:
            returning_owners.append(owner_id)

        if (
            seasons
            and seasons[0] == first_year
            and seasons[-1] == last_year
            and not data["gaps"]
        ):
            continuous_owners.append(owner_id)

        if seasons and seasons[-1] < last_year:
            departed_owners.append(owner_id)

    # -------------------------------------------------------------
    # Save audit
    # -------------------------------------------------------------
    output = {
        "league": {
            "first_season": first_year,
            "last_season": last_year,
            "season_count": len(all_years),
        },
        "owner_count": len(owner_history),
        "team_id_count": len(team_history),
        "owners": dict(sorted(owner_history.items())),
        "teams": dict(sorted(team_history.items())),
        "returning_owners": returning_owners,
        "continuous_owners": continuous_owners,
        "departed_owners": departed_owners,
        "anomalies": anomalies,
        "season_summary": season_summary,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------
    # Console report
    # -------------------------------------------------------------
    print()
    print("=" * 80)
    print("OWNER IDENTITY AUDIT")
    print("=" * 80)

    print(f"Seasons:        {first_year}-{last_year}")
    print(f"Owners found:   {len(owner_history)}")
    print(f"Team IDs found: {len(team_history)}")
    print(f"Anomalies:      {len(anomalies)}")
    print()

    print("-" * 80)
    print("OWNER TIMELINES")
    print("-" * 80)

    for owner_id, data in sorted(
        owner_history.items(),
        key=lambda item: (
            min(item[1]["seasons"]),
            item[0]
        )
    ):
        seasons = data["seasons"]

        names = [
            name
            for name in data["display_names"].values()
            if name
        ]

        display_name = names[0] if names else owner_id

        if data["gaps"]:
            status = "RETURNED"
        elif seasons[-1] == last_year:
            status = "ACTIVE"
        else:
            status = "DEPARTED"

        season_text = f"{seasons[0]}-{seasons[-1]}"

        print(
            f"{display_name:<28} "
            f"{season_text:<11} "
            f"{status:<9} "
            f"teams={','.join(map(str, data['team_ids_used']))}"
        )

        for gap in data["gaps"]:
            print(
                f"    RETURN: left after {gap['left_after']}, "
                f"returned {gap['returned']} "
                f"(missed {', '.join(map(str, gap['missing_seasons']))})"
            )

    print()
    print("-" * 80)
    print("RETURNING OWNERS")
    print("-" * 80)

    if returning_owners:
        for owner_id in returning_owners:
            data = owner_history[owner_id]

            names = [
                name
                for name in data["display_names"].values()
                if name
            ]

            display_name = names[0] if names else owner_id

            print(display_name)

            for gap in data["gaps"]:
                print(
                    f"    {gap['left_after']} -> {gap['returned']} "
                    f"(missed {gap['missing_seasons']})"
                )
    else:
        print("None found.")

    print()
    print("-" * 80)
    print("ANOMALIES")
    print("-" * 80)

    if anomalies:
        for anomaly in anomalies:
            print(
                f"{anomaly['year']}: "
                f"{anomaly['type']}"
            )
    else:
        print("None found.")

    print()
    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()