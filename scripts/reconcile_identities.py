import json
import sys
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher

sys.stdout.reconfigure(encoding="utf-8")

RAW_DIR = Path("data/raw")
OUTPUT_FILE = Path("data/identity_reconciliation.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def unwrap(data):
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]
        return {}

    if isinstance(data, dict):
        return data

    return {}


def normalize_name(name):
    if not name:
        return ""

    return "".join(
        char.lower()
        for char in name
        if char.isalnum()
    )


def get_years():
    return sorted(
        int(p.name)
        for p in RAW_DIR.iterdir()
        if p.is_dir() and p.name.isdigit()
    )


def build_owner_profiles():
    """
    Build one profile for each ESPN owner/member ID.
    """

    owners = {}

    for year in get_years():
        path = RAW_DIR / str(year) / "mTeam.json"

        data = unwrap(load_json(path))

        for member in data.get("members", []):
            owner_id = member.get("id")

            if not owner_id:
                continue

            if owner_id not in owners:
                owners[owner_id] = {
                    "owner_id": owner_id,
                    "display_names": {},
                    "full_names": {},
                    "seasons": [],
                    "teams": {},
                }

            display_name = member.get("displayName")

            full_name = " ".join(
                part
                for part in [
                    member.get("firstName"),
                    member.get("lastName"),
                ]
                if part
            ).strip()

            owners[owner_id]["display_names"][str(year)] = display_name
            owners[owner_id]["full_names"][str(year)] = full_name

            if year not in owners[owner_id]["seasons"]:
                owners[owner_id]["seasons"].append(year)

        # Team ownership
        for team in data.get("teams", []):
            team_id = team.get("id")
            team_name = team.get("name")

            if team_id is None:
                continue

            for owner_id in team.get("owners", []):
                if owner_id not in owners:
                    continue

                owners[owner_id]["teams"][str(year)] = {
                    "team_id": team_id,
                    "team_name": team_name,
                }

    return owners


def similarity(a, b):
    return SequenceMatcher(
        None,
        normalize_name(a),
        normalize_name(b)
    ).ratio()


def build_candidates(owners):
    """
    Find potentially related ESPN identities.

    This is intentionally conservative.
    Nothing is automatically merged.
    """

    candidates = []

    owner_ids = list(owners.keys())

    for i in range(len(owner_ids)):
        for j in range(i + 1, len(owner_ids)):
            id_a = owner_ids[i]
            id_b = owner_ids[j]

            a = owners[id_a]
            b = owners[id_b]

            names_a = set(
                name
                for name in a["display_names"].values()
                if name
            )

            names_b = set(
                name
                for name in b["display_names"].values()
                if name
            )

            # Compare every historical display name.
            best_similarity = 0
            best_pair = None

            for name_a in names_a:
                for name_b in names_b:
                    score = similarity(name_a, name_b)

                    if score > best_similarity:
                        best_similarity = score
                        best_pair = (name_a, name_b)

            seasons_a = set(a["seasons"])
            seasons_b = set(b["seasons"])

            # A useful signal is a temporal gap:
            # A stops before B begins.
            temporal_gap = None

            if seasons_a and seasons_b:
                a_end = max(seasons_a)
                b_start = min(seasons_b)

                if a_end < b_start:
                    missing = list(range(a_end + 1, b_start))

                    if missing:
                        temporal_gap = {
                            "a_end": a_end,
                            "b_start": b_start,
                            "missing_seasons": missing,
                        }

                b_end = max(seasons_b)
                a_start = min(seasons_a)

                if b_end < a_start:
                    missing = list(range(b_end + 1, a_start))

                    if missing:
                        temporal_gap = {
                            "a_end": b_end,
                            "b_start": a_start,
                            "missing_seasons": missing,
                        }

            # Same person could have totally different usernames,
            # so we don't require high name similarity.
            #
            # However, we only surface candidates when there is
            # either a decent name match or a clean temporal gap.
            if best_similarity >= 0.45 or temporal_gap:
                candidates.append({
                    "owner_a": id_a,
                    "owner_b": id_b,
                    "names_a": sorted(names_a),
                    "names_b": sorted(names_b),
                    "seasons_a": sorted(seasons_a),
                    "seasons_b": sorted(seasons_b),
                    "best_name_similarity": round(
                        best_similarity,
                        3
                    ),
                    "best_name_pair": best_pair,
                    "temporal_gap": temporal_gap,
                    "teams_a": a["teams"],
                    "teams_b": b["teams"],
                })

    # Highest confidence signals first.
    candidates.sort(
        key=lambda x: (
            x["temporal_gap"] is not None,
            x["best_name_similarity"],
        ),
        reverse=True,
    )

    return candidates


def main():
    owners = build_owner_profiles()
    candidates = build_candidates(owners)

    output = {
        "instructions": {
            "purpose": (
                "Candidate ESPN identity relationships. "
                "Nothing here should be automatically merged."
            ),
            "confirmed_merges": [],
        },
        "owner_count": len(owners),
        "owners": owners,
        "candidates": candidates,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 80)
    print("IDENTITY RECONCILIATION")
    print("=" * 80)

    print(f"ESPN identities: {len(owners)}")
    print(f"Candidate pairs: {len(candidates)}")
    print()

    print("-" * 80)
    print("POTENTIAL IDENTITY PAIRS")
    print("-" * 80)

    if not candidates:
        print("No candidates found.")
    else:
        for index, candidate in enumerate(candidates, start=1):
            print()
            print(f"[{index}]")

            print(
                f"  A: {', '.join(candidate['names_a'])}"
            )

            print(
                f"     Seasons: "
                f"{candidate['seasons_a'][0]}-"
                f"{candidate['seasons_a'][-1]}"
            )

            print(
                f"  B: {', '.join(candidate['names_b'])}"
            )

            print(
                f"     Seasons: "
                f"{candidate['seasons_b'][0]}-"
                f"{candidate['seasons_b'][-1]}"
            )

            print(
                f"  Name similarity: "
                f"{candidate['best_name_similarity']}"
            )

            if candidate["best_name_pair"]:
                print(
                    f"  Closest names: "
                    f"{candidate['best_name_pair'][0]} "
                    f"<-> "
                    f"{candidate['best_name_pair'][1]}"
                )

            if candidate["temporal_gap"]:
                gap = candidate["temporal_gap"]

                print(
                    f"  Temporal gap: "
                    f"left after {gap['a_end']}, "
                    f"next identity begins {gap['b_start']}"
                )

                print(
                    f"  Missing seasons: "
                    f"{', '.join(map(str, gap['missing_seasons']))}"
                )

            print("  Team history A:")

            for year, team in candidate["teams_a"].items():
                print(
                    f"      {year}: "
                    f"{team['team_id']} - "
                    f"{team['team_name']}"
                )

            print("  Team history B:")

            for year, team in candidate["teams_b"].items():
                print(
                    f"      {year}: "
                    f"{team['team_id']} - "
                    f"{team['team_name']}"
                )

    print()
    print("-" * 80)
    print("NEXT STEP")
    print("-" * 80)
    print(
        "Review the candidates above. "
        "Only explicitly confirmed relationships should be merged."
    )

    print()
    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()