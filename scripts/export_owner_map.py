#!/usr/bin/env python3
"""Export the private ESPN owner map from the pre-migration people.json.

Run locally before merging:
    python scripts/export_owner_map.py > espn-owner-map.json

Add the JSON output as the GitHub Actions secret ESPN_OWNER_MAP_JSON.
Keep the generated file private and delete it after creating the secret.
This uses the exact pre-migration commit and maps people to opaque IDs in
the same order preserved by the identity migration.
"""
import argparse
import json
import subprocess
import sys

SOURCE_COMMIT = "d70be2a1cc82351cf48a29db09e120a1fff727bf"
SOURCE_PATH = "data/processed/people.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Write the private map to this local file instead of stdout.")
    args = parser.parse_args()

    result = subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{SOURCE_PATH}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    people = json.loads(result.stdout)
    mapping = {}
    for index, person in enumerate(people, start=1):
        canonical_id = f"person_{index:03d}"
        for espn_id in person.get("espn_ids", []):
            key = str(espn_id).strip().upper()
            if not key:
                raise SystemExit("Source people.json contains an empty ESPN ID.")
            if key in mapping and mapping[key] != canonical_id:
                raise SystemExit("Source people.json contains conflicting owner mappings.")
            mapping[key] = canonical_id
    if len(mapping) < len(people):
        raise SystemExit("Source people.json did not produce a complete owner map.")
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output:
            json.dump(mapping, output, indent=2, ensure_ascii=False)
            output.write("\n")
        print(f"Wrote private owner map to {args.output}")
    else:
        json.dump(mapping, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
