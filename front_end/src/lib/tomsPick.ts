/**
 * Work out which listed card Tom recommends from what he says, so the listings panel can
 * highlight it. Tom picks one card from up to 10 results and names it out loud.
 */
import type { Candidate } from "../types/search";

/** Lower-case, collapse whitespace and drop punctuation so names compare loosely. */
export function normaliseText(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The front face of a double-faced card name ("A // B" -> "A"). */
export function frontFace(name: string): string {
  return name.split("//")[0].trim();
}

/**
 * Find the card Tom names in an utterance. When several cards are mentioned, the longest
 * name wins (so "Troop of Ponies" beats a card called "Troop"), then the first listed.
 *
 * @returns the name of the mentioned candidate, or null if none is mentioned
 */
export function findMentionedCard(utterance: string, candidates: Candidate[]): string | null {
  const spoken = ` ${normaliseText(utterance)} `;
  const mentioned = candidates.filter((candidate) => {
    const name = normaliseText(frontFace(candidate.name));
    return name.length > 0 && spoken.includes(` ${name} `);
  });
  if (mentioned.length === 0) {
    return null;
  }
  return mentioned.reduce((best, candidate) =>
    frontFace(candidate.name).length > frontFace(best.name).length ? candidate : best,
  ).name;
}
