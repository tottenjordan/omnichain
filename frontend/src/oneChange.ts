// Client-side mirror of the backend's one-change-per-turn heuristic
// (backend/src/omnichain/api/generation.py::_enforce_one_change) so the Dailies
// chat can block a multi-change edit before it is ever sent.

const CONNECTORS = /\s+and then\s+|\s+then\s+|\s+also\s+|\s+as well as\s+|\s+plus\s+|;|\s+and\s+/i;
const MIN_CLAUSE_WORDS = 3;

const wordCount = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

/** Returns true when the instruction appears to bundle more than one change. */
export function looksLikeMultipleChanges(instruction: string): boolean {
  const text = instruction.trim();
  if (!text) return false;
  const sentences = text.split(/[.!?]+/).filter((s) => s.trim().length > 0);
  const clauses = text
    .replace(/\.+$/, "")
    .split(CONNECTORS)
    .filter((c) => wordCount(c) >= MIN_CLAUSE_WORDS);
  return sentences.length > 1 || clauses.length > 1;
}
