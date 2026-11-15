/**
 * Pure logic for relaying the PAL's search_cards tool calls to the backend. No React here,
 * so it can be unit tested and reused by both the live call and the dev simulator.
 *
 * Flow: Tavus sends conversation.tool_call (app message) -> we POST the arguments to
 * /api/search -> we reply with conversation.tool_result carrying the compact pal_output,
 * or status "error". Every call gets a reply, otherwise the PAL is left waiting.
 */
import { BackendError } from "../api/backend";
import type { SearchRequest, SearchResponse, SearchResult } from "../types/search";

export const SEARCH_TOOL_NAME = "search_cards";
/** Tavus app messages over this size are dropped in transit without an error. */
export const TOOL_RESULT_LIMIT_BYTES = 4096;

/** The parts of an incoming app message we look at. */
export interface IncomingAppMessage {
  event_type?: string;
  conversation_id?: string;
  properties?: {
    name?: string;
    arguments?: unknown;
    tool_call_id?: string;
  };
}

export type ToolResultStatus = "success" | "error";

/** The conversation.tool_result message sent back to the PAL. */
export interface ToolResultMessage {
  message_type: "conversation";
  event_type: "conversation.tool_result";
  conversation_id: string;
  properties: {
    tool_call_id: string;
    output: string | Record<string, unknown>;
    status: ToolResultStatus;
  };
}

/** A search_cards call, either with valid arguments or with the reason they're invalid. */
export type ParsedToolCall =
  | { valid: true; toolCallId: string; conversationId: string; request: SearchRequest }
  | { valid: false; toolCallId: string; conversationId: string; error: string };

/**
 * Read the tool's arguments into a SearchRequest. Tavus sends them as a JSON string written
 * by the LLM, so they're parsed defensively and only known fields are kept.
 *
 * @returns the request, or an error message describing what's wrong
 */
export function parseSearchArguments(raw: unknown): SearchRequest | string {
  let args: unknown = raw;
  if (typeof raw === "string") {
    try {
      args = JSON.parse(raw);
    } catch {
      return "The search arguments weren't valid JSON.";
    }
  }
  if (typeof args !== "object" || args === null) {
    return "The search arguments were missing.";
  }
  const values = args as Record<string, unknown>;
  const commander = typeof values.commander === "string" ? values.commander.trim() : "";
  if (!commander) {
    return "The search needs the customer's commander.";
  }
  const request: SearchRequest = { commander };
  if (typeof values.card_type === "string" && values.card_type) {
    request.card_type = values.card_type;
  }
  if (typeof values.role === "string" && values.role) {
    request.role = values.role;
  }
  const maxPrice = Number(values.max_price);
  if (values.max_price !== undefined && values.max_price !== null && Number.isFinite(maxPrice)) {
    request.max_price = maxPrice;
  }
  return request;
}

/**
 * Recognise a search_cards tool call.
 *
 * @returns the parsed call, or null if the message is anything else (other events or tools)
 */
export function parseSearchToolCall(message: IncomingAppMessage): ParsedToolCall | null {
  const properties = message.properties;
  if (
    message.event_type !== "conversation.tool_call" ||
    properties?.name !== SEARCH_TOOL_NAME ||
    !properties.tool_call_id
  ) {
    return null;
  }
  const ids = { toolCallId: properties.tool_call_id, conversationId: message.conversation_id ?? "" };
  const parsed = parseSearchArguments(properties.arguments);
  return typeof parsed === "string"
    ? { valid: false, ...ids, error: parsed }
    : { valid: true, ...ids, request: parsed };
}

/** Build the conversation.tool_result reply for a tool call. */
export function toolResultMessage(
  conversationId: string,
  toolCallId: string,
  output: string | Record<string, unknown>,
  status: ToolResultStatus,
): ToolResultMessage {
  return {
    message_type: "conversation",
    event_type: "conversation.tool_result",
    conversation_id: conversationId,
    properties: { tool_call_id: toolCallId, output, status },
  };
}

/** Size in bytes of a message as sent over the data channel (UTF-8 JSON). */
export function messageSize(message: unknown): number {
  return new TextEncoder().encode(JSON.stringify(message)).length;
}

/**
 * A short, PAL-friendly description of a failed search. The PAL reads this and responds
 * (e.g. asking the customer to repeat the commander's name on a 404).
 */
export function searchErrorMessage(error: unknown): string {
  if (error instanceof BackendError) {
    if (error.status === 404) {
      return `${error.message}. Ask the customer to repeat or spell their commander's name.`;
    }
    return `The stock search failed: ${error.message}`;
  }
  return "The stock search failed unexpectedly.";
}

export interface SearchToolCallDeps {
  /** Runs the search, normally api/backend.searchCards. */
  search: (request: SearchRequest) => Promise<SearchResponse>;
  /** Sends the reply to the PAL, normally the Daily app-message sender. */
  send: (message: ToolResultMessage) => void;
  onSearchStart?: (request: SearchRequest) => void;
  onListings?: (result: SearchResult) => void;
  onError?: (message: string) => void;
}

/**
 * Handle one incoming app message. Non-search messages are ignored. A search_cards call
 * always gets exactly one tool_result: pal_output on success, status "error" otherwise.
 *
 * @returns the reply that was sent, or null if the message wasn't a search_cards call
 */
export async function handleSearchToolCall(
  message: IncomingAppMessage,
  deps: SearchToolCallDeps,
): Promise<ToolResultMessage | null> {
  const call = parseSearchToolCall(message);
  if (call === null) {
    return null;
  }

  let reply: ToolResultMessage;
  if (!call.valid) {
    deps.onError?.(call.error);
    reply = toolResultMessage(call.conversationId, call.toolCallId, call.error, "error");
  } else {
    deps.onSearchStart?.(call.request);
    try {
      const response = await deps.search(call.request);
      deps.onListings?.(response.result);
      reply = toolResultMessage(call.conversationId, call.toolCallId, response.pal_output, "success");
    } catch (error) {
      const description = searchErrorMessage(error);
      deps.onError?.(description);
      reply = toolResultMessage(call.conversationId, call.toolCallId, description, "error");
    }
  }
  deps.send(reply);
  return reply;
}
