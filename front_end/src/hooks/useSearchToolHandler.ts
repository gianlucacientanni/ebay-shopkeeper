/**
 * Connects the live Tavus call to the card search: relays search_cards tool calls to the
 * backend and replies to the PAL, and passes on what the PAL says (to spot Tom's pick).
 * Must be rendered inside CVIProvider while a call is active.
 */
import { useCallback } from "react";
import { useAppMessage } from "@daily-co/daily-react";
import { searchCards } from "../api/backend";
import { useObservableEvent } from "../components/cvi/hooks/cvi-events-hooks";
import {
  handleSearchToolCall,
  type IncomingAppMessage,
  type ToolResultMessage,
} from "../lib/toolCall";
import type { SearchRequest, SearchResult } from "../types/search";

/** An app message as delivered by the generated useObservableEvent hook. */
type CviEvent = Parameters<Parameters<typeof useObservableEvent<unknown>>[0]>[0];

export interface SearchToolHandlers {
  onSearchStart: (request: SearchRequest) => void;
  onListings: (result: SearchResult) => void;
  onError: (message: string) => void;
  /** Called with each full PAL utterance. */
  onPalSpeech: (speech: string) => void;
}

/**
 * Listen for app messages in the active call. The generated useSendAppMessage hook's types
 * don't include conversation.tool_result, so Daily's useAppMessage is used to send it.
 */
export function useSearchToolHandler(handlers: SearchToolHandlers): void {
  const sendAppMessage = useAppMessage();
  const { onSearchStart, onListings, onError, onPalSpeech } = handlers;

  const send = useCallback(
    (message: ToolResultMessage) => {
      console.info("[shopkeeper] tool_result sent to Tom", message);
      sendAppMessage(message, "*");
    },
    [sendAppMessage],
  );

  useObservableEvent<unknown>(
    useCallback(
      (event: CviEvent) => {
        if (event.event_type === "conversation.utterance") {
          // Tavus sends PAL turns twice (role "pal" and legacy "replica"); handling both is
          // harmless because spotting the pick is idempotent.
          if (event.properties.role !== "user") {
            onPalSpeech(event.properties.speech);
          }
          return;
        }
        if (event.event_type === "conversation.tool_call") {
          console.info("[shopkeeper] tool_call from Tom", event);
        }
        void handleSearchToolCall(event as IncomingAppMessage, {
          search: searchCards,
          send,
          onSearchStart,
          onListings,
          onError,
        });
      },
      [send, onSearchStart, onListings, onError, onPalSpeech],
    ),
  );
}
