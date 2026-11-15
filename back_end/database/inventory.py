# standard library
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Optional

# ebay_shopkeeper imports
from back_end.common.cards import normalize_name
from back_end.common.config import INVENTORY_DB_PATH
from back_end.common.models import InventoryRow, Listing, ScryfallCard


FOIL = "FOIL"
NONFOIL = "NONFOIL"

# In-stock listings keyed by normalize_name(card name). A card can have several listings,
# e.g. a foil and a non-foil copy.
InventoryIndex = dict[str, list[InventoryRow]]


def sku_finish(sku: str) -> str:
    """
    Return the finish part of an Arcanum SKU (NAME-FINISH-SETCODE-COLLECTORNUMBER), e.g.
    "TROOP_OF_PONIES-FOIL-HOB-1" -> "FOIL"
    The name may itself contain hyphens, so the SKU is split from the right.
    """
    parts = sku.rsplit("-", 3)
    return parts[1].upper() if len(parts) == 4 else "UNKNOWN"


def load_inventory(db_path: Path = INVENTORY_DB_PATH) -> InventoryIndex:
    """
    Load every in-stock listing from the local SQLite copy of the eBay store, keyed by
    normalised card name. The database is opened read-only.

    Matching is done by name rather than scryfall_id because Scryfall ids are per printing:
    a Scryfall search may return a different printing of a card that is in stock.

    :raises FileNotFoundError: if the database file does not exist
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Inventory database not found: {db_path}")
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT sku, name, price, quantity, listing_url, image_url "
            "FROM inventory WHERE quantity IS NULL OR quantity > 0"
        ).fetchall()

    index: InventoryIndex = defaultdict(list)
    for sku, name, price, quantity, listing_url, image_url in rows:
        index[normalize_name(name)].append(
            InventoryRow(
                sku=sku,
                name=name,
                price=None if price is None else Decimal(str(price)),
                quantity=quantity,
                listing_url=listing_url,
                image_url=image_url,
            )
        )
    return dict(index)


def choose_row(rows: list[InventoryRow]) -> InventoryRow:
    """
    Choose which listing of a card to show: the foil if there is one, otherwise the cheapest.
    Listings without a price sort last.
    """
    foils = [row for row in rows if sku_finish(row.sku) == FOIL]
    return min(foils or rows, key=lambda row: (row.price is None, row.price or Decimal(0)))


def find_in_stock(
    cards: Iterable[ScryfallCard],
    inventory: InventoryIndex,
    max_price: Optional[Decimal] = None,
) -> list[Listing]:
    """
    Return one Listing per in-stock card, keeping the order of the input cards (EDHREC order
    when called from the pipeline). Cards that appear more than once are only returned once.

    :param cards: Scryfall cards to check
    :param inventory: index from load_inventory
    :param max_price: if set, listings above this price (or without a price) are ignored
    """
    listings: list[Listing] = []
    seen: set[str] = set()
    for card in cards:
        key = normalize_name(card.name)
        if key in seen:
            continue
        rows = inventory.get(key, [])
        if max_price is not None:
            rows = [row for row in rows if row.price is not None and row.price <= max_price]
        if not rows:
            continue
        seen.add(key)
        chosen = choose_row(rows)
        finish = sku_finish(chosen.sku)
        listings.append(
            Listing(
                row=chosen,
                finish=finish,
                card=card,
                other_finishes=sorted({sku_finish(row.sku) for row in rows} - {finish}),
            )
        )
    return listings


def listing_title(listing: Listing) -> str:
    """
    A short, speakable title for a listing, e.g. "Troop of Ponies (foil)".
    Non-foil listings are shown with the card name alone.
    """
    if listing.finish == NONFOIL:
        return listing.row.name
    return f"{listing.row.name} ({listing.finish.lower()})"
