# standard library
import logging
from typing import Any, Optional

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

# A JSON Patch (RFC 6902) document, as used by the PAL and objectives PATCH endpoints.
JsonPatch = list[dict[str, Any]]


class TavusError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


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


def raise_for_tavus_error(response: requests.Response, action: str) -> None:
    """
    Raise a TavusError with Tavus' error message (and the status code) if the response isn't
    a 2xx.
    """
    if response.ok:
        return
    try:
        body = response.json()
        detail = body.get("error") or body.get("message") or response.text
    except ValueError:
        detail = response.text
    raise TavusError(
        f"Tavus failed to {action} ({response.status_code}): {detail}",
        status_code=response.status_code,
    )


def tavus_request(
    session: requests.Session,
    method: str,
    path: str,
    action: str,
    json: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Make a Tavus API request and return the JSON body ({} for empty responses).

    :param path: path under TAVUS_BASE_URL, e.g. "/pals/p123"
    :param action: what the request does, used in error messages, e.g. "create the PAL"
    :raises TavusError: if the request fails to complete or Tavus returns a non-2xx
    """
    try:
        response = session.request(
            method, f"{TAVUS_BASE_URL}{path}", json=json, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise TavusError(f"Tavus request to {action} failed: {exc.__class__.__name__}") from exc
    raise_for_tavus_error(response, action)
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


# Conversations


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


def create_conversation(session: requests.Session, payload: dict[str, Any]) -> dict[str, str]:
    """
    Create a Tavus conversation.

    :param payload: body from conversation_payload
    :return dict: conversation_id and conversation_url, the only fields the frontend needs
    :raises TavusError: if Tavus rejects the request
    """
    body = tavus_request(session, "POST", "/conversations", "create the conversation", payload)
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
    tavus_request(
        session,
        "POST",
        f"/conversations/{conversation_id}/end",
        f"end conversation {conversation_id}",
    )


# Tools


def create_tool(session: requests.Session, tool: dict[str, Any]) -> str:
    """
    Create a tool and return its tool_id.

    :param tool: body for POST /v2/tools, e.g. from shopkeeper.tool_definition
    """
    body = tavus_request(session, "POST", "/tools", f"create tool {tool['name']}", tool)
    return str(body["tool_id"])


def update_tool(session: requests.Session, tool_id: str, tool: dict[str, Any]) -> None:
    """
    Update a tool. Only the fields present in tool are changed.
    """
    tavus_request(session, "PATCH", f"/tools/{tool_id}", f"update tool {tool_id}", tool)


def get_tool(session: requests.Session, tool_id: str) -> dict[str, Any]:
    """
    Fetch a tool by id.

    :raises TavusError: with status_code 404 if the tool doesn't exist
    """
    return tavus_request(session, "GET", f"/tools/{tool_id}", f"get tool {tool_id}")


# Objectives


def create_objectives(session: requests.Session, objectives: list[dict[str, Any]]) -> str:
    """
    Create an objectives set and return its objectives_id.

    :param objectives: the objectives, sent as {"data": objectives}
    """
    body = tavus_request(
        session, "POST", "/objectives", "create the objectives", {"data": objectives}
    )
    return str(body["objectives_id"])


def patch_objectives(session: requests.Session, objectives_id: str, patch: JsonPatch) -> None:
    """
    Update an objectives set with JSON Patch operations.
    """
    tavus_request(
        session,
        "PATCH",
        f"/objectives/{objectives_id}",
        f"update objectives {objectives_id}",
        patch,
    )


def get_objectives(session: requests.Session, objectives_id: str) -> dict[str, Any]:
    """
    Fetch an objectives set by id.

    :raises TavusError: with status_code 404 if the objectives don't exist
    """
    return tavus_request(
        session, "GET", f"/objectives/{objectives_id}", f"get objectives {objectives_id}"
    )


# PALs


def create_pal(session: requests.Session, pal: dict[str, Any]) -> str:
    """
    Create a PAL and return its pal_id.

    :param pal: body for POST /v2/pals, e.g. from shopkeeper.pal_definition
    """
    body = tavus_request(session, "POST", "/pals", "create the PAL", pal)
    return str(body["pal_id"])


def patch_pal(session: requests.Session, pal_id: str, patch: JsonPatch) -> None:
    """
    Update a PAL with JSON Patch operations.
    """
    tavus_request(session, "PATCH", f"/pals/{pal_id}", f"update PAL {pal_id}", patch)


def get_pal(session: requests.Session, pal_id: str) -> dict[str, Any]:
    """
    Fetch a PAL by id.

    :raises TavusError: with status_code 404 if the PAL doesn't exist
    """
    return tavus_request(session, "GET", f"/pals/{pal_id}", f"get PAL {pal_id}")


def attach_tools(session: requests.Session, pal_id: str, tool_ids: list[str]) -> None:
    """
    Attach tools to a PAL. Attaching an already attached tool is a no-op on Tavus' side.
    System tools are attached by name, e.g. "end_call".
    """
    tavus_request(
        session,
        "POST",
        f"/pals/{pal_id}/tools",
        f"attach tools to PAL {pal_id}",
        {"tool_ids": tool_ids},
    )
