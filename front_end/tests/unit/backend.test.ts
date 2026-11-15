import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BackendError,
  createConversation,
  endConversation,
  searchCards,
} from "../../src/api/backend";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("backend client", () => {
  it("searchCards posts the request as JSON", async () => {
    const fetchMock = mockFetch(jsonResponse(200, { result: {}, pal_output: {} }));
    await searchCards({ commander: "Radagast", role: "ramp" });

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commander: "Radagast", role: "ramp" }),
    });
  });

  it("createConversation returns the id and URL", async () => {
    const conversation = { conversation_id: "c1", conversation_url: "https://tavus.daily.co/c1" };
    mockFetch(jsonResponse(200, conversation));
    await expect(createConversation()).resolves.toEqual(conversation);
  });

  it("endConversation handles 204 and encodes the id", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));
    await expect(endConversation("c 1")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/conversations/c%201/end");
  });

  const errorCases = [
    {
      description: "FastAPI detail string",
      response: jsonResponse(404, { detail: "No card found on Scryfall matching 'zzz'" }),
      expectedStatus: 404,
      expectedMessage: "No card found on Scryfall matching 'zzz'",
    },
    {
      description: "validation error list",
      response: jsonResponse(422, { detail: [{ msg: "Input should be less than or equal to 10" }] }),
      expectedStatus: 422,
      expectedMessage: "Invalid search: Input should be less than or equal to 10",
    },
    {
      description: "non-JSON error body",
      response: new Response("Internal Server Error", { status: 500, statusText: "Internal Server Error" }),
      expectedStatus: 500,
      expectedMessage: "500 Internal Server Error",
    },
    {
      description: "network failure",
      response: new TypeError("Failed to fetch"),
      expectedStatus: 0,
      expectedMessage: "Couldn't reach the shop's backend. Is it running?",
    },
  ];
  for (const testCase of errorCases) {
    it(`throws BackendError for ${testCase.description}`, async () => {
      mockFetch(testCase.response);
      const error = await searchCards({ commander: "x" }).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(BackendError);
      expect((error as BackendError).status).toBe(testCase.expectedStatus);
      expect((error as BackendError).message).toBe(testCase.expectedMessage);
    });
  }
});
