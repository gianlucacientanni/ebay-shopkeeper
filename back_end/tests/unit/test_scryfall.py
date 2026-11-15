# standard library
import unittest
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.api.scryfall.scryfall import to_commander, to_scryfall_card
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


if __name__ == "__main__":
    unittest.main()
