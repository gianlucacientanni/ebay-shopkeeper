"""
The card-search pipeline:
1) look up the commander's colour identity on Scryfall,
2) search Scryfall (stocked sets, colour identity, type, role), ordered by EDHREC rank,
3) check the results against local stock in windows of 10, sliding on until at least 5
   are in stock (or 50 cards have been checked),
4) return the in-stock cards with their eBay listings and card text. The PAL's LLM picks
   the best few and explains them in conversation.
"""

# standard library
import logging
from collections.abc import Callable, Iterator
from decimal import Decimal
from itertools import islice
from typing import Optional

# ebay_shopkeeper imports
from back_end.api.scryfall import scryfall
from back_end.common import config
from back_end.common.models import (
    Candidate,
    Commander,
    Listing,
    ScryfallCard,
    SearchRequest,
    SearchResult,
)
from back_end.database.inventory import (
    InventoryIndex,
    find_in_stock,
    listing_title,
    load_inventory,
)
from back_end.search.query import build_query, normalize_role


log = logging.getLogger(__name__)

# A function that runs a Scryfall query and yields the matching cards in EDHREC order.
SearchFn = Callable[[str], Iterator[ScryfallCard]]


def find_in_stock_windowed(
    cards: Iterator[ScryfallCard],
    inventory: InventoryIndex,
    max_price: Optional[Decimal] = None,
    window_size: int = config.WINDOW_SIZE,
    max_windows: int = config.MAX_WINDOWS,
    min_in_stock: int = config.MIN_IN_STOCK,
) -> tuple[list[Listing], int]:
    """
    Check cards against stock window_size at a time, moving on to the next window until at
    least min_in_stock cards are in stock or max_windows windows have been checked.
    Cards beyond the last window checked are never pulled from the iterator, so Scryfall
    pages that aren't needed are never requested.

    :param cards: Scryfall cards in EDHREC order
    :return tuple: in-stock listings in EDHREC order, number of cards checked
    """
    in_stock: list[Listing] = []
    inspected = 0
    for _ in range(max_windows):
        window = list(islice(cards, window_size))
        if not window:
            break
        inspected += len(window)
        in_stock.extend(find_in_stock(window, inventory, max_price))
        if len(in_stock) >= min_in_stock:
            break
    return in_stock, inspected


def to_candidate(listing: Listing) -> Candidate:
    """
    Convert an in-stock listing into the candidate returned to the PAL.
    """
    return Candidate(
        name=listing.row.name,
        title=listing_title(listing),
        price=listing.row.price,
        finish=listing.finish,
        listing_url=listing.row.listing_url,
        image_url=listing.row.image_url,
        type_line=listing.card.type_line,
        mana_cost=listing.card.mana_cost,
        oracle_text=listing.card.oracle_text,
        other_finishes=listing.other_finishes,
    )


def search_inventory(
    request: SearchRequest,
    commander: Commander,
    search: SearchFn,
    inventory: InventoryIndex,
) -> SearchResult:
    """
    Run the search for a request once the commander is known. If nothing is in stock with
    the role filter, the search is retried once without it and the result is marked relaxed.

    :param commander: the customer's commander, from scryfall.get_commander
    :param search: function running a Scryfall query and yielding cards in EDHREC order
    :param inventory: index from load_inventory
    :return SearchResult: up to request.limit in-stock candidates, in EDHREC order
    """
    query = build_query(request, commander.colour_identity, commander.name)
    in_stock, inspected = find_in_stock_windowed(search(query), inventory, request.max_price)

    relaxed = False
    if not in_stock and normalize_role(request.role):
        log.info("Nothing in stock for %r; retrying without the role filter", query)
        query = build_query(request, commander.colour_identity, commander.name, include_role=False)
        in_stock, more_inspected = find_in_stock_windowed(
            search(query), inventory, request.max_price
        )
        inspected += more_inspected
        relaxed = True

    return SearchResult(
        query=query,
        commander=commander,
        inspected=inspected,
        in_stock_count=len(in_stock),
        relaxed=relaxed,
        candidates=[to_candidate(listing) for listing in in_stock[: request.limit]],
    )


def card_search(request: SearchRequest) -> SearchResult:
    """
    Run the full card search against live Scryfall and the local inventory database.

    :raises scryfall.CommanderNotFound: if the commander can't be found on Scryfall
    :raises scryfall.ScryfallError: if Scryfall rejects the generated query
    """
    session = scryfall.new_session()
    commander = scryfall.get_commander(session, request.commander)
    return search_inventory(
        request,
        commander,
        search=lambda query: scryfall.search_cards(session, query),
        inventory=load_inventory(),
    )
