// T-018-082 [red] · FR-018-66 (the CI mislabel check: an artefact or engine labelled live whose measurements give replay, or a live engine without a measurement,
// fails the web build and is named), FR-000-15 (honest lane labels), with FR-018-64 (every engine measured) and FR-018-67 (invalid files fail the build, naming the file).
//
// Expected API (file web/scripts/check-lanes.mjs, an ES module loaded by path; run in CI as `node scripts/check-lanes.mjs`)
//     checkLanes({ artefacts, liveEngines, engines, measurements }): { ok: boolean; violations: Array<{ id: string; rule: string; message: string }> }
//         artefacts      [{ id, lane }] from the web manifest (only those labelled "live" are checked)
//         liveEngines    engine ids labelled live
//         engines        optional: every engine id of the engine table; each must have an entry (FR-018-64)
//         measurements   the parsed lane-measurement file (DC-018-06): { entries: [{ engine | artefact, measurements: {...} }] }
//       Rules (violation.rule), each naming the subject id in `id` and in `message`:
//         "mislabel"            labelled live, but `deriveLane` of its measurements gives replay            (FR-018-66)
//         "unmeasured"          labelled live, but no entry in the measurement file                        (FR-018-66)
//         "engine-not-measured" an engine of `engines` has no entry                                          (FR-018-64)
//         "duplicate-entry"     the same engine or artefact listed twice                                     (FR-018-66)
//         "unknown-artefact"    an entry names an artefact that is not in the web manifest                   (FR-018-66)
//       `ok` is true iff there is no violation. The function never throws for well-formed input and does not modify it.
//     main(argv: string[]): number     CLI: `--manifest <web manifest json> --measurements <lane-measurements json> [--engines a,b,c] [--live-engines a,b]`;
//         exit 0 when ok; 1 when there is a violation (every violation printed to stderr with its subject id) or a file is missing, is not JSON or does not
//         have the shape above (the message names that file); 2 for bad arguments
//
// Oracles (independent of the code under test): the gate of data-model 001 section 2.6 / FR-018-65 evaluated by hand on the entries below; the checker rules listed in
// specs/018-web-cases/contracts/examples/index.json for the lane-measurement file; the valid example of the file (lane-measurements.valid.json).
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { afterAll, describe, expect, it } from "vitest";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const SCRIPT = resolve(WEB, "scripts/check-lanes.mjs");
async function load(): Promise<{
  checkLanes: (i: unknown) => {
    ok: boolean;
    violations: Array<{ id: string; rule: string; message: string }>;
  };
  main: (a: string[]) => number;
}> {
  const href = pathToFileURL(SCRIPT).href;
  return (await import(/* @vite-ignore */ href)) as never;
}

const m = (over: Record<string, unknown> = {}) => ({
  web_drivable: true,
  max_asset_bytes: 1_000_000,
  interaction_ms: 4,
  run_ms_t2: 120,
  trace_bytes: null,
  measured: { tier: "T2", date: "2026-10-07", browser: "chromium 141.0.7390.37" },
  ...over,
});
const slowRun = m({ interaction_ms: null, run_ms_t2: 5000 }); // gate: replay
const goodEngine = { engine: "geotech", measurements: m() }; // gate: live

describe("the gate applied to labels (FR-018-66)", () => {
  it("FR-018-66 · a live engine and a live artefact whose measurements pass the gate give no violation", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [{ id: "a3-replay", lane: "live" }],
      liveEngines: ["geotech"],
      measurements: { entries: [goodEngine, { artefact: "a3-replay", measurements: m() }] },
    });
    expect(r).toEqual({ ok: true, violations: [] });
  });

  it("FR-018-66 · a live engine whose measurements give replay (run time 5 s, no interaction) is a mislabel naming the engine", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [],
      liveEngines: ["des"],
      measurements: { entries: [{ engine: "des", measurements: slowRun }] },
    });
    expect(r.ok).toBe(false);
    expect(r.violations).toHaveLength(1);
    expect(r.violations[0]?.rule).toBe("mislabel");
    expect(r.violations[0]?.id).toBe("des");
    expect(r.violations[0]?.message).toContain("des");
  });

  it("FR-018-66 · a live artefact whose measurements give replay is a mislabel naming the artefact", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [{ id: "big-model", lane: "live" }],
      liveEngines: [],
      measurements: {
        entries: [{ artefact: "big-model", measurements: m({ max_asset_bytes: 26_000_000 }) }],
      },
    });
    expect(r.violations.map((v) => [v.rule, v.id])).toEqual([["mislabel", "big-model"]]);
  });

  it("FR-018-66 · a live engine without an entry is 'unmeasured', and so is a live artefact", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [{ id: "x-art", lane: "live" }],
      liveEngines: ["plume"],
      measurements: { entries: [goodEngine] },
    });
    expect(r.violations.map((v) => [v.rule, v.id]).sort()).toEqual(
      [
        ["unmeasured", "plume"],
        ["unmeasured", "x-art"],
      ].sort(),
    );
  });

  it("FR-018-66 · replay and static artefacts are not checked against the gate, measured or not", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [
        { id: "r1", lane: "replay" },
        { id: "s1", lane: "static" },
      ],
      liveEngines: [],
      measurements: { entries: [{ artefact: "r1", measurements: m({ max_asset_bytes: 99_000_000 }) }] },
    });
    expect(r.ok).toBe(true);
  });

  it("FR-018-66 · every violation is reported (two mislabels and one unmeasured give three), each naming its subject", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [{ id: "a", lane: "live" }],
      liveEngines: ["des", "gns"],
      measurements: {
        entries: [
          { engine: "des", measurements: slowRun },
          { artefact: "a", measurements: m({ web_drivable: false }) },
        ],
      },
    });
    expect(r.violations.map((v) => v.id).sort()).toEqual(["a", "des", "gns"]);
  });

  it("FR-018-66 · the gate boundaries are inclusive: exactly 25 MB, 16 ms and 10 MB is live, a byte more is a mislabel", async () => {
    const { checkLanes } = await load();
    const edge = (over: Record<string, unknown>) =>
      checkLanes({
        artefacts: [],
        liveEngines: ["e"],
        measurements: {
          entries: [
            {
              engine: "e",
              measurements: m({
                max_asset_bytes: 25_000_000,
                interaction_ms: 16,
                run_ms_t2: null,
                trace_bytes: 10_000_000,
                ...over,
              }),
            },
          ],
        },
      });
    expect(edge({}).ok).toBe(true);
    expect(edge({ max_asset_bytes: 25_000_001 }).ok).toBe(false);
    expect(edge({ trace_bytes: 10_000_001 }).ok).toBe(false);
    expect(edge({ interaction_ms: 16.5 }).ok).toBe(false);
  });
});

describe("entries and coverage (FR-018-64, FR-018-66)", () => {
  it("FR-018-64 · an engine of the engine table without an entry is 'engine-not-measured', whatever its label", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [],
      liveEngines: [],
      engines: ["geotech", "plume"],
      measurements: { entries: [goodEngine] },
    });
    expect(r.violations.map((v) => [v.rule, v.id])).toEqual([["engine-not-measured", "plume"]]);
  });

  it("FR-018-66 · the same engine or artefact listed twice is a 'duplicate-entry'", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [{ id: "a", lane: "replay" }],
      liveEngines: [],
      measurements: {
        entries: [
          goodEngine,
          goodEngine,
          { artefact: "a", measurements: m() },
          { artefact: "a", measurements: m() },
        ],
      },
    });
    expect(r.violations.map((v) => [v.rule, v.id]).sort()).toEqual(
      [
        ["duplicate-entry", "a"],
        ["duplicate-entry", "geotech"],
      ].sort(),
    );
  });

  it("FR-018-66 · an entry for an artefact that is not in the web manifest is an 'unknown-artefact'", async () => {
    const { checkLanes } = await load();
    const r = checkLanes({
      artefacts: [{ id: "known", lane: "replay" }],
      liveEngines: [],
      measurements: { entries: [{ artefact: "ghost", measurements: m() }] },
    });
    expect(r.violations.map((v) => [v.rule, v.id])).toEqual([["unknown-artefact", "ghost"]]);
  });

  it("FR-018-66 · non-finite, negative and missing measurements are read as failing their conditions (the mislabel of FR-018-65)", async () => {
    const { checkLanes } = await load();
    for (const bad of [Number.NaN, -1, Number.POSITIVE_INFINITY]) {
      const r = checkLanes({
        artefacts: [],
        liveEngines: ["e"],
        measurements: { entries: [{ engine: "e", measurements: m({ max_asset_bytes: bad }) }] },
      });
      expect(r.violations.map((v) => v.rule)).toEqual(["mislabel"]);
    }
  });

  it("FR-018-66 · the input is not modified", async () => {
    const { checkLanes } = await load();
    const input = {
      artefacts: [{ id: "a", lane: "live" }],
      liveEngines: ["des"],
      measurements: { entries: [{ engine: "des", measurements: slowRun }] },
    };
    const before = structuredClone(input);
    checkLanes(input);
    expect(input).toEqual(before);
  });
});

describe("the CLI (FR-018-66, FR-018-67, FR-000-15)", () => {
  const root = mkdtempSync(join(process.env.PITSTUDIO_TMP ?? tmpdir(), "check-lanes-"));
  afterAll(() => rmSync(root, { recursive: true, force: true }));
  const write = (name: string, body: unknown) => {
    mkdirSync(dirname(join(root, name)), { recursive: true });
    writeFileSync(join(root, name), typeof body === "string" ? body : JSON.stringify(body));
    return join(root, name);
  };
  const run = (args: string[]) =>
    spawnSync(process.execPath, [SCRIPT, ...args], { encoding: "utf8", cwd: WEB, timeout: 60_000 });
  const web = (artefacts: unknown[]) => write("manifest.json", { kind: "web-index", artefacts });

  it("FR-018-66 · exits 0 when every live subject passes the gate", () => {
    const out = run([
      "--manifest",
      web([{ id: "a", lane: "live" }]),
      "--measurements",
      write("ok.json", { entries: [{ artefact: "a", measurements: m() }] }),
    ]);
    expect(out.status, out.stderr).toBe(0);
  });

  it("FR-018-66 · exits 1 and names a mislabelled artefact on stderr", () => {
    const out = run([
      "--manifest",
      web([{ id: "slow-art", lane: "live" }]),
      "--measurements",
      write("bad.json", { entries: [{ artefact: "slow-art", measurements: slowRun }] }),
    ]);
    expect(out.status).toBe(1);
    expect(out.stderr).toContain("slow-art");
  });

  it("FR-018-66 · exits 1 and names a live engine that has no measurement", () => {
    const out = run([
      "--manifest",
      web([]),
      "--measurements",
      write("e.json", { entries: [goodEngine] }),
      "--live-engines",
      "geotech,plume",
    ]);
    expect(out.status).toBe(1);
    expect(out.stderr).toContain("plume");
    expect(out.stderr).not.toContain("geotech:");
  });

  it("FR-018-67 · a measurement file that is not JSON, has no entries array, or does not exist fails the build and the message names the file", () => {
    for (const [name, body] of [
      ["broken.json", "{not json"],
      ["shapeless.json", { engines: [] }],
      ["empty.json", { entries: [] }],
    ] as Array<[string, unknown]>) {
      const file = write(name, body);
      const out = run(["--manifest", web([]), "--measurements", file]);
      expect(out.status, name).toBe(1);
      expect(out.stderr, name).toContain(name);
    }
    const missing = run(["--manifest", web([]), "--measurements", join(root, "nope.json")]);
    expect(missing.status).toBe(1);
    expect(missing.stderr).toContain("nope.json");
  });

  it("FR-018-67 · a missing, empty or malformed web manifest fails the build, naming it", () => {
    const meas = write("m.json", { entries: [goodEngine] });
    const out = run(["--manifest", write("broken-manifest.json", "[[["), "--measurements", meas]);
    expect(out.status).toBe(1);
    expect(out.stderr).toContain("broken-manifest.json");
  });

  it("FR-018-66 · missing arguments exit 2 with a usage message", () => {
    expect(run([]).status).toBe(2);
    expect(run(["--manifest", web([])]).status).toBe(2);
  });
});
