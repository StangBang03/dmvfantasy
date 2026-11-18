import json
from pathlib import Path


RAW_DIR = Path("data/raw")

TEST_YEARS = [2011, 2018, 2026]

VIEWS = [
    "mSettings",
    "mTeam",
    "mStandings",
    "mSchedule",
    "mMatchupScore",
    "mDraftDetail",
]


def load_json(year, view):
    path = RAW_DIR / str(year) / f"{view}.json"

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def describe(value, indent=0):
    prefix = " " * indent

    if isinstance(value, dict):
        print(f"{prefix}DICT ({len(value)} keys)")

        for key, child in list(value.items())[:20]:
            print(f"{prefix}  {key!r}: ", end="")
            describe(child, indent + 4)

    elif isinstance(value, list):
        print(f"LIST ({len(value)} items)")

        if value:
            print(f"{prefix}  First item:")
            describe(value[0], indent + 4)

    else:
        print(f"{type(value).__name__}: {repr(value)[:150]}")


def main():
    for year in TEST_YEARS:
        print()
        print("=" * 80)
        print(f"YEAR {year}")
        print("=" * 80)

        for view in VIEWS:
            print()
            print(f"--- {view} ---")

            data = load_json(year, view)

            describe(data, 2)


if __name__ == "__main__":
    main()