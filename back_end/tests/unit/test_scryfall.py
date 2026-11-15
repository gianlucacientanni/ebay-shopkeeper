# standard library
import unittest
from unittest import TestCase, mock

# third party
import requests

# ebay_shopkeeper imports
from back_end.api.scryfall.scryfall import (
    CommanderNotFound,
    ScryfallError,
    get_commander,
    search_cards,
    to_commander,
    to_scryfall_card,
)
from back_end.common.models import Commander, ScryfallCard


SINGLE_FACED_CARD = {
    "name": "Troop of Ponies",
    "type_line": "Creature — Horse",
    "mana_cost": "{1}{G}",
    "oracle_text": "Vigilance",
    "color_identity": ["G"],
}
DOUBLE_FACED_CARD = {
    "name": "Studious First-Year // Rampant Growth",
    "type_line": "Creature — Bear Wizard // Sorcery — Adventure",
    "card_faces": [
        {"mana_cost": "{G}", "oracle_text": "Reach"},
        {"mana_cost": "{1}{G}", "oracle_text": "Search your library for a basic land card."},
    ],
    "color_identity": ["G"],
}
COMMANDER_CARD = {
    "name": "Radagast the Brown",
    "type_line": "Legendary Creature — Avatar Wizard",
    "oracle_text": "Whenever Radagast the Brown or another nontoken creature enters...",
    "color_identity": ["G"],
}


class ScryfallTest(TestCase):
    def test_to_scryfall_card(self):
        self.assertEqual(
            to_scryfall_card(SINGLE_FACED_CARD),
            ScryfallCard(
                name="Troop of Ponies",
                type_line="Creature — Horse",
                oracle_text="Vigilance",
                mana_cost="{1}{G}",
            ),
        )

    def test_to_scryfall_card_double_faced(self):
        self.assertEqual(
            to_scryfall_card(DOUBLE_FACED_CARD),
            ScryfallCard(
                name="Studious First-Year // Rampant Growth",
                type_line="Creature — Bear Wizard // Sorcery — Adventure",
                oracle_text="Reach\n//\nSearch your library for a basic land card.",
                mana_cost="{G}",
            ),
        )

    def test_to_commander(self):
        self.assertEqual(
            to_commander(COMMANDER_CARD),
            Commander(
                name="Radagast the Brown",
                colour_identity="G",
                type_line="Legendary Creature — Avatar Wizard",
                oracle_text="Whenever Radagast the Brown or another nontoken creature enters...",
            ),
        )

    def test_to_commander_colourless(self):
        card = {"name": "Kozilek", "type_line": "Legendary Creature", "color_identity": []}
        self.assertEqual(to_commander(card).colour_identity, "C")

    def test_to_commander_not_legendary_warns(self):
        with self.assertLogs("back_end.api.scryfall.scryfall", level="WARNING"):
            commander = to_commander(SINGLE_FACED_CARD)
        self.assertEqual(commander.name, "Troop of Ponies")



def response(status_code: int, body: dict) -> mock.Mock:
    """
    A stand-in for requests.Response with a status code and a JSON body.
    """
    fake = mock.Mock(status_code=status_code, ok=200 <= status_code < 300, text=str(body))
    fake.json.return_value = body
    return fake


def session_returning(*outcomes) -> mock.Mock:
    """
    A stand-in for requests.Session whose get() returns (or raises) each outcome in turn.
    """
    session = mock.Mock()
    session.get.side_effect = outcomes
    return session


@mock.patch("back_end.api.scryfall.scryfall.time.sleep")
class ScryfallRequestTest(TestCase):
    def test_get_commander(self, sleep):
        session = session_returning(response(200, COMMANDER_CARD))
        self.assertEqual(get_commander(session, "radagast").name, "Radagast the Brown")

    def test_get_commander_not_found(self, sleep):
        session = session_returning(response(404, {"details": "No cards found"}))
        with self.assertRaises(CommanderNotFound):
            get_commander(session, "zzqqxx")

    def test_get_commander_failures_raise_scryfall_error(self, sleep):
        test_cases = [
            {"description": "server error", "outcome": response(500, {"details": "Oops"})},
            {"description": "rate limited", "outcome": response(429, {"details": "Slow down"})},
            {"description": "timeout", "outcome": requests.Timeout("read timed out")},
            {"description": "connection error", "outcome": requests.ConnectionError("refused")},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            session = session_returning(test_case["outcome"])
            with self.assertRaises(ScryfallError, msg=f"Test case {test_desc} failed."):
                get_commander(session, "radagast")

    def test_search_cards_follows_next_page(self, sleep):
        session = session_returning(
            response(200, {"data": [SINGLE_FACED_CARD], "has_more": True, "next_page": "p2"}),
            response(200, {"data": [DOUBLE_FACED_CARD], "has_more": False}),
        )
        names = [card.name for card in search_cards(session, "s:hob")]
        self.assertEqual(names, ["Troop of Ponies", "Studious First-Year // Rampant Growth"])

    def test_search_cards_no_matches(self, sleep):
        session = session_returning(response(404, {"details": "Your query didn't match"}))
        self.assertEqual(list(search_cards(session, "s:hob t:nothing")), [])

    def test_search_cards_failures_raise_scryfall_error(self, sleep):
        test_cases = [
            {
                "description": "invalid query",
                "outcome": response(400, {"details": "Unknown keyword"}),
                "expected_message": "Scryfall returned 400: Unknown keyword",
            },
            {
                "description": "server error",
                "outcome": response(503, {"details": "Down for maintenance"}),
                "expected_message": "Scryfall returned 503: Down for maintenance",
            },
            {
                "description": "timeout",
                "outcome": requests.Timeout("read timed out"),
                "expected_message": "Scryfall request failed: Timeout",
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            session = session_returning(test_case["outcome"])
            with self.assertRaises(ScryfallError, msg=f"Test case {test_desc} failed.") as ctx:
                list(search_cards(session, "s:hob"))
            self.assertEqual(
                str(ctx.exception), test_case["expected_message"], f"Test case {test_desc} failed."
            )


if __name__ == "__main__":
    unittest.main()
