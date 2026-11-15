# standard library
import os
from pathlib import Path

# third party
from dotenv import load_dotenv


BACK_END_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACK_END_DIR.parent

load_dotenv(BACK_END_DIR / ".env")

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
