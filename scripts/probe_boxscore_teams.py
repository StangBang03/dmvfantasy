import json
from pathlib import Path

BOX_DIR = Path("data/raw/boxscore")
SEASONS = [2011, 2018, 2025]


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def inspect_season(season):
    files = sorted((BOX_DIR / str(season)).glob("matchup_*_scoring_*.json"))
    if not files:
        print(f"{season}: NO BOXCORE FILES")
        return

    path = files[0]
    data = load_json(path)
    response = data.get("response", data)

    print()
    print("=" * 70)
    print(f"SEASON {season}")
    print(f"FILE: {path}")
    print("=" * 70)

    teams = response.get("teams", [])
    print(f"Top-level teams: {len(teams)}")

    for i, team in enumerate(teams[:2]):
        print(f"\nTEAM {i + 1} keys:")
        print("  " + ", ".join(team.keys()))

        roster = team.get("roster")
        if not isinstance(roster, dict):
            print("  roster: NOT PRESENT")
            continue

        print("  roster keys:")
        print("    " + ", ".join(roster.keys()))

        entries = roster.get("entries")
        if not isinstance(entries, list):
            print("  roster.entries: NOT PRESENT")
            continue

        print(f"  roster.entries: {len(entries)}")

        if not entries:
            continue

        entry = entries[0]
        print("\n  FIRST ROSTER ENTRY")
        print("  keys:")
        print("    " + ", ".join(entry.keys()))

        print("\n  Full first roster entry:")
        print(json.dumps(entry, indent=2)[:8000])

    schedule = response.get("schedule", [])
    if schedule:
        matchup = schedule[0]
        print("\nFIRST SCHEDULE MATCHUP HOME FULL OBJECT:")
        print(json.dumps(matchup.get("home"), indent=2)[:8000])

        print("\nFIRST SCHEDULE MATCHUP AWAY FULL OBJECT:")
        print(json.dumps(matchup.get("away"), indent=2)[:8000])


def main():
    print("=" * 70)
    print("TARGETED ESPN mBOXSCORE STRUCTURE PROBE")
    print("=" * 70)

    for season in SEASONS:
        inspect_season(season)

    print()
    print("=" * 70)
    print("PROBE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
