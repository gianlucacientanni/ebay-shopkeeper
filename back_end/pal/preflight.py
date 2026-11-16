"""
Check everything is ready before a real call with Tom. Read-only and free: it uses no
avatar minutes.

    uv run preflight
    uv run preflight --backend-url http://localhost:8000
"""

# standard library
import argparse
import sys
from dataclasses import dataclass
from typing import Any, Optional

# third party
import requests

# ebay_shopkeeper imports
from back_end.api.tavus import tavus
from back_end.common import config
from back_end.common.models import SearchRequest
from back_end.pal import shopkeeper
from back_end.pal.tool_output import TOOL_RESULT_LIMIT_BYTES, pal_tool_output, tool_result_size
from back_end.search.pipeline import card_search


DEFAULT_BACKEND_URL = "http://localhost:8000"
MAX_TEST_CALL_SECONDS = 180
# The search from the call script in the README ("A real call").
SCRIPTED_SEARCH = SearchRequest(commander="Radagast the Brown", role="ramp")
EXPECTED_TOOLS = {shopkeeper.TOOL_NAME, shopkeeper.END_CALL_TOOL_ID}


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


def value_at(document: dict[str, Any], path: str) -> Any:
    """
    Read a JSON Pointer path such as "/layers/llm/model" from a dict; None if missing.
    """
    node: Any = document
    for key in path.strip("/").split("/"):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def check_backend(backend_url: str) -> Check:
    """
    The FastAPI backend is running, so the frontend can create calls and relay tool calls.
    """
    try:
        response = requests.get(f"{backend_url}/api/health", timeout=5)
        return Check("Backend running", response.ok, f"{backend_url} ({response.status_code})")
    except requests.RequestException as exc:
        return Check("Backend running", False, f"{backend_url}: {exc.__class__.__name__}")


def check_config() -> list[Check]:
    """
    Calls are real (not test mode) and capped at a short duration.
    """
    return [
        Check("Real calls (TAVUS_TEST_MODE=false)", not config.TAVUS_TEST_MODE),
        Check(
            f"Call capped at {MAX_TEST_CALL_SECONDS}s or less",
            config.MAX_CALL_DURATION <= MAX_TEST_CALL_SECONDS,
            f"MAX_CALL_DURATION={config.MAX_CALL_DURATION}",
        ),
        Check("PAL id configured", bool(config.TAVUS_PAL_ID), config.TAVUS_PAL_ID or "missing"),
    ]


def check_pal(pal: dict[str, Any]) -> Check:
    """
    The PAL on Tavus matches shopkeeper.py; if not, `uv run setup-pal` needs rerunning.
    """
    expected = shopkeeper.pal_fields(str(pal.get("objectives_id", "")))
    stale = [path for path, value in expected.items() if value_at(pal, path) != value]
    if not pal.get("objectives_id"):
        stale.append("/objectives_id")
    return Check(
        "PAL matches shopkeeper.py",
        not stale,
        "out of date: " + ", ".join(stale) + " (run `uv run setup-pal`)" if stale else "",
    )


def check_tools(tools: list[dict[str, Any]]) -> Check:
    """
    Exactly search_cards (speaking its result) and end_call are attached.
    """
    names = {tool.get("name") for tool in tools}
    search = next((tool for tool in tools if tool.get("name") == shopkeeper.TOOL_NAME), {})
    passed = names == EXPECTED_TOOLS and search.get("on_resolve") == "generate_response"
    return Check("Tools attached", passed, ", ".join(sorted(str(name) for name in names)))


def check_search(request: SearchRequest = SCRIPTED_SEARCH) -> Check:
    """
    The scripted search finds stock and its tool result fits in a Tavus app message.
    """
    try:
        result = card_search(request)
    except Exception as exc:  # report any failure as a failed check
        return Check("Scripted search works", False, f"{exc.__class__.__name__}: {exc}")
    size = tool_result_size(pal_tool_output(result))
    return Check(
        "Scripted search works",
        bool(result.candidates) and size <= TOOL_RESULT_LIMIT_BYTES,
        f"{len(result.candidates)} cards for {result.commander.name}, tool result {size} bytes",
    )


def run_checks(session: requests.Session, backend_url: str) -> list[Check]:
    """
    Run every pre-flight check, continuing past failures so the report is complete.
    """
    checks = [check_backend(backend_url), *check_config()]
    if config.TAVUS_PAL_ID:
        try:
            checks.append(check_pal(tavus.get_pal(session, config.TAVUS_PAL_ID)))
            checks.append(check_tools(tavus.list_pal_tools(session, config.TAVUS_PAL_ID)))
        except tavus.TavusError as exc:
            checks.append(Check("PAL reachable on Tavus", False, str(exc)))
    checks.append(check_search())
    return checks


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """
    CLI entry point (installed as `preflight`).

    :return int: 0 if every check passed, 1 otherwise
    """
    args = parse_args(argv)
    try:
        session = tavus.new_session(config.TAVUS_API_KEY)
    except tavus.TavusError as exc:
        print(f"✖ {exc}")
        return 1
    checks = run_checks(session, args.backend_url)
    for check in checks:
        print(f"{'✔' if check.passed else '✖'} {check.name}" + (f": {check.detail}" if check.detail else ""))
    ready = all(check.passed for check in checks)
    print("\nReady for a real call." if ready else "\nNot ready: fix the ✖ items first.")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
