/**
 * Client for our FastAPI backend. The browser never talks to tavusapi.com and never sees
 * the Tavus API key: the backend does that.
 */
import type { ConversationInfo, SearchRequest, SearchResponse } from "../types/search";

const DEFAULT_BACKEND_URL = "http://localhost:8000";

/** An error response (or no response) from the backend. status is 0 for network failures. */
export class BackendError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "BackendError";
    this.status = status;
  }
}

/** Base URL of the backend, from VITE_BACKEND_URL (not a secret). */
export function backendUrl(): string {
  return (import.meta.env.VITE_BACKEND_URL as string | undefined) || DEFAULT_BACKEND_URL;
}

/**
 * Turn a non-2xx response into a BackendError, using FastAPI's {"detail": ...} body when
 * there is one. Validation errors (422) have a list as detail; they're summarised.
 */
async function errorFromResponse(response: Response): Promise<BackendError> {
  let detail = `${response.status} ${response.statusText}`.trim();
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body?.detail)) {
      detail = "Invalid search: " + body.detail.map((d: { msg?: string }) => d.msg).join("; ");
    }
  } catch {
    // Not JSON: keep the status text.
  }
  return new BackendError(response.status, detail);
}

/**
 * POST to the backend and return the parsed JSON body (or undefined for 204).
 *
 * @throws BackendError for non-2xx responses, or with status 0 if the backend is unreachable
 */
async function post<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${backendUrl()}${path}`, {
      method: "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new BackendError(0, "Couldn't reach the shop's backend. Is it running?");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** Create a shopkeeper conversation (test mode and the call length are set by the backend). */
export function createConversation(): Promise<ConversationInfo> {
  return post<ConversationInfo>("/api/conversations");
}

/** End a conversation so it stops using minutes. */
export function endConversation(conversationId: string): Promise<void> {
  return post<void>(`/api/conversations/${encodeURIComponent(conversationId)}/end`);
}

/** Run the card search for a search_cards tool call. */
export function searchCards(request: SearchRequest): Promise<SearchResponse> {
  return post<SearchResponse>("/api/search", request);
}
