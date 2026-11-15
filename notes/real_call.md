# Real call runbook (objective 5)

Every real call uses avatar minutes (100 in total). Each call is capped at 3 minutes
(`MAX_CALL_DURATION=180`), ends 10 s after you leave, and Tom can hang up himself (`end_call`).
Budget: aim for one call; at most two more after fixes (about 10 minutes).

## 1. Pre-flight (free)

```bash
cd back_end && uv run shopkeeper-api          # terminal 1
cd back_end && uv run preflight               # terminal 2: everything must be ✔
cd front_end && npm run dev                   # terminal 3: http://localhost:5173
```

If the PAL check says it's out of date, run `uv run setup-pal` (free), then `preflight` again.

Optional: run the scripted search through **"Dev: simulate Tom's search_cards call"** on the
page to see the listings panel fill before spending any minutes.

## 2. Before you click

- Use Chrome, and allow the microphone and camera when asked.
- Quiet room, headphones if possible, so Tom doesn't hear himself.
- Open DevTools → Console: tool calls and replies are logged as `[shopkeeper] …`.
- Want a demo video for the submission? Start a local screen recording (e.g. OBS) now.

## 3. The call script (about 2 minutes)

| Tom | You |
|---|---|
| Greeting, "What commander are you building around today?" | "Radagast the Brown." |
| "What's going wrong when you play it?" | "It feels too slow, I fall behind early." |
| (may ask about budget) | "Under five pounds a card." |
| "Let me have a look at what's on the shelves…" (filler while searching) | wait, watch the listings panel fill |
| Recommends **one** card and why; it's highlighted as "Tom's pick" | "Great, that's all, thanks!" |
| Wraps up and ends the call | if he hasn't ended it within ~20 s, click Leave |

## 4. Review (free)

The start screen shows the call id after you leave.

```bash
cd back_end && uv run review-call <conversation_id>
```

This waits for Tavus to save the transcript (up to a minute) and writes
`notes/calls/<date>-<id>.md` with the transcript and checks:
`search_cards` called with sensible arguments, cards returned, Tom recommended one of them,
one question at a time, how long it took, and why the call ended.

Fill in "What to tweak", change `back_end/pal/shopkeeper.py` if needed, run
`uv run setup-pal`, and only then decide on another call.

## If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| "Couldn't reach the shop's backend" | backend not running | start `uv run shopkeeper-api` |
| Call ends straight away | test mode on, or the room failed | check `TAVUS_TEST_MODE=false`, rerun `preflight` |
| Tom talks but the panel never fills | tool call not arriving or not relayed | check the console for `[shopkeeper] tool_call`; check backend logs for `/api/search` |
| Tom says the search failed | backend returned an error | see `notes/errors.md`; backend logs show the detail |
| Tom names a card that isn't on screen | prompt not followed | note it in the review; tighten the prompt in `shopkeeper.py` |
