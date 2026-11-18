#!/usr/bin/env python3
"""Validate public owner identity data, privacy, and canonical references."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
GUID = re.compile(
    r"^\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?$",
    re.I,
)
CANONICAL_PERSON_ID = re.compile(r"^person_[0-9]{3}$")

# Normalize keys before comparing so camelCase, snake_case, and kebab-case
# variants cannot bypass the public-data privacy checks.
FORBIDDEN_KEYS = {
    "espnids",
    "espnid",
    "espnownerid",
    "primaryownerespnid",
    "primaryownerid",
    "ownerid",
    "ownerids",
    "memberid",
    "memberids",
    "owners",
    "swid",
    "swidid",
    "espnswid",
    "espns2",
}

IDENTITY_VALUE_KEYS = {
    "personid",
    "personids",
    "espnid",
    "espnownerid",
    "primaryownerespnid",
    "memberid",
    "memberids",
    "ownerid",
    "ownerids",
    "swid",
    "swidid",
    "espnswid",
    "owners",
}


def normalize_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def is_person_reference_key(key):
    normalized = normalize_key(key)
    return normalized.endswith("personid") or normalized.endswith("personids")


def is_identity_value_key(key):
    normalized = normalize_key(key)
    return (
        normalized in IDENTITY_VALUE_KEYS
        or normalized.endswith("ownerid")
        or normalized.endswith("ownerids")
        or normalized.endswith("memberid")
        or normalized.endswith("memberids")
        or normalized.endswith("espnid")
        or normalized.endswith("espnids")
        or normalized.endswith("swid")
    )


def walk(value, path, errors, references, field_name=None):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            normalized = normalize_key(key)
            if normalized in FORBIDDEN_KEYS:
                errors.append(f"{child_path}: forbidden identity field")
            walk(child, child_path, errors, references, key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if is_person_reference_key(field_name) and isinstance(child, str):
                references.add(child)
            walk(child, child_path, errors, references, field_name)
    elif isinstance(value, str):
        if is_person_reference_key(field_name):
            references.add(value)
        if value.lower().startswith("espn_") or (
            is_identity_value_key(field_name) and GUID.fullmatch(value)
        ):
            errors.append(f"{path}: exposed ESPN-derived identifier")


def main():
    people_path = PROCESSED / "people.json"
    people = json.loads(people_path.read_text(encoding="utf-8"))
    if not isinstance(people, list) or not people:
        raise SystemExit("people.json must contain a non-empty array.")

    person_ids = {p.get("person_id") for p in people if isinstance(p, dict)}
    if len(person_ids) != len(people):
        raise SystemExit("Duplicate or missing canonical person_id values.")
    if not all(
        isinstance(pid, str) and CANONICAL_PERSON_ID.fullmatch(pid)
        for pid in person_ids
    ):
        raise SystemExit("All public person_id values must be opaque person_NNN identifiers.")

    errors = []
    references = set()
    for directory in (PROCESSED, ANALYTICS):
        if not directory.is_dir():
            errors.append(f"Missing required data directory: {directory.name}")
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{path.relative_to(ROOT)}: unreadable or invalid JSON ({type(exc).__name__})")
                continue
            walk(data, str(path.relative_to(ROOT)), errors, references)

    unresolved = references - person_ids
    if unresolved:
        errors.append(f"Unresolved canonical person references: {len(unresolved)}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"PASS: {len(person_ids)} canonical people; all owner references resolve; "
        "no public ESPN owner identifiers found."
    )


if __name__ == "__main__":
    main()
