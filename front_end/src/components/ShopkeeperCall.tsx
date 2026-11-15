/**
 * The live call with Tom. Renders the Tavus Conversation component and relays Tom's
 * search_cards tool calls to the backend. Must be rendered inside CVIProvider.
 */
import { Conversation } from "./cvi/components/conversation";
import { useSearchToolHandler, type SearchToolHandlers } from "../hooks/useSearchToolHandler";

interface ShopkeeperCallProps extends SearchToolHandlers {
  conversationUrl: string;
  onLeave: () => void;
}

export function ShopkeeperCall({ conversationUrl, onLeave, ...handlers }: ShopkeeperCallProps) {
  useSearchToolHandler(handlers);
  return (
    <div className="call">
      <Conversation conversationUrl={conversationUrl} onLeave={onLeave} />
    </div>
  );
}
