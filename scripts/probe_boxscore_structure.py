import json
from pathlib import Path

BOX_DIR = Path("data/raw/boxscore")
SEASONS = [2011, 2018, 2025]


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def summarize(value, depth=0, max_depth=4):
    if depth > max_depth:
        return type(value).__name__

    if isinstance(value, dict):
        keys = list(value.keys())
        result = {"__type__": "dict", "__keys__": keys[:50]}
        for key in keys[:20]:
            if key in {
                "response",
                "schedule",
                "home",
                "away",
                "rosterForCurrentScoringPeriod",
                "roster",
                "entries",
                "playerPoolEntry",
                "player",
                "stats",
            }:
                result[key] = summarize(value[key], depth + 1, max_depth)
        return result

    if isinstance(value, list):
        result = {
            "__type__": "list",
            "__len__": len(value),
        }
        if value:
            result["__first__"] = summarize(value[0], depth + 1, max_depth)
        return result

    return {
        "__type__": type(value).__name__,
        "__value__": value,
    }


def inspect_season(season):
    season_dir = BOX_DIR / str(season)
    files = sorted(season_dir.glob("*.json"))

    if not files:
        print(f"{season}: NO FILES FOUND")
        return

    path = files[0]
    data = load_json(path)

    print()
    print("=" * 70)
    print(f"SEASON {season}")
    print(f"FILE: {path}")
    print("=" * 70)

    response = data.get("response", data)
    print("Top-level response keys:")
    print("  " + ", ".join(response.keys()))

    schedule = response.get("schedule", [])
    print(f"\nSchedule rows: {len(schedule)}")

    if not schedule:
        print("No schedule rows.")
        return

    matchup = schedule[0]

    print("\nFirst matchup keys:")
    print("  " + ", ".join(matchup.keys()))

    for side in ("home", "away"):
        team = matchup.get(side)
        if not isinstance(team, dict):
            continue

        print(f"\n{side.upper()} keys:")
        print("  " + ", ".join(team.keys()))

        # Check every known location where ESPN has historically put entries.
        locations = [
            ("rosterForCurrentScoringPeriod", team.get("rosterForCurrentScoringPeriod")),
            ("roster", team.get("roster")),
        ]

        for name, roster in locations:
            if not isinstance(roster, dict):
                continue

            print(f"\n  {name} keys:")
            print("    " + ", ".join(roster.keys()))

            entries = roster.get("entries")
            if isinstance(entries, list):
                print(f"    entries: {len(entries)}")
                if entries:
                    entry = entries[0]
                    print("    first entry keys:")
                    print("      " + ", ".join(entry.keys()))

                    pool = entry.get("playerPoolEntry")
                    if isinstance(pool, dict):
                        print("    playerPoolEntry keys:")
                        print("      " + ", ".join(pool.keys()))

                        player = pool.get("player")
                        if isinstance(player, dict):
                            print("    player keys:")
                            print("      " + ", ".join(player.keys()))

                            stats = player.get("stats")
                            if isinstance(stats, list):
                                print(f"    player.stats entries: {len(stats)}")
                                if stats:
                                    print("    first player.stats object:")
                                    print(json.dumps(stats[0], indent=2)[:4000])

                        print("    playerPoolEntry.appliedStatTotal:",
                              pool.get("appliedStatTotal"))

                    print("    lineupSlotId:", entry.get("lineupSlotId"))
                    print("    playerId:", entry.get("playerId"))

    # Save a compact structural probe for later parser development.
    probe_path = season_dir / "structure_probe.json"
    with probe_path.open("w", encoding="utf-8") as f:
        json.dump(summarize(data), f, indent=2)

    print(f"\nWrote structural probe: {probe_path}")


def main():
    print("=" * 70)
    print("INSPECT ESPN mBOXSCORE STRUCTURE")
    print("=" * 70)

    for season in SEASONS:
        inspect_season(season)

    print()
    print("=" * 70)
    print("PROBE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
