# standard library
import unittest
from decimal import Decimal
from unittest import TestCase, mock

# third party
import requests

# ebay_shopkeeper imports
from back_end.common import config
from back_end.common.models import Candidate, Commander, SearchResult
from back_end.pal import preflight, shopkeeper


SEARCH_TOOL = {"name": "search_cards", "on_resolve": "generate_response"}
END_CALL_TOOL = {"name": "end_call", "on_resolve": None}
RESULT = SearchResult(
    query="q",
    commander=Commander(name="Radagast the Brown", colour_identity="G"),
    inspected=10,
    in_stock_count=1,
    candidates=[
        Candidate(
            name="Springleaf Drum", title="Springleaf Drum", price=Decimal("1.99"), finish="NONFOIL",
            listing_url="https://www.ebay.co.uk/itm/1", image_url=None, type_line="Artifact",
            mana_cost="{1}", oracle_text="",
        )
    ],
)


def live_pal(objectives_id: str = "o1") -> dict:
    """
    A PAL document as Tavus returns it, matching shopkeeper.py.
    """
    return shopkeeper.pal_definition(objectives_id)


class PreflightTest(TestCase):
    def test_value_at(self):
        document = {"layers": {"llm": {"model": "tavus-gpt-sol"}}}
        self.assertEqual(preflight.value_at(document, "/layers/llm/model"), "tavus-gpt-sol")
        self.assertIsNone(preflight.value_at(document, "/layers/tts/voice_id"))

    def test_check_pal(self):
        test_cases = [
            {"description": "matches", "pal": live_pal(), "expected": True},
            {
                "description": "prompt changed locally",
                "pal": {**live_pal(), "system_prompt": "old prompt"},
                "expected": False,
            },
            {
                "description": "wrong model",
                "pal": {**live_pal(), "layers": {**live_pal()["layers"], "llm": {"model": "tavus-gemma"}}},
                "expected": False,
            },
            {
                "description": "no objectives",
                "pal": {**live_pal(), "objectives_id": ""},
                "expected": False,
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            check = preflight.check_pal(test_case["pal"])
            self.assertEqual(check.passed, test_case["expected"], f"Test case {test_desc} failed: {check}")

    def test_check_pal_stale_suggests_setup(self):
        check = preflight.check_pal({**live_pal(), "greeting": "Hello"})
        self.assertIn("/greeting", check.detail)
        self.assertIn("setup-pal", check.detail)

    def test_check_tools(self):
        test_cases = [
            {"description": "both tools", "tools": [SEARCH_TOOL, END_CALL_TOOL], "expected": True},
            {"description": "end_call missing", "tools": [SEARCH_TOOL], "expected": False},
            {
                "description": "search result not spoken",
                "tools": [{**SEARCH_TOOL, "on_resolve": "fire_and_forget"}, END_CALL_TOOL],
                "expected": False,
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                preflight.check_tools(test_case["tools"]).passed,
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_check_config(self):
        test_cases = [
            {"description": "ready", "test_mode": False, "duration": 180, "pal_id": "p1", "failed": []},
            {
                "description": "test mode on",
                "test_mode": True, "duration": 180, "pal_id": "p1",
                "failed": ["Real calls (TAVUS_TEST_MODE=false)"],
            },
            {
                "description": "call too long and no PAL",
                "test_mode": False, "duration": 600, "pal_id": "",
                "failed": ["Call capped at 180s or less", "PAL id configured"],
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            with (
                mock.patch.object(config, "TAVUS_TEST_MODE", test_case["test_mode"]),
                mock.patch.object(config, "MAX_CALL_DURATION", test_case["duration"]),
                mock.patch.object(config, "TAVUS_PAL_ID", test_case["pal_id"]),
            ):
                failed = [check.name for check in preflight.check_config() if not check.passed]
            self.assertEqual(failed, test_case["failed"], f"Test case {test_desc} failed.")

    def test_check_backend(self):
        test_cases = [
            {"description": "running", "outcome": mock.Mock(ok=True, status_code=200), "expected": True},
            {"description": "erroring", "outcome": mock.Mock(ok=False, status_code=500), "expected": False},
            {"description": "not running", "outcome": requests.ConnectionError(), "expected": False},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            with mock.patch.object(preflight.requests, "get", side_effect=[test_case["outcome"]]):
                check = preflight.check_backend("http://localhost:8000")
            self.assertEqual(check.passed, test_case["expected"], f"Test case {test_desc} failed.")

    def test_check_search(self):
        test_cases = [
            {"description": "finds stock", "outcome": RESULT, "expected": True},
            {"description": "no stock", "outcome": RESULT.model_copy(update={"candidates": []}), "expected": False},
            {"description": "search fails", "outcome": RuntimeError("Scryfall down"), "expected": False},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            with mock.patch.object(preflight, "card_search", side_effect=[test_case["outcome"]]):
                check = preflight.check_search()
            self.assertEqual(check.passed, test_case["expected"], f"Test case {test_desc} failed.")


if __name__ == "__main__":
    unittest.main()
