import type { SearchRequest, SearchResult } from "./search";

/** What the listings panel is showing. */
export type ListingsState =
  | { status: "idle" }
  | { status: "searching"; request: SearchRequest }
  | { status: "results"; result: SearchResult }
  | { status: "error"; message: string };
