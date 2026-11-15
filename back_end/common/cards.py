# standard library
import re
from collections.abc import Iterable, Mapping
from typing import Any, Optional


WUBRG_ORDER = "WUBRG"
NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")


def front_face_name(name: str) -> str:
    """
    Return the front face of a double-faced card name.
    E.g. "Studious First-Year // Rampant Growth" -> "Studious First-Year"
    Single-faced names are returned unchanged (minus surrounding whitespace).
    """
    return name.split(" // ")[0].strip()


def normalize_name(name: str) -> str:
    """
    Normalise a card name so that SKU tokens, eBay listing names and Scryfall names compare
    equal. Only upper-case alphanumerics of the front face are kept, e.g.
    "Gandalf, the Grey" -> "GANDALFTHEGREY"
    "GANDALF_THE_GREY" -> "GANDALFTHEGREY"
    """
    front = name.split("//")[0]
    return NON_ALNUM_RE.sub("", front.upper())


def format_colour_identity(colours: Iterable[str]) -> str:
    """
    Return colour identity letters in WUBRG order, e.g. ["G", "w"] -> "WG".
    An empty colour identity (a colourless card) is returned as "C".
    """
    letters = {c.upper() for c in colours}
    ordered = "".join(c for c in WUBRG_ORDER if c in letters)
    return ordered or "C"


def image_url_for(card: Mapping[str, Any]) -> Optional[str]:
    """
    Return the "normal" sized image URL for a Scryfall card object.
    Double-faced cards have no top-level image_uris, so the front face's image is used instead.
    """
    image_uris = card.get("image_uris")
    if isinstance(image_uris, Mapping) and image_uris.get("normal"):
        return str(image_uris["normal"])
    faces = card.get("card_faces")
    if isinstance(faces, list) and faces and isinstance(faces[0], Mapping):
        face_uris = faces[0].get("image_uris")
        if isinstance(face_uris, Mapping) and face_uris.get("normal"):
            return str(face_uris["normal"])
    return None


def oracle_text_for(card: Mapping[str, Any]) -> str:
    """
    Return the rules (oracle) text for a Scryfall card object.
    Double-faced cards have no top-level oracle_text, so each face's text is joined with "//".
    """
    if card.get("oracle_text"):
        return str(card["oracle_text"])
    faces = card.get("card_faces")
    if isinstance(faces, list):
        return "\n//\n".join(
            str(face.get("oracle_text") or "") for face in faces if isinstance(face, Mapping)
        )
    return ""
