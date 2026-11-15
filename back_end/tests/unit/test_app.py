# standard library
import unittest
from decimal import Decimal
from unittest import TestCase, mock

# third party
from fastapi.testclient import TestClient

# ebay_shopkeeper imports
from back_end.api.scryfall.scryfall import CommanderNotFound, ScryfallError
from back_end.api.tavus.tavus import TavusError
from back_end.common import config
from back_end.common.models import Candidate, Commander, SearchRequest, SearchResult
from back_end.server.app import app


CLIENT = TestClient(app)
CANDIDATE = Candidate(
    name="Troop of Ponies",
    title="Troop of Ponies (foil)",
    price=Decimal("3.99"),
    finish="FOIL",
    listing_url="https://www.ebay.co.uk/itm/147540417740",
    image_url=None,
    type_line="Creature — Horse",
    mana_cost="{2}",
    oracle_text="Vigilance",
)
RESULT = SearchResult(
    query="(s:hob) id<=g",
    commander=Commander(name="Radagast the Brown", colour_identity="G"),
    inspected=10,
    in_stock_count=1,
    candidates=[CANDIDATE],
)
CONVERSATION = {"conversation_id": "c123", "conversation_url": "https://tavus.daily.co/c123"}


class SearchEndpointTest(TestCase):
    @mock.patch("back_end.server.app.card_search", return_value=RESULT)
    def test_search(self, card_search):
        response = CLIENT.post("/api/search", json={"commander": "Radagast", "role": "ramp"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["result"]["candidates"][0]["listing_url"], CANDIDATE.listing_url)
        self.assertEqual(
            body["pal_output"],
            {
                "commander": "Radagast the Brown",
                "relaxed": False,
                "cards": [
                    {
                        "name": "Troop of Ponies",
                        "price": "£3.99",
                        "type": "Creature — Horse",
                        "text": "Vigilance",
                    }
                ],
            },
        )
        card_search.assert_called_once_with(SearchRequest(commander="Radagast", role="ramp"))

    def test_search_errors(self):
        test_cases = [
            {
                "description": "unknown commander",
                "error": CommanderNotFound("No card found"),
                "expected_status": 404,
            },
            {
                "description": "Scryfall rejects the query",
                "error": ScryfallError("Invalid query"),
                "expected_status": 502,
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            with mock.patch("back_end.server.app.card_search", side_effect=test_case["error"]):
                response = CLIENT.post("/api/search", json={"commander": "x"})
            self.assertEqual(
                response.status_code, test_case["expected_status"], f"Test case {test_desc} failed."
            )
            self.assertEqual(
                response.json()["detail"], str(test_case["error"]), f"Test case {test_desc} failed."
            )

    @mock.patch("back_end.server.app.card_search", return_value=RESULT)
    def test_search_invalid_request(self, card_search):
        test_cases = [
            {"description": "limit above 10", "body": {"commander": "x", "limit": 11}},
            {"description": "missing commander", "body": {"role": "ramp"}},
            {"description": "unknown card type", "body": {"commander": "x", "card_type": "dragon"}},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            response = CLIENT.post("/api/search", json=test_case["body"])
            self.assertEqual(response.status_code, 422, f"Test case {test_desc} failed.")
        card_search.assert_not_called()


@mock.patch.object(config, "TAVUS_API_KEY", "secret-key")
@mock.patch.object(config, "TAVUS_PAL_ID", "p123")
@mock.patch.object(config, "TAVUS_FACE_ID", "")
@mock.patch.object(config, "TAVUS_TEST_MODE", True)
@mock.patch.object(config, "MAX_CALL_DURATION", 180)
class ConversationEndpointTest(TestCase):
    @mock.patch("back_end.api.tavus.tavus.create_conversation", return_value=CONVERSATION)
    def test_create_conversation(self, create_conversation):
        response = CLIENT.post("/api/conversations")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), CONVERSATION)
        session, payload = create_conversation.call_args.args
        self.assertEqual(session.headers["x-api-key"], "secret-key")
        self.assertEqual(payload["pal_id"], "p123")
        self.assertTrue(payload["test_mode"])
        self.assertEqual(payload["properties"]["max_call_duration"], 180)

    def test_create_conversation_not_configured(self):
        test_cases = [
            {"description": "missing API key", "api_key": "", "pal_id": "p123"},
            {"description": "missing PAL id", "api_key": "secret-key", "pal_id": ""},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            with (
                mock.patch.object(config, "TAVUS_API_KEY", test_case["api_key"]),
                mock.patch.object(config, "TAVUS_PAL_ID", test_case["pal_id"]),
            ):
                response = CLIENT.post("/api/conversations")
            self.assertEqual(response.status_code, 500, f"Test case {test_desc} failed.")
            self.assertNotIn("secret-key", response.text, f"Test case {test_desc} failed.")

    @mock.patch(
        "back_end.api.tavus.tavus.create_conversation", side_effect=TavusError("Tavus failed")
    )
    def test_create_conversation_tavus_error(self, create_conversation):
        response = CLIENT.post("/api/conversations")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Tavus failed")

    @mock.patch("back_end.api.tavus.tavus.end_conversation", return_value=None)
    def test_end_conversation(self, end_conversation):
        response = CLIENT.post("/api/conversations/c123/end")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(end_conversation.call_args.args[1], "c123")

    @mock.patch("back_end.api.tavus.tavus.end_conversation", return_value=None)
    def test_end_conversation_invalid_id(self, end_conversation):
        response = CLIENT.post("/api/conversations/bad%20id!/end")
        self.assertEqual(response.status_code, 422)
        end_conversation.assert_not_called()


class HealthEndpointTest(TestCase):
    def test_health(self):
        response = CLIENT.get("/api/health")
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
