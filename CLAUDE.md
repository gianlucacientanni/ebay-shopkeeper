This repo is part of a coding challenge for https://www.tavus.io/. Their ask is simple: use Tavus and demonstrate what you can do with it.

My idea is to make a shop-keeper for my Magic The Gathering eBay store: https://www.ebay.co.uk/str/arcanumcollectibles. What this shop keeper will do is be able to talk you through what card you might want to buy. It will give you prompts such as "Who is your commander", "What card type are you looking for: creature, instant, sorcery or something else?". It will then look through my inventory to find close matching results.

My eBay store is driven mainly by API calls rather than through the UI, you can find the repo here: ~/arcanum.

# Tavus

When you need a Tavus API please refer to: https://docs.tavus.io/openapi.yaml, this is where the API contracts are defined and is the source of truth.
 
Tavus give a bunch of examples using Python, I want these to drive the coding style of the repo, as well as drive how I want to build my shopkeeper: https://github.com/Tavus-Engineering/tavus-examples, make special note of the "how to build a deployment with an agent". For the documentation, please use the Tavus docs MCP: https://docs.tavus.io/mcp. For the set of skills please consult:     https://docs.tavus.io/skill.md.

I have a limited 100 minutes of using a Tavus avatar, I will add the credentials to use this later once I have generated a sufficient amount of code.

# Arcanum / eBay Store

The source of truth for cards is my eBay store, the databases in arcanum are temporary and change often. You will need to query the eBay listings to be able to check whether a card exists there.

I don't actually want to integrate this with my store, so I'm going to make a copy of the listings I have on eBay and persist them locally to a sql3.lite database (I haven't yet done this but will). "In stock" below means "present in that local SQLite copy".

The primary flow should be:
1) the PAL gathers the user's description of the card they want (commander, card type, role in the deck, etc.) and calls a backend tool with those details as structured arguments,
2) convert that into a generic Scryfall query with an additional filter on the following sets (I primarily have cards from the following sets): Lorwyn Eclipsed, Secrets of Strixhaven, The Hobbit and Reality Fracture, presume in your searching that cards can only be from those sets and nothing else. Use the commander's colour identity as an `id<=` filter,
3) fetch a wide set of Scryfall results (e.g. up to 100, not just the top 10), so that enough of them survive the stock check,
4) check which of those cards are in stock and discard the rest,
5) make another LLM prompt to make a decision: based on the commander, order the in-stock cards in terms of priority and keep the top few (e.g. 5), each with a one-line reason,
6) return the eBay listing for each (title, price, URL, image) to the PAL to talk through, and show them in the frontend.

Checking stock before ranking means we never rank cards we can't sell, and the ranking prompt stays small.

# Architecture

React frontend + Python backend. API keys (Tavus, LLM) live **only** in the backend; nothing secret is ever put in a `VITE_*` variable, since those are bundled into browser code.

- `front_end/`: React + Vite + TypeScript, Tavus CVI components (`<CVIProvider>`, `<Conversation>`), plus a panel that displays the recommended listings. It asks the backend to create a conversation and never calls `tavusapi.com` directly.
- `back_end/`: Python (uv, FastAPI), styled after the tavus-examples repo. Responsibilities:
  - creating the PAL and conversations via the Tavus API,
  - the card-search tool: Scryfall query → stock check → LLM ranking → listings,
  - reading the local SQLite copy of the eBay listings.

The whole card-search pipeline must be runnable from the command line without a Tavus avatar, so it can be built and tested without spending the 100 minutes. Only start avatar conversations once the tool works end to end, and give test conversations a short maximum duration.

# Prompt checklist
This prompt is suggested by Tavus. It applies to the `front_end/` app only, with these overrides from the Architecture section above:
- the app lives in `front_end/` rather than `my-tavus-app/`;
- step 4: the frontend `POST`s to our backend (which calls `https://tavusapi.com/v2/conversations` with the key) and uses the `conversation_url` it returns;
- step 6: there is no `VITE_TAVUS_API_KEY`. The Tavus key goes in `back_end/.env`. `front_end/.env` holds only non-secret values such as the backend URL.

## ✅ **System Prompt for AI: React (Vite) + Tavus CVI Integration**

**Purpose:**
Generate **React (TypeScript)** apps with Tavus CVI using **Vite**, following the official docs and GitHub examples (embed guide: `https://docs.tavus.io/sections/integrations/embedding-cvi`).

***

### ✅ **AI MUST ALWAYS DO THE FOLLOWING:**

#### **1. Setup React App Using Vite**

```bash  theme={null}
npm create vite@latest my-tavus-app -- --template react-ts
cd my-tavus-app
npm install
```

***

#### **2. Install Tavus CVI UI Components**

```bash  theme={null}
npx @tavus/cvi-ui@latest init
npx @tavus/cvi-ui@latest add conversation
```

✅ This creates:

```
src/components/cvi/components/
  cvi-provider.tsx
  conversation.tsx
```

***

#### **3. Wrap App with `CVIProvider`**

Update `src/App.tsx`:

```tsx  theme={null}
import { CVIProvider } from "./components/cvi/components/cvi-provider";

function App() {
  return <CVIProvider>{/* Your app content */}</CVIProvider>;
}
```

***

#### **4. Create Conversation API Call**

Always use this pattern:

```ts  theme={null}
const response = await fetch("https://tavusapi.com/v2/conversations", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": import.meta.env.VITE_TAVUS_API_KEY || "",
  },
  body: JSON.stringify({
    face_id: import.meta.env.VITE_REPLICA_ID || "rc9cff32ceba",  // Default
    pal_id: import.meta.env.VITE_PERSONA_ID || "pcb7a34da5fe",  // Default
  }),
});

const data = await response.json();
setConversationUrl(data.conversation_url);
```

✅ **Explain:** `conversation_url` from API response is used inside `<Conversation>`.

***

#### **5. Render `Conversation` Inside `CVIProvider`**

```tsx  theme={null}
<Conversation
  conversationUrl={conversationUrl}
  onLeave={() => setConversationUrl(null)}
/>
```

***

#### **6. Add Environment Variable**

Create `.env` in the **`my-tavus-app`** folder (if not already there):

```
VITE_TAVUS_API_KEY=your_api_key_here
VITE_REPLICA_ID=rc9cff32ceba   // Default face_id, can be overridden in .env
VITE_PERSONA_ID=pcb7a34da5fe  // Default pal_id, can be overridden in .env
```

* **Important**: **DO NOT** create `.env` outside of the `my-tavus-app` folder. It must be inside your project directory where `src` exists.

Access via:

```ts  theme={null}
import.meta.env.VITE_TAVUS_API_KEY
import.meta.env.VITE_REPLICA_ID
import.meta.env.VITE_PERSONA_ID
```

***

#### **7. Create `cvi-components.json` by Default**

Ensure that the `cvi-components.json` file is generated in the `my-tavus-app` folder with the following content:

```json  theme={null}
{
  "tsx": true
}
```

***

### ✅ **Expected AI Output Example**

**`src/App.tsx`:**

```tsx  theme={null}
import React, { useState } from "react";
import { CVIProvider } from "./components/cvi/components/cvi-provider";
import { Conversation } from "./components/cvi/components/conversation";

const App: React.FC = () => {
  const [conversationUrl, setConversationUrl] = useState<string | null>(null);

  const createConversation = async () => {
    const response = await fetch("https://tavusapi.com/v2/conversations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": import.meta.env.VITE_TAVUS_API_KEY || "",
      },
      body: JSON.stringify({
        face_id: import.meta.env.VITE_REPLICA_ID || "rc9cff32ceba",
        pal_id: import.meta.env.VITE_PERSONA_ID || "pcb7a34da5fe",
      }),
    });

    const data = await response.json();
    setConversationUrl(data.conversation_url);
  };

  return (
    <CVIProvider>
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          width: "100vw",
          height: "100vh",
          backgroundColor: "#1e1e1e",
          color: "#fff",
          textAlign: "center",
          flexDirection: "column",
          margin: 0,
          padding: 0,
        }}
      >
        <h1 style={{ marginBottom: "1rem" }}>Tavus CVI Integration (Vite)</h1>
        {!conversationUrl ? (
          <button
            onClick={createConversation}
            style={{
              padding: "0.75rem 1.5rem",
              fontSize: "1rem",
              background: "#6a0dad",  // Purple for light and dark modes
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            Start Conversation
          </button>
        ) : (
          <div style={{ width: "100%", maxWidth: "800px" }}>
            <Conversation
              conversationUrl={conversationUrl}
              onLeave={() => setConversationUrl(null)}
            />
          </div>
        )}
      </div>
    </CVIProvider>
  );
};

export default App;
```

***

### ✅ **Checklist for AI Output**

* ✅ Uses **Vite + React TypeScript** (`npm create vite@latest --template react-ts`)
* ✅ Includes `npx @tavus/cvi-ui init` and `add conversation`
* ✅ Imports `CVIProvider` and `Conversation` from `src/components/cvi/components/`
* ✅ Uses correct API call with:

  * `https://tavusapi.com/v2/conversations`
  * Headers: `Content-Type`, `x-api-key`
  * Body: `face_id` & `pal_id`
* ✅ Uses `import.meta.env.VITE_TAVUS_API_KEY`
* ✅ Renders `<Conversation>` inside `<CVIProvider>`
* ✅ Purple button is visible in both light and dark modes
* ✅ `.env` is created inside the correct project folder (`my-tavus-app`)
* ✅ `cvi-components.json` is created by default with `{ "tsx": true }`

***

### Keep things in mind:

* If you're already in the `my-tavus-app` folder, avoid running `cd my-tavus-app` again. Check your current folder before running commands.
* After running the necessary setup, remember to run `npm run dev` to start your app.
* Do **NOT** place the `.env` file outside of the project folder. It must reside within the `my-tavus-app` directory.
