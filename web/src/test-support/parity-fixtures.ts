// Shared, locked test support (first used by T-018-064; later engine tasks import it). Not a test file.
//
// Loads the DC-018-04 parity fixtures `web/tests/fixtures/parity/<engine-id>/<fixture>.json[.gz]` (written by
// tools/make_parity_fixtures.py, T-018-005) and applies the tolerance of FR-018-51:
//     |y_ts - y_py| <= 1e-12 * s_y + rtol * |y_py|
// with s_y the output's unit scale from `$defs/unit_scales` of the engine schema (DC-018-02), rtol = 1e-9 for closed forms and
// max(1e-9, 10 x solver_tol) for iterative functions (both read from the fixture's tolerance record, which the contract caps).
// A fixture set that is missing, empty or too small is a FAILURE here (FR-018-67: no engine passes on an empty fixture set).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";
import { expect } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../..");
export const FIXTURE_ROOT = resolve(REPO, "web/tests/fixtures/parity");

export interface FixtureVector {
  name?: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  variates?: { generator: string; entropy: string; spawn_key: number[]; samples: number[][] };
}
export interface ParityFixture {
  file: string;
  engine: string;
  fixture: string;
  function?: string;
  reference: { name: string; version: string; callable?: string };
  tolerance: { class: string; rtol?: number; atol_scale?: number; solver_tol?: number; [k: string]: unknown };
  cases: FixtureVector[];
}

export function loadParityFixtures(engine: string): ParityFixture[] {
  const dir = resolve(FIXTURE_ROOT, engine);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => /\.json(\.gz)?$/.test(f))
    .sort()
    .map((f) => {
      const raw = readFileSync(resolve(dir, f));
      const text = (f.endsWith(".gz") ? gunzipSync(raw) : raw).toString("utf8");
      return { ...(JSON.parse(text) as Omit<ParityFixture, "file">), file: `${engine}/${f}` };
    });
}

/** `$defs/unit_scales.const` of the engine schema: function -> output field -> s_y (DC-018-02). */
export function unitScales(engine: string): Record<string, Record<string, number>> {
  const schema = JSON.parse(
    readFileSync(resolve(REPO, `specs/018-web-cases/contracts/engines/${engine}.schema.json`), "utf8"),
  ) as { $defs: { unit_scales: { const: Record<string, Record<string, number>> } } };
  return schema.$defs.unit_scales.const;
}

/** Recursively compares numbers within the FR-018-51 tolerance; other leaves must be equal. */
export function expectClose(
  actual: unknown,
  expected: unknown,
  scale: number,
  rtol: number,
  path: string,
): void {
  if (typeof expected === "number") {
    expect(typeof actual, `${path}: a number`).toBe("number");
    const a = actual as number;
    const bound = 1e-12 * scale + rtol * Math.abs(expected);
    expect(Math.abs(a - expected), `${path}: ${a} vs ${expected} (bound ${bound})`).toBeLessThanOrEqual(
      bound,
    );
  } else if (Array.isArray(expected)) {
    expect(Array.isArray(actual) || ArrayBuffer.isView(actual), `${path}: an array`).toBe(true);
    const arr = Array.from(actual as ArrayLike<unknown>);
    expect(arr.length, `${path}: length`).toBe(expected.length);
    expected.forEach((e, i) => {
      expectClose(arr[i], e, scale, rtol, `${path}[${i}]`);
    });
  } else if (expected !== null && typeof expected === "object") {
    for (const [k, v] of Object.entries(expected as Record<string, unknown>)) {
      expectClose((actual as Record<string, unknown>)?.[k], v, scale, rtol, `${path}.${k}`);
    }
  } else {
    expect(actual, path).toEqual(expected);
  }
}

/**
 * FR-018-51 for one function of an analytical engine: a fixture for `fn` exists, has at least 200 vectors, is of an analytical class
 * with the tolerances the contract allows, and `run(args)` equals every reference output within the tolerance.
 */
export function expectAnalyticalParity(
  engine: string,
  fn: string,
  run: (args: Record<string, unknown>) => unknown,
): void {
  const fixtures = loadParityFixtures(engine).filter((f) => f.function === fn);
  expect(
    fixtures.length,
    `a parity fixture for ${engine}.${fn} exists under ${FIXTURE_ROOT}`,
  ).toBeGreaterThan(0);
  const scales = unitScales(engine)[fn] ?? {};
  let vectors = 0;
  for (const fx of fixtures) {
    expect(["analytical-closed-form", "analytical-iterative"], `${fx.file}: class`).toContain(
      fx.tolerance.class,
    );
    const rtol =
      fx.tolerance.class === "analytical-iterative"
        ? Math.max(1e-9, 10 * (fx.tolerance.solver_tol ?? 0))
        : (fx.tolerance.rtol ?? 1e-9);
    expect(rtol, `${fx.file}: rtol is the FR-018-51 one`).toBeLessThanOrEqual(1e-4);
    for (const [i, v] of fx.cases.entries()) {
      const result = run(structuredClone(v.input));
      for (const [key, expected] of Object.entries(v.output)) {
        expectClose(
          (result as Record<string, unknown>)[key],
          expected,
          scales[key] ?? 1,
          rtol,
          `${fx.file} #${i} ${key}`,
        );
      }
      vectors++;
    }
  }
  expect(vectors, `${engine}.${fn}: at least 200 reference vectors`).toBeGreaterThanOrEqual(200);
}
