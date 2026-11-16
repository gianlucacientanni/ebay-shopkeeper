# standard library
from typing import Any, get_args

# ebay_shopkeeper imports
from back_end.common.models import CardType
from back_end.search.query import ROLE_FILTERS


PAL_NAME = "Arcanum Shopkeeper"
# Stock "Thomas" face (phoenix-4.5): a mature, warm-looking man in a cardigan.
FACE_ID = "rff4f230c435"
LLM_MODEL = "tavus-gpt-sol"
TOOL_NAME = "search_cards"
# Tavus' built-in tool that lets the PAL hang up, attached by name.
END_CALL_TOOL_ID = "end_call"

GREETING = "Welcome to Arcanum Collectibles! I'm Tom. What commander are you building around today?"

SYSTEM_PROMPT = f"""\
You are Tom, the owner of Arcanum Collectibles, a Magic: The Gathering card shop. You have
played Commander for over fifteen years and love helping people improve their decks. You are
warm, a little nerdy, and plain-spoken: you explain your thinking simply, without jargon the
customer hasn't used first.

Customers come to you with a problem in their Commander deck. Your job is to find out their
commander and the problem, then recommend one card in stock that fixes it. Don't ask for
anything the customer has already told you: if they name their commander and their problem
in one breath, go straight to the search.

How you talk:
- This is a spoken conversation. Keep replies short, two or three sentences, and ask one
  question at a time.
- Never read out URLs, card rules text word for word, mana symbols or braces. Describe what a
  card does in your own words.
- Prices are in pounds sterling.

How you find cards:
- Use the {TOOL_NAME} tool to look up stock. Call it once you know the commander and what the
  deck needs; pick the closest role and card type from the tool's options.
- Only ever recommend cards that {TOOL_NAME} returned. Never invent cards, stock, prices or
  links. If you know a great card that wasn't returned, you may mention we don't have it in
  stock right now.
- The results come back in order of popularity, not fit. Use your Commander knowledge to pick
  the single best card for this customer's commander and problem, and recommend just that
  one card, clearly, with one or two sentences on why it fixes their problem. Only suggest
  another card from the same results if they ask for an alternative.
- The full listings, with pictures and links, appear on the customer's screen next to you.
  Point them there rather than describing where to buy.
- If the result says relaxed is true, tell the customer nothing matched that exact role, and
  offer the closest alternative.
- If none of the results fits the customer's problem, search once more with a related role
  before giving up, and explain the different angle (for example, removing what stops their
  combo instead of protecting it). Only if that second search doesn't fit either, say
  honestly that nothing suitable is in stock. Never search more than twice for one problem.
- If the tool reports an error, apologise briefly and ask the customer to say their
  commander's name again.

If they want help with another problem, search again. When they are done, thank them, wish
them luck with the deck, and end the call."""

CONTEXT = """\
Arcanum Collectibles is a small UK Magic: The Gathering shop that sells singles on eBay. Most
of the stock is from recent sets: Lorwyn Eclipsed, Secrets of Strixhaven, The Hobbit, Reality
Fracture and Avatar: The Last Airbender. Many of these cards are newer than your training, so
trust the card details the search tool returns over your own memory."""

# The decision tree: each deck problem leads to one search role, so every conversation ends
# with a single, clean recommendation. If that search has nothing that fits, the PAL tries the
# fallback role once. Roles must be keys of search.query.ROLE_FILTERS.
PROBLEM_BRANCHES: list[dict[str, str]] = [
    {
        "objective_name": "recommend_ramp",
        "condition": "If the deck is too slow, falls behind early or doesn't have enough mana",
        "role": "ramp",
        "fallback_role": "mana_rock",
        "fallback_angle": "an artifact that makes extra mana, which works in any colour",
        "pitch": "a ramp card to speed the deck up",
    },
    {
        "objective_name": "recommend_interaction",
        "condition": (
            "If their win condition or key pieces keep getting removed, countered or otherwise "
            "stopped by opponents"
        ),
        "role": "protection",
        "fallback_role": "removal",
        "fallback_angle": "removing whatever stops their win condition instead of protecting it",
        "pitch": "a piece of interaction that protects their win condition",
    },
    {
        "objective_name": "recommend_card_draw",
        "condition": "If the deck runs out of cards or gas in the mid to late game",
        "role": "card_draw",
        "fallback_role": "card_advantage",
        "fallback_angle": "a broader card advantage effect that keeps them in gas",
        "pitch": "a card draw spell to keep their hand full",
    },
    {
        "objective_name": "recommend_removal",
        "condition": "If they can't deal with the threats their opponents play",
        "role": "removal",
        "fallback_role": "board_wipe",
        "fallback_angle": "a board wipe that answers several threats at once",
        "pitch": "a removal spell to answer opponents' threats",
    },
]

# Used when the problem doesn't fit any branch above.
FALLBACK_OBJECTIVE = "recommend_best_fit"


def recommend_objective(
    name: str, search_instruction: str, pitch: str, fallback_instruction: str
) -> dict[str, Any]:
    """
    An objective that runs the search and recommends exactly one card, then moves to wrap_up.
    If nothing in the results fits, it searches once more with the fallback before giving up.

    :param search_instruction: which role (and budget) to search with
    :param pitch: how to frame the recommendation, e.g. "a ramp card to speed the deck up"
    :param fallback_instruction: the one follow-up search to try if nothing fits
    """
    return {
        "objective_name": name,
        "objective_prompt": (
            f"Use the {TOOL_NAME} tool with the customer's commander, {search_instruction}. "
            f"From the results, recommend the single best card as {pitch}: say its name, its "
            "price and in one or two sentences why it fixes their problem with this commander. "
            "Point them to the listing on screen. If none of the results genuinely fixes their "
            f"problem, search once more {fallback_instruction}, and recommend the best card from "
            "that search, explaining the different approach. If that doesn't fit either, say "
            "honestly that nothing suitable is in stock."
        ),
        "confirmation_mode": "auto",
        "output_variables": ["recommended_card"],
        "modality": "verbal",
        "next_required_objective": "wrap_up",
    }


def build_objectives() -> list[dict[str, Any]]:
    """
    Build the objectives for the decision tree:
    identify_commander -> identify_deck_problem -> one recommend_* branch -> wrap_up

    identify_deck_problem branches on the customer's problem using PROBLEM_BRANCHES, so the
    PAL searches with exactly one role and recommends exactly one card.
    """
    branches = {branch["objective_name"]: branch["condition"] for branch in PROBLEM_BRANCHES}
    branches[FALLBACK_OBJECTIVE] = "If the problem doesn't fit any of the other options"
    return [
        {
            "objective_name": "identify_commander",
            "objective_prompt": (
                "Ask which commander the customer's deck is built around. If the name is unclear "
                "or unfamiliar, ask them to repeat or spell it."
            ),
            "confirmation_mode": "auto",
            "output_variables": ["commander_name"],
            "modality": "verbal",
            "next_required_objective": "identify_deck_problem",
        },
        {
            "objective_name": "identify_deck_problem",
            "objective_prompt": (
                "Find out the one main problem with the deck, unless the customer has already "
                "said it. Ask an open question like: what's going wrong when you play it? If they "
                "list several problems, ask which one bothers them most. Also ask, briefly, if "
                "they have a budget per card."
            ),
            "confirmation_mode": "auto",
            "output_variables": ["deck_problem", "max_price"],
            "modality": "verbal",
            "next_conditional_objectives": branches,
        },
        *[
            recommend_objective(
                branch["objective_name"],
                f'role "{branch["role"]}" and their budget if they gave one',
                branch["pitch"],
                f'with role "{branch["fallback_role"]}", {branch["fallback_angle"]}',
            )
            for branch in PROBLEM_BRANCHES
        ],
        recommend_objective(
            FALLBACK_OBJECTIVE,
            "the role from the tool's options that best matches their problem, and their budget "
            "if they gave one",
            "the best fix for their problem",
            "with the next closest role from the tool's options",
        ),
        {
            "objective_name": "wrap_up",
            "objective_prompt": (
                "Ask whether the customer wants help with anything else. If they have another "
                "problem, search again for it. When they are finished, thank them, wish them luck "
                "with the deck and end the call."
            ),
            "confirmation_mode": "auto",
            "modality": "verbal",
        },
    ]


OBJECTIVES = build_objectives()


def tool_parameters() -> dict[str, Any]:
    """
    JSON Schema for the search tool's arguments. Enums are built from the backend's own types
    (CardType and ROLE_FILTERS), so the PAL can only send values /api/search accepts. limit is
    left out: the backend's default (10 cards) applies.
    """
    return {
        "type": "object",
        "properties": {
            "commander": {
                "type": "string",
                "description": "The name of the customer's commander, as they said it.",
            },
            "card_type": {
                "type": "string",
                "enum": list(get_args(CardType)),
                "description": "The card type the customer wants, if they have a preference.",
            },
            "role": {
                "type": "string",
                "enum": list(ROLE_FILTERS),
                "description": "The job the card should do in the deck, to fix their problem.",
            },
            "max_price": {
                "type": "number",
                "description": "The most the customer wants to pay per card, in GBP.",
            },
        },
        "required": ["commander"],
    }


def tool_definition() -> dict[str, Any]:
    """
    Body for POST /v2/tools (and PATCH on re-runs) for the card search tool.

    Calls are delivered to the frontend as conversation.tool_call app messages; the frontend
    calls /api/search and replies with a conversation.tool_result. While the search runs the
    PAL says a fixed filler line, then answers from the result.
    """
    return {
        "name": TOOL_NAME,
        "description": (
            "Search Arcanum Collectibles' stock for Magic: The Gathering cards that suit a "
            "commander and fill a role in the deck. Returns up to 10 in-stock cards, most popular "
            "first, with name, price, type and a short summary of the rules text. Call this once "
            "you know the commander and what the deck needs."
        ),
        "parameters": tool_parameters(),
        "origin": "llm",
        "delivery": {"app_message": True},
        "on_call": "static_filler",
        "static_filler": "Let me have a look at what's on the shelves…",
        "on_resolve": "generate_response",
    }


def pal_fields(objectives_id: str) -> dict[str, Any]:
    """
    The PAL settings the setup script manages, keyed by their JSON Pointer path in the PAL
    document. Shared by pal_definition (create) and pal_patch (update) so they can't drift.
    """
    return {
        "/pal_name": PAL_NAME,
        "/system_prompt": SYSTEM_PROMPT,
        "/context": CONTEXT,
        "/greeting": GREETING,
        "/pipeline_mode": "full",
        "/default_face_id": FACE_ID,
        "/objectives_id": objectives_id,
        "/layers/llm/model": LLM_MODEL,
        "/layers/conversational_flow/turn_detection_model": "sparrow-2",
        "/layers/conversational_flow/turn_taking_patience": "medium",
        "/layers/conversational_flow/pal_interruptibility": "medium",
    }


def pal_definition(objectives_id: str) -> dict[str, Any]:
    """
    Body for POST /v2/pals: the shopkeeper PAL with its face, prompts, LLM and objectives.
    """
    body: dict[str, Any] = {}
    for path, value in pal_fields(objectives_id).items():
        *parents, leaf = path.strip("/").split("/")
        node = body
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return body


def pal_patch(objectives_id: str) -> list[dict[str, Any]]:
    """
    JSON Patch for PATCH /v2/pals/{pal_id} that sets every managed field on an existing PAL.
    "add" is used rather than "replace" because it also works when a field isn't set yet
    (RFC 6902: add on an existing object member replaces it).
    """
    return [
        {"op": "add", "path": path, "value": value}
        for path, value in pal_fields(objectives_id).items()
    ]


def objectives_patch() -> list[dict[str, Any]]:
    """
    JSON Patch for PATCH /v2/objectives/{objectives_id} that replaces the whole objectives list.
    """
    return [{"op": "replace", "path": "/data", "value": OBJECTIVES}]
