// T-020-032 [red] · FR-020-24: for each model of plan section 7 (D-FINE-N/S, RF-DETR-Seg-N, U-Net, GNS, FNO, PPO and attention dispatch, IL-1, IL-2, slope forecasters, mine-to-mill meta-model, DEM calibration, Cosmos Reason 2, TensorRT
// engines) /results shows its pre-registered acceptance criterion as recorded in DC-020-01 and the status pass, fail or "Not yet run" computed from the results bundle against that criterion.
//
// Expected API (web/src/results/criteria.ts, plus a change of `readBundle` in web/src/results/bundles.ts):
//   readBundle(raw) now also returns `criteria: Array<{ requirement: string; status: "pass" | "fail" | "not-run" }>` (the `criteria` array of DC-020-02, [] when absent or malformed entries are dropped).
//   MODEL_ROWS: Array<{ id: string; methods: string[]; requirements: string[] }>   the 13 rows of plan section 7 in this order and with these ids: dfine, rfdetr-seg, unet, gns, fno, dispatch, il1, il2, slope-forecasters, meta-model,
//       dem-calibration, cosmos, tensorrt-engines; `methods` are method-registry ids (M1..M23) whose criterion is shown, `requirements` the success-criterion ids (SC-nnn-nn) whose status is computed; every row has both non-empty.
//   criterionStatus(requirements: string[], bundles: Array<{ criteria: ... }>): "pass" | "fail" | "not-yet-run"
//       "fail" when any listed requirement is recorded as fail in any bundle; else "pass" when every listed requirement is recorded as pass in some bundle; else "not-yet-run" (a requirement that no bundle records, or records as not-run,
//       keeps the row "not-yet-run"); an empty list is "not-yet-run".
// Oracles: the valid results examples of DC-020-02 (specs/020-web-knowledge/contracts/examples/results.valid*.json: criteria SC-007-01 pass, ...), hand-built bundles for each combination, the 13 rows written out from plan section 7.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { readBundle } from "~/results/bundles";
import { criterionStatus, MODEL_ROWS } from "~/results/criteria";

const EX = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../specs/020-web-knowledge/contracts/examples",
);
const example = (name: string) =>
  JSON.parse(readFileSync(resolve(EX, name), "utf8")) as Record<string, unknown>;
const bundle = (...criteria: Array<[string, string]>) => ({
  criteria: criteria.map(([requirement, status]) => ({ requirement, status })),
});

describe("the 13 model rows (FR-020-24)", () => {
  it("FR-020-24 · the rows are the 13 models of plan section 7, in order", () => {
    expect(MODEL_ROWS.map((r) => r.id)).toEqual([
      "dfine",
      "rfdetr-seg",
      "unet",
      "gns",
      "fno",
      "dispatch",
      "il1",
      "il2",
      "slope-forecasters",
      "meta-model",
      "dem-calibration",
      "cosmos",
      "tensorrt-engines",
    ]);
  });

  it("FR-020-24 · every row names at least one method of the registry (M1..M23) and at least one success criterion (SC-nnn-nn)", () => {
    for (const row of MODEL_ROWS) {
      expect(row.methods.length, row.id).toBeGreaterThan(0);
      expect(row.requirements.length, row.id).toBeGreaterThan(0);
      for (const m of row.methods) expect(m, row.id).toMatch(/^M([1-9]|1\d|2[0-3])$/);
      for (const r of row.requirements) expect(r, row.id).toMatch(/^SC-\d{3}-\d{2}$/);
    }
  });

  it("FR-020-24 · the dispatch row carries both of its criteria (PPO SC-007-01 and attention SC-007-02), the Cosmos row SC-015-03", () => {
    expect(MODEL_ROWS.find((r) => r.id === "dispatch")?.requirements).toEqual(
      expect.arrayContaining(["SC-007-01", "SC-007-02"]),
    );
    expect(MODEL_ROWS.find((r) => r.id === "dispatch")?.methods).toEqual(
      expect.arrayContaining(["M4", "M5"]),
    );
    expect(MODEL_ROWS.find((r) => r.id === "cosmos")?.requirements).toContain("SC-015-03");
    expect(MODEL_ROWS.find((r) => r.id === "cosmos")?.methods).toContain("M22");
  });
});

describe("reading the criteria of a bundle (DC-020-02)", () => {
  it("FR-020-24 · readBundle keeps the criteria of a valid bundle: results.valid.json records SC-007-01 as pass", () => {
    const b = readBundle(example("results.valid.json"));
    expect(b?.criteria).toEqual([{ requirement: "SC-007-01", status: "pass" }]);
  });

  it("FR-020-24 · the cosmos and acceleration bundles keep theirs", () => {
    for (const name of ["results.valid-cosmos.json", "results.valid-acceleration.json"]) {
      const raw = example(name);
      const b = readBundle(raw);
      expect(b, name).not.toBeNull();
      expect(b?.criteria, name).toEqual((raw.criteria as unknown[]) ?? []);
    }
  });

  it("FR-020-24 · malformed criteria entries are dropped, a missing array is empty", () => {
    const raw = {
      ...example("results.valid.json"),
      criteria: [
        { requirement: "SC-007-01", status: "pass" },
        { requirement: 7 },
        null,
        "x",
        { requirement: "SC-007-02", status: "maybe" },
        { status: "pass" },
      ],
    };
    expect(readBundle(raw)?.criteria).toEqual([{ requirement: "SC-007-01", status: "pass" }]);
    const { criteria: _dropped, ...without } = example("results.valid.json");
    expect(readBundle(without)?.criteria).toEqual([]);
  });
});

describe("the computed status (FR-020-24)", () => {
  it("FR-020-24 · every listed requirement recorded as pass: pass", () => {
    expect(
      criterionStatus(
        ["SC-007-01", "SC-007-02"],
        [bundle(["SC-007-01", "pass"]), bundle(["SC-007-02", "pass"])],
      ),
    ).toBe("pass");
    expect(criterionStatus(["SC-007-01"], [bundle(["SC-007-01", "pass"])])).toBe("pass");
  });

  it("FR-020-24 · any listed requirement recorded as fail: fail, even when the others pass or are missing", () => {
    expect(
      criterionStatus(["SC-007-01", "SC-007-02"], [bundle(["SC-007-01", "pass"], ["SC-007-02", "fail"])]),
    ).toBe("fail");
    expect(criterionStatus(["SC-007-01", "SC-007-02"], [bundle(["SC-007-01", "fail"])])).toBe("fail");
  });

  it("FR-020-24 · a requirement that no bundle records, or records as not-run, keeps the row 'not-yet-run'", () => {
    expect(criterionStatus(["SC-007-01"], [])).toBe("not-yet-run");
    expect(criterionStatus(["SC-007-01"], [bundle(["SC-099-01", "pass"])])).toBe("not-yet-run");
    expect(criterionStatus(["SC-007-01"], [bundle(["SC-007-01", "not-run"])])).toBe("not-yet-run");
    expect(criterionStatus(["SC-007-01", "SC-007-02"], [bundle(["SC-007-01", "pass"])])).toBe("not-yet-run");
  });

  it("FR-020-24 · an empty list of requirements is 'not-yet-run', never a vacuous pass", () => {
    expect(criterionStatus([], [bundle(["SC-007-01", "pass"])])).toBe("not-yet-run");
  });

  it("FR-020-24 · a requirement recorded in two bundles: fail wins over pass, pass wins over not-run", () => {
    expect(
      criterionStatus(["SC-007-01"], [bundle(["SC-007-01", "pass"]), bundle(["SC-007-01", "fail"])]),
    ).toBe("fail");
    expect(
      criterionStatus(["SC-007-01"], [bundle(["SC-007-01", "not-run"]), bundle(["SC-007-01", "pass"])]),
    ).toBe("pass");
  });

  it("FR-020-24 · the status is computed from the bundle's criteria, not from any stored verdict or title", () => {
    const sneaky = { ...bundle(["SC-007-01", "fail"]), verdict: "pass", status: "pass", title: "pass" };
    expect(criterionStatus(["SC-007-01"], [sneaky as never])).toBe("fail");
  });

  it("FR-020-24 · bundles with a missing or malformed criteria field are ignored", () => {
    expect(
      criterionStatus(
        ["SC-007-01"],
        [
          {} as never,
          { criteria: null } as never,
          { criteria: [null, 3] } as never,
          bundle(["SC-007-01", "pass"]),
        ],
      ),
    ).toBe("pass");
  });
});
