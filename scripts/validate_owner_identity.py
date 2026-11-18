#!/usr/bin/env python3
"""Validate public owner identity data and references."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
GUID = re.compile(r"^\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?$", re.I)
FORBIDDEN_KEYS = {"espn_ids", "espn_owner_id", "primary_owner_espn_id", "member_id"}
PERSON_REFERENCE_KEYS = {
    "person_id", "home_person_id", "away_person_id", "champion_person_id",
    "runner_up_person_id", "third_place_person_id", "person_a_id", "person_b_id",
}


IDENTITY_VALUE_KEYS = {
    "person_id", "espn_id", "espn_owner_id", "primary_owner_espn_id",
    "member_id", "owner_id", "owner_ids", "member_ids", "swid", "swid_id",
}


def walk(value, path, errors, references, field_name=None):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                errors.append(f"{path}: forbidden field {key}")
            if key in PERSON_REFERENCE_KEYS and isinstance(child, str):
                references.add(child)
            walk(child, path, errors, references, key)
    elif isinstance(value, list):
        for child in value:
            walk(child, path, errors, references, field_name)
    elif isinstance(value, str):
        if value.startswith("espn_") or (
            field_name in IDENTITY_VALUE_KEYS and GUID.fullmatch(value)
        ):
            errors.append(f"{path}: exposed ESPN-derived identifier")


def main():
    people = json.loads((PROCESSED / "people.json").read_text(encoding="utf-8"))
    person_ids = {p.get("person_id") for p in people}
    if len(person_ids) != len(people):
        raise SystemExit("Duplicate canonical person_id values.")
    if not all(isinstance(pid, str) and re.fullmatch(r"person_[0-9]{3}", pid) for pid in person_ids):
        raise SystemExit("All public person_id values must be opaque person_NNN identifiers.")

    errors = []
    references = set()
    for directory in (PROCESSED, ANALYTICS):
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            walk(data, str(path.relative_to(ROOT)), errors, references)

    unresolved = references - person_ids
    if unresolved:
        errors.append(f"Unresolved canonical person references: {len(unresolved)}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(person_ids)} canonical people; all owner references resolve; no public ESPN owner identifiers found.")


if __name__ == "__main__":
    main()
