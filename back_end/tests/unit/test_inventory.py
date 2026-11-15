# standard library
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.common.models import InventoryRow, Listing, ScryfallCard
from back_end.database.inventory import (
    choose_row,
    find_in_stock,
    listing_title,
    load_inventory,
    sku_finish,
)


SCHEMA = (Path(__file__).resolve().parents[2] / "database" / "inventory.sql").read_text()
TROOP_NONFOIL = InventoryRow(
    sku="TROOP_OF_PONIES-NONFOIL-HOB-1",
    name="Troop of Ponies",
    price=Decimal("1.49"),
    quantity=2,
    listing_url="https://www.ebay.co.uk/itm/1",
    image_url=None,
)
TROOP_FOIL = InventoryRow(
    sku="TROOP_OF_PONIES-FOIL-HOB-1",
    name="Troop of Ponies",
    price=Decimal("3.99"),
    quantity=1,
    listing_url="https://www.ebay.co.uk/itm/2",
    image_url=None,
)
STUDIOUS = InventoryRow(
    sku="STUDIOUS_FIRSTYEAR-NONFOIL-SOS-2",
    name="Studious First-Year",
    price=Decimal("2.99"),
    quantity=1,
    listing_url="https://www.ebay.co.uk/itm/3",
    image_url=None,
)
GANDALF = InventoryRow(
    sku="GANDALF_THE_GREY-NONFOIL-HOB-3",
    name="Gandalf, the Grey",
    price=Decimal("9.99"),
    quantity=1,
    listing_url="https://www.ebay.co.uk/itm/4",
    image_url=None,
)
INVENTORY = {
    "TROOPOFPONIES": [TROOP_NONFOIL, TROOP_FOIL],
    "STUDIOUSFIRSTYEAR": [STUDIOUS],
    "GANDALFTHEGREY": [GANDALF],
}


def card(name: str) -> ScryfallCard:
    return ScryfallCard(name=name, type_line="Creature")


class InventoryTest(TestCase):
    def test_sku_finish(self):
        test_cases = [
            {"description": "foil", "sku": "TROOP_OF_PONIES-FOIL-HOB-1", "expected": "FOIL"},
            {"description": "non-foil", "sku": "ISLAND-NONFOIL-HOB-195", "expected": "NONFOIL"},
            {"description": "hyphen in name", "sku": "X-Y-FOIL-ECL-12A", "expected": "FOIL"},
            {"description": "malformed sku", "sku": "NOT_A_SKU", "expected": "UNKNOWN"},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                sku_finish(test_case["sku"]), test_case["expected"], f"Test case {test_desc} failed."
            )

    def test_choose_row_prefers_foil(self):
        self.assertEqual(choose_row([TROOP_NONFOIL, TROOP_FOIL]), TROOP_FOIL)

    def test_choose_row_cheapest_without_foil(self):
        expensive = InventoryRow(
            sku="TROOP_OF_PONIES-NONFOIL-LTR-9",
            name="Troop of Ponies",
            price=Decimal("5.00"),
            quantity=1,
            listing_url="https://www.ebay.co.uk/itm/9",
            image_url=None,
        )
        self.assertEqual(choose_row([expensive, TROOP_NONFOIL]), TROOP_NONFOIL)

    def test_find_in_stock_prefers_foil(self):
        listings = find_in_stock([card("Troop of Ponies")], INVENTORY)
        self.assertEqual(
            listings,
            [
                Listing(
                    row=TROOP_FOIL,
                    finish="FOIL",
                    card=card("Troop of Ponies"),
                    other_finishes=["NONFOIL"],
                )
            ],
        )

    def test_find_in_stock_double_faced_card(self):
        listings = find_in_stock([card("Studious First-Year // Rampant Growth")], INVENTORY)
        self.assertEqual([listing.row for listing in listings], [STUDIOUS])

    def test_find_in_stock_ignores_punctuation(self):
        listings = find_in_stock([card("Gandalf the Grey")], INVENTORY)
        self.assertEqual([listing.row for listing in listings], [GANDALF])

    def test_find_in_stock_not_in_inventory(self):
        self.assertEqual(find_in_stock([card("Sol Ring")], INVENTORY), [])

    def test_find_in_stock_keeps_order_and_dedupes(self):
        cards = [card("Gandalf, the Grey"), card("Troop of Ponies"), card("Gandalf, the Grey")]
        listings = find_in_stock(cards, INVENTORY)
        self.assertEqual([listing.row.name for listing in listings],
                         ["Gandalf, the Grey", "Troop of Ponies"])

    def test_find_in_stock_max_price(self):
        test_cases = [
            {
                "description": "foil over budget, non-foil chosen instead",
                "card_name": "Troop of Ponies",
                "max_price": Decimal("2"),
                "expected_rows": [TROOP_NONFOIL],
            },
            {
                "description": "every listing over budget",
                "card_name": "Gandalf, the Grey",
                "max_price": Decimal("5"),
                "expected_rows": [],
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            listings = find_in_stock(
                [card(test_case["card_name"])], INVENTORY, test_case["max_price"]
            )
            self.assertEqual(
                [listing.row for listing in listings],
                test_case["expected_rows"],
                f"Test case {test_desc} failed.",
            )

    def test_listing_title(self):
        test_cases = [
            {
                "description": "foil",
                "listing": Listing(row=TROOP_FOIL, finish="FOIL", card=card("Troop of Ponies")),
                "expected": "Troop of Ponies (foil)",
            },
            {
                "description": "non-foil",
                "listing": Listing(row=STUDIOUS, finish="NONFOIL", card=card("x")),
                "expected": "Studious First-Year",
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                listing_title(test_case["listing"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_load_inventory(self):
        rows = [
            # sku, name, price, quantity
            ("TROOP_OF_PONIES-NONFOIL-HOB-1", "Troop of Ponies", 1.49, 2),
            ("TROOP_OF_PONIES-FOIL-HOB-1", "Troop of Ponies", 3.99, 1),
            ("SOLD_OUT-NONFOIL-ECL-4", "Sold Out", 1.00, 0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "inventory.sqlite3"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(SCHEMA)
                for i, (sku, name, price, quantity) in enumerate(rows):
                    conn.execute(
                        "INSERT INTO inventory (id, sku, name, colour_identity, listing_url, "
                        "price, quantity) VALUES (?, ?, ?, 'G', ?, ?, ?)",
                        (str(i), sku, name, f"https://www.ebay.co.uk/itm/{i}", price, quantity),
                    )
            inventory = load_inventory(db_path)

        self.assertEqual(list(inventory), ["TROOPOFPONIES"])
        self.assertEqual(
            [(row.sku, row.price) for row in inventory["TROOPOFPONIES"]],
            [
                ("TROOP_OF_PONIES-NONFOIL-HOB-1", Decimal("1.49")),
                ("TROOP_OF_PONIES-FOIL-HOB-1", Decimal("3.99")),
            ],
        )

    def test_load_inventory_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_inventory(Path(tmp) / "missing.sqlite3")


if __name__ == "__main__":
    unittest.main()
