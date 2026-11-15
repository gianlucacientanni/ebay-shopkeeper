/**
 * Options for the dev simulator's form. These mirror the search tool's enums, which the
 * backend generates from CardType (back_end/common/models.py) and ROLE_FILTERS
 * (back_end/search/query.py). Keep them in step if either changes.
 */

export const CARD_TYPES = [
  "creature",
  "instant",
  "sorcery",
  "artifact",
  "enchantment",
  "planeswalker",
  "land",
  "battle",
] as const;

export const ROLES = [
  "ramp",
  "mana_rock",
  "removal",
  "board_wipe",
  "counterspell",
  "card_draw",
  "card_advantage",
  "tutor",
  "protection",
  "recursion",
  "reanimation",
  "tokens",
  "lifegain",
  "evasion",
  "sacrifice_outlet",
  "anthem",
] as const;
