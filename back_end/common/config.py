# standard library
import json
import os
from pathlib import Path

# third party
from dotenv import load_dotenv


BACK_END_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACK_END_DIR.parent

load_dotenv(BACK_END_DIR / ".env")



def env_bool(name: str, default: bool) -> bool:
    """
    Read a boolean environment variable. "1", "true", "yes" and "on" (any case) are True,
    anything else set is False, and an unset variable returns default.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# Sets the store mainly stocks. Scryfall searches are restricted to these.
STOCKED_SETS: tuple[str, ...] = ("ecl", "sos", "hob", "fra", "tla")

INVENTORY_DB_PATH = Path(
    os.environ.get("INVENTORY_DB_PATH", REPO_ROOT / "ebay_data" / "inventory.sqlite3")
)

# Sliding window over Scryfall's EDHREC-ordered results: inspect WINDOW_SIZE cards at a
# time, moving on until at least MIN_IN_STOCK are in stock or MAX_WINDOWS are used up.
WINDOW_SIZE = int(os.environ.get("SEARCH_WINDOW_SIZE", "10"))
MAX_WINDOWS = int(os.environ.get("SEARCH_MAX_WINDOWS", "5"))
MIN_IN_STOCK = int(os.environ.get("SEARCH_MIN_IN_STOCK", "5"))

# Most cards a search returns. Keeps the tool result sent to the PAL under the 4 KB
# app-message limit.
MAX_CANDIDATES = 10

# Tavus. The API key is only ever read here and sent to tavusapi.com from the backend.
TAVUS_API_KEY = os.environ.get("TAVUS_API_KEY", "")
# Ids of the tool, objectives and PAL created by `uv run setup-pal` (gitignored).
TAVUS_RESOURCES_PATH = BACK_END_DIR / ".tavus_resources.json"


def saved_pal_id(path: Path = TAVUS_RESOURCES_PATH) -> str:
    """
    The pal_id saved by the setup script, or "" if setup hasn't been run.
    """
    if not path.exists():
        return ""
    return str(json.loads(path.read_text()).get("pal_id", ""))


# An explicit TAVUS_PAL_ID wins; otherwise use the PAL created by the setup script.
TAVUS_PAL_ID = os.environ.get("TAVUS_PAL_ID") or saved_pal_id()
TAVUS_FACE_ID = os.environ.get("TAVUS_FACE_ID", "")
# Real calls by default. Set TAVUS_TEST_MODE=true to create conversations the PAL doesn't
# join (no minutes used), e.g. to test the start/leave plumbing for free.
TAVUS_TEST_MODE = env_bool("TAVUS_TEST_MODE", False)
MAX_CALL_DURATION = int(os.environ.get("MAX_CALL_DURATION", "180"))

# Origin of the React dev server, allowed by CORS.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
