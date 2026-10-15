// T-017-015 [red] · FR-017-11: hostile meta-model input rows in the web engine `meta-model` (the Python and ONNX Runtime
// sides are tests/pipeline/test_t_017_015_meta_model_guards.py).
//
// Spec: specs/017-planning-survey/spec.md FR-017-11: a row whose width or order differs from DC-011-02, or that holds a
// non-finite value, makes the web engine show "no answer - <reason>" (an em dash in the label) and return no output.
//
// Oracles: the 15 input names of DC-011-02 in their fixed order (same names and order as the Python side and the spec 011
// valid meta-model example); hand-written invalid rows (width 14 and 16, NaN, +/-Infinity, strings, null, undefined, a
// non-array, two columns swapped); a spy model that counts its calls, so "returns no output" and "never runs the graph"
// are observable.
//
// Expected API (module `web/src/cases/d2/metaModelGuards.ts`):
//   export const INPUT_NAMES: readonly string[]                       // 15 names, fixed order
//   export type GuardResult = { ok: true } | { ok: false; reason: string }
//   export function guardMetaModelRow(row: unknown, names?: readonly string[]): GuardResult
//     row: an array or typed array of 15 finite numbers; `names` (optional): the column names of the caller, which
//     must equal INPUT_NAMES exactly (order included). The reason contains "width", "order", "finite" or "numbers".
//   export function noAnswerLabel(reason: string): string             // "no answer — " + reason
//   export interface MetaModelRunner { run(row: Float32Array): Float32Array }
//   export function answerMetaModel(model: MetaModelRunner, row: unknown, names?: readonly string[]):
//     { answer: number[]; label: null } | { answer: null; label: string }
//     a valid row gives the three outputs in order (kWh/t, t/h, USD/t) and label null; an invalid row gives
//     answer null, the label noAnswerLabel(reason), and never calls model.run.
import { describe, expect, it, vi } from "vitest";
import { answerMetaModel, guardMetaModelRow, INPUT_NAMES, noAnswerLabel } from "./metaModelGuards";

const EM_DASH = "—";
const VALID = Array.from({ length: 15 }, (_, i) => 1 + i / 10);

describe("input description", () => {
  it("FR-017-11 · the input vector has 15 distinct names in a fixed order", () => {
    expect(INPUT_NAMES).toHaveLength(15);
    expect(new Set(INPUT_NAMES).size).toBe(15);
    expect(INPUT_NAMES[0]).toBe("burden_m");
    expect(INPUT_NAMES[14]).toBe("consumables_usd_per_t");
  });
});

describe("guardMetaModelRow", () => {
  it("FR-017-11 · a row of 15 finite numbers passes, as an array or a typed array", () => {
    expect(guardMetaModelRow(VALID)).toEqual({ ok: true });
    expect(guardMetaModelRow(Float32Array.from(VALID))).toEqual({ ok: true });
    expect(guardMetaModelRow(VALID, INPUT_NAMES)).toEqual({ ok: true });
  });

  it.each([
    ["14 numbers", VALID.slice(0, 14)],
    ["16 numbers", [...VALID, 1]],
    ["an empty row", []],
  ])("FR-017-11 · %s is refused with a width reason", (_label, row) => {
    const result = guardMetaModelRow(row);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toContain("width");
  });

  it.each([
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["-Infinity", Number.NEGATIVE_INFINITY],
  ])("FR-017-11 · %s anywhere in the row is refused with a finite reason", (_label, bad) => {
    for (const at of [0, 7, 14]) {
      const row = [...VALID];
      row[at] = bad;
      const result = guardMetaModelRow(row);
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.reason).toContain("finite");
    }
  });

  it.each([
    ["a string cell", [...VALID.slice(0, 14), "5"]],
    ["a null cell", [...VALID.slice(0, 14), null]],
    ["an undefined cell", [...VALID.slice(0, 14), undefined]],
    ["a boolean cell", [...VALID.slice(0, 14), true]],
  ])("FR-017-11 · %s is refused, never coerced", (_label, row) => {
    const result = guardMetaModelRow(row);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/numbers|finite/);
  });

  it.each([
    ["a string", "1,2,3"],
    ["a number", 15],
    ["null", null],
    ["undefined", undefined],
    ["an object", { length: 15 }],
  ])("FR-017-11 · %s is not a row and is refused", (_label, row) => {
    expect(guardMetaModelRow(row).ok).toBe(false);
  });

  it("FR-017-11 · column names in another order are refused with an order reason", () => {
    const swapped = [...INPUT_NAMES];
    [swapped[0], swapped[1]] = [swapped[1], swapped[0]];
    const result = guardMetaModelRow(VALID, swapped);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toContain("order");
    expect(guardMetaModelRow(VALID, INPUT_NAMES.slice(0, 14)).ok).toBe(false);
    expect(guardMetaModelRow(VALID, [...INPUT_NAMES.slice(0, 14), "unknown_column"]).ok).toBe(false);
  });
});

describe("answerMetaModel", () => {
  it("FR-017-11 · the label is 'no answer', an em dash and the reason", () => {
    expect(noAnswerLabel("width 14, expected 15")).toBe(`no answer ${EM_DASH} width 14, expected 15`);
  });

  it("FR-017-11 · a valid row runs the model once and returns its three outputs", () => {
    const run = vi.fn((_row: Float32Array) => Float32Array.from([8.5, 1200, 4.25]));
    const out = answerMetaModel({ run }, VALID, INPUT_NAMES);
    expect(run).toHaveBeenCalledTimes(1);
    expect(out).toEqual({ answer: [8.5, 1200, 4.25], label: null });
  });

  it.each([
    ["a short row", VALID.slice(0, 14)],
    ["a NaN", [Number.NaN, ...VALID.slice(1)]],
    ["a string", ["x", ...VALID.slice(1)]],
    ["not an array", "abc"],
  ])("FR-017-11 · %s gives no answer, a no-answer label and no model call", (_label, row) => {
    const run = vi.fn((_r: Float32Array) => Float32Array.from([1, 2, 3]));
    const out = answerMetaModel({ run }, row);
    expect(run).not.toHaveBeenCalled();
    expect(out.answer).toBeNull();
    expect(out.label).toMatch(new RegExp(`^no answer ${EM_DASH} .+`));
  });

  it("FR-017-11 · swapped column names give no answer even for a well-formed numeric row", () => {
    const run = vi.fn((_r: Float32Array) => Float32Array.from([1, 2, 3]));
    const names = [...INPUT_NAMES];
    [names[3], names[4]] = [names[4], names[3]];
    const out = answerMetaModel({ run }, VALID, names);
    expect(run).not.toHaveBeenCalled();
    expect(out.answer).toBeNull();
  });
});
