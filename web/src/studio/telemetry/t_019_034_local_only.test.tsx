// T-019-034 [red] · FR-019-30 (stages that ran Isaac Sim, Kit, Replicator, ovrtx or TensorRT for RTX appear on /studio/gpu with links to their outputs, the note "Performance measured locally, not published (licence: NVIDIA SLA §8.9 /
// TensorRT for RTX SLA §2.13)" and no numeric telemetry, while stages that ran regular TensorRT on PitStudio's own models show full telemetry), FR-019-32 (every published timing states the GPU model, driver, enforced power
// limit and the share of time in each throttle state, and the text "our hardware, not a comparative benchmark"), FR-000-08.
//
// Expected API (web/src/studio/telemetry/*.tsx):
//   LocalOnly.tsx    LocalOnlyCards({ run: RunCard }): one `[data-testid="local-only-stage"][data-stage]` for every stage of the run card whose `performance` is `local-only` (the registry class of Isaac Sim, Kit, Replicator, ovrtx and
//                    TensorRT for RTX), holding the tool, the exact note above, one `a[data-testid="output-link"]` per artefact of the run card produced by that stage (href `/studio/runs/<run id>/#<artefact id>`), and NO number of the
//                    stage (wall time, energy, VRAM, utilisation, clocks, throttle shares: none is printed, even when the run card holds them).
//   Conditions.tsx   ConditionsNote({ run: RunCard; stage: string }): `[data-testid="conditions"]` with the GPU model, the driver, "<W> W" for the enforced power limit, the five throttle shares of the stage
//                    (clocks_event_frac: software power cap, software thermal, hardware thermal, hardware slowdown, power brake, as percentages) and "our hardware, not a comparative benchmark".
//   GpuTimelines (T-019-033): every `[data-testid="gpu-stage"]` contains a `[data-testid="conditions"]`; a public TensorRT stage is charted like any other public stage.
// Oracles: the strings of the EARS rows (the NVIDIA licence sections as written in the spec), hand-built run cards (fixture GPU RTX 5000 Ada, driver 582.78, 175 W; clocks_event_frac 0.125, 0, 0.5, 0.01, 0.25 = 12.5, 0, 50, 1, 25 %).
import { within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { ConditionsNote } from "~/studio/telemetry/Conditions";
import { GpuTimelines } from "~/studio/telemetry/GpuTimelines";
import { LocalOnlyCards } from "~/studio/telemetry/LocalOnly";
import { renderApp } from "~/test-support/render";
import { loadTelemetryExample, makeRunCard, makeStage } from "~/test-support/studio-fixtures";

const NOTE =
  "Performance measured locally, not published (licence: NVIDIA SLA §8.9 / TensorRT for RTX SLA §2.13)";
const RUN = "20261007T210000Z-c2-slope";
const art = (id: string, stage: string, tool: string) => ({
  id,
  run_id: RUN,
  producer: { tool, stage: { id: stage } },
  kind: "image",
});
const leaky = (id: string, tool: string) =>
  makeStage(id, tool, {
    performance: "local-only",
    wall_s: 913.75,
    telemetry: {
      sample_hz: 2,
      n_samples: 4567,
      gpu_busy_pct: { mean: 77.7, p50: 78, p95: 91.5 },
      mem_used_peak_bytes: 12_345_678_901,
      power_w: { mean: 111.1, p95: 140, max: 155.5 },
      power_at_limit_frac: 0.31,
      energy_j: 98765.5,
      sm_clock_mhz: { mean: 1700, p5: 1300 },
      temp_c_max: 79,
      clocks_event_frac: {
        sw_power_cap: 0.3,
        sw_thermal: 0,
        hw_thermal: 0,
        hw_slowdown: 0,
        power_brake: 0,
        idle: 0,
      },
      pcie_replays_delta: 0,
    },
    throughput: { value: 4321.5, unit: "frames/s" },
  });
const card = (stages: unknown[], artefacts: unknown[] = []) =>
  makeRunCard({ run_id: RUN, stages, artefacts } as never);
const stageCard = (id: string) =>
  document.querySelector<HTMLElement>(`[data-testid="local-only-stage"][data-stage="${id}"]`) as HTMLElement;

describe("local-only stages on the GPU page (FR-019-30, FR-000-08)", () => {
  const tools: Array<[string, string]> = [
    ["st52_rtx_render", "isaac-sim-replicator"],
    ["st58_kit_capture", "kit-usd-composer-explorer"],
    ["st55_sdg", "isaac-sim-replicator"],
    ["st53_sensors", "ovrtx"],
    ["s62_accel_rtx", "tensorrt"],
  ];

  for (const [stage, tool] of tools) {
    it(`FR-019-30 · the local-only stage ${stage} (${tool}) has a card with the licence note, links to its outputs and no number`, async () => {
      const run = card(
        [leaky(stage, tool)],
        [art("out-1", stage, tool), art("out-2", stage, tool), art("other", "st40_compose", "openusd")],
      );
      await renderApp(createElement(LocalOnlyCards, { run: run as never }));
      const c = stageCard(stage);
      expect(c).not.toBeNull();
      expect(c.textContent).toContain(NOTE);
      expect(c.textContent).toContain(tool);
      const links = Array.from(c.querySelectorAll('a[data-testid="output-link"]')).map((a) =>
        a.getAttribute("href"),
      );
      expect(links).toEqual([`/studio/runs/${RUN}/#out-1`, `/studio/runs/${RUN}/#out-2`]);
      for (const planted of [
        "913.75",
        "4567",
        "77.7",
        "12345678901",
        "111.1",
        "98765.5",
        "4321.5",
        "0.31",
        "1700",
      ])
        expect(c.textContent, planted).not.toContain(planted);
      expect(c.querySelectorAll('[data-testid="chart"], canvas')).toHaveLength(0);
    });
  }

  it("FR-019-30 · the note is written exactly: 'Performance measured locally, not published (licence: NVIDIA SLA §8.9 / TensorRT for RTX SLA §2.13)'", async () => {
    await renderApp(
      createElement(LocalOnlyCards, { run: card([leaky("st55_sdg", "isaac-sim-replicator")]) as never }),
    );
    expect(stageCard("st55_sdg").textContent).toContain(
      "Performance measured locally, not published (licence: NVIDIA SLA §8.9 / TensorRT for RTX SLA §2.13)",
    );
  });

  it("FR-019-30 · a public stage has no local-only card, and a card with no local-only stage renders none", async () => {
    await renderApp(
      createElement(LocalOnlyCards, {
        run: card([makeStage("st50_physics", "warp"), makeStage("s62_accel", "tensorrt")]) as never,
      }),
    );
    expect(document.querySelectorAll('[data-testid="local-only-stage"]')).toHaveLength(0);
  });

  it("FR-019-30 · a stage with no output artefact still has its card and the note, and no link", async () => {
    await renderApp(
      createElement(LocalOnlyCards, { run: card([leaky("st55_sdg", "isaac-sim-replicator")], []) as never }),
    );
    expect(stageCard("st55_sdg").textContent).toContain(NOTE);
    expect(stageCard("st55_sdg").querySelectorAll("a")).toHaveLength(0);
  });

  it("FR-000-08 · the licence sentence given as the stage's telemetry is not a number and adds none", async () => {
    const s = makeStage("st53_sensors", "ovrtx", {
      performance: "local-only",
      telemetry: "measured locally, not published (licence)",
    });
    delete (s as Record<string, unknown>).wall_s;
    await renderApp(createElement(LocalOnlyCards, { run: card([s]) as never }));
    const text = (stageCard("st53_sensors").textContent ?? "").replace(NOTE, "").replace("st53_sensors", "");
    expect(text.match(/\d/g) ?? []).toEqual([]);
  });

  it("FR-019-30 · a hostile output id is an escaped fragment, a hostile stage id is text", async () => {
    const run = card([leaky("<b>x</b>", "ovrtx")], [art("a b#c", "<b>x</b>", "ovrtx")]);
    const { container } = await renderApp(createElement(LocalOnlyCards, { run: run as never }));
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector('a[data-testid="output-link"]')?.getAttribute("href")).toBe(
      `/studio/runs/${RUN}/#${encodeURIComponent("a b#c")}`,
    );
  });
});

describe("regular TensorRT shows full telemetry (FR-019-30)", () => {
  it("FR-019-30 · a public TensorRT stage on PitStudio's own model is charted like any public stage", async () => {
    const stage = makeStage("st50_physics", "tensorrt");
    const telemetry = { ...loadTelemetryExample(), run_id: RUN };
    await renderApp(
      createElement(GpuTimelines, { run: card([stage]) as never, telemetry: telemetry as never }),
    );
    for (const name of ["busy", "memory", "power", "sm_clock", "throttle"])
      expect(document.querySelector(`[data-testid="chart"][data-chart="${name}"]`), name).not.toBeNull();
    expect(document.body.textContent).not.toContain("not published (licence");
  });

  it("FR-019-30 · the same stage marked local-only (TensorRT for RTX) is not charted and gets the note on the local-only card", async () => {
    const stage = leaky("st50_physics", "tensorrt");
    const telemetry = { ...loadTelemetryExample(), run_id: RUN };
    await renderApp(
      createElement(
        "div",
        null,
        createElement(GpuTimelines, { run: card([stage]) as never, telemetry: telemetry as never }),
        createElement(LocalOnlyCards, { run: card([stage]) as never }),
      ),
    );
    expect(document.querySelectorAll('[data-testid="chart"]')).toHaveLength(0);
    expect(stageCard("st50_physics").textContent).toContain(NOTE);
  });
});

describe("conditions of a published timing (FR-019-32)", () => {
  const withFrac = (frac: Record<string, number>, gpu: unknown = undefined) =>
    makeRunCard({
      run_id: RUN,
      ...(gpu === undefined ? {} : { gpu }),
      stages: [
        makeStage("st50_physics", "warp", {
          telemetry: {
            ...(makeStage("x", "y").telemetry as Record<string, unknown>),
            clocks_event_frac: frac,
          },
        }),
      ],
    } as never);
  const FRAC = {
    sw_power_cap: 0.125,
    sw_thermal: 0,
    hw_thermal: 0.5,
    hw_slowdown: 0.01,
    power_brake: 0.25,
    idle: 0.02,
  };

  it("FR-019-32 · states the GPU model, the driver, the enforced power limit, each throttle share and 'our hardware, not a comparative benchmark'", async () => {
    await renderApp(createElement(ConditionsNote, { run: withFrac(FRAC) as never, stage: "st50_physics" }));
    const t = document.querySelector('[data-testid="conditions"]')?.textContent ?? "";
    for (const needle of [
      "NVIDIA RTX 5000 Ada Generation Laptop GPU",
      "582.78",
      "175 W",
      "our hardware, not a comparative benchmark",
    ])
      expect(t, needle).toContain(needle);
    for (const share of [/12\.5\s?%/, /\b50\s?%/, /\b1\s?%/, /\b25\s?%/]) expect(t).toMatch(share);
    for (const reason of [
      "software power cap",
      "software thermal",
      "hardware thermal",
      "hardware slowdown",
      "power brake",
    ])
      expect(t.toLowerCase(), reason).toContain(reason);
  });

  it("FR-019-32 · the idle fraction is not a throttle state and is not listed", async () => {
    await renderApp(createElement(ConditionsNote, { run: withFrac(FRAC) as never, stage: "st50_physics" }));
    expect(document.querySelector('[data-testid="conditions"]')?.textContent?.toLowerCase()).not.toMatch(
      /\bidle\b/,
    );
  });

  it("FR-019-32 · the power limit and the shares come from the run card: a 140 W card reads 140 W", async () => {
    const gpu = {
      backend: "nvml",
      name: "Another GPU",
      driver: "999.1",
      vram_total_bytes: 8_589_934_592,
      power_limit_enforced_w: 140,
    };
    await renderApp(
      createElement(ConditionsNote, {
        run: withFrac({ ...FRAC, sw_power_cap: 0.75 }, gpu) as never,
        stage: "st50_physics",
      }),
    );
    const t = document.querySelector('[data-testid="conditions"]')?.textContent ?? "";
    expect(t).toContain("Another GPU");
    expect(t).toContain("999.1");
    expect(t).toContain("140 W");
    expect(t).toMatch(/75\s?%/);
    expect(t).not.toContain("175 W");
  });

  it("FR-019-32 · missing values read 'not available on this GPU' and never null, undefined, NaN or 0 for a share that was not recorded", async () => {
    const gpu = {
      backend: "nvml",
      name: "G",
      driver: "1",
      vram_total_bytes: 1,
      power_limit_enforced_w: null,
    };
    await renderApp(
      createElement(ConditionsNote, {
        run: withFrac({ sw_power_cap: Number.NaN } as never, gpu) as never,
        stage: "st50_physics",
      }),
    );
    const t = document.querySelector('[data-testid="conditions"]')?.textContent ?? "";
    expect(t).toContain("not available on this GPU");
    expect(t).not.toMatch(/null|undefined|NaN/);
    expect(t).toContain("our hardware, not a comparative benchmark");
  });

  it("FR-019-32 · every block of the GPU page carries the conditions", async () => {
    const telemetry = { ...loadTelemetryExample(), run_id: RUN };
    await renderApp(
      createElement(GpuTimelines, { run: withFrac(FRAC) as never, telemetry: telemetry as never }),
    );
    const blocks = Array.from(document.querySelectorAll('[data-testid="gpu-stage"]'));
    expect(blocks.length).toBeGreaterThan(0);
    for (const b of blocks)
      expect(within(b as HTMLElement).getByTestId("conditions").textContent).toContain(
        "our hardware, not a comparative benchmark",
      );
  });

  it("FR-019-32 · the conditions text is escaped: a hostile GPU name is text", async () => {
    const gpu = {
      backend: "nvml",
      name: "<img src=x onerror=alert(1)>",
      driver: "1",
      vram_total_bytes: 1,
      power_limit_enforced_w: 100,
    };
    const { container } = await renderApp(
      createElement(ConditionsNote, { run: withFrac(FRAC, gpu) as never, stage: "st50_physics" }),
    );
    expect(container.querySelector("img[src='x']")).toBeNull();
  });
});
