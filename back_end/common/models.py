# standard library
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Optional

# third party
from pydantic import BaseModel, Field

# ebay_shopkeeper imports
from back_end.common.config import MAX_CANDIDATES


CardType = Literal[
    "creature", "instant", "sorcery", "artifact", "enchantment", "planeswalker", "land", "battle"
]


# Internal data passed between pipeline steps.


@dataclass(frozen=True)
class Commander:
    name: str
    # WUBRG-ordered letters, "C" for colourless
    colour_identity: str
    type_line: str = ""
    oracle_text: str = ""


@dataclass(frozen=True)
class ScryfallCard:
    name: str
    type_line: str = ""
    oracle_text: str = ""
    mana_cost: str = ""


@dataclass(frozen=True)
class InventoryRow:
    sku: str
    name: str
    price: Optional[Decimal]
    quantity: Optional[int]
    listing_url: str
    image_url: Optional[str]


@dataclass(frozen=True)
class Listing:
    """
    The eBay listing chosen for an in-stock card, alongside the Scryfall card it matched.
    """

    row: InventoryRow
    finish: str
    card: ScryfallCard
    other_finishes: list[str] = field(default_factory=list)


# API boundary: the PAL's tool arguments and the tool result. These are pydantic models so
# they validate input and serialise to JSON.


class SearchRequest(BaseModel):
    """
    What the customer is looking for. Mirrors the arguments of the PAL's search tool.
    """

    commander: str = Field(description="Name of the customer's commander.")
    card_type: Optional[CardType] = Field(default=None, description="Card type wanted, if any.")
    role: Optional[str] = Field(
        default=None, description="Role the card should fill in the deck, e.g. 'ramp'."
    )
    max_price: Optional[Decimal] = Field(default=None, description="Maximum price in GBP.")
    limit: int = Field(
        default=MAX_CANDIDATES,
        ge=1,
        le=MAX_CANDIDATES,
        description="Maximum candidates to return.",
    )


class Candidate(BaseModel):
    """
    An in-stock card returned to the PAL, which picks and explains the best few.
    """

    name: str
    title: str
    price: Optional[Decimal]
    finish: str
    listing_url: str
    image_url: Optional[str]
    type_line: str
    mana_cost: str
    oracle_text: str
    other_finishes: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    query: str
    commander: Commander
    # number of Scryfall cards checked against stock
    inspected: int
    in_stock_count: int
    # True if the role filter was dropped to find any results
    relaxed: bool = False
    candidates: list[Candidate]


class SearchResponse(BaseModel):
    """
    What /api/search returns to the frontend: the full result for the listings panel, and
    the compact output the frontend sends back to the PAL as the tool result.
    """

    result: SearchResult
    pal_output: dict[str, Any]
