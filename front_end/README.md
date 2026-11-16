# Arcanum Collectibles shopkeeper: frontend

React + Vite + TypeScript app: a Tavus CVI call with Tom (the shopkeeper PAL) beside a
panel of the eBay listings he finds, styled after the Arcanum store banner
(`src/assets/banner.webp`, `src/assets/logo.webp`).

## Run

```bash
# 1. backend (in another terminal)
cd back_end && uv run shopkeeper-api

# 2. frontend
cd front_end
cp .env.example .env   # VITE_BACKEND_URL only; never put secrets in VITE_* variables
npm install
npm run dev            # http://localhost:5173
```

## How it works

- **Talk to Tom:** asks the backend's `POST /api/conversations` for a conversation (the Tavus
  key stays server-side) and renders `<Conversation>` inside `<CVIProvider>`. Leaving the call
  calls `/end`.
- **Tool calls:** Tom's `search_cards` calls arrive as `conversation.tool_call` app messages.
  `src/lib/toolCall.ts` posts the arguments to `/api/search`, shows the full result in the
  listings panel and replies with `conversation.tool_result`: the compact `pal_output` on
  success, `status: "error"` otherwise. Every call gets exactly one reply.
- **Tom's pick:** the card Tom names out loud is highlighted in the panel (`src/lib/tomsPick.ts`).

## Testing without spending minutes

Real calls use avatar minutes; each call is capped by `MAX_CALL_DURATION` (180 s by default).
To check starting and leaving a call for free, set `TAVUS_TEST_MODE=true` in `back_end/.env`:
the conversation is created but Tom doesn't join. The tool-call relay is covered by the unit
tests (`tests/unit/toolCall.test.ts`).

## Production build

```bash
npm run build
npm run preview -- --port 5173 --strictPort   # keep 5173: the backend's CORS allows only that origin
```

```bash
npm test         # unit tests (Vitest)
npm run build    # type-check and production build
```
