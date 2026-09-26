import unittest

from app.communication_brain.triage import _apply_deterministic_safety, DEEP_SCHEMA


class SemanticConsistencyTests(unittest.TestCase):
    def test_automated_service_mail_cannot_be_family_personal(self):
        item = {
            "bucket": "TRANSACTIONAL",
            "relationship_type": "PERSONAL",
            "sender_type": "COMPANY",
            "communication_type": "AUTOMATED",
            "direct_human": False,
            "risk": 0.0,
            "priority": 0.5,
            "requires_action": True,
            "security_event": False,
        }
        msg = {"subject": "Account update", "snippet": "Please review your account.", "from": "service@example.test"}
        out = _apply_deterministic_safety(item, msg)
        self.assertEqual(out["relationship_type"], "SERVICE")

    def test_real_human_personal_relationship_is_preserved(self):
        item = {
            "bucket": "CONVERSATIONAL",
            "relationship_type": "FAMILY",
            "sender_type": "PERSONAL",
            "communication_type": "CONVERSATIONAL",
            "direct_human": True,
            "risk": 0.0,
            "priority": 0.5,
            "requires_action": False,
            "security_event": False,
        }
        msg = {"subject": "Dinner", "snippet": "See you tonight", "from": "person@example.test"}
        out = _apply_deterministic_safety(item, msg)
        self.assertEqual(out["relationship_type"], "FAMILY")

    def test_deep_analysis_requires_semantic_bucket(self):
        self.assertIn("bucket", DEEP_SCHEMA["properties"])
        self.assertIn("bucket", DEEP_SCHEMA["required"])


if __name__ == "__main__":
    unittest.main()
