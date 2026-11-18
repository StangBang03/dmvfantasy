"""Unit tests for public owner identity leakage detection."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_owner_identity import walk, is_person_reference_key, normalize_key


class PublicIdentityValidationTests(unittest.TestCase):
    def test_key_normalization_covers_camel_snake_and_kebab_case(self):
        for key in ("primaryOwnerId", "primary_owner_id", "primary-owner-id"):
            with self.subTest(key=key):
                self.assertEqual(normalize_key(key), "primaryownerid")

    def test_owner_lists_are_canonical_person_references(self):
        errors = []
        references = set()
        walk(
            {"owners": ["person_001", "person_002"]},
            "sample",
            errors,
            references,
        )
        self.assertTrue(is_person_reference_key("owners"))
        self.assertEqual(references, {"person_001", "person_002"})
        self.assertEqual(errors, [])

    def test_forbidden_identity_field_variants_are_rejected(self):
        for key in ("primaryOwnerId", "member_id", "espnOwnerId", "swid"):
            with self.subTest(key=key):
                errors = []
                walk({key: "opaque-looking-value"}, "sample", errors, set())
                self.assertTrue(errors)

    def test_guid_in_canonical_person_reference_is_rejected(self):
        errors = []
        references = set()
        walk(
            {"person_id": "{12345678-1234-1234-1234-123456789abc}"},
            "sample",
            errors,
            references,
        )
        self.assertTrue(any("exposed ESPN-derived identifier" in e for e in errors))

    def test_guid_in_unrelated_transaction_reference_is_not_misclassified(self):
        errors = []
        walk(
            {"transaction_id": "{12345678-1234-1234-1234-123456789abc}"},
            "sample",
            errors,
            set(),
        )
        self.assertEqual(errors, [])

    def test_noncanonical_owner_list_reference_is_collected_for_resolution(self):
        errors = []
        references = set()
        walk({"owners": ["not-a-person-id"]}, "sample", errors, references)
        self.assertEqual(references, {"not-a-person-id"})


if __name__ == "__main__":
    unittest.main()
