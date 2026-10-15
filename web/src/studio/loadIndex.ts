// The studio index loader (DC-019-03, FR-019-47): the byte cap is checked before anything is parsed.

export const STUDIO_INDEX_CAP_BYTES = 1_000_000;

export class StudioIndexError extends Error {
  readonly code: "too-large" | "malformed";
  readonly bytes?: number;

  constructor(code: "too-large" | "malformed", message: string, bytes?: number) {
    super(message);
    this.name = "StudioIndexError";
    this.code = code;
    this.bytes = bytes;
  }
}

const encoder = new TextEncoder();

/** UTF-8 length of the document: the byte length of an array, the encoded length of a string. */
function byteLength(raw: string | Uint8Array): number {
  if (typeof raw !== "string") return raw.byteLength;
  // Every UTF-16 unit takes at most 3 bytes in UTF-8, so a string shorter than a third of the cap is within it.
  if (raw.length * 3 <= STUDIO_INDEX_CAP_BYTES) return raw.length * 3;
  return encoder.encode(raw).byteLength;
}

/** Parses a studio index; one over 1,000,000 bytes is rejected without calling JSON.parse, invalid JSON is "malformed". */
export function parseStudioIndex(raw: string | Uint8Array): unknown {
  const bytes = byteLength(raw);
  if (bytes > STUDIO_INDEX_CAP_BYTES) {
    const exact = typeof raw === "string" ? encoder.encode(raw).byteLength : bytes;
    if (exact > STUDIO_INDEX_CAP_BYTES)
      throw new StudioIndexError(
        "too-large",
        `the studio index is ${exact} bytes, above the cap of ${STUDIO_INDEX_CAP_BYTES.toLocaleString("en-US")} bytes`,
        exact,
      );
  }
  const text = typeof raw === "string" ? raw : new TextDecoder().decode(raw);
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new StudioIndexError(
      "malformed",
      `the studio index is not valid JSON: ${(error as Error).message}`,
    );
  }
}
