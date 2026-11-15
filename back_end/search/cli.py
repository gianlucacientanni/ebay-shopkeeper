"""
Search the shop's stock for cards that fix a Commander deck problem.

Prints the in-stock candidates the PAL would receive from its search tool (EDHREC order).
The PAL's LLM picks the best few from these and explains them to the customer.

Examples:

    uv run card-search --commander "Radagast the Brown" --card-type creature --role ramp
    uv run card-search --commander "Radagast the Brown" --role ramp --json
"""

# standard library
import argparse
import logging
import sys
from decimal import Decimal
from typing import Optional, get_args

# ebay_shopkeeper imports
from back_end.api.scryfall.scryfall import CommanderNotFound, ScryfallError
from back_end.common.models import CardType, Candidate, SearchRequest, SearchResult
from back_end.search.pipeline import card_search
from back_end.search.query import ROLE_FILTERS


ORACLE_TEXT_PREVIEW_CHARS = 140


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments. --commander is required unless --list-roles is given.
    """
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        epilog="Roles: " + ", ".join(ROLE_FILTERS),
    )
    parser.add_argument("--commander", help="Name of the commander (fuzzy matched).")
    parser.add_argument("--card-type", choices=get_args(CardType))
    parser.add_argument("--role", help="Deck role, e.g. ramp, removal, card_draw.")
    parser.add_argument("--max-price", type=Decimal, help="Maximum price in GBP.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum candidates to return.")
    parser.add_argument("--json", action="store_true", help="Print the raw JSON result.")
    parser.add_argument("--list-roles", action="store_true", help="List roles and exit.")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)
    if not args.list_roles and not args.commander:
        parser.error("--commander is required")
    return args


def format_candidate(position: int, candidate: Candidate) -> list[str]:
    """
    Format one candidate as three lines: title and price, type and rules text, listing URL.
    """
    price = f"£{candidate.price}" if candidate.price is not None else "?"
    also = (
        f" (also: {', '.join(f.lower() for f in candidate.other_finishes)})"
        if candidate.other_finishes
        else ""
    )
    text = candidate.oracle_text.replace("\n", " ")
    if len(text) > ORACLE_TEXT_PREVIEW_CHARS:
        text = text[:ORACLE_TEXT_PREVIEW_CHARS] + "..."
    return [
        f"{position}. {candidate.title} {candidate.mana_cost} - {price}{also}",
        f"   {candidate.type_line}: {text}",
        f"   {candidate.listing_url}",
    ]


def format_result(result: SearchResult) -> str:
    """
    Format a search result as human readable text for the terminal.
    """
    lines = [
        f"Commander: {result.commander.name} ({result.commander.colour_identity})",
        f"Query:     {result.query}",
        f"Inspected {result.inspected} cards, {result.in_stock_count} in stock"
        + (" (role filter dropped to find stock)" if result.relaxed else ""),
        "",
    ]
    if not result.candidates:
        lines.append("Nothing suitable in stock.")
    for position, candidate in enumerate(result.candidates, 1):
        lines.extend(format_candidate(position, candidate))
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    """
    CLI entry point (installed as `card-search`).

    :return int: exit code, 0 on success, 2 if the commander isn't found, 1 for other errors
    """
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s"
    )

    if args.list_roles:
        for role, fragment in ROLE_FILTERS.items():
            print(f"{role:18} {fragment}")
        return 0

    request = SearchRequest(
        commander=args.commander,
        card_type=args.card_type,
        role=args.role,
        max_price=args.max_price,
        limit=args.limit,
    )
    try:
        result = card_search(request)
    except CommanderNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ScryfallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(result.model_dump_json(indent=2) if args.json else format_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
