# standard library
import logging
from typing import Optional

# ebay_shopkeeper imports
from back_end.common.config import STOCKED_SETS
from back_end.common.models import SearchRequest


log = logging.getLogger(__name__)

# Deck roles the shopkeeper understands, mapped to Scryfall search fragments (mostly
# Scryfall Tagger oracle tags). Each was checked against live Scryfall to match cards
# in the stocked sets.
ROLE_FILTERS: dict[str, str] = {
    "ramp": "otag:ramp",
    "mana_rock": "otag:mana-rock",
    "removal": "otag:removal",
    "board_wipe": "otag:sweeper",
    "counterspell": "otag:counterspell",
    "card_draw": "otag:draw",
    "card_advantage": "otag:card-advantage",
    "tutor": "otag:tutor",
    "protection": "otag:protection",
    "recursion": "otag:recursion",
    "reanimation": "otag:reanimate",
    "tokens": "o:create o:token",
    "lifegain": "otag:lifegain",
    "evasion": "otag:evasion",
    "sacrifice_outlet": "otag:sacrifice-outlet",
    "anthem": "otag:anthem",
}

ROLE_ALIASES: dict[str, str] = {
    "draw": "card_draw",
    "wipe": "board_wipe",
    "boardwipe": "board_wipe",
    "sweeper": "board_wipe",
    "counter": "counterspell",
    "token": "tokens",
    "token_generation": "tokens",
    "reanimate": "reanimation",
    "life_gain": "lifegain",
    "rock": "mana_rock",
}


def normalize_role(role: Optional[str]) -> Optional[str]:
    """
    Map loosely written role text onto a ROLE_FILTERS key, e.g.
    "Card draw" -> "card_draw"
    "board-wipe" -> "board_wipe"
    "draw" -> "card_draw" (via ROLE_ALIASES)
    Unknown roles return None, so the search runs without a role filter.
    """
    if not role:
        return None
    key = role.strip().lower().replace("-", "_").replace(" ", "_")
    key = ROLE_ALIASES.get(key, key)
    if key not in ROLE_FILTERS:
        log.warning("Unknown role %r; searching without a role filter", role)
        return None
    return key


def quote(value: str) -> str:
    """
    Wrap a value in double quotes for Scryfall syntax, dropping any quotes inside it.
    """
    return '"' + value.replace('"', "") + '"'


def build_query(
    request: SearchRequest, colour_identity: str, commander_name: str, include_role: bool = True
) -> str:
    """
    Build the Scryfall query for a search request, e.g.
    (s:ecl or s:sos or s:hob or s:fra or s:tla) id<=g t:creature otag:ramp -t:basic -!"Radagast"

    Basic lands and the commander itself are always excluded.

    :param colour_identity: the commander's colour identity, e.g. "WG" or "C" for colourless
    :param commander_name: the commander's exact name, excluded from the results
    :param include_role: set False to drop the role filter when a search finds nothing in stock
    """
    sets = " or ".join(f"s:{code}" for code in STOCKED_SETS)
    parts = [f"({sets})", f"id<={colour_identity.lower()}"]
    if request.card_type:
        parts.append(f"t:{request.card_type}")
    role = normalize_role(request.role) if include_role else None
    if role:
        parts.append(ROLE_FILTERS[role])
    parts.append("-t:basic")
    parts.append(f"-!{quote(commander_name)}")
    return " ".join(parts)
