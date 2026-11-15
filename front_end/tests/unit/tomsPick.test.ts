import { describe, expect, it } from "vitest";
import { findMentionedCard } from "../../src/lib/tomsPick";
import type { Candidate } from "../../src/types/search";

function candidate(name: string): Candidate {
  return {
    name,
    title: name,
    price: "1.99",
    finish: "NONFOIL",
    listing_url: `https://www.ebay.co.uk/itm/${encodeURIComponent(name)}`,
    image_url: null,
    type_line: "Creature",
    mana_cost: "{G}",
    oracle_text: "",
    other_finishes: [],
  };
}

const CANDIDATES = [
  candidate("Springleaf Drum"),
  candidate("Troop"),
  candidate("Troop of Ponies"),
  candidate("Studious First-Year // Rampant Growth"),
];

describe("findMentionedCard", () => {
  const testCases = [
    {
      description: "exact name",
      utterance: "I'd go with Springleaf Drum, it's only £1.99.",
      expected: "Springleaf Drum",
    },
    {
      description: "case and punctuation insensitive",
      utterance: "honestly? SPRINGLEAF DRUM!",
      expected: "Springleaf Drum",
    },
    {
      description: "longest matching name wins",
      utterance: "Troop of Ponies is the one for you.",
      expected: "Troop of Ponies",
    },
    {
      description: "double-faced card by its front face",
      utterance: "Studious First-Year gets you a land early.",
      expected: "Studious First-Year // Rampant Growth",
    },
    {
      description: "no card mentioned",
      utterance: "Let me have a look at what's on the shelves.",
      expected: null,
    },
    {
      description: "name only as part of another word",
      utterance: "The troopers will love this.",
      expected: null,
    },
  ];
  for (const testCase of testCases) {
    it(testCase.description, () => {
      expect(findMentionedCard(testCase.utterance, CANDIDATES)).toBe(testCase.expected);
    });
  }
});
