"""One-off backfill of the shopkeeper inventory table from the live eBay store.

Read-only against eBay: it only issues GET requests (offers and inventory items).

Run from the arcanum repo so its environment, config and keyring credentials are used:

    cd ~/arcanum
    uv run python ~/repos/ebay_shopkeeper/back_end/database/backfill_inventory.py

Flow:
1) page through every eBay inventory item (SKU, title, quantity), then fetch each SKU's
   offers (price, listing id, quantity); getOffers rejects requests without a sku,
2) parse set code + collector number out of each SKU (NAME-FINISH-SETCODE-COLLECTORNUMBER)
   and batch-look them up with Scryfall's /cards/collection endpoint,
3) for anything still unmatched, find the card name in arcanum's card_phash table to get a
   scryfall_id (preferring the SKU's set), then look that id up on Scryfall,
4) as a last resort, ask Scryfall's fuzzy name search,
5) recreate the inventory table in ebay_data/inventory.sqlite3 and write the rows.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sqlite3
import sys
import time
import uuid
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).resolve().parent / "inventory.sql"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "ebay_data" / "inventory.sqlite3"

SCRYFALL_BASE_URL = "https://api.scryfall.com"
SCRYFALL_HEADERS = {
    "User-Agent": "ebay-shopkeeper-backfill/0.1",
    "Accept": "application/json",
}
SCRYFALL_COLLECTION_BATCH_SIZE = 75
SCRYFALL_REQUEST_DELAY_SECONDS = 0.1

EBAY_PAGE_SIZE = 200
EBAY_MAX_PAGES = 250
EBAY_LISTING_URL = "https://www.ebay.co.uk/itm/{listing_id}"

MATCH_PRINTING = "set+collector_number"
MATCH_PHASH = "card_phash"
MATCH_FUZZY = "scryfall_fuzzy"

SKU_NAMESPACE = uuid.UUID("6f1c1d8e-3b0e-4c8e-9a51-2b7f0d0c5e11")
WUBRG_ORDER = "WUBRG"
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")


# --------------------------------------------------------------------------- models


@dataclass(frozen=True, slots=True)
class ParsedSku:
    name_token: str
    finish: str
    set_code: str
    collector_number: str

    @property
    def name(self) -> str:
        return " ".join(self.name_token.replace("_", " ").split())


@dataclass(frozen=True, slots=True)
class Listing:
    sku: str
    listing_url: str
    price: Decimal | None
    quantity: int | None
    title: str | None


@dataclass(frozen=True, slots=True)
class InventoryRow:
    id: str
    sku: str
    name: str
    scryfall_id: str
    scryfall_url: str
    colour_identity: str
    image_url: str | None
    listing_url: str
    price: Decimal | None
    quantity: int | None


# --------------------------------------------------------------------------- helpers


def parse_sku(sku: str) -> ParsedSku | None:
    """Split an arcanum SKU (NAME-FINISH-SETCODE-COLLECTORNUMBER).

    The name may itself contain hyphens, so split from the right.
    """
    parts = sku.strip().rsplit("-", 3)
    if len(parts) != 4 or not all(parts):
        return None
    name_token, finish, set_code, collector_number = parts
    return ParsedSku(
        name_token=name_token,
        finish=finish.lower(),
        set_code=set_code.lower(),
        collector_number=collector_number.lower(),
    )


def normalize_name(name: str) -> str:
    """Normalise a card name so SKU tokens and real names compare equal.

    SKUs drop punctuation ("Gandalf, the Grey" -> "GANDALF_THE_GREY"), so compare on
    upper-case alphanumerics only, using the front face of double-faced cards.
    """
    front = name.split("//")[0]
    return _NON_ALNUM_RE.sub("", front.upper())


def name_from_title(title: str) -> str:
    """Arcanum titles look like "Card Name - foil - Set Name - MTG"."""
    return title.split(" - ")[0].strip()


def format_colour_identity(colours: Iterable[str]) -> str:
    letters = {c.upper() for c in colours}
    ordered = "".join(c for c in WUBRG_ORDER if c in letters)
    return ordered or "C"


def clean_scryfall_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.split("?", 1)[0]


def front_face_name(name: str) -> str:
    return name.split(" // ")[0].strip()


def image_url_for(card: Mapping[str, Any]) -> str | None:
    image_uris = card.get("image_uris")
    if isinstance(image_uris, Mapping) and image_uris.get("normal"):
        return str(image_uris["normal"])
    faces = card.get("card_faces")
    if isinstance(faces, list) and faces and isinstance(faces[0], Mapping):
        face_uris = faces[0].get("image_uris")
        if isinstance(face_uris, Mapping) and face_uris.get("normal"):
            return str(face_uris["normal"])
    return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def listing_from_offer(
    offer: Mapping[str, Any], inventory_items: Mapping[str, Mapping[str, Any]]
) -> Listing | None:
    """Turn an eBay offer into a Listing, or None if it isn't live and in stock."""
    sku = str(offer.get("sku") or "").strip()
    if not sku or offer.get("status") != "PUBLISHED":
        return None

    listing = offer.get("listing")
    listing = listing if isinstance(listing, Mapping) else {}
    listing_id = listing.get("listingId") or offer.get("listingId")
    if not listing_id:
        return None
    listing_status = listing.get("listingStatus")
    if listing_status and listing_status != "ACTIVE":
        return None

    item = inventory_items.get(sku, {})
    quantity = _to_int(offer.get("availableQuantity"))
    if quantity is None:
        availability = item.get("availability")
        if isinstance(availability, Mapping):
            ship = availability.get("shipToLocationAvailability")
            if isinstance(ship, Mapping):
                quantity = _to_int(ship.get("quantity"))
    if quantity == 0:
        return None

    pricing = offer.get("pricingSummary")
    price_info = pricing.get("price") if isinstance(pricing, Mapping) else None
    price = _to_decimal(price_info.get("value")) if isinstance(price_info, Mapping) else None

    product = item.get("product")
    title = product.get("title") if isinstance(product, Mapping) else None

    return Listing(
        sku=sku,
        listing_url=EBAY_LISTING_URL.format(listing_id=listing_id),
        price=price,
        quantity=quantity,
        title=str(title) if title else None,
    )


def to_inventory_row(listing: Listing, card: Mapping[str, Any]) -> InventoryRow:
    return InventoryRow(
        id=str(uuid.uuid5(SKU_NAMESPACE, listing.sku)),
        sku=listing.sku,
        name=front_face_name(str(card["name"])),
        scryfall_id=str(card["id"]),
        scryfall_url=clean_scryfall_url(card.get("scryfall_uri")) or "",
        colour_identity=format_colour_identity(card.get("color_identity") or []),
        image_url=image_url_for(card),
        listing_url=listing.listing_url,
        price=listing.price,
        quantity=listing.quantity,
    )


def _batched(items: list[Any], size: int) -> Iterator[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


# --------------------------------------------------------------------------- eBay


def _paginate(client: Any, path: str, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    for _ in range(EBAY_MAX_PAGES):
        payload = client.request(
            "GET", path, params={"limit": EBAY_PAGE_SIZE, "offset": offset}
        )
        page = [row for row in payload.get(key) or [] if isinstance(row, dict)]
        rows.extend(page)
        total = _to_int(payload.get("total"))
        offset += EBAY_PAGE_SIZE
        logger.info("Fetched %s %s (total=%s)", len(rows), key, total)
        if not page or len(page) < EBAY_PAGE_SIZE or (total is not None and offset >= total):
            break
    return rows


def build_ebay_client() -> Any:
    """Build arcanum's eBay client from the production keyring, as arcanum's CLIs do."""
    from arcanum.api.ebay import ebay
    from arcanum.common import constants

    if not constants.IS_PRODUCTION:
        raise SystemExit(
            "Arcanum is not in production mode. Re-run with ARCANUM_ENV=production."
        )

    creds = ebay.load_keyring_credentials(service=constants.KEYRING_SERVICE)
    config = ebay.EbayConfig()
    config.base_url = constants.DEFAULT_BASE_URL
    config.auth_url = constants.DEFAULT_AUTH_URL
    config.consent_url = constants.DEFAULT_CONSENT_URL
    config.keyring_service = constants.KEYRING_SERVICE
    config.access_token = creds.get("user_access_token")
    config.client_id = creds.get("ebay_client_id")
    config.client_secret = creds.get("ebay_client_secret")
    config.refresh_token = creds.get("ebay_refresh_token")

    if config.client_id and not constants.client_id_matches_environment(config.client_id):
        raise SystemExit(
            f"Keyring service '{constants.KEYRING_SERVICE}' does not hold production "
            "credentials."
        )
    return ebay.EbayClient(config)


def fetch_offers_for_sku(client: Any, sku: str) -> list[dict[str, Any]]:
    """getOffers requires a sku, so offers are fetched one inventory item at a time."""
    try:
        payload = client.request("GET", "/sell/inventory/v1/offer", params={"sku": sku})
    except RuntimeError as exc:
        # e.g. 404 for an inventory item that never had an offer created
        logger.debug("No offers for sku=%s: %s", sku, exc)
        return []
    return [offer for offer in payload.get("offers") or [] if isinstance(offer, dict)]


def fetch_listings(client: Any) -> list[Listing]:
    items = _paginate(client, "/sell/inventory/v1/inventory_item", "inventoryItems")
    items_by_sku = {str(item.get("sku")): item for item in items if item.get("sku")}

    listings: dict[str, Listing] = {}
    offer_count = 0
    for position, sku in enumerate(items_by_sku, start=1):
        for offer in fetch_offers_for_sku(client, sku):
            offer_count += 1
            listing = listing_from_offer(offer, items_by_sku)
            if listing is not None:
                listings.setdefault(listing.sku, listing)
        if position % 50 == 0 or position == len(items_by_sku):
            logger.info(
                "Fetched offers for %s/%s SKUs (%s live listings so far)",
                position,
                len(items_by_sku),
                len(listings),
            )
    logger.info(
        "%s inventory items, %s offers -> %s live listings",
        len(items_by_sku),
        offer_count,
        len(listings),
    )
    return list(listings.values())


# --------------------------------------------------------------------------- Scryfall


def scryfall_collection(
    session: Any, identifiers: list[dict[str, str]]
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for batch in _batched(identifiers, SCRYFALL_COLLECTION_BATCH_SIZE):
        response = session.post(
            f"{SCRYFALL_BASE_URL}/cards/collection",
            json={"identifiers": batch},
            timeout=30,
        )
        response.raise_for_status()
        cards.extend(response.json().get("data") or [])
        time.sleep(SCRYFALL_REQUEST_DELAY_SECONDS)
    return cards


def scryfall_fuzzy(session: Any, name: str) -> dict[str, Any] | None:
    response = session.get(
        f"{SCRYFALL_BASE_URL}/cards/named", params={"fuzzy": name}, timeout=30
    )
    time.sleep(SCRYFALL_REQUEST_DELAY_SECONDS)
    if response.status_code != 200:
        return None
    return response.json()


def load_phash_index(phash_db: Path) -> dict[str, list[tuple[str | None, str]]]:
    """normalised name -> [(set_code, scryfall_id), ...] from arcanum's card_phash."""
    index: dict[str, list[tuple[str | None, str]]] = {}
    uri = f"file:{phash_db}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        for scryfall_id, name, set_code in conn.execute(
            "SELECT scryfall_id, name, set_code FROM card_phash"
        ):
            key = normalize_name(name)
            index.setdefault(key, []).append(
                ((set_code or "").lower() or None, scryfall_id)
            )
    logger.info("Loaded %s card names from card_phash", len(index))
    return index


def pick_phash_id(
    candidates: list[tuple[str | None, str]], set_code: str | None
) -> str | None:
    if not candidates:
        return None
    if set_code:
        for candidate_set, scryfall_id in candidates:
            if candidate_set == set_code:
                return scryfall_id
    return candidates[0][1]


def match_cards(
    listings: list[Listing], session: Any, phash_db: Path
) -> tuple[list[InventoryRow], list[Listing], dict[str, str]]:
    rows: dict[str, InventoryRow] = {}
    methods: dict[str, str] = {}
    parsed = {listing.sku: parse_sku(listing.sku) for listing in listings}

    # 1) exact printing via set code + collector number
    by_printing: dict[tuple[str, str], list[Listing]] = {}
    for listing in listings:
        sku = parsed[listing.sku]
        if sku is not None:
            by_printing.setdefault((sku.set_code, sku.collector_number), []).append(
                listing
            )
    identifiers = [{"set": s, "collector_number": n} for s, n in by_printing]
    for card in scryfall_collection(session, identifiers):
        key = (str(card.get("set", "")).lower(), str(card.get("collector_number", "")).lower())
        for listing in by_printing.get(key, []):
            rows[listing.sku] = to_inventory_row(listing, card)
            methods[listing.sku] = MATCH_PRINTING
    logger.info("Matched %s/%s listings by set + collector number", len(rows), len(listings))

    # 2) card_phash name lookup -> Scryfall by id
    remaining = [listing for listing in listings if listing.sku not in rows]
    if remaining:
        index = load_phash_index(phash_db)
        by_id: dict[str, list[Listing]] = {}
        for listing in remaining:
            sku = parsed[listing.sku]
            name = sku.name if sku else name_from_title(listing.title or "")
            scryfall_id = pick_phash_id(
                index.get(normalize_name(name), []), sku.set_code if sku else None
            )
            if scryfall_id:
                by_id.setdefault(scryfall_id, []).append(listing)
        for card in scryfall_collection(session, [{"id": i} for i in by_id]):
            for listing in by_id.get(str(card.get("id")), []):
                rows[listing.sku] = to_inventory_row(listing, card)
                methods[listing.sku] = MATCH_PHASH
        logger.info("Matched %s/%s listings after card_phash", len(rows), len(listings))

    # 3) Scryfall fuzzy name search
    remaining = [listing for listing in listings if listing.sku not in rows]
    for listing in remaining:
        sku = parsed[listing.sku]
        name = name_from_title(listing.title) if listing.title else (sku.name if sku else "")
        card = scryfall_fuzzy(session, name) if name else None
        if card is not None:
            rows[listing.sku] = to_inventory_row(listing, card)
            methods[listing.sku] = MATCH_FUZZY
    if remaining:
        logger.info("Matched %s/%s listings after fuzzy search", len(rows), len(listings))

    unmatched = [listing for listing in listings if listing.sku not in rows]
    return list(rows.values()), unmatched, methods


# --------------------------------------------------------------------------- quality


def quality_flags(listing: Listing, row: InventoryRow) -> list[str]:
    """Cheap sanity checks on a matched row; an empty list means it looks right.

    The main one: the card name Scryfall returned should match the name in the SKU
    (or, failing that, the eBay title). A mismatch usually means a wrong match.
    """
    flags: list[str] = []
    expected = []
    sku = parse_sku(listing.sku)
    if sku is not None:
        expected.append(normalize_name(sku.name))
    if listing.title:
        expected.append(normalize_name(name_from_title(listing.title)))
    if expected and normalize_name(row.name) not in expected:
        flags.append("name_mismatch")
    if row.price is None:
        flags.append("missing_price")
    if row.quantity is None:
        flags.append("missing_quantity")
    if not row.image_url:
        flags.append("missing_image")
    return flags


PREVIEW_COLUMNS = [
    "flags",
    "match_method",
    "sku",
    "ebay_title",
    "name",
    "colour_identity",
    "price",
    "quantity",
    "scryfall_url",
    "listing_url",
    "image_url",
]


def write_preview(
    path: Path,
    rows: list[InventoryRow],
    listings: list[Listing],
    methods: Mapping[str, str],
) -> tuple[Counter[str], int]:
    """Write every matched row to a CSV for eyeballing; flagged rows sort first."""
    by_sku = {listing.sku: listing for listing in listings}
    flag_counts: Counter[str] = Counter()
    flagged_rows = 0
    records = []
    for row in rows:
        flags = quality_flags(by_sku[row.sku], row)
        flag_counts.update(flags)
        flagged_rows += bool(flags)
        records.append(
            [
                ";".join(flags),
                methods.get(row.sku, ""),
                row.sku,
                by_sku[row.sku].title or "",
                row.name,
                row.colour_identity,
                "" if row.price is None else str(row.price),
                "" if row.quantity is None else row.quantity,
                row.scryfall_url,
                row.listing_url,
                row.image_url or "",
            ]
        )
    records.sort(key=lambda record: (record[0] == "", record[1], record[2]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(PREVIEW_COLUMNS)
        writer.writerows(records)
    return flag_counts, flagged_rows


# --------------------------------------------------------------------------- SQLite


def write_inventory(output: Path, rows: list[InventoryRow]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output) as conn:
        conn.execute("DROP TABLE IF EXISTS inventory")
        conn.executescript(SCHEMA_PATH.read_text())
        conn.executemany(
            """
            INSERT INTO inventory (
              id, sku, name, scryfall_id, scryfall_url, colour_identity,
              image_url, listing_url, price, quantity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.id,
                    row.sku,
                    row.name,
                    row.scryfall_id,
                    row.scryfall_url,
                    row.colour_identity,
                    row.image_url,
                    row.listing_url,
                    str(row.price) if row.price is not None else None,
                    row.quantity,
                )
                for row in rows
            ],
        )


def write_unmatched(path: Path, unmatched: list[Listing]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sku", "title", "listing_url"])
        for listing in unmatched:
            writer.writerow([listing.sku, listing.title or "", listing.listing_url])


# --------------------------------------------------------------------------- main


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"SQLite file to write (default: {DEFAULT_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--phash-db",
        type=Path,
        default=None,
        help="SQLite file with the card_phash table (default: arcanum's prod DB).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and match everything, but don't write the database.",
    )
    parser.add_argument("--log_level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(message)s"
    )
    if args.log_level.upper() != "DEBUG":
        # arcanum logs every eBay request/response at INFO; ~1000 per-SKU calls is noise.
        logging.getLogger("arcanum.api.ebay.ebay").setLevel(logging.WARNING)

    import requests
    from arcanum.common import constants

    phash_db = args.phash_db or constants.PROD_DB_PATH

    client = build_ebay_client()
    try:
        listings = fetch_listings(client)
    finally:
        client.session.close()

    with requests.Session() as session:
        session.headers.update(SCRYFALL_HEADERS)
        rows, unmatched, methods = match_cards(listings, session, phash_db)

    total = len(listings)
    coverage = (len(rows) / total * 100) if total else 0.0
    print(f"Matched {len(rows)}/{total} live listings ({coverage:.1f}%).")
    for method, count in Counter(methods.values()).most_common():
        print(f"  {method}: {count}")

    preview_path = args.output.with_name("backfill_preview.csv")
    flag_counts, flagged = write_preview(preview_path, rows, listings, methods)
    print(f"Quality flags ({flagged} rows flagged): {dict(flag_counts) or 'none'}")
    print(f"Preview of every matched row (flagged first): {preview_path}")

    if args.dry_run:
        print("Dry run: nothing written.")
    else:
        write_inventory(args.output, rows)
        print(f"Wrote {len(rows)} rows to {args.output}")

    if unmatched:
        unmatched_path = args.output.with_name("backfill_unmatched.csv")
        write_unmatched(unmatched_path, unmatched)
        print(f"{len(unmatched)} unmatched listings written to {unmatched_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
