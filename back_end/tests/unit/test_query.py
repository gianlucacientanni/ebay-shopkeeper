# standard library
import unittest
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.common.models import SearchRequest
from back_end.search.query import ROLE_FILTERS, build_query, normalize_role, quote


STOCKED_SETS_FILTER = "(s:ecl or s:sos or s:hob or s:fra or s:tla)"


class QueryTest(TestCase):
    def test_build_query(self):
        request = SearchRequest(commander="Radagast", card_type="creature", role="ramp")
        query = build_query(request, "G", "Radagast the Brown")
        self.assertEqual(
            query,
            f'{STOCKED_SETS_FILTER} id<=g t:creature otag:ramp -t:basic -!"Radagast the Brown"',
        )

    def test_build_query_no_type_or_role(self):
        query = build_query(SearchRequest(commander="x"), "WUB", "Some Commander")
        self.assertEqual(query, f'{STOCKED_SETS_FILTER} id<=wub -t:basic -!"Some Commander"')

    def test_build_query_colourless_commander(self):
        query = build_query(SearchRequest(commander="x"), "C", "Kozilek")
        self.assertIn(" id<=c ", query)

    def test_build_query_exclude_role(self):
        request = SearchRequest(commander="x", role="removal")
        query = build_query(request, "B", "X", include_role=False)
        self.assertNotIn("otag:removal", query)

    def test_build_query_unknown_role_dropped(self):
        request = SearchRequest(commander="x", role="make my deck better")
        with self.assertLogs("back_end.search.query", level="WARNING"):
            query = build_query(request, "B", "X")
        self.assertNotIn("otag", query)

    def test_quote(self):
        self.assertEqual(quote('Bad "Name"'), '"Bad Name"')

    def test_normalize_role(self):
        test_cases = [
            {"description": "exact key", "role": "ramp", "expected": "ramp"},
            {"description": "spaces and capitals", "role": "Card draw", "expected": "card_draw"},
            {"description": "hyphenated", "role": "board-wipe", "expected": "board_wipe"},
            {"description": "alias", "role": "draw", "expected": "card_draw"},
            {"description": "surrounding whitespace", "role": "  RAMP ", "expected": "ramp"},
            {"description": "None", "role": None, "expected": None},
            {"description": "empty string", "role": "", "expected": None},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                normalize_role(test_case["role"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_normalize_role_every_role_maps_to_itself(self):
        for role in ROLE_FILTERS:
            self.assertEqual(normalize_role(role), role, f"Test case {role} failed.")


if __name__ == "__main__":
    unittest.main()
