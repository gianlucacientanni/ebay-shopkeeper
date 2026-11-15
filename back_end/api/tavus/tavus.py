# standard library
import logging
from typing import Any

# third party
import requests


log = logging.getLogger(__name__)

TAVUS_BASE_URL = "https://tavusapi.com/v2"
TIMEOUT_SECONDS = 30
CONVERSATION_NAME = "Arcanum shopkeeper"
# End the call this many seconds after the customer leaves, so abandoned calls stop quickly.
PARTICIPANT_LEFT_TIMEOUT = 10
# End the call if nobody joins within this many seconds of it being created.
PARTICIPANT_ABSENT_TIMEOUT = 60


class TavusError(Exception):
    pass


def new_session(api_key: str) -> requests.Session:
    """
    Create a requests session authenticated against the Tavus API.

    :raises TavusError: if no API key is configured
    """
    if not api_key:
        raise TavusError("TAVUS_API_KEY is not set in back_end/.env")
    session = requests.Session()
    session.headers.update({"x-api-key": api_key, "Content-Type": "application/json"})
    return session


def conversation_payload(
    pal_id: str, face_id: str, test_mode: bool, max_call_duration: int
) -> dict[str, Any]:
    """
    Build the POST /v2/conversations body for a shopkeeper conversation.

    :param pal_id: the shopkeeper PAL, created by the setup script
    :param face_id: optional face override; an empty string uses the PAL's default face
    :param test_mode: if True the PAL doesn't join and no minutes are used
    :param max_call_duration: hard limit on the call length in seconds
    """
    payload: dict[str, Any] = {
        "pal_id": pal_id,
        "conversation_name": CONVERSATION_NAME,
        "test_mode": test_mode,
        "properties": {
            "max_call_duration": max_call_duration,
            "participant_left_timeout": PARTICIPANT_LEFT_TIMEOUT,
            "participant_absent_timeout": PARTICIPANT_ABSENT_TIMEOUT,
        },
    }
    if face_id:
        payload["face_id"] = face_id
    return payload


def raise_for_tavus_error(response: requests.Response, action: str) -> None:
    """
    Raise a TavusError with Tavus' error message if the response isn't a 2xx.
    """
    if response.ok:
        return
    try:
        body = response.json()
        detail = body.get("error") or body.get("message") or response.text
    except ValueError:
        detail = response.text
    raise TavusError(f"Tavus failed to {action} ({response.status_code}): {detail}")


def create_conversation(session: requests.Session, payload: dict[str, Any]) -> dict[str, str]:
    """
    Create a Tavus conversation.

    :param payload: body from conversation_payload
    :return dict: conversation_id and conversation_url, the only fields the frontend needs
    :raises TavusError: if Tavus rejects the request
    """
    response = session.post(
        f"{TAVUS_BASE_URL}/conversations", json=payload, timeout=TIMEOUT_SECONDS
    )
    raise_for_tavus_error(response, "create the conversation")
    body = response.json()
    log.info(
        "Created conversation %s (test_mode=%s)", body.get("conversation_id"), payload["test_mode"]
    )
    return {
        "conversation_id": str(body["conversation_id"]),
        "conversation_url": str(body["conversation_url"]),
    }


def end_conversation(session: requests.Session, conversation_id: str) -> None:
    """
    End a Tavus conversation so it stops using minutes.

    :raises TavusError: if Tavus rejects the request
    """
    response = session.post(
        f"{TAVUS_BASE_URL}/conversations/{conversation_id}/end", timeout=TIMEOUT_SECONDS
    )
    raise_for_tavus_error(response, f"end conversation {conversation_id}")
