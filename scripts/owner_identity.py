"""Private ESPN owner identity mapping validation."""
import json


def load_owner_map(people, raw):
    """Return normalized ESPN member ID -> canonical person ID mappings.

    The raw JSON must come from the protected ESPN_OWNER_MAP_JSON secret.
    All canonical people must have at least one private ESPN identity alias.
    """
    if not raw:
        raise RuntimeError("Missing ESPN_OWNER_MAP_JSON GitHub Actions secret.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ESPN_OWNER_MAP_JSON is not valid JSON.") from exc
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("ESPN_OWNER_MAP_JSON must be a non-empty JSON object.")

    known_people = {person["person_id"] for person in people}
    if not known_people:
        raise RuntimeError("No canonical people are available for owner mapping.")

    owner_to_person = {}
    for espn_id, person_id in payload.items():
        key = str(espn_id).strip().upper() if espn_id is not None else ""
        if not key or not isinstance(person_id, str) or person_id not in known_people:
            raise RuntimeError("ESPN_OWNER_MAP_JSON contains an invalid owner mapping.")
        if key in owner_to_person and owner_to_person[key] != person_id:
            raise RuntimeError("ESPN_OWNER_MAP_JSON contains conflicting owner mappings.")
        owner_to_person[key] = person_id

    unmapped_people = known_people - set(owner_to_person.values())
    if unmapped_people:
        raise RuntimeError(
            f"{len(unmapped_people)} canonical owner(s) have no private ESPN identity mapping."
        )
    return owner_to_person
