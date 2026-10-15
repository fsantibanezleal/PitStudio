// Literal, accent- and case-insensitive search over the knowledge tables (FR-020-35, FR-020-41, P-020-32, NFR-020-08).
// No regular expression is ever built from a query; matching is substring matching on normalised text.

export const MAX_QUERY = 2000;

// biome-ignore lint/suspicious/noControlCharactersInRegex: the fast path tests for plain ASCII
const ASCII = /^[\u0000-\u007f]*$/;
const COMBINING = /[̀-ͯ]/g;

/** Lower case with accents removed (Unicode NFD without the combining marks U+0300..U+036F). */
export function normalise(text: string): string {
  if (ASCII.test(text)) return text.toLowerCase();
  return text.toLowerCase().normalize("NFD").replace(COMBINING, "");
}

/** The first 2,000 characters (UTF-16 units) of a query. */
export function truncateQuery(query: string): string {
  return query.length > MAX_QUERY ? query.slice(0, MAX_QUERY) : query;
}

/** The rows, in order, one of whose fields contains the query as a literal substring after normalisation. */
export function searchRows<T>(rows: T[], query: string, fields: (row: T) => string[]): T[] {
  const q = truncateQuery(query);
  if (q.trim() === "") return rows;
  const needle = normalise(q);
  return rows.filter((row) => fields(row).some((f) => normalise(f).includes(needle)));
}

/**
 * The text cut into segments in which exactly the (normalised, literal) occurrences of the query are `match: true`.
 * Positions of the normalised text are mapped back to the original, so the segments concatenate to the input.
 */
export function highlight(text: string, query: string): Array<{ text: string; match: boolean }> {
  const q = truncateQuery(query);
  if (q.trim() === "" || text === "") return [{ text, match: false }];
  const needle = normalise(q);
  if (needle === "") return [{ text, match: false }];
  // Normalise code point by code point, remembering where each normalised unit starts and ends in the original.
  let norm = "";
  const start: number[] = [];
  const end: number[] = [];
  let i = 0;
  for (const ch of text) {
    const piece = normalise(ch);
    for (let k = 0; k < piece.length; k++) {
      start.push(i);
      end.push(i + ch.length);
    }
    if (piece.length === 0 && end.length > 0) end[end.length - 1] = i + ch.length;
    norm += piece;
    i += ch.length;
  }
  const out: Array<{ text: string; match: boolean }> = [];
  let from = 0;
  let pos = norm.indexOf(needle);
  while (pos !== -1) {
    const s = start[pos] as number;
    const e = end[pos + needle.length - 1] as number;
    if (s >= from) {
      if (s > from) out.push({ text: text.slice(from, s), match: false });
      out.push({ text: text.slice(s, e), match: true });
      from = e;
    }
    pos = norm.indexOf(needle, pos + Math.max(needle.length, 1));
  }
  if (from < text.length) out.push({ text: text.slice(from), match: false });
  return out;
}
