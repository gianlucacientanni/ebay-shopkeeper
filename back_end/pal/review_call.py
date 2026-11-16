"""
Review a finished call with Tom: fetch its transcript from Tavus and check it against what
the shopkeeper should do. Free to run; it only reads the conversation.

    uv run review-call <conversation_id>

Writes notes/calls/<date>-<conversation_id>.md and prints a short summary.
"""

# standard library
import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ebay_shopkeeper imports
from back_end.api.tavus import tavus
from back_end.common import config
from back_end.common.cards import normalize_name
from back_end.pal.shopkeeper import TOOL_NAME


log = logging.getLogger(__name__)

CALLS_DIR = config.REPO_ROOT / "notes" / "calls"
TRANSCRIPT_EVENT = "application.transcription_ready"
SHUTDOWN_EVENT = "system.shutdown"
PAL_JOINED_EVENTS = ("system.pal_joined", "system.replica_joined")
# Tavus saves the transcript shortly after the call ends; wait up to this long for it.
TRANSCRIPT_WAIT_ATTEMPTS = 6
TRANSCRIPT_WAIT_SECONDS = 10
# Tavus' placeholder tool turn while a tool call is in flight; the real result follows.
DISPATCHED_PLACEHOLDER = "dispatched, awaiting result"

# A transcript entry: role, content, seconds_from_start, duration, ...
Turn = dict[str, Any]


def find_event(conversation: dict[str, Any], *event_types: str) -> Optional[dict[str, Any]]:
    """
    Return the first event of any of the given types from a verbose conversation, or None.
    """
    for event in conversation.get("events") or []:
        if event.get("event_type") in event_types:
            return event
    return None


def transcript(conversation: dict[str, Any]) -> list[Turn]:
    """
    The end-of-call transcript, or [] if Tavus hasn't saved it yet.
    """
    event = find_event(conversation, TRANSCRIPT_EVENT)
    if event is None:
        return []
    return list((event.get("properties") or {}).get("transcript") or [])


def fetch_with_transcript(
    session: Any,
    conversation_id: str,
    attempts: int = TRANSCRIPT_WAIT_ATTEMPTS,
    delay: float = TRANSCRIPT_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """
    Fetch the verbose conversation, retrying while the transcript isn't available yet.

    :return dict: the last conversation fetched, with or without a transcript
    """
    conversation: dict[str, Any] = {}
    for attempt in range(attempts):
        conversation = tavus.get_conversation(session, conversation_id)
        if transcript(conversation):
            return conversation
        if attempt < attempts - 1:
            log.info("Transcript not ready yet; retrying in %ss", delay)
            sleep(delay)
    return conversation


def parse_json(value: Any) -> Any:
    """
    Parse a JSON string, returning the value unchanged if it isn't JSON. Tavus appends a
    note after the tool's JSON in the transcript ("{...} | NOTE: ..."), so a leading JSON
    value followed by other text is also accepted.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    if text[:1] in "{[":
        try:
            parsed, _ = json.JSONDecoder().raw_decode(text)
            return parsed
        except ValueError:
            pass
    return value


def search_calls(turns: list[Turn]) -> list[dict[str, Any]]:
    """
    Arguments of each search_cards call. Tool calls may appear as OpenAI-style "tool_calls"
    on assistant turns; the exact transcript shape isn't documented, so this is lenient.
    """
    calls = []
    seen_ids = set()
    for turn in turns:
        for tool_call in turn.get("tool_calls") or []:
            function = tool_call.get("function") or tool_call
            # Tavus records the result as a second tool_calls entry with id "<id>_result".
            call_id = str(tool_call.get("id", "")).removesuffix("_result")
            if function.get("name") != TOOL_NAME or (call_id and call_id in seen_ids):
                continue
            seen_ids.add(call_id)
            arguments = parse_json(function.get("arguments"))
            calls.append(arguments if isinstance(arguments, dict) else {"raw": arguments})
    return calls


def tool_results(turns: list[Turn]) -> list[Any]:
    """
    Content of each tool turn (role "tool"): the pal_output dict, or an error string.
    """
    return [
        parse_json(turn.get("content"))
        for turn in turns
        if turn.get("role") == "tool"
        and not str(turn.get("content", "")).startswith(DISPATCHED_PLACEHOLDER)
    ]


def result_card_names(results: list[Any]) -> list[str]:
    """
    Names of the cards in successful search results.
    """
    names = []
    for result in results:
        if isinstance(result, dict):
            names.extend(str(card.get("name")) for card in result.get("cards") or [])
    return names


def mentioned_cards(text: str, card_names: list[str]) -> list[str]:
    """
    Card names (front face, ignoring punctuation and case) that appear in text.
    """
    spoken = normalize_name(text)
    return [name for name in card_names if normalize_name(name) and normalize_name(name) in spoken]


def review(conversation: dict[str, Any]) -> dict[str, Any]:
    """
    Check a call against the shopkeeper's expected behaviour.

    :return dict: facts about the call and a list of (check, passed, detail) tuples
    """
    turns = transcript(conversation)
    assistant = [turn for turn in turns if turn.get("role") == "assistant"]
    calls = search_calls(turns)
    results = tool_results(turns)
    card_names = result_card_names(results)

    recommendation_turn = next(
        (turn for turn in assistant if mentioned_cards(str(turn.get("content", "")), card_names)),
        None,
    )
    recommended = (
        mentioned_cards(str(recommendation_turn.get("content", "")), card_names)
        if recommendation_turn
        else []
    )
    multi_question_turns = [
        turn for turn in assistant if str(turn.get("content", "")).count("?") > 1
    ]
    last = turns[-1] if turns else {}
    speaking_seconds = float(last.get("seconds_from_start", 0)) + float(last.get("duration", 0))
    shutdown = find_event(conversation, SHUTDOWN_EVENT)
    shutdown_reason = ((shutdown or {}).get("properties") or {}).get("shutdown_reason")
    first_assistant = assistant[0] if assistant else None
    time_to_recommendation = (
        float(recommendation_turn["seconds_from_start"])
        - float(first_assistant["seconds_from_start"])
        if recommendation_turn and first_assistant and "seconds_from_start" in recommendation_turn
        else None
    )

    checks = [
        ("Transcript available", bool(turns), f"{len(turns)} turns"),
        ("Tom joined", find_event(conversation, *PAL_JOINED_EVENTS) is not None, ""),
        (
            f"{TOOL_NAME} called",
            bool(calls) or bool(results),
            json.dumps(calls) if calls else f"{len(results)} tool result(s)",
        ),
        (
            "Search returned cards",
            bool(card_names),
            f"{len(card_names)} cards" if card_names else json.dumps(results)[:200],
        ),
        (
            "Tom named a card from the results",
            bool(recommended),
            ", ".join(recommended),
        ),
        (
            "One question at a time",
            not multi_question_turns,
            f"{len(multi_question_turns)} turn(s) with several questions",
        ),
        (
            "Ended before the time limit",
            "max_call_duration" not in str(shutdown_reason),
            shutdown_reason or "unknown",
        ),
    ]
    return {
        "turns": turns,
        "search_calls": calls,
        "tool_results": results,
        "recommended": recommended,
        "speaking_seconds": round(speaking_seconds, 1),
        "time_to_recommendation": (
            round(time_to_recommendation, 1) if time_to_recommendation is not None else None
        ),
        "shutdown_reason": shutdown_reason,
        "checks": checks,
    }


def format_turn(turn: Turn) -> str:
    """
    One transcript line: "[12.6s] assistant: text".
    """
    seconds = turn.get("seconds_from_start")
    stamp = f"[{float(seconds):5.1f}s] " if seconds is not None else ""
    content = turn.get("content")
    if not isinstance(content, str):
        content = json.dumps(content)
    extra = f" tool_calls={json.dumps(turn['tool_calls'])}" if turn.get("tool_calls") else ""
    return f"{stamp}**{turn.get('role', '?')}**: {content}{extra}"


def render_markdown(conversation_id: str, conversation: dict[str, Any], result: dict[str, Any]) -> str:
    """
    The review as Markdown, for notes/calls/.
    """
    lines = [
        f"# Call review: {conversation_id}",
        "",
        f"- Created: {conversation.get('created_at', '?')}",
        f"- Status: {conversation.get('status', '?')}",
        f"- Shutdown reason: {result['shutdown_reason'] or 'unknown'}",
        f"- Speaking time: {result['speaking_seconds']}s",
        "- Greeting to recommendation: "
        + (f"{result['time_to_recommendation']}s" if result["time_to_recommendation"] is not None else "n/a"),
        "",
        "## Checks",
        "",
    ]
    for name, passed, detail in result["checks"]:
        lines.append(f"- {'✔' if passed else '✖'} {name}" + (f": {detail}" if detail else ""))
    lines += ["", "## Transcript", ""]
    lines += [f"- {format_turn(turn)}" for turn in result["turns"]] or ["(not available yet)"]
    lines += ["", "## What to tweak", "", "- ", ""]
    return "\n".join(lines)


def write_review(conversation_id: str, markdown: str, calls_dir: Path = CALLS_DIR) -> Path:
    """
    Save the review as notes/calls/<date>-<conversation_id>.md.
    """
    calls_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = calls_dir / f"{date}-{conversation_id}.md"
    path.write_text(markdown)
    return path


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("conversation_id")
    parser.add_argument(
        "--no-wait", action="store_true", help="Don't wait for the transcript to be saved."
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """
    CLI entry point (installed as `review-call`).

    :return int: 0 if every check passed, 1 if any failed or Tavus rejected the request
    """
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        session = tavus.new_session(config.TAVUS_API_KEY)
        conversation = fetch_with_transcript(
            session, args.conversation_id, attempts=1 if args.no_wait else TRANSCRIPT_WAIT_ATTEMPTS
        )
    except tavus.TavusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    result = review(conversation)
    path = write_review(args.conversation_id, render_markdown(args.conversation_id, conversation, result))
    for name, passed, detail in result["checks"]:
        print(f"{'✔' if passed else '✖'} {name}" + (f": {detail}" if detail else ""))
    print(f"\nReview written to {path}")
    return 0 if all(passed for _, passed, _ in result["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
