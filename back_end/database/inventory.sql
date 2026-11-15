-- Local snapshot of the Arcanum Collectibles eBay listings, used by the shopkeeper.
-- One row per active eBay listing (offer). Populated by back_end/database/backfill_inventory.py.
CREATE TABLE IF NOT EXISTS inventory (
  id               TEXT PRIMARY KEY,      -- UUID (deterministic: uuid5 of the eBay SKU)
  sku              TEXT NOT NULL UNIQUE,  -- eBay SKU: NAME-FINISH-SETCODE-COLLECTORNUMBER
  name             TEXT NOT NULL,         -- card name (front face for double-faced cards)
  scryfall_id      TEXT,
  scryfall_url     TEXT,
  colour_identity  TEXT NOT NULL,         -- WUBRG-ordered letters, e.g. 'WU'; colourless is 'C'
  image_url        TEXT,
  listing_url      TEXT NOT NULL,
  price            NUMERIC,               -- GBP
  quantity         INTEGER
);

CREATE INDEX IF NOT EXISTS idx_inventory_scryfall_id ON inventory (scryfall_id);
CREATE INDEX IF NOT EXISTS idx_inventory_name ON inventory (name);
