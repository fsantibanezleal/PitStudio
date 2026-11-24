// Training envelopes of the 011 surrogates and the decisions that follow from them (DC-011-02, FR-011-11, FR-011-39, NFR-011-02,
// NFR-011-03). Pure functions, nothing here throws: a value that is not a finite number is outside every range.
//
// The ranges are read from the `training_envelope` of the contract examples (`specs/011-surrogates/contracts/examples/surrogate-io.valid.json`
// and `surrogate-io.valid-fno.json`), so a changed envelope reaches the page with the contract and cannot drift;
// `envelope.test.ts` compares them with those files.
import fnoExample from "../../../../specs/011-surrogates/contracts/examples/surrogate-io.valid-fno.json";
import gnsExample from "../../../../specs/011-surrogates/contracts/examples/surrogate-io.valid.json";

export interface Range {
  min: number;
  max: number;
}

export type GnsFamily = "column-collapse" | "pile-formation" | "dump-over-crest";

export const GNS_FAMILIES: readonly GnsFamily[] = ["column-collapse", "pile-formation", "dump-over-crest"];

const rangeOf = (envelope: Readonly<Record<string, Range>>, name: string): Range => {
  const r = envelope[name] as Range;
  return { min: r.min, max: r.max };
};
const gnsRanges = (names: readonly string[]): Record<string, Range> =>
  Object.fromEntries(names.map((n) => [n, rangeOf(gnsExample.training_envelope, n)]));

/** The GNS training envelope per family (the dataset's design envelope), from the DC-011-02 example. */
export const GNS_ENVELOPE: Readonly<Record<GnsFamily, Readonly<Record<string, Range>>>> = {
  "column-collapse": gnsRanges(["column_aspect_ratio", "column_width"]),
  "pile-formation": gnsRanges(["pour_height", "pour_rate"]),
  "dump-over-crest": gnsRanges(["crest_height", "dump_rate"]),
};

/** The FNO training envelope of C2 (DC-011-02) and the C3 wind controls (DC-011-02, field dataset of the dust case). */
export const FNO_ENVELOPE: Readonly<Record<string, Range>> = {
  ...Object.fromEntries(
    ["breach_row", "breach_col", "release_volume", "yield_stress", "plastic_viscosity"].map((n) => [
      n,
      rangeOf(fnoExample.training_envelope, n),
    ]),
  ),
  wind_speed: { min: 0, max: 50 },
  wind_direction: { min: 0, max: 359 },
};

/** A value is inside a range when it is finite and between the limits, the limits themselves included. */
export function insideRange(value: number, range: Range): boolean {
  return typeof value === "number" && Number.isFinite(value) && value >= range.min && value <= range.max;
}

/** Names of the parameters of `values` that lie outside `envelope` (a parameter without a value counts as outside). */
export function outsideParameters(
  values: Readonly<Record<string, number>>,
  envelope: Readonly<Record<string, Range>>,
): string[] {
  return Object.keys(envelope).filter((name) => {
    const range = envelope[name] as Range;
    const value = Object.hasOwn(values, name) ? (values[name] as number) : Number.NaN;
    return !insideRange(value, range);
  });
}

/** FR-011-11: the geometry of a family is an extrapolation when any of its parameters leaves the training envelope. */
export function gnsIsExtrapolation(family: GnsFamily, values: Readonly<Record<string, number>>): boolean {
  if (!Object.hasOwn(GNS_ENVELOPE, family)) return true;
  return outsideParameters(values, GNS_ENVELOPE[family]).length > 0;
}

/** FR-011-39: a control value outside the training ranges makes the field an extrapolation. */
export function fnoIsExtrapolation(
  names: readonly string[],
  values: Readonly<Record<string, number>>,
): boolean {
  const envelope: Record<string, Range> = {};
  for (const name of names)
    if (Object.hasOwn(FNO_ENVELOPE, name)) envelope[name] = FNO_ENVELOPE[name] as Range;
  return outsideParameters(values, envelope).length > 0;
}

/** NFR-011-03: the live evaluation budget of the FNO on T2. */
export const FNO_T2_LIVE_MS = 1000;
/** NFR-011-02: the step-time budget of the GNS. */
export const GNS_STEP_MS = 50;

/** NFR-011-03: slower than the budget (or not measured as a finite number) means the view is not LIVE but REPLAY (PRECOMPUTE). */
export function fnoIsLive(evaluationMs: number, budgetMs: number = FNO_T2_LIVE_MS): boolean {
  return Number.isFinite(evaluationMs) && evaluationMs >= 0 && evaluationMs <= budgetMs;
}
