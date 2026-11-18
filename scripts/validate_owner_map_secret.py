#!/usr/bin/env python3
"""Validate the protected ESPN owner map without contacting ESPN or writing data."""
import json
import os
from pathlib import Path

from owner_identity import load_owner_map


ROOT = Path(__file__).resolve().parents[1]


def main():
    people = json.loads(
        (ROOT / "data" / "processed" / "people.json").read_text(encoding="utf-8")
    )
    mapping = load_owner_map(people, os.getenv("ESPN_OWNER_MAP_JSON"))
    print(
        "PASS: private owner map is valid "
        f"({len(mapping)} ESPN identity aliases mapped to {len(people)} canonical owners)."
    )


if __name__ == "__main__":
    main()
