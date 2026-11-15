"""
Live end-to-end search against real Scryfall and the real inventory database.

    RUN_LIVE=1 uv run pytest tests/e2e
"""

# standard library
import os
import unittest
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.common.config import INVENTORY_DB_PATH
from back_end.common.models import SearchRequest
from back_end.search.pipeline import card_search


RUN_LIVE = os.environ.get("RUN_LIVE") == "1"
RADAGAST_RAMP_REQUEST = SearchRequest(
    commander="Radagast the Brown", card_type="creature", role="ramp"
)


@unittest.skipUnless(RUN_LIVE, "set RUN_LIVE=1 to hit Scryfall")
@unittest.skipUnless(INVENTORY_DB_PATH.exists(), "inventory database missing")
class CardSearchLiveTest(TestCase):
    def test_card_search(self):
        result = card_search(RADAGAST_RAMP_REQUEST)
        self.assertEqual(result.commander.colour_identity, "G")
        self.assertTrue(result.candidates)
        for candidate in result.candidates:
            self.assertTrue(candidate.oracle_text, f"Test case {candidate.name} failed.")
            self.assertTrue(
                candidate.listing_url.startswith("https://www.ebay.co.uk/itm/"),
                f"Test case {candidate.name} failed.",
            )


if __name__ == "__main__":
    unittest.main()
