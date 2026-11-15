# standard library
import unittest
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.common.cards import (
    format_colour_identity,
    front_face_name,
    image_url_for,
    normalize_name,
    oracle_text_for,
)


class CardsTest(TestCase):
    def test_front_face_name(self):
        test_cases = [
            {
                "description": "double-faced card",
                "name": "Studious First-Year // Rampant Growth",
                "expected": "Studious First-Year",
            },
            {
                "description": "single-faced card",
                "name": "Troop of Ponies",
                "expected": "Troop of Ponies",
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                front_face_name(test_case["name"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_normalize_name(self):
        test_cases = [
            {"description": "punctuation", "name": "Gandalf, the Grey", "expected": "GANDALFTHEGREY"},
            {"description": "sku token", "name": "GANDALF_THE_GREY", "expected": "GANDALFTHEGREY"},
            {
                "description": "double-faced card",
                "name": "Studious First-Year // Rampant Growth",
                "expected": "STUDIOUSFIRSTYEAR",
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                normalize_name(test_case["name"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_format_colour_identity(self):
        test_cases = [
            {"description": "reordered to WUBRG", "colours": ["G", "w"], "expected": "WG"},
            {"description": "colourless", "colours": [], "expected": "C"},
            {"description": "five colour", "colours": list("GRBUW"), "expected": "WUBRG"},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                format_colour_identity(test_case["colours"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_image_url_for(self):
        test_cases = [
            {
                "description": "single-faced card",
                "card": {"image_uris": {"normal": "https://img/card.jpg"}},
                "expected": "https://img/card.jpg",
            },
            {
                "description": "double-faced card uses the front face",
                "card": {"card_faces": [{"image_uris": {"normal": "https://img/front.jpg"}}]},
                "expected": "https://img/front.jpg",
            },
            {"description": "no image", "card": {}, "expected": None},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                image_url_for(test_case["card"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_oracle_text_for(self):
        test_cases = [
            {
                "description": "single-faced card",
                "card": {"oracle_text": "Vigilance"},
                "expected": "Vigilance",
            },
            {
                "description": "double-faced card joins faces",
                "card": {"card_faces": [{"oracle_text": "Reach"}, {"oracle_text": "Draw a card."}]},
                "expected": "Reach\n//\nDraw a card.",
            },
            {"description": "no text", "card": {}, "expected": ""},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                oracle_text_for(test_case["card"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )


if __name__ == "__main__":
    unittest.main()
