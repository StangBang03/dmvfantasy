"""Unit tests for private owner identity mapping validation."""
import json
import unittest

from owner_identity import load_owner_map


PEOPLE = [{"person_id": "person_001"}, {"person_id": "person_002"}]


class LoadOwnerMapTests(unittest.TestCase):
    def test_valid_mapping_normalizes_keys_and_allows_aliases(self):
        raw = json.dumps({
            "{ABC}": "person_001",
            "{ABC-OLD}": "person_001",
            "{DEF}": "person_002",
        })
        self.assertEqual(
            load_owner_map(PEOPLE, raw),
            {"{ABC}": "person_001", "{ABC-OLD}": "person_001", "{DEF}": "person_002"},
        )

    def test_missing_secret_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Missing ESPN_OWNER_MAP_JSON"):
            load_owner_map(PEOPLE, None)

    def test_invalid_json_fails(self):
        with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
            load_owner_map(PEOPLE, "{not-json")

    def test_empty_or_non_object_mapping_fails(self):
        for raw in ("{}", "[]", "null", '""'):
            with self.subTest(raw=raw):
                with self.assertRaises(RuntimeError):
                    load_owner_map(PEOPLE, raw)

    def test_unknown_canonical_person_fails(self):
        with self.assertRaisesRegex(RuntimeError, "invalid owner mapping"):
            load_owner_map(PEOPLE, json.dumps({"{ABC}": "person_999"}))

    def test_conflicting_case_normalized_keys_fail(self):
        with self.assertRaisesRegex(RuntimeError, "conflicting owner mappings"):
            load_owner_map(
                PEOPLE,
                json.dumps({"{ABC}": "person_001", "{abc}": "person_002"}),
            )

    def test_every_canonical_person_must_be_mapped(self):
        with self.assertRaisesRegex(RuntimeError, "no private ESPN identity mapping"):
            load_owner_map(PEOPLE, json.dumps({"{ABC}": "person_001"}))


if __name__ == "__main__":
    unittest.main()
