# standard library
import json
import unittest
from decimal import Decimal
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.common.models import Candidate, Commander, SearchResult
from back_end.pal.tool_output import (
    PAL_TEXT_CHARS,
    TOOL_RESULT_LIMIT_BYTES,
    pal_card,
    pal_tool_output,
    tool_result_size,
    truncate_text,
)


TROOP = Candidate(
    name="Troop of Ponies",
    title="Troop of Ponies (foil)",
    price=Decimal("3.99"),
    finish="FOIL",
    listing_url="https://www.ebay.co.uk/itm/147540417740",
    image_url="https://cards.scryfall.io/normal/front/troop.jpg",
    type_line="Creature — Horse",
    mana_cost="{2}",
    oracle_text="{2}, {T}, Sacrifice this creature:\nSearch your library for up to two basic lands.",
    other_finishes=["NONFOIL"],
)
RESULT = SearchResult(
    query="(s:hob) id<=g",
    commander=Commander(name="Radagast the Brown", colour_identity="G"),
    inspected=10,
    in_stock_count=1,
    relaxed=True,
    candidates=[TROOP],
)


class ToolOutputTest(TestCase):
    def test_truncate_text(self):
        test_cases = [
            {"description": "short text unchanged", "text": "Vigilance", "expected": "Vigilance"},
            {
                "description": "newlines and runs of spaces flattened",
                "text": "Flying\n\nWhen this  creature enters, draw a card.",
                "expected": "Flying When this creature enters, draw a card.",
            },
            {
                "description": "long text cut with an ellipsis",
                "text": "word " * 100,
                "expected": ("word " * 24).rstrip() + "…",
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                truncate_text(test_case["text"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_truncate_text_never_exceeds_limit(self):
        self.assertLessEqual(len(truncate_text("x" * 500)), PAL_TEXT_CHARS)

    def test_pal_card(self):
        self.assertEqual(
            pal_card(TROOP),
            {
                "name": "Troop of Ponies",
                "price": "£3.99",
                "type": "Creature — Horse",
                "text": "{2}, {T}, Sacrifice this creature: Search your library for up to two "
                "basic lands.",
            },
        )

    def test_pal_card_unknown_price(self):
        self.assertEqual(pal_card(TROOP.model_copy(update={"price": None}))["price"], "unknown")

    def test_pal_tool_output(self):
        output = pal_tool_output(RESULT)
        self.assertEqual(output["commander"], "Radagast the Brown")
        self.assertTrue(output["relaxed"])
        self.assertEqual([card["name"] for card in output["cards"]], ["Troop of Ponies"])

    def test_pal_tool_output_has_no_urls(self):
        serialised = json.dumps(pal_tool_output(RESULT))
        self.assertNotIn("http", serialised)

    def test_tool_result_size_worst_case_under_limit(self):
        # 10 cards (the maximum a search returns) with long names, long type lines and
        # rules text well beyond the truncation length.
        worst_case_card = TROOP.model_copy(
            update={
                "name": "Sakashima of a Thousand Faces // Some Very Long Back Face",
                "type_line": "Legendary Enchantment Creature — Human Wizard Rogue // Sorcery",
                "price": Decimal("199.99"),
                "oracle_text": "When this creature enters, \"quote\" " * 30,
            }
        )
        result = RESULT.model_copy(update={"candidates": [worst_case_card] * 10})
        size = tool_result_size(pal_tool_output(result))
        self.assertLess(size, TOOL_RESULT_LIMIT_BYTES)

    def test_tool_result_size_counts_utf8_bytes(self):
        self.assertEqual(tool_result_size("£") - tool_result_size(""), 2)


if __name__ == "__main__":
    unittest.main()
