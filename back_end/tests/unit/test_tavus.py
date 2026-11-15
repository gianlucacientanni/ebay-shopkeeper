# standard library
import unittest
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.api.tavus.tavus import TavusError, conversation_payload, new_session


EXPECTED_PROPERTIES = {
    "max_call_duration": 180,
    "participant_left_timeout": 10,
    "participant_absent_timeout": 60,
}


class TavusTest(TestCase):
    def test_conversation_payload(self):
        test_cases = [
            {
                "description": "test mode, PAL's default face",
                "face_id": "",
                "test_mode": True,
                "expected": {
                    "pal_id": "p123",
                    "conversation_name": "Arcanum shopkeeper",
                    "test_mode": True,
                    "properties": EXPECTED_PROPERTIES,
                },
            },
            {
                "description": "real call with a face override",
                "face_id": "rc9cff32ceba",
                "test_mode": False,
                "expected": {
                    "pal_id": "p123",
                    "conversation_name": "Arcanum shopkeeper",
                    "test_mode": False,
                    "properties": EXPECTED_PROPERTIES,
                    "face_id": "rc9cff32ceba",
                },
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            payload = conversation_payload(
                pal_id="p123",
                face_id=test_case["face_id"],
                test_mode=test_case["test_mode"],
                max_call_duration=180,
            )
            self.assertEqual(payload, test_case["expected"], f"Test case {test_desc} failed.")

    def test_new_session_sets_api_key_header(self):
        session = new_session("secret-key")
        self.assertEqual(session.headers["x-api-key"], "secret-key")

    def test_new_session_missing_api_key(self):
        with self.assertRaises(TavusError):
            new_session("")


if __name__ == "__main__":
    unittest.main()
