/**
 * TypeScript mirrors of the backend's search models (back_end/common/models.py).
 * Keep these in step with the pydantic models when either side changes.
 */

/** Arguments of the PAL's search_cards tool, sent to POST /api/search. */
export interface SearchRequest {
  commander: string;
  card_type?: string;
  role?: string;
  max_price?: number;
  limit?: number;
}

/** An in-stock card with its eBay listing. Decimal prices arrive as strings. */
export interface Candidate {
  name: string;
  title: string;
  price: string | null;
  finish: string;
  listing_url: string;
  image_url: string | null;
  type_line: string;
  mana_cost: string;
  oracle_text: string;
  other_finishes: string[];
}

export interface Commander {
  name: string;
  colour_identity: string;
  type_line: string;
  oracle_text: string;
}

export interface SearchResult {
  query: string;
  commander: Commander;
  inspected: number;
  in_stock_count: number;
  relaxed: boolean;
  candidates: Candidate[];
}

/** POST /api/search response: the full result for the panel, the compact output for the PAL. */
export interface SearchResponse {
  result: SearchResult;
  pal_output: Record<string, unknown>;
}

/** POST /api/conversations response. */
export interface ConversationInfo {
  conversation_id: string;
  conversation_url: string;
}
