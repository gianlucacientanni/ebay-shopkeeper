# standard library
import json
from typing import Any, Union

# ebay_shopkeeper imports
from back_end.common.models import Candidate, SearchResult


# Tavus app messages (which carry conversation.tool_result) are capped at 4 KB; anything
# larger is dropped in transit without an error.
TOOL_RESULT_LIMIT_BYTES = 4096
# Rules text is cut to this many characters for the PAL, enough for it to know what a card
# does without blowing the size budget.
PAL_TEXT_CHARS = 120


def truncate_text(text: str, max_chars: int = PAL_TEXT_CHARS) -> str:
    """
    Flatten rules text onto one line and cut it to max_chars, ending with "…" when cut.
    """
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    return flat[: max_chars - 1].rstrip() + "…"


def pal_card(candidate: Candidate) -> dict[str, str]:
    """
    The compact view of a candidate that the PAL receives. It has what the PAL needs to talk
    about the card (name, price, type, what it does) and deliberately no listing URL or
    image: the frontend shows those in the listings panel.
    """
    return {
        "name": candidate.name,
        "price": f"£{candidate.price}" if candidate.price is not None else "unknown",
        "type": candidate.type_line,
        "text": truncate_text(candidate.oracle_text),
    }


def pal_tool_output(result: SearchResult) -> dict[str, Any]:
    """
    Build the output the frontend sends back to the PAL as the conversation.tool_result.

    :return dict: the commander, whether the role filter was dropped to find stock (so the
    PAL can say nothing matched that role exactly) and the compact cards in EDHREC order
    """
    return {
        "commander": result.commander.name,
        "relaxed": result.relaxed,
        "cards": [pal_card(candidate) for candidate in result.candidates],
    }


def tool_result_size(output: Union[str, dict[str, Any]]) -> int:
    """
    Size in bytes of the full conversation.tool_result app message carrying output, using
    realistic lengths for the conversation and tool call ids. Compare against
    TOOL_RESULT_LIMIT_BYTES.
    """
    message = {
        "message_type": "conversation",
        "event_type": "conversation.tool_result",
        "conversation_id": "c" + "0" * 15,
        "properties": {
            "tool_call_id": "call_" + "0" * 36,
            "output": output,
            "status": "success",
        },
    }
    return len(json.dumps(message, ensure_ascii=False).encode("utf-8"))
