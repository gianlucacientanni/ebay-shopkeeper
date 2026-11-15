# standard library
import logging
import time
from collections.abc import Iterator
from typing import Any, Optional

# third party
import requests

# ebay_shopkeeper imports
from back_end.common.cards import format_colour_identity, oracle_text_for
from back_end.common.models import Commander, ScryfallCard


log = logging.getLogger(__name__)

SCRYFALL_BASE_URL = "https://api.scryfall.com"
SCRYFALL_HEADERS = {
    "User-Agent": "ebay-shopkeeper/0.1",
    "Accept": "application/json",
}
# Scryfall asks for 50-100 ms between requests.
REQUEST_DELAY_SECONDS = 0.1
TIMEOUT_SECONDS = 15


class ScryfallError(Exception):
    pass


class CommanderNotFound(ScryfallError):
    pass


def new_session() -> requests.Session:
    """
    Create a requests session with the headers Scryfall asks API clients to send.
    """
    session = requests.Session()
    session.headers.update(SCRYFALL_HEADERS)
    return session


def scryfall_get(
    session: requests.Session, url: str, params: Optional[dict[str, str]] = None
) -> requests.Response:
    """
    GET a Scryfall URL, then wait REQUEST_DELAY_SECONDS to respect Scryfall's rate limit.
    The response is returned as-is so callers can handle Scryfall's status codes themselves.

    :raises ScryfallError: if the request fails to complete (timeout, connection error)
    """
    try:
        response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ScryfallError(f"Scryfall request failed: {exc.__class__.__name__}") from exc
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)
    return response


def raise_for_scryfall_error(response: requests.Response) -> None:
    """
    Raise a ScryfallError for any non-2xx response, using Scryfall's error details when the
    body has them (Scryfall errors are JSON objects with a "details" field).

    :raises ScryfallError: if the response isn't a 2xx
    """
    if response.ok:
        return
    try:
        details = response.json().get("details") or response.text
    except ValueError:
        details = response.text
    raise ScryfallError(f"Scryfall returned {response.status_code}: {details}")


def to_scryfall_card(card: dict[str, Any]) -> ScryfallCard:
    """
    Keep the parts of a Scryfall card object that the pipeline and the PAL use.
    Double-faced cards keep their mana cost and rules text on each face, so fall back to those.
    """
    faces = card.get("card_faces") or []
    mana_cost = card.get("mana_cost") or (faces[0].get("mana_cost") if faces else "") or ""
    return ScryfallCard(
        name=str(card["name"]),
        type_line=str(card.get("type_line") or ""),
        oracle_text=oracle_text_for(card),
        mana_cost=str(mana_cost),
    )


def to_commander(card: dict[str, Any]) -> Commander:
    """
    Build a Commander from a Scryfall card object, warning if the card is not legendary
    (it is still used, as the customer may have misnamed their commander).
    """
    type_line = str(card.get("type_line") or "")
    if "Legendary" not in type_line:
        log.warning("%s is not legendary (%s)", card.get("name"), type_line)
    return Commander(
        name=str(card["name"]),
        colour_identity=format_colour_identity(card.get("color_identity") or []),
        type_line=type_line,
        oracle_text=oracle_text_for(card),
    )


def get_commander(session: requests.Session, name: str) -> Commander:
    """
    Look up a commander by (fuzzy) name to get its colour identity and rules text.

    :raises CommanderNotFound: if no card matches the name
    :raises ScryfallError: if Scryfall fails (5xx, rate limited, timeout, connection error)
    """
    response = scryfall_get(session, f"{SCRYFALL_BASE_URL}/cards/named", {"fuzzy": name})
    if response.status_code == 404:
        raise CommanderNotFound(f"No card found on Scryfall matching {name!r}")
    raise_for_scryfall_error(response)
    return to_commander(response.json())


def search_cards(
    session: requests.Session, query: str, order: str = "edhrec"
) -> Iterator[ScryfallCard]:
    """
    Yield the cards matching a Scryfall query, one printing per card, in the given order.
    Results are paged (175 per page) and further pages are only fetched once the caller has
    consumed the previous one, so taking the first few cards costs a single request.

    :param query: Scryfall search syntax, e.g. "s:hob id<=g t:creature"
    :param order: Scryfall sort order, "edhrec" sorts by popularity in Commander decks
    :raises ScryfallError: if Scryfall rejects the query (400) or fails (5xx, rate limited,
    timeout, connection error)
    """
    url: Optional[str] = f"{SCRYFALL_BASE_URL}/cards/search"
    params: Optional[dict[str, str]] = {"q": query, "order": order, "unique": "cards"}
    while url:
        response = scryfall_get(session, url, params)
        # Scryfall returns a 404 when no cards match the query
        if response.status_code == 404:
            return
        raise_for_scryfall_error(response)
        payload = response.json()
        for card in payload.get("data") or []:
            yield to_scryfall_card(card)
        url = payload.get("next_page") if payload.get("has_more") else None
        # next_page already carries the query string
        params = None
