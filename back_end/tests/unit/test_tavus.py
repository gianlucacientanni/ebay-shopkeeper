# standard library
import unittest
from unittest import TestCase, mock

# third party
import requests

# ebay_shopkeeper imports
from back_end.api.tavus.tavus import TavusError, conversation_payload, new_session, tavus_request


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


    def test_tavus_request(self):
        session = mock.Mock()
        session.request.return_value = mock.Mock(ok=True, content=b'{"pal_id": "p1"}')
        session.request.return_value.json.return_value = {"pal_id": "p1"}
        body = tavus_request(session, "POST", "/pals", "create the PAL", {"pal_name": "x"})
        self.assertEqual(body, {"pal_id": "p1"})
        session.request.assert_called_once_with(
            "POST", "https://tavusapi.com/v2/pals", json={"pal_name": "x"}, timeout=30
        )

    def test_tavus_request_empty_body(self):
        session = mock.Mock()
        session.request.return_value = mock.Mock(ok=True, content=b"")
        self.assertEqual(tavus_request(session, "POST", "/conversations/c1/end", "end"), {})

    def test_tavus_request_errors(self):
        rejected = mock.Mock(ok=False, status_code=404, text="not found")
        rejected.json.return_value = {"error": "PAL not found"}
        test_cases = [
            {
                "description": "non-2xx response",
                "outcome": rejected,
                "expected_status": 404,
                "expected_message": "Tavus failed to get PAL p1 (404): PAL not found",
            },
            {
                "description": "timeout",
                "outcome": requests.Timeout("read timed out"),
                "expected_status": None,
                "expected_message": "Tavus request to get PAL p1 failed: Timeout",
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            session = mock.Mock()
            session.request.side_effect = [test_case["outcome"]]
            with self.assertRaises(TavusError, msg=f"Test case {test_desc} failed.") as ctx:
                tavus_request(session, "GET", "/pals/p1", "get PAL p1")
            self.assertEqual(
                ctx.exception.status_code, test_case["expected_status"], f"Test case {test_desc} failed."
            )
            self.assertEqual(
                str(ctx.exception), test_case["expected_message"], f"Test case {test_desc} failed."
            )


if __name__ == "__main__":
    unittest.main()
