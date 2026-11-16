/**
 * Arcanum Collectibles shopkeeper: a call with Tom (Tavus CVI) beside the listings he finds.
 *
 * The app asks our backend to create the conversation (the Tavus key stays server-side),
 * relays Tom's search_cards tool calls to the backend, and shows the results.
 */
import { useCallback, useState } from "react";
import "./App.css";
import banner from "./assets/banner.webp";
import { createConversation, endConversation, BackendError } from "./api/backend";
import { CVIProvider } from "./components/cvi/components/cvi-provider";
import { ListingsPanel } from "./components/ListingsPanel";
import { ShopkeeperCall } from "./components/ShopkeeperCall";
import { StartScreen } from "./components/StartScreen";
import { findMentionedCard } from "./lib/tomsPick";
import type { ListingsState } from "./types/listings";
import type { ConversationInfo, SearchRequest, SearchResult } from "./types/search";

const STORE_URL = "https://www.ebay.co.uk/str/arcanumcollectibles";

function App() {
  const [conversation, setConversation] = useState<ConversationInfo | null>(null);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastConversationId, setLastConversationId] = useState<string | null>(null);
  const [listings, setListings] = useState<ListingsState>({ status: "idle" });
  const [tomsPick, setTomsPick] = useState<string | null>(null);

  const startCall = useCallback(async () => {
    setStarting(true);
    setNotice(null);
    try {
      setConversation(await createConversation());
      setListings({ status: "idle" });
      setTomsPick(null);
    } catch (error) {
      setNotice(error instanceof BackendError ? error.message : "Couldn't start the call.");
    } finally {
      setStarting(false);
    }
  }, []);

  const leaveCall = useCallback(() => {
    if (conversation) {
      // Best effort: the backend's leave timeout also ends abandoned calls.
      void endConversation(conversation.conversation_id).catch(() => undefined);
      setLastConversationId(conversation.conversation_id);
    }
    setConversation(null);
    setNotice("The call has ended. Thanks for visiting!");
  }, [conversation]);

  const onSearchStart = useCallback((request: SearchRequest) => {
    setListings({ status: "searching", request });
    setTomsPick(null);
  }, []);
  const onListings = useCallback((result: SearchResult) => {
    setListings({ status: "results", result });
  }, []);
  const onError = useCallback((message: string) => {
    setListings({ status: "error", message });
  }, []);
  const onPalSpeech = useCallback(
    (speech: string) => {
      if (listings.status === "results") {
        const pick = findMentionedCard(speech, listings.result.candidates);
        if (pick) setTomsPick(pick);
      }
    },
    [listings],
  );

  return (
    <CVIProvider>
      <header className="masthead">
        <img className="masthead__banner" src={banner} alt="arcanum" />
      </header>
      <main className="shop">
        <div className="shop__stage">
          {conversation ? (
            <ShopkeeperCall
              conversationUrl={conversation.conversation_url}
              onLeave={leaveCall}
              onSearchStart={onSearchStart}
              onListings={onListings}
              onError={onError}
              onPalSpeech={onPalSpeech}
            />
          ) : (
            <StartScreen
              onStart={startCall}
              starting={starting}
              notice={notice}
              lastConversationId={lastConversationId}
            />
          )}
        </div>
        <ListingsPanel state={listings} tomsPick={tomsPick} />
      </main>
      <footer className="colophon">
        <span className="colophon__star" aria-hidden="true">✦</span>
        <a href={STORE_URL} target="_blank" rel="noopener noreferrer">
          Visit Arcanum Collectibles on eBay
        </a>
        <span className="colophon__star" aria-hidden="true">✦</span>
      </footer>
    </CVIProvider>
  );
}

export default App;
