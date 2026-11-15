# Card search: request/response and errors

## Flow

```
PAL ──conversation.tool_call──▶ frontend ──POST /api/search──▶ backend ──▶ Scryfall + local SQLite
PAL ◀─conversation.tool_result─ frontend ◀── SearchResponse ──┘
```

1. The PAL calls the search tool. Tavus delivers it to the browser as `conversation.tool_call` (app message).
2. The frontend POSTs the tool arguments (`SearchRequest`) to `/api/search`.
3. The backend makes up to three kinds of Scryfall request:
   - `GET /cards/named?fuzzy=` to look up the commander,
   - `GET /cards/search` with `order=edhrec`, fetching later pages only when they're needed,
   - one retry of the search without the role filter, if nothing was in stock.
4. The backend returns `{result, pal_output}`. The frontend shows `result` in the listings panel and sends only `pal_output` back to the PAL in `conversation.tool_result` with the same `tool_call_id`, because app messages are capped at 4 KB.

## Behaviour by case

| Case | Scryfall | `/api/search` | `tool_result` sent to PAL | PAL behaviour |
|---|---|---|---|---|
| Cards found in stock | 200 | 200, 1–10 candidates | `status: "success"`, `pal_output` | Picks and explains the best few |
| Nothing in stock for the role | 200 / 404 | 200, `relaxed: true`, candidates from the search without the role filter | success | Says nothing matched that role exactly, offers alternatives |
| Nothing in stock at all | 404 (no matches) or no in-stock hits | 200, `cards: []` | success | Says we have nothing suitable in stock |
| Commander not found | 404 on `/cards/named` | **404** `{"detail": "No card found…"}` | `status: "error"` | Acknowledges the failure, asks the customer to repeat the commander's name |
| Commander isn't legendary | 200 | 200 (warning logged, search still runs) | success | Continues normally |
| Invalid Scryfall query | 400 | **502** `{"detail": "Scryfall returned 400: …"}` | `status: "error"` | Acknowledges the failure |
| Scryfall down or rate limited | 5xx / 429 | **502** `{"detail": "Scryfall returned 503: …"}` | `status: "error"` | Acknowledges the failure |
| Scryfall unreachable | timeout / connection error | **502** `{"detail": "Scryfall request failed: Timeout"}` | `status: "error"` | Acknowledges the failure |
| Bad tool arguments (e.g. `limit` > 10, unknown `card_type`, no `commander`) | not called | **422** | `status: "error"` | Acknowledges the failure |
| Inventory DB missing | not called | **500** (unhandled) | `status: "error"` | Acknowledges the failure |

**Rule for the frontend:** any non-200 response from `/api/search` becomes `conversation.tool_result` with `status: "error"`. Always send a result: if none is sent, the call just drops out of the PAL's context.

