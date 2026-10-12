// T-015-062 [red] · FR-015-43: hostile baked answer records in the reason panel.
//
// Spec: specs/015-vlm/spec.md FR-015-43 ("If a baked record file fails its SHA-256 or its schema, then the panel shows
// "answers unavailable" and renders none of its text"); FR-015-41 (the panel shows wrong answers as well as right ones, with
// "Built on NVIDIA Cosmos" and "Zero-shot 2B VLM; not a safety system."); plan.md test strategy row FR-015-43
// ("corrupted record fixtures", Vitest).
//
// Expected module API, `~/features/reason/records` (pure functions, no DOM):
//   export const UNAVAILABLE_TEXT = "answers unavailable";
//   export type RecordsResult =
//     | { ok: true; doc: unknown }                                   // the parsed, verified `vlm-record` document
//     | { ok: false; reason: "sha256" | "json" | "schema"; message: string };
//   export function verifyRecordFile(text: string, expectedSha256: string): Promise<RecordsResult>;
//       - never throws and never rejects, for any text and any digest string;
//       - the digest is the lower-case hex SHA-256 of the UTF-8 bytes of `text`; an `expectedSha256` that is not 64 lower-case hex
//         characters is a "sha256" failure; a digest mismatch is a "sha256" failure and is reported before the text is parsed;
//       - then the text is parsed as JSON ("json" failure) and validated against `contracts/vlm-record.schema.json`
//         ("schema" failure: every rule of the contract, including the notices, the display-only class of Cosmos records and the
//         sampling object); a document with a `__proto__` key is a failure and must not pollute `Object.prototype`.
//   export function panelText(result: RecordsResult): string[];
//       - the strings the panel renders: for a failure exactly [UNAVAILABLE_TEXT] (no record text, no message, no field of the file);
//       - for a verified document: the two notices, and for every record its question, its full output, its parsed answer, its truth
//         and the word "correct" or "incorrect" (so wrong answers are shown as well as right ones); text is plain, never markup.
//
// Oracles: the spec's own corpus (`specs/015-vlm/contracts/examples/vlm-record.valid*.json` and `vlm-record.hostile-*.json`, whose
// hostile members each violate the schema); SHA-256 computed with node:crypto in the test; a canary string planted in a corrupted file.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { panelText, UNAVAILABLE_TEXT, verifyRecordFile } from "~/features/reason/records";

// vitest runs from `web/` (package script `test`): the spec corpus lies one level up
const EXAMPLES = `${resolve(process.cwd(), "../specs/015-vlm/contracts/examples")}/`;
const sha = (t: string) => createHash("sha256").update(t, "utf8").digest("hex");
const read = (name: string) => readFileSync(`${EXAMPLES}${name}`, "utf8");
const VALID = read("vlm-record.valid.json");
const HOSTILE = readdirSync(EXAMPLES).filter((f) => f.startsWith("vlm-record.hostile-"));
const CANARY = "PWNED-CANARY-7f3a";

describe("hostile baked answer records (FR-015-43)", () => {
  it("FR-015-43 · the spec corpus has the hostile files this test relies on", () => {
    expect(HOSTILE.length).toBeGreaterThanOrEqual(14);
  });

  it("FR-015-43 · a valid file with its own digest is verified and shows the notices and the right and wrong answers", async () => {
    const r = await verifyRecordFile(VALID, sha(VALID));
    expect(r.ok).toBe(true);
    const text = panelText(r).join("\n");
    expect(text).toContain("Built on NVIDIA Cosmos");
    expect(text).toContain("Zero-shot 2B VLM; not a safety system.");
    expect(text).not.toContain(UNAVAILABLE_TEXT);
    const doc = JSON.parse(VALID) as { records: { question: string; output: string; correct: boolean }[] };
    for (const rec of doc.records) {
      expect(text).toContain(rec.question);
      expect(text).toContain(rec.output);
    }
    expect(doc.records.some((x) => x.correct)).toBe(true);
    expect(doc.records.some((x) => !x.correct)).toBe(true);
    expect(text).toMatch(/\bcorrect\b/);
    expect(text).toMatch(/\bincorrect\b/);
  });

  it("FR-015-43 · the other valid example (BF16 and Qwen records) is verified too", async () => {
    const t = read("vlm-record.valid-bf16-qwen.json");
    expect((await verifyRecordFile(t, sha(t))).ok).toBe(true);
  });

  it.each([
    ["all zeros", "0".repeat(64)],
    ["upper case digest of the right file", sha(VALID).toUpperCase()],
    ["digest of another text", sha(`${VALID} `)],
    ["too short", sha(VALID).slice(0, 63)],
    ["too long", `${sha(VALID)}0`],
    ["empty", ""],
    ["not hex", "z".repeat(64)],
    ["whitespace around the right digest", ` ${sha(VALID)} `],
  ])(
    "FR-015-43 · a wrong or malformed digest (%s) shows only 'answers unavailable' and none of the file's text",
    async (_name, digest) => {
      const r = await verifyRecordFile(VALID, digest);
      expect(r).toMatchObject({ ok: false, reason: "sha256" });
      expect(panelText(r)).toEqual([UNAVAILABLE_TEXT]);
      const doc = JSON.parse(VALID) as { records: { question: string; output: string }[] };
      const all = panelText(r).join("\n");
      for (const rec of doc.records) {
        expect(all).not.toContain(rec.question);
        expect(all).not.toContain(rec.output);
      }
    },
  );

  it("FR-015-43 · one changed character with the original digest is a sha256 failure and renders none of the planted text", async () => {
    const tampered = VALID.replace('"<answer>no</answer>"', `"${CANARY}"`);
    expect(tampered).not.toBe(VALID);
    const r = await verifyRecordFile(tampered, sha(VALID));
    expect(r).toMatchObject({ ok: false, reason: "sha256" });
    const all = panelText(r).join("\n");
    expect(all).toBe(UNAVAILABLE_TEXT);
    expect(all).not.toContain(CANARY);
  });

  it.each(HOSTILE)(
    "FR-015-43 · the hostile corpus file %s fails its schema even with a matching digest and renders none of its text",
    async (name) => {
      const t = read(name);
      const r = await verifyRecordFile(t, sha(t));
      expect(r.ok).toBe(false);
      if (r.ok) return;
      expect(["schema", "json"]).toContain(r.reason);
      expect(panelText(r)).toEqual([UNAVAILABLE_TEXT]);
    },
  );

  it("FR-015-43 · a schema failure never leaks a field of the file into the panel (canary in a rejected record)", async () => {
    const doc = JSON.parse(VALID) as { records: Record<string, unknown>[] };
    doc.records[0] = { ...doc.records[0], question: CANARY, output: CANARY, licence_class: "own" }; // a Cosmos record that is not display-only
    const t = JSON.stringify(doc);
    const r = await verifyRecordFile(t, sha(t));
    expect(r).toMatchObject({ ok: false, reason: "schema" });
    expect(panelText(r).join("\n")).not.toContain(CANARY);
    expect(panelText(r)).toEqual([UNAVAILABLE_TEXT]);
  });

  it.each([
    ["empty text", ""],
    ["a lone brace", "{"],
    ["null", "null"],
    ["an array", "[]"],
    ["a number", "42"],
    ["a string", '"records"'],
    ["NaN", '{"records": NaN}'],
    ["a byte order mark", `﻿${VALID}`],
    ["trailing garbage", `${VALID} xyz`],
    ["an empty object", "{}"],
    ["truncated", VALID.slice(0, Math.floor(VALID.length / 2))],
    ["control characters", `{"records": "\u0000\u0001"}`],
    ["deep nesting", `${"[".repeat(5000)}${"]".repeat(5000)}`],
    ["a huge file of one string", `{"records": "${"x".repeat(5_000_000)}"}`],
    ["unicode", '{"records": "é中😀"}'],
  ])("FR-015-43 · %s is refused with the unavailable text and without throwing", async (_name, text) => {
    const r = await verifyRecordFile(text, sha(text));
    expect(r.ok).toBe(false);
    expect(panelText(r)).toEqual([UNAVAILABLE_TEXT]);
  });

  it("FR-015-43 · a __proto__ key does not pollute Object.prototype and is a schema failure", async () => {
    const t = VALID.replace("{", '{"__proto__": {"polluted": "yes"},');
    const r = await verifyRecordFile(t, sha(t));
    expect(r.ok).toBe(false);
    expect(({} as { polluted?: string }).polluted).toBeUndefined();
  });

  it("FR-015-43 · markup inside a verified record is plain text, never markup", async () => {
    const doc = JSON.parse(VALID) as { records: Record<string, unknown>[] };
    const payload = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
    doc.records[0] = { ...doc.records[0], output: payload };
    const t = JSON.stringify(doc);
    const r = await verifyRecordFile(t, sha(t));
    expect(r.ok).toBe(true);
    expect(panelText(r)).toContain(payload); // returned as text: the panel renders text nodes only
  });

  it("FR-015-43 · the unavailable text is exactly 'answers unavailable'", () => {
    expect(UNAVAILABLE_TEXT).toBe("answers unavailable");
  });
});
