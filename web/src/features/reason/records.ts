// Baked answer records of the reason lane (spec 015, FR-015-41, FR-015-43): verify, then show as plain text.
//
// A record file is shown only when its SHA-256 matches the digest baked next to it and it satisfies the `vlm-record`
// contract; otherwise the panel shows "answers unavailable" and none of the file's text. Nothing here throws or rejects.
import { validate } from "~/contracts/validators/vlm-record.js";

export const UNAVAILABLE_TEXT = "answers unavailable";

export type RecordsResult =
  | { ok: true; doc: unknown }
  | { ok: false; reason: "sha256" | "json" | "schema"; message: string };

const HEX64 = /^[0-9a-f]{64}$/;

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function fail(reason: "sha256" | "json" | "schema", message: string): RecordsResult {
  return { ok: false, reason, message };
}

export async function verifyRecordFile(text: string, expectedSha256: string): Promise<RecordsResult> {
  try {
    if (typeof text !== "string" || typeof expectedSha256 !== "string" || !HEX64.test(expectedSha256)) {
      return fail("sha256", "the expected digest is not 64 lower-case hex characters");
    }
    if ((await sha256Hex(text)) !== expectedSha256) {
      return fail("sha256", "the digest of the record file does not match");
    }
    let doc: unknown;
    try {
      doc = JSON.parse(text);
    } catch {
      return fail("json", "the record file is not valid JSON");
    }
    if (doc === null || typeof doc !== "object" || Array.isArray(doc)) {
      return fail("schema", "the record file is not a JSON object");
    }
    if (Object.hasOwn(doc, "__proto__") || !validate(doc)) {
      return fail("schema", "the record file does not satisfy the vlm-record contract");
    }
    return { ok: true, doc };
  } catch {
    return fail("json", "the record file could not be verified");
  }
}

type RecordLike = {
  question?: unknown;
  output?: unknown;
  parsed?: unknown;
  truth?: unknown;
  correct?: unknown;
};

/** The strings the panel renders (text nodes only): the notices, then for every record its question, full output,
 * parsed answer, truth and "correct" or "incorrect", so wrong answers are shown as well as right ones. */
export function panelText(result: RecordsResult): string[] {
  if (!result.ok) return [UNAVAILABLE_TEXT];
  const doc = result.doc as { notices: { cosmos: string; honesty: string }; records: RecordLike[] };
  const out = [doc.notices.cosmos, doc.notices.honesty];
  for (const r of doc.records) {
    for (const field of [r.question, r.output, r.parsed, r.truth]) {
      if (typeof field === "string") out.push(field);
    }
    out.push(r.correct === true ? "correct" : "incorrect");
  }
  return out;
}
