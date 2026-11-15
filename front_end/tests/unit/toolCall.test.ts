import { describe, expect, it, vi } from "vitest";
import { BackendError } from "../../src/api/backend";
import {
  handleSearchToolCall,
  messageSize,
  parseSearchArguments,
  parseSearchToolCall,
  toolResultMessage,
} from "../../src/lib/toolCall";
import type { SearchResponse } from "../../src/types/search";

const SEARCH_RESPONSE: SearchResponse = {
  result: {
    query: "(s:hob) id<=g otag:ramp",
    commander: { name: "Radagast the Brown", colour_identity: "G", type_line: "", oracle_text: "" },
    inspected: 10,
    in_stock_count: 1,
    relaxed: false,
    candidates: [
      {
        name: "Troop of Ponies",
        title: "Troop of Ponies (foil)",
        price: "3.99",
        finish: "FOIL",
        listing_url: "https://www.ebay.co.uk/itm/147540417740",
        image_url: null,
        type_line: "Creature — Horse",
        mana_cost: "{2}",
        oracle_text: "Vigilance",
        other_finishes: ["NONFOIL"],
      },
    ],
  },
  pal_output: {
    commander: "Radagast the Brown",
    relaxed: false,
    cards: [{ name: "Troop of Ponies", price: "£3.99", type: "Creature — Horse", text: "Vigilance" }],
  },
};

function toolCall(args: unknown, overrides: Record<string, unknown> = {}) {
  return {
    event_type: "conversation.tool_call",
    conversation_id: "c123",
    properties: { name: "search_cards", arguments: args, tool_call_id: "call_1" },
    ...overrides,
  };
}

function deps(search: () => Promise<SearchResponse>) {
  return {
    search: vi.fn(search),
    send: vi.fn(),
    onSearchStart: vi.fn(),
    onListings: vi.fn(),
    onError: vi.fn(),
  };
}

describe("parseSearchArguments", () => {
  const testCases = [
    {
      description: "JSON string with every field",
      raw: JSON.stringify({ commander: "Radagast", role: "ramp", card_type: "creature", max_price: 5 }),
      expected: { commander: "Radagast", role: "ramp", card_type: "creature", max_price: 5 },
    },
    {
      description: "object instead of a string, unknown fields dropped",
      raw: { commander: " Radagast ", colour: "green" },
      expected: { commander: "Radagast" },
    },
    {
      description: "numeric string price",
      raw: JSON.stringify({ commander: "Radagast", max_price: "2.50" }),
      expected: { commander: "Radagast", max_price: 2.5 },
    },
    { description: "invalid JSON", raw: "{not json", expected: "The search arguments weren't valid JSON." },
    {
      description: "missing commander",
      raw: JSON.stringify({ role: "ramp" }),
      expected: "The search needs the customer's commander.",
    },
    { description: "null arguments", raw: null, expected: "The search arguments were missing." },
  ];
  for (const testCase of testCases) {
    it(testCase.description, () => {
      expect(parseSearchArguments(testCase.raw)).toEqual(testCase.expected);
    });
  }
});

describe("parseSearchToolCall", () => {
  const ignored = [
    { description: "an utterance", message: { event_type: "conversation.utterance", properties: {} } },
    { description: "another tool", message: toolCall("{}", { properties: { name: "end_call", tool_call_id: "x" } }) },
    { description: "no tool_call_id", message: toolCall("{}", { properties: { name: "search_cards" } }) },
  ];
  for (const testCase of ignored) {
    it(`ignores ${testCase.description}`, () => {
      expect(parseSearchToolCall(testCase.message)).toBeNull();
    });
  }

  it("parses a valid call", () => {
    expect(parseSearchToolCall(toolCall(JSON.stringify({ commander: "Radagast" })))).toEqual({
      valid: true,
      toolCallId: "call_1",
      conversationId: "c123",
      request: { commander: "Radagast" },
    });
  });
});

describe("handleSearchToolCall", () => {
  it("replies with pal_output and passes the full result to the panel", async () => {
    const d = deps(() => Promise.resolve(SEARCH_RESPONSE));
    const reply = await handleSearchToolCall(toolCall(JSON.stringify({ commander: "Radagast", role: "ramp" })), d);

    expect(d.search).toHaveBeenCalledWith({ commander: "Radagast", role: "ramp" });
    expect(d.onSearchStart).toHaveBeenCalledWith({ commander: "Radagast", role: "ramp" });
    expect(d.onListings).toHaveBeenCalledWith(SEARCH_RESPONSE.result);
    expect(reply).toEqual(toolResultMessage("c123", "call_1", SEARCH_RESPONSE.pal_output, "success"));
    expect(d.send).toHaveBeenCalledOnce();
    expect(d.send).toHaveBeenCalledWith(reply);
    expect(JSON.stringify(reply)).not.toContain("http");
  });

  const failures = [
    {
      description: "unknown commander (404)",
      error: new BackendError(404, "No card found on Scryfall matching 'zzz'"),
      expectedOutput:
        "No card found on Scryfall matching 'zzz'. Ask the customer to repeat or spell their commander's name.",
    },
    {
      description: "Scryfall down (502)",
      error: new BackendError(502, "Scryfall returned 503: Down"),
      expectedOutput: "The stock search failed: Scryfall returned 503: Down",
    },
    {
      description: "backend unreachable",
      error: new BackendError(0, "Couldn't reach the shop's backend. Is it running?"),
      expectedOutput: "The stock search failed: Couldn't reach the shop's backend. Is it running?",
    },
    {
      description: "unexpected exception",
      error: new TypeError("boom"),
      expectedOutput: "The stock search failed unexpectedly.",
    },
  ];
  for (const testCase of failures) {
    it(`replies with status error on ${testCase.description}`, async () => {
      const d = deps(() => Promise.reject(testCase.error));
      const reply = await handleSearchToolCall(toolCall(JSON.stringify({ commander: "x" })), d);

      expect(reply).toEqual(toolResultMessage("c123", "call_1", testCase.expectedOutput, "error"));
      expect(d.send).toHaveBeenCalledOnce();
      expect(d.onError).toHaveBeenCalledWith(testCase.expectedOutput);
      expect(d.onListings).not.toHaveBeenCalled();
    });
  }

  it("replies with status error for invalid arguments without searching", async () => {
    const d = deps(() => Promise.resolve(SEARCH_RESPONSE));
    const reply = await handleSearchToolCall(toolCall("{oops"), d);

    expect(reply?.properties.status).toBe("error");
    expect(reply?.properties.tool_call_id).toBe("call_1");
    expect(d.search).not.toHaveBeenCalled();
    expect(d.send).toHaveBeenCalledOnce();
  });

  it("ignores messages that aren't search_cards calls", async () => {
    const d = deps(() => Promise.resolve(SEARCH_RESPONSE));
    const reply = await handleSearchToolCall({ event_type: "conversation.utterance" }, d);

    expect(reply).toBeNull();
    expect(d.send).not.toHaveBeenCalled();
  });
});

describe("messageSize", () => {
  it("counts UTF-8 bytes", () => {
    expect(messageSize("£") - messageSize("")).toBe(2);
  });
});
