/**
 * Dev-only stand-in for Tom: builds a fake conversation.tool_call and runs it through the
 * same handler the live call uses, without starting a call or spending minutes. Shows the
 * exact tool_result that would be sent to Tom and its size against the 4 KB limit.
 */
import { useState, type FormEvent } from "react";
import { searchCards } from "../api/backend";
import {
  SEARCH_TOOL_NAME,
  TOOL_RESULT_LIMIT_BYTES,
  handleSearchToolCall,
  messageSize,
  type ToolResultMessage,
} from "../lib/toolCall";
import { CARD_TYPES, ROLES } from "../lib/searchOptions";
import type { SearchToolHandlers } from "../hooks/useSearchToolHandler";

type SimulatorProps = Omit<SearchToolHandlers, "onPalSpeech">;

let simulatedCallCount = 0;

/** Build the app message Tavus would send when Tom calls search_cards. */
export function fakeToolCall(args: Record<string, unknown>) {
  simulatedCallCount += 1;
  return {
    message_type: "conversation",
    event_type: "conversation.tool_call",
    conversation_id: "dev-simulator",
    properties: {
      name: SEARCH_TOOL_NAME,
      arguments: JSON.stringify(args),
      tool_call_id: `sim_${simulatedCallCount}`,
    },
  };
}

export function DevToolCallSimulator(handlers: SimulatorProps) {
  const [commander, setCommander] = useState("Radagast the Brown");
  const [role, setRole] = useState("ramp");
  const [cardType, setCardType] = useState("");
  const [reply, setReply] = useState<ToolResultMessage | null>(null);

  async function simulate(event: FormEvent) {
    event.preventDefault();
    const args: Record<string, unknown> = { commander };
    if (role) args.role = role;
    if (cardType) args.card_type = cardType;
    await handleSearchToolCall(fakeToolCall(args), {
      search: searchCards,
      send: setReply,
      ...handlers,
    });
  }

  const size = reply ? messageSize(reply) : 0;

  return (
    <details className="simulator">
      <summary>Dev: simulate Tom's search_cards call</summary>
      <form className="simulator__form" onSubmit={simulate}>
        <label>
          Commander
          <input value={commander} onChange={(e) => setCommander(e.target.value)} />
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">(none)</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label>
          Card type
          <select value={cardType} onChange={(e) => setCardType(e.target.value)}>
            <option value="">(any)</option>
            {CARD_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">Send tool call</button>
      </form>
      {reply && (
        <div className="simulator__reply">
          <p>
            tool_result sent to Tom: <strong>{reply.properties.status}</strong>, {size} /{" "}
            {TOOL_RESULT_LIMIT_BYTES} bytes {size > TOOL_RESULT_LIMIT_BYTES ? "(TOO LARGE)" : "(OK)"}
          </p>
          <pre>{JSON.stringify(reply, null, 2)}</pre>
        </div>
      )}
    </details>
  );
}
