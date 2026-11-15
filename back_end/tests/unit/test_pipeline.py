# standard library
import unittest
from decimal import Decimal
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.common.models import (
    Candidate,
    Commander,
    InventoryRow,
    Listing,
    ScryfallCard,
    SearchRequest,
)
from back_end.search.pipeline import find_in_stock_windowed, search_inventory, to_candidate


COMMANDER = Commander(name="Radagast the Brown", colour_identity="G")
ROLE_QUERY = (
    '(s:ecl or s:sos or s:hob or s:fra or s:tla) id<=g otag:ramp -t:basic -!"Radagast the Brown"'
)
BROAD_QUERY = '(s:ecl or s:sos or s:hob or s:fra or s:tla) id<=g -t:basic -!"Radagast the Brown"'
# 60 Scryfall results named CARD00..CARD59, in EDHREC order
CARDS = [ScryfallCard(name=f"CARD{i:02}", type_line="Creature") for i in range(60)]


def inventory_of(*names: str) -> dict[str, list[InventoryRow]]:
    """
    Build an inventory index with one foil listing per card name.
    Names are already normalised (upper-case alphanumerics) so they can be used as keys.
    """
    return {
        name: [
            InventoryRow(
                sku=f"{name}-FOIL-HOB-1",
                name=name,
                price=Decimal("2.00"),
                quantity=1,
                listing_url=f"https://www.ebay.co.uk/itm/{name}",
                image_url=None,
            )
        ]
        for name in names
    }


def names_of(listings: list[Listing]) -> list[str]:
    return [listing.row.name for listing in listings]


class PipelineTest(TestCase):
    def test_find_in_stock_windowed_stops_once_enough_in_stock(self):
        cards = iter(CARDS)
        inventory = inventory_of("CARD00", "CARD02", "CARD04", "CARD06", "CARD08", "CARD15")
        in_stock, inspected = find_in_stock_windowed(cards, inventory, min_in_stock=5)
        self.assertEqual(inspected, 10)
        self.assertEqual(names_of(in_stock), ["CARD00", "CARD02", "CARD04", "CARD06", "CARD08"])
        # cards beyond the first window are never pulled from the iterator
        self.assertEqual(next(cards).name, "CARD10")

    def test_find_in_stock_windowed_slides_until_min_in_stock(self):
        inventory = inventory_of("CARD03", "CARD12", "CARD25", "CARD27", "CARD31", "CARD44")
        in_stock, inspected = find_in_stock_windowed(iter(CARDS), inventory, min_in_stock=5)
        # the fifth in-stock card (CARD31) is in the fourth window
        self.assertEqual(inspected, 40)
        self.assertEqual(names_of(in_stock), ["CARD03", "CARD12", "CARD25", "CARD27", "CARD31"])

    def test_find_in_stock_windowed_window_limit(self):
        inventory = inventory_of("CARD25", "CARD55")
        in_stock, inspected = find_in_stock_windowed(
            iter(CARDS), inventory, min_in_stock=5, max_windows=5
        )
        # CARD55 is beyond 5 windows of 10, so only CARD25 is found
        self.assertEqual(inspected, 50)
        self.assertEqual(names_of(in_stock), ["CARD25"])

    def test_find_in_stock_windowed_fewer_results_than_window(self):
        in_stock, inspected = find_in_stock_windowed(
            iter(CARDS[:3]), inventory_of("CARD01"), min_in_stock=5
        )
        self.assertEqual(inspected, 3)
        self.assertEqual(names_of(in_stock), ["CARD01"])

    def test_to_candidate(self):
        row = InventoryRow(
            sku="TROOP_OF_PONIES-FOIL-HOB-1",
            name="Troop of Ponies",
            price=Decimal("3.99"),
            quantity=1,
            listing_url="https://www.ebay.co.uk/itm/2",
            image_url="https://img/troop.jpg",
        )
        card = ScryfallCard(
            name="Troop of Ponies",
            type_line="Creature — Horse",
            oracle_text="Vigilance",
            mana_cost="{1}{G}",
        )
        listing = Listing(row=row, finish="FOIL", card=card, other_finishes=["NONFOIL"])
        self.assertEqual(
            to_candidate(listing),
            Candidate(
                name="Troop of Ponies",
                title="Troop of Ponies (foil)",
                price=Decimal("3.99"),
                finish="FOIL",
                listing_url="https://www.ebay.co.uk/itm/2",
                image_url="https://img/troop.jpg",
                type_line="Creature — Horse",
                mana_cost="{1}{G}",
                oracle_text="Vigilance",
                other_finishes=["NONFOIL"],
            ),
        )

    def test_search_inventory(self):
        results = {ROLE_QUERY: CARDS}
        inventory = inventory_of("CARD01", "CARD02", "CARD03", "CARD04", "CARD05", "CARD06")
        result = search_inventory(
            SearchRequest(commander="radagast", role="ramp", limit=3),
            COMMANDER,
            search=lambda query: iter(results.get(query, [])),
            inventory=inventory,
        )
        self.assertEqual(result.query, ROLE_QUERY)
        self.assertEqual(result.inspected, 10)
        self.assertEqual(result.in_stock_count, 6)
        self.assertFalse(result.relaxed)
        # limit caps the candidates returned, in EDHREC order
        self.assertEqual([c.name for c in result.candidates], ["CARD01", "CARD02", "CARD03"])

    def test_search_inventory_relaxes_role_when_nothing_in_stock(self):
        results = {ROLE_QUERY: [ScryfallCard(name="UNSTOCKED")], BROAD_QUERY: CARDS[:2]}
        queries: list[str] = []

        def search(query: str):
            queries.append(query)
            return iter(results.get(query, []))

        result = search_inventory(
            SearchRequest(commander="radagast", role="ramp"),
            COMMANDER,
            search=search,
            inventory=inventory_of("CARD01"),
        )
        self.assertEqual(queries, [ROLE_QUERY, BROAD_QUERY])
        self.assertTrue(result.relaxed)
        self.assertEqual(result.query, BROAD_QUERY)
        self.assertEqual(result.inspected, 3)
        self.assertEqual([c.name for c in result.candidates], ["CARD01"])

    def test_search_inventory_nothing_in_stock_without_role(self):
        result = search_inventory(
            SearchRequest(commander="radagast"),
            COMMANDER,
            search=lambda query: iter(CARDS[:5]),
            inventory={},
        )
        self.assertFalse(result.relaxed)
        self.assertEqual(result.candidates, [])


if __name__ == "__main__":
    unittest.main()
