"""
Create or update the shopkeeper on Tavus: the search tool, the objectives and the PAL.

    uv run setup-pal --dry-run   # print every payload, no API calls
    uv run setup-pal             # create on the first run, update on later runs

Uses only the Tavus REST API, so it costs no avatar minutes. The ids it creates are saved to
back_end/.tavus_resources.json, which config reads as the default TAVUS_PAL_ID.
"""

# standard library
import argparse
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

# third party
import requests

# ebay_shopkeeper imports
from back_end.api.tavus import tavus
from back_end.common import config
from back_end.pal import shopkeeper


log = logging.getLogger(__name__)

PAL_MAKER_URL = "https://maker.tavus.io/dev"
# Status codes Tavus uses when an id no longer exists (e.g. deleted in the PAL Maker).
MISSING_STATUS_CODES = (400, 404)

# Ids of the resources this script manages: tool_id, objectives_id and pal_id.
State = dict[str, str]


def load_state(path: Path = config.TAVUS_RESOURCES_PATH) -> State:
    """
    Load the saved resource ids, or an empty state if setup hasn't run yet.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(state: State, path: Path = config.TAVUS_RESOURCES_PATH) -> None:
    """
    Save the resource ids so later runs update the same resources instead of creating new ones.
    """
    path.write_text(json.dumps(state, indent=2) + "\n")


def exists(get: Callable[[requests.Session, str], Any], session: requests.Session,
           resource_id: Optional[str]) -> bool:
    """
    Check whether a saved resource id still exists on Tavus.

    :param get: the matching tavus.get_* function
    :return bool: False if there is no saved id or Tavus says it doesn't exist
    :raises TavusError: for any other failure, so setup stops instead of creating duplicates
    """
    if not resource_id:
        return False
    try:
        get(session, resource_id)
        return True
    except tavus.TavusError as exc:
        if exc.status_code in MISSING_STATUS_CODES:
            log.warning("Saved id %s no longer exists on Tavus; creating a new one", resource_id)
            return False
        raise


def ensure_tool(session: requests.Session, tool_id: Optional[str]) -> str:
    """
    Update the search tool if it exists, otherwise create it.

    :return str: the tool_id
    """
    tool = shopkeeper.tool_definition()
    if exists(tavus.get_tool, session, tool_id):
        tavus.update_tool(session, tool_id, tool)
        log.info("Updated tool %s (%s)", shopkeeper.TOOL_NAME, tool_id)
        return tool_id
    new_id = tavus.create_tool(session, tool)
    log.info("Created tool %s (%s)", shopkeeper.TOOL_NAME, new_id)
    return new_id


def ensure_objectives(session: requests.Session, objectives_id: Optional[str]) -> str:
    """
    Update the objectives if they exist, otherwise create them. If Tavus rejects the update,
    new objectives are created instead; the PAL is pointed at whichever id is returned.

    :return str: the objectives_id
    """
    if exists(tavus.get_objectives, session, objectives_id):
        try:
            tavus.patch_objectives(session, objectives_id, shopkeeper.objectives_patch())
            log.info("Updated objectives %s", objectives_id)
            return objectives_id
        except tavus.TavusError as exc:
            log.warning("Couldn't update objectives (%s); creating new ones", exc)
    new_id = tavus.create_objectives(session, shopkeeper.OBJECTIVES)
    log.info("Created objectives %s", new_id)
    return new_id


def ensure_pal(session: requests.Session, pal_id: Optional[str], objectives_id: str) -> str:
    """
    Update the PAL if it exists, otherwise create it.

    :return str: the pal_id
    """
    if exists(tavus.get_pal, session, pal_id):
        tavus.patch_pal(session, pal_id, shopkeeper.pal_patch(objectives_id))
        log.info("Updated PAL %s", pal_id)
        return pal_id
    new_id = tavus.create_pal(session, shopkeeper.pal_definition(objectives_id))
    log.info("Created PAL %s", new_id)
    return new_id


def setup(session: requests.Session, state: State) -> State:
    """
    Create or update the tool, objectives and PAL, then attach the search tool and Tavus'
    end_call tool to the PAL.

    :param state: ids from a previous run, or {} on the first run
    :return State: the ids now in use
    """
    tool_id = ensure_tool(session, state.get("tool_id"))
    objectives_id = ensure_objectives(session, state.get("objectives_id"))
    pal_id = ensure_pal(session, state.get("pal_id"), objectives_id)
    tavus.attach_tools(session, pal_id, [tool_id, shopkeeper.END_CALL_TOOL_ID])
    log.info("Attached %s and %s to PAL %s", tool_id, shopkeeper.END_CALL_TOOL_ID, pal_id)
    return {"tool_id": tool_id, "objectives_id": objectives_id, "pal_id": pal_id}


def dry_run_payloads(state: State) -> dict[str, Any]:
    """
    Every payload setup would send, for review without calling the API.
    """
    objectives_id = state.get("objectives_id", "<objectives_id>")
    return {
        "tool": shopkeeper.tool_definition(),
        "objectives": {"data": shopkeeper.OBJECTIVES},
        "pal": shopkeeper.pal_definition(objectives_id),
        "attach_tools": [state.get("tool_id", "<tool_id>"), shopkeeper.END_CALL_TOOL_ID],
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the payloads without calling Tavus."
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """
    CLI entry point (installed as `setup-pal`).

    :return int: exit code, 0 on success, 1 if Tavus rejects a request
    """
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    state = load_state()

    if args.dry_run:
        print(json.dumps(dry_run_payloads(state), indent=2, ensure_ascii=False))
        return 0

    try:
        session = tavus.new_session(config.TAVUS_API_KEY)
        state = setup(session, state)
    except tavus.TavusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    save_state(state)
    print(f"\nPAL ready: {state['pal_id']}")
    print(f"Saved ids to {config.TAVUS_RESOURCES_PATH}")
    print(f"View it in the PAL Maker: {PAL_MAKER_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
