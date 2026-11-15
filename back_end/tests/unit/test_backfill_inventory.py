import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from back_end.database import backfill_inventory as backfill


def _offer(**overrides):
    offer = {
        "sku": "GANDALF_THE_GREY-FOIL-HOB-123A",
        "status": "PUBLISHED",
        "availableQuantity": 2,
        "pricingSummary": {"price": {"value": "1.49", "currency": "GBP"}},
        "listing": {"listingId": "987654321", "listingStatus": "ACTIVE"},
    }
    offer.update(overrides)
    return offer


CARD = {
    "id": "1f9a61a1-454e-4d5b-a6dd-1a79fe9dedf3",
    "name": "Front Face // Back Face",
    "color_identity": ["G", "W"],
    "scryfall_uri": "https://scryfall.com/card/hob/9/x?utm_source=api",
    "card_faces": [{"image_uris": {"normal": "https://img/front.jpg"}}],
}


class TestParseSku(unittest.TestCase):
    def test_parses_parts_from_the_right(self):
        sku = backfill.parse_sku("BAT-WINGED_THING-NONFOIL-ECL-12")
        self.assertIsNotNone(sku)
        assert sku is not None
        self.assertEqual(sku.name, "BAT-WINGED THING")
        self.assertEqual(sku.finish, "nonfoil")
        self.assertEqual(sku.set_code, "ecl")
        self.assertEqual(sku.collector_number, "12")

    def test_rejects_malformed(self):
        self.assertIsNone(backfill.parse_sku("JUST_A_NAME"))
        self.assertIsNone(backfill.parse_sku("A--HOB-1"))


class TestHelpers(unittest.TestCase):
    def test_normalize_name_matches_sku_token(self):
        self.assertEqual(
            backfill.normalize_name("Gandalf, the Grey"),
            backfill.normalize_name("GANDALF THE GREY"),
        )
        self.assertEqual(backfill.normalize_name("Fire // Ice"), "FIRE")

    def test_colour_identity_is_wubrg_ordered(self):
        self.assertEqual(backfill.format_colour_identity(["G", "W", "U"]), "WUG")
        self.assertEqual(backfill.format_colour_identity([]), "C")

    def test_name_from_title(self):
        self.assertEqual(
            backfill.name_from_title("Dwarven Provisioner - foil - The Hobbit - MTG"),
            "Dwarven Provisioner",
        )

    def test_pick_phash_id_prefers_matching_set(self):
        candidates = [("ltr", "id-ltr"), ("hob", "id-hob")]
        self.assertEqual(backfill.pick_phash_id(candidates, "hob"), "id-hob")
        self.assertEqual(backfill.pick_phash_id(candidates, "xyz"), "id-ltr")
        self.assertIsNone(backfill.pick_phash_id([], "hob"))


class TestListingFromOffer(unittest.TestCase):
    def test_live_offer(self):
        listing = backfill.listing_from_offer(_offer(), {})
        assert listing is not None
        self.assertEqual(listing.listing_url, "https://www.ebay.co.uk/itm/987654321")
        self.assertEqual(listing.price, Decimal("1.49"))
        self.assertEqual(listing.quantity, 2)

    def test_skips_unpublished_ended_and_sold_out(self):
        self.assertIsNone(backfill.listing_from_offer(_offer(status="UNPUBLISHED"), {}))
        self.assertIsNone(
            backfill.listing_from_offer(
                _offer(listing={"listingId": "1", "listingStatus": "ENDED"}), {}
            )
        )
        self.assertIsNone(backfill.listing_from_offer(_offer(availableQuantity=0), {}))
        self.assertIsNone(backfill.listing_from_offer(_offer(listing={}), {}))

    def test_falls_back_to_inventory_item(self):
        offer = _offer()
        del offer["availableQuantity"]
        items = {
            offer["sku"]: {
                "availability": {"shipToLocationAvailability": {"quantity": 3}},
                "product": {"title": "Gandalf, the Grey - foil - The Hobbit - MTG"},
            }
        }
        listing = backfill.listing_from_offer(offer, items)
        assert listing is not None
        self.assertEqual(listing.quantity, 3)
        self.assertEqual(listing.title, "Gandalf, the Grey - foil - The Hobbit - MTG")


class FakeEbayClient:
    """Mimics eBay: getOffers without a sku is a 400, unknown skus are a 404."""

    def __init__(self, items, offers_by_sku):
        self.items = items
        self.offers_by_sku = offers_by_sku

    def request(self, method, path, *, params=None):
        params = params or {}
        if path.endswith("/inventory_item"):
            offset, limit = params["offset"], params["limit"]
            page = self.items[offset : offset + limit]
            return {"inventoryItems": page, "total": len(self.items)}
        if path.endswith("/offer"):
            sku = params.get("sku")
            if not sku:
                raise RuntimeError("eBay API error 400: invalid value for a SKU")
            if sku not in self.offers_by_sku:
                raise RuntimeError("eBay API error 404")
            return {"offers": self.offers_by_sku[sku]}
        raise AssertionError(path)


class TestFetchListings(unittest.TestCase):
    def test_fetches_offers_per_sku(self):
        live, ended, no_offer = "A-FOIL-HOB-1", "B-FOIL-HOB-2", "C-FOIL-HOB-3"
        client = FakeEbayClient(
            items=[{"sku": live}, {"sku": ended}, {"sku": no_offer}],
            offers_by_sku={
                live: [_offer(sku=live)],
                ended: [_offer(sku=ended, listing={"listingId": "2", "listingStatus": "ENDED"})],
            },
        )
        listings = backfill.fetch_listings(client)
        self.assertEqual([listing.sku for listing in listings], [live])


class TestQuality(unittest.TestCase):
    def _row(self, sku, card_name, **listing_overrides):
        listing = backfill.Listing(
            sku=sku,
            listing_url="u",
            price=Decimal("1"),
            quantity=1,
            title=listing_overrides.get("title"),
        )
        card = dict(CARD, name=card_name)
        return listing, backfill.to_inventory_row(listing, card)

    def test_matching_name_has_no_flags(self):
        listing, row = self._row("GANDALF_THE_GREY-FOIL-HOB-1", "Gandalf, the Grey")
        self.assertEqual(backfill.quality_flags(listing, row), [])

    def test_wrong_card_is_flagged(self):
        listing, row = self._row("GANDALF_THE_GREY-FOIL-HOB-1", "Bilbo Baggins")
        self.assertIn("name_mismatch", backfill.quality_flags(listing, row))

    def test_title_name_is_accepted_when_sku_unparseable(self):
        listing, row = self._row(
            "WEIRDSKU", "Lightning Bolt", title="Lightning Bolt - foil - X - MTG"
        )
        self.assertEqual(backfill.quality_flags(listing, row), [])

    def test_preview_sorts_flagged_rows_first(self):
        good_listing, good = self._row("A_CARD-FOIL-HOB-1", "A Card")
        bad_listing, bad = self._row("B_CARD-FOIL-HOB-2", "Something Else")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preview.csv"
            counts, flagged = backfill.write_preview(
                path, [good, bad], [good_listing, bad_listing], {}
            )
            lines = path.read_text().splitlines()
        self.assertEqual(flagged, 1)
        self.assertEqual(counts["name_mismatch"], 1)
        self.assertTrue(lines[1].startswith("name_mismatch"))


class TestRowsAndWrite(unittest.TestCase):
    def test_row_and_write_roundtrip(self):
        listing = backfill.listing_from_offer(_offer(), {})
        assert listing is not None
        row = backfill.to_inventory_row(listing, CARD)
        self.assertEqual(row.name, "Front Face")
        self.assertEqual(row.colour_identity, "WG")
        self.assertEqual(row.scryfall_url, "https://scryfall.com/card/hob/9/x")
        self.assertEqual(row.image_url, "https://img/front.jpg")
        self.assertEqual(row.id, backfill.to_inventory_row(listing, CARD).id)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "inventory.sqlite3"
            backfill.write_inventory(output, [row])
            backfill.write_inventory(output, [row])  # re-runnable
            with sqlite3.connect(output) as conn:
                rows = conn.execute(
                    "SELECT sku, colour_identity, price, quantity FROM inventory"
                ).fetchall()
        self.assertEqual(rows, [("GANDALF_THE_GREY-FOIL-HOB-123A", "WG", 1.49, 2)])


if __name__ == "__main__":
    unittest.main()
