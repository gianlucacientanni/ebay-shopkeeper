# Arcanum Collectibles: a Tavus shopkeeper for a Magic: The Gathering store

Tom is a video shopkeeper built on Tavus CVI. A customer tells him which commander they play and
what's going wrong with their deck. Tom works out what the deck needs, searches the shop's stock
and recommends one card he can actually sell, with its eBay listing shown next to the call.

## How it works

```
PAL (Tom) ──conversation.tool_call──▶ frontend ──POST /api/search──▶ backend ──▶ Scryfall + local SQLite
PAL (Tom) ◀─conversation.tool_result─ frontend ◀── {result, pal_output} ─┘
```

1. **Objectives** steer the call: greet the customer, ask for their commander, diagnose the problem
   (too slow, can't protect the combo, runs out of cards, can't answer threats), then branch to a
   recommendation.
2. Tom calls the **`search_cards`** tool with structured arguments (commander, role, card type,
   budget). Tavus sends this to the browser as an app message.
3. The frontend posts the arguments to the **backend**, which:
   - looks up the commander on Scryfall and builds a query limited to its colour identity
     (`id<=`) and the sets the shop stocks (ECL, SOS, HOB, FRA, TLA),
   - reads the results in EDHREC order, 10 at a time, and keeps only cards in stock in the local
     SQLite copy of the eBay listings. It stops once at least 5 are in stock or after 50 cards,
   - returns the full listings (title, price, URL, image) for the frontend's panel, plus a compact
     `pal_output` for Tom, because Tavus app messages are capped at 4 KB.
4. The frontend fills the listings panel and replies to Tom with `conversation.tool_result`.
   Tom's own LLM picks the best card and explains why it fixes the problem. If nothing fits, he
   searches once more from a related angle before saying nothing suitable is in stock.

The Tavus API key stays in the backend. The browser never calls `tavusapi.com` directly.

| Path | What's there |
|---|---|
| `back_end/search/` | Card-search pipeline (`pipeline.py`), Scryfall query builder (`query.py`), CLI |
| `back_end/server/app.py` | FastAPI: `/api/search`, `/api/conversations`, `/api/conversations/{id}/end`, `/api/health` |
| `back_end/pal/shopkeeper.py` | Tom's persona, system prompt, objectives and the `search_cards` tool definition |
| `back_end/pal/setup.py` | Creates or updates the tool, objectives and PAL on Tavus |
| `back_end/pal/preflight.py`, `review_call.py` | Free checks before a call; transcript review after one |
| `front_end/src/lib/toolCall.ts` | Relays Tom's tool calls to the backend and sends the tool results back |
| `front_end/src/components/` | CVI components, start screen, listings panel |
| `ebay_data/inventory.sqlite3` | Snapshot of the store's eBay listings (~1,350 cards); the backend reads stock from here |

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ (or 22.12+) and npm
- A Tavus API key
- Chrome is recommended for the call (allow camera and microphone)

## Setup

### 1. Backend

```bash
cd back_end
uv sync
cp .env.example .env        # then set TAVUS_API_KEY
uv run pytest               # unit tests, no network needed
```

Try the search pipeline on its own. It needs no Tavus key and uses no minutes:

```bash
uv run card-search --commander "Radagast the Brown" --role ramp
uv run card-search --commander "Radagast the Brown" --role ramp --pal-output   # what Tom receives
```

Create the shopkeeper in your Tavus account. This uses only the REST API, so it costs no minutes:

```bash
uv run setup-pal --dry-run  # print the tool, objectives and PAL payloads
uv run setup-pal            # creates them; ids are saved to back_end/.tavus_resources.json
```

Re-running `setup-pal` updates the same resources. Then start the API on http://localhost:8000:

```bash
uv run shopkeeper-api
```

### 2. Frontend

In a second terminal:

```bash
cd front_end
cp .env.example .env        # only VITE_BACKEND_URL, no secrets
npm install
npm test                    # optional: unit tests
npm run dev                 # http://localhost:5173
```

Keep the frontend on port 5173, because the backend's CORS only allows `FRONTEND_ORIGIN`
(default `http://localhost:5173`).

### 3. Pre-flight checks

With the backend running:

```bash
cd back_end
uv run preflight            # checks the backend, config, PAL, tools and a scripted search; uses no minutes
```

## Configuration (`back_end/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `TAVUS_API_KEY` | (none, required) | Tavus API key |
| `TAVUS_PAL_ID` | from `.tavus_resources.json` | Use an existing PAL instead of the one `setup-pal` made |
| `TAVUS_FACE_ID` | stock "Thomas" face | Override Tom's face |
| `TAVUS_TEST_MODE` | `false` | `true` creates conversations Tom doesn't join (tests the start/leave flow without using minutes) |
| `MAX_CALL_DURATION` | `180` | Call length cap in seconds |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS origin |
| `INVENTORY_DB_PATH` | `ebay_data/inventory.sqlite3` | Stock database |
| `SEARCH_WINDOW_SIZE` / `SEARCH_MAX_WINDOWS` / `SEARCH_MIN_IN_STOCK` | `10` / `5` / `5` | Search window tuning |

## A real call

Open http://localhost:5173, click **Talk to Tom**, and try this script (about 2 minutes):

| Tom | You |
|---|---|
| "What commander are you building around today?" | "Radagast the Brown." |
| "What's going wrong when you play it?" | "It feels too slow, I fall behind early." |
| (may ask about budget) | "Under five pounds a card." |
| "Let me have a look at what's on the shelves…" | Watch the listings panel fill |
| Recommends one card and why; it's highlighted as "Tom's pick" | "Great, that's all, thanks!" |

Other problems Tom handles: the deck can't protect its win condition, runs out of cards, or
can't deal with opponents' threats. Tool calls and replies are logged in the browser console as
`[shopkeeper] …`.

After the call, the start screen shows the conversation id. To review it:

```bash
cd back_end
uv run review-call <conversation_id>   # writes notes/calls/<date>-<id>.md (gitignored)
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Couldn't reach the shop's backend" | Backend not running | `uv run shopkeeper-api` |
| Call ends straight away | `TAVUS_TEST_MODE=true`, or the room failed | Set it to `false`, rerun `preflight` |
| Tom talks but the panel never fills | Tool call not arriving or not relayed | Look for `[shopkeeper] tool_call` in the console and `/api/search` in the backend logs |
| Tom says the search failed | Backend returned an error (commander not found, Scryfall down) | Check the backend logs; Tom will ask the customer to repeat the commander |
| `preflight` says the PAL is out of date | `shopkeeper.py` changed since the last setup | `uv run setup-pal` |

## Tests

```bash
cd back_end && uv run pytest                      # unit tests
cd back_end && RUN_LIVE=1 uv run pytest tests/e2e # live search against Scryfall
cd front_end && npm test && npm run build         # unit tests, type-check and build
```

`back_end/database/backfill_inventory.py` is the one-off script that built
`ebay_data/inventory.sqlite3` from the live store. It needs the store's private eBay credentials,
so reviewers don't need to run it.
