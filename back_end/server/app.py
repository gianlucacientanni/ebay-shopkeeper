"""
FastAPI backend for the shopkeeper frontend.

    uv run shopkeeper-api
    uv run uvicorn back_end.server.app:app --reload --port 8000

The Tavus API key stays here: the frontend asks this backend to create conversations and
never calls tavusapi.com itself.
"""

# standard library
import logging

# third party
import uvicorn
from fastapi import FastAPI, HTTPException, Path, Response
from fastapi.middleware.cors import CORSMiddleware

# ebay_shopkeeper imports
from back_end.api.scryfall.scryfall import CommanderNotFound, ScryfallError
from back_end.api.tavus import tavus
from back_end.common import config
from back_end.common.models import SearchRequest, SearchResponse
from back_end.pal.tool_output import pal_tool_output
from back_end.search.pipeline import card_search


log = logging.getLogger(__name__)

# Tavus conversation ids are short alphanumeric strings, e.g. "c477c9dd7aa6e4fe".
CONVERSATION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

app = FastAPI(title="Arcanum shopkeeper")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """
    Liveness check for the frontend and local development.
    """
    return {"status": "ok"}


@app.post("/api/search")
def search(request: SearchRequest) -> SearchResponse:
    """
    Run the card search for the PAL's tool call. The frontend shows result in the listings
    panel and sends pal_output back to the PAL as the conversation.tool_result.

    Errors: 404 if the commander can't be found (the frontend reports the error to the PAL,
    which asks the customer again), 502 if Scryfall rejects the search.
    """
    try:
        result = card_search(request)
    except CommanderNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScryfallError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SearchResponse(result=result, pal_output=pal_tool_output(result))


@app.post("/api/conversations")
def create_conversation() -> dict[str, str]:
    """
    Create a shopkeeper conversation and return its id and URL for the CVI components.
    Uses test_mode and max_call_duration from config.

    Errors: 500 if TAVUS_API_KEY or TAVUS_PAL_ID isn't configured, 502 if Tavus rejects
    the request.
    """
    if not config.TAVUS_API_KEY or not config.TAVUS_PAL_ID:
        raise HTTPException(
            status_code=500,
            detail="TAVUS_API_KEY and TAVUS_PAL_ID must be set in back_end/.env",
        )
    payload = tavus.conversation_payload(
        pal_id=config.TAVUS_PAL_ID,
        face_id=config.TAVUS_FACE_ID,
        test_mode=config.TAVUS_TEST_MODE,
        max_call_duration=config.MAX_CALL_DURATION,
    )
    try:
        return tavus.create_conversation(tavus.new_session(config.TAVUS_API_KEY), payload)
    except tavus.TavusError as exc:
        log.warning("%s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/conversations/{conversation_id}/end", status_code=204)
def end_conversation(
    conversation_id: str = Path(pattern=CONVERSATION_ID_PATTERN),
) -> Response:
    """
    End a conversation when the customer leaves, so it stops using minutes.

    Errors: 500 if TAVUS_API_KEY isn't configured, 502 if Tavus rejects the request.
    """
    if not config.TAVUS_API_KEY:
        raise HTTPException(status_code=500, detail="TAVUS_API_KEY must be set in back_end/.env")
    try:
        tavus.end_conversation(tavus.new_session(config.TAVUS_API_KEY), conversation_id)
    except tavus.TavusError as exc:
        log.warning("%s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(status_code=204)


def main() -> None:
    """
    Run the API with uvicorn (installed as `shopkeeper-api`).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run("back_end.server.app:app", host="127.0.0.1", port=8000, reload=True)
