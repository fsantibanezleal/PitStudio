// T-018-081 [red] · FR-018-64 (the lane-gate measurement suite) and NFR-018-03 (gate targets reported, not hidden). On forced T2 in headless Chromium, for every engine
// of spec 018 section 7.1 and every live model, the suite measures the 95th-percentile interaction time over 50 interactions (ms), the median full-run time over 5 runs
// and the byte sizes of the largest engine-specific asset and of the trace, and writes them with the runner configuration to the lane-measurement file (DC-018-06,
// `assets/lane-measurements.json` of the Pages artifact; override the path with LANE_MEASUREMENTS_OUT). CI then runs web/scripts/check-lanes.mjs on that file.
//
// Hook (invented by the test author, flagged in the red report), on the parity route opened with `?tier=t2`:
//   window.__pitstudio.lane.measure(engineId: string, protocol: { interactions: number; runs: number }) ->
//     Promise<{ web_drivable: boolean; interaction_ms: number[]; run_ms: number[]; asset_bytes: number; trace_bytes: number | null }>
//   `interaction_ms` has `protocol.interactions` samples and `run_ms` has `protocol.runs` samples when the engine is web-drivable on T2, and both are empty otherwise
//   (WGSL compute engines need T1).
// Oracles: the protocol of FR-018-64 (50 interactions, 5 runs, p95 by the nearest-rank method = the 48th of 50 sorted samples, median of 5 = the 3rd); the DC-018-06 shape of
// lane-measurements.valid.json (`run_ms_t2` in ms; `trace_bytes` null for none; subject `engine`).
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { ENGINE_IDS } from "../../src/test-support/engine-examples";
import { openParityRunner } from "../support/parity";

const OUT = process.env.LANE_MEASUREMENTS_OUT ?? resolve("build/client/assets/lane-measurements.json");
const p95 = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.ceil(0.95 * xs.length) - 1] as number;
const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? (s[mid] as number) : ((s[mid - 1] as number) + (s[mid] as number)) / 2;
};

interface Raw {
  web_drivable: boolean;
  interaction_ms: number[];
  run_ms: number[];
  asset_bytes: number;
  trace_bytes: number | null;
}

test.describe.configure({ mode: "serial" });

test.describe("lane-gate measurement suite (FR-018-64)", () => {
  const entries: Array<Record<string, unknown>> = [];

  for (const engine of ENGINE_IDS) {
    test(`FR-018-64 · ${engine}: 50 interactions and 5 runs on forced T2 give p95 and median, and the asset and trace sizes`, async ({
      page,
      browserName,
    }) => {
      expect(browserName).toBe("chromium");
      await openParityRunner(page);
      const raw = await page.evaluate(
        async ([id]) =>
          (
            window as unknown as {
              __pitstudio: {
                lane: { measure(id: string, p: { interactions: number; runs: number }): Promise<Raw> };
              };
            }
          ).__pitstudio.lane.measure(id as string, { interactions: 50, runs: 5 }),
        [engine] as const,
      );
      expect(typeof raw.web_drivable).toBe("boolean");
      expect(Number.isInteger(raw.asset_bytes) && raw.asset_bytes >= 0, "asset bytes").toBe(true);
      expect(
        raw.trace_bytes === null || (Number.isInteger(raw.trace_bytes) && raw.trace_bytes >= 0),
        "trace bytes",
      ).toBe(true);
      if (raw.web_drivable) {
        expect(raw.interaction_ms).toHaveLength(50);
        expect(raw.run_ms).toHaveLength(5);
        for (const v of [...raw.interaction_ms, ...raw.run_ms])
          expect(Number.isFinite(v) && v >= 0).toBe(true);
      } else {
        expect(raw.interaction_ms).toHaveLength(0);
        expect(raw.run_ms).toHaveLength(0);
      }
      entries.push({
        engine,
        measurements: {
          web_drivable: raw.web_drivable,
          max_asset_bytes: raw.asset_bytes,
          interaction_ms: raw.web_drivable ? p95(raw.interaction_ms) : null,
          run_ms_t2: raw.web_drivable ? median(raw.run_ms) : null,
          trace_bytes: raw.trace_bytes,
          measured: { tier: "T2", date: new Date().toISOString().slice(0, 10), browser: "chromium" },
        },
      });
    });
  }

  test("FR-018-64 · the suite wrote the measurement file with the runner configuration and one entry per engine of the engine table", async ({
    page,
  }) => {
    expect(entries.map((e) => e.engine)).toEqual([...ENGINE_IDS]);
    await openParityRunner(page);
    const runner = await page.evaluate(() =>
      (
        window as unknown as { __pitstudio: { lane: { runnerConfig(): Promise<Record<string, unknown>> } } }
      ).__pitstudio.lane.runnerConfig(),
    );
    expect(runner).toMatchObject({
      browser: "chromium",
      headless: true,
      forced_tier: "T2",
      interactions: 50,
      runs: 5,
    });
    for (const key of [
      "os_image",
      "cpu_model",
      "logical_cpus",
      "memory_bytes",
      "browser_version",
      "playwright_version",
      "node_version",
    ])
      expect(runner, key).toHaveProperty(key);
    const doc = {
      schema_version: "1.0",
      git_sha: process.env.GITHUB_SHA ?? "0".repeat(40),
      generated: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
      runner,
      entries,
    };
    mkdirSync(dirname(OUT), { recursive: true });
    writeFileSync(OUT, `${JSON.stringify(doc, null, 2)}\n`);
    expect(doc.entries).toHaveLength(25);
  });

  test("NFR-018-03 · the gate targets per engine family are reported: analytical <= 50 ms, DES shift <= 1 s, min-cut 10^5 blocks <= 1 s, surrogate step <= 50 ms (a miss demotes to REPLAY, it does not fail the suite)", () => {
    const byId = new Map(
      entries.map((e) => [
        e.engine as string,
        e.measurements as { interaction_ms: number | null; run_ms_t2: number | null },
      ]),
    );
    const targets: Array<[string, "interaction_ms" | "run_ms_t2", number]> = [
      ["geotech", "run_ms_t2", 50],
      ["blasting", "run_ms_t2", 50],
      ["comminution", "run_ms_t2", 50],
      ["des", "run_ms_t2", 1000],
      ["mincut", "run_ms_t2", 1000],
      ["gns", "interaction_ms", 50],
    ];
    const misses = targets.filter(([id, key, limit]) => {
      const v = byId.get(id)?.[key];
      return v === undefined || v === null || v > limit;
    });
    test
      .info()
      .annotations.push({
        type: "gate-target-misses",
        description: JSON.stringify(misses.map(([id, key, limit]) => `${id}.${key} > ${limit}`)),
      });
    expect(byId.size).toBe(25);
  });
});
