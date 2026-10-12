// T-019-093 [red] · FR-019-47: the studio index loader rejects an index larger than 1,000,000 bytes before parsing it. Python half (CI size check and cap table):
// tests/unit/test_t_019_093_studio_index_cap.py.
//
// Expected API: `~/studio/loadIndex` (web/src/studio/loadIndex.ts):
//   STUDIO_INDEX_CAP_BYTES = 1_000_000
//   class StudioIndexError extends Error { code: "too-large" | "malformed"; bytes?: number }
//   parseStudioIndex(raw: string | Uint8Array): unknown      checks the byte length first (a string counts as its UTF-8 encoding), throws StudioIndexError
//                                                            "too-large" (message names the size and the cap) without calling JSON.parse, then parses
//                                                            strictly (invalid JSON, NaN and Infinity literals: "malformed")
// Oracle: byte arithmetic (cap 1,000,000; the boundary documents hold 1,000,000 and 1,000,001 bytes; two-byte characters weigh 2) and the valid example of the
// studio index schema (specs/019-web-studio/contracts/examples/studio-index.valid.json), padded with trailing JSON whitespace to the boundary sizes.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { parseStudioIndex, STUDIO_INDEX_CAP_BYTES, StudioIndexError } from "~/studio/loadIndex";

const EXAMPLE = readFileSync(
  resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../../specs/019-web-studio/contracts/examples/studio-index.valid.json",
  ),
  "utf8",
);
const exampleBytes = new TextEncoder().encode(EXAMPLE);
const padded = (size: number): Uint8Array => {
  const out = new Uint8Array(size).fill(0x20);
  out.set(exampleBytes, 0);
  return out;
};

describe("cap of the studio index (FR-019-47)", () => {
  it("FR-019-47 · the cap is 1,000,000 bytes", () => {
    expect(STUDIO_INDEX_CAP_BYTES).toBe(1_000_000);
  });

  it("FR-019-47 · a valid index of exactly 1,000,000 bytes is accepted and parses to the example", () => {
    expect(exampleBytes.length).toBeLessThan(1_000_000);
    expect(parseStudioIndex(padded(1_000_000))).toEqual(JSON.parse(EXAMPLE));
  });

  it("FR-019-47 · the same index with one more byte is rejected as too-large, naming the size and the cap", () => {
    let caught: unknown;
    try {
      parseStudioIndex(padded(1_000_001));
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(StudioIndexError);
    const err = caught as StudioIndexError;
    expect(err.code).toBe("too-large");
    expect(err.message).toContain("1000001");
    expect(err.message).toMatch(/1[,.  ]?000[,.  ]?000/);
  });

  it("FR-019-47 · an oversized index is never parsed: JSON.parse is not called", () => {
    const spy = vi.spyOn(JSON, "parse");
    expect(() => parseStudioIndex(padded(1_000_001))).toThrow(StudioIndexError);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("FR-019-47 · an oversized document that is not even JSON is still reported as too-large (the size is checked first)", () => {
    const garbage = new Uint8Array(1_000_001).fill(0xff);
    expect(() => parseStudioIndex(garbage)).toThrow(expect.objectContaining({ code: "too-large" }));
  });

  it("FR-019-47 · a string is measured in UTF-8 bytes, not characters", () => {
    const twoByte = `"${"é".repeat(499_999)}"`; // 1,000,000 bytes, 500,001 characters
    expect(new TextEncoder().encode(twoByte).length).toBe(1_000_000);
    expect(parseStudioIndex(twoByte)).toBe("é".repeat(499_999));
    const over = `${twoByte}  `; // 1,000,002 bytes
    expect(() => parseStudioIndex(over)).toThrow(expect.objectContaining({ code: "too-large" }));
  });

  it("FR-019-47 · a string of 600,000 ASCII characters plus the example is below the cap and accepted as a string", () => {
    const text = EXAMPLE + " ".repeat(600_000);
    expect(parseStudioIndex(text)).toEqual(JSON.parse(EXAMPLE));
  });

  it("FR-019-47 · malformed JSON below the cap is a 'malformed' error, never a bare SyntaxError", () => {
    for (const raw of ["", "{", '{"a": NaN}', '{"a": Infinity}', "undefined", "\u0000", "[1,]"]) {
      expect(() => parseStudioIndex(raw), JSON.stringify(raw)).toThrow(
        expect.objectContaining({ code: "malformed" }),
      );
    }
  });
});
