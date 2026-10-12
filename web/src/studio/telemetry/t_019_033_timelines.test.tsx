// T-019-033 [red] · FR-019-27 (timelines for every public stage: GPU busy % labelled "time-busy fraction, not SM occupancy", memory used against the GPU's total memory, board power against the enforced power limit, SM clock, and
// the clocks-event reasons as a stacked fraction band, charts of spec 020), FR-019-28 (GPU busy % never without the stage's power-at-limit fraction beside it), FR-019-29 ("How measured" popover) and FR-019-31 (a null or
// missing telemetry field reads "not available on this GPU", never 0 and never interpolated). E2E half: web/e2e/t_019_033_gpu_page.spec.ts.
//
// Expected API: `~/studio/telemetry/GpuTimelines` (web/src/studio/telemetry/GpuTimelines.tsx): named export GpuTimelines({ run: RunCard; telemetry: PublishedTelemetry }) where `run` is the published run card (DC-001-01) and
// `telemetry` its published telemetry (DC-002-03: { run_id, stages: [{ key, performance, bucket_s, points: [{ t_s, util_pct, power_w, sm_clock_mhz, temp_c, mem_used_bytes, clocks_event_mask }] }] }).
// Hooks: one `[data-testid="gpu-stage"][data-stage="<stage id>"]` per telemetry stage whose `performance` is public AND whose stage in the run card is public (a stage the card marks local-only is never charted, whatever the
//   telemetry file holds); in it five charts `[data-testid="chart"][data-chart="busy|memory|power|sm_clock|throttle"]` (the chart component of spec 020: each has a "Show data" button that reveals a `table` whose header cells carry
//   the unit and whose body has one row per plotted point, first cell the time in seconds, second cell the series value), `data-missing` = the number of points whose value is null;
//   `[data-testid="power-at-limit"]` inside the busy chart (the stage's power_at_limit_frac as a percentage, or "not available on this GPU");
//   `[data-testid="chart-reference"][data-ref="vram_total" | "power_limit"][data-value]` inside the memory and the power chart (data-value = `gpu.vram_total_bytes` bytes, `gpu.power_limit_enforced_w` watts) with the text
//   "<GiB rounded> GB" / "<W> W"; the throttle chart has `data-kind="stacked-band"` and one `[data-series="sw_power_cap|sw_thermal|hw_thermal|hw_slowdown|power_brake"]` per reason (a point's reason is set by its
//   `clocks_event_mask` bit: 0x4, 0x20, 0x40, 0x8, 0x80 of the NVML clocks-event reasons, NVML API reference, "Clocks Event Reasons"; 0x1 is GPU idle and 0x2 application clocks: not throttle reasons here);
//   `button[data-testid="how-measured"]` in each chart opening `[data-testid="how-measured-popover"]` (role dialog or popover): the run's sampling rate (`sample_hz` of the stage's telemetry summary, "<n> Hz"), the definitions of
//   utilisation, of power averaging and of energy ("difference of the total-energy counter"), and links to the NVML reference pages (https://docs.nvidia.com/deploy/nvml-api/...), Escape closes it and returns the focus to its button.
//   A field that is null in a point is a gap (never 0, never interpolated); a field null or absent in every point replaces its chart by `[data-testid="chart-unavailable"]` "not available on this GPU".
// Oracles: the valid published telemetry of DC-002-03 and the valid run card of DC-001-01 (GPU RTX 5000 Ada: 17,171,480,576 B = 16 GiB, 175 W), the NVML bit values, hand arithmetic (GiB, percentages).
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { GpuTimelines } from "~/studio/telemetry/GpuTimelines";
import { renderApp } from "~/test-support/render";
import {
  loadTelemetryExample,
  makeRunCard,
  makeStage,
  type TelemetryJson,
} from "~/test-support/studio-fixtures";

const RUN = "20261007T210000Z-c2-slope";
const NA = "not available on this GPU";
const stageSummary = (over: Record<string, unknown> = {}) => {
  const base = makeStage("st50_physics", "warp").telemetry as Record<string, unknown>;
  return { ...base, sample_hz: 2, power_at_limit_frac: 0.0625, ...over };
};
const run = (over: Record<string, unknown> = {}, stageOver: Record<string, unknown> = {}) =>
  makeRunCard({
    run_id: RUN,
    stages: [makeStage("st50_physics", "warp", { telemetry: stageSummary(), ...stageOver })],
    ...over,
  } as never);
const telemetry = (): TelemetryJson => ({ ...loadTelemetryExample(), run_id: RUN });
const render = (r: unknown = run(), t: unknown = telemetry()) =>
  renderApp(createElement(GpuTimelines, { run: r as never, telemetry: t as never }));
const chart = (name: string) =>
  document.querySelector<HTMLElement>(
    `[data-testid="gpu-stage"][data-stage="st50_physics"] [data-testid="chart"][data-chart="${name}"]`,
  ) as HTMLElement;
const dataTable = async (name: string) => {
  fireEvent.click(within(chart(name)).getByRole("button", { name: /Show data/i }));
  return chart(name).querySelector("table") as HTMLTableElement;
};
const column = (table: HTMLTableElement, col: number) =>
  Array.from(table.querySelectorAll("tbody tr")).map((tr) =>
    tr.querySelectorAll("td, th")[col]?.textContent?.trim(),
  );

describe("which stages and which charts (FR-019-27)", () => {
  it("FR-019-27 · a public stage gets the five charts: busy, memory, power, SM clock and the throttle band", async () => {
    await render();
    for (const name of ["busy", "memory", "power", "sm_clock", "throttle"])
      expect(chart(name), name).not.toBeNull();
    expect(chart("throttle").getAttribute("data-kind")).toBe("stacked-band");
  });

  it("FR-019-27 · a stage that the run card marks local-only is not charted even if the telemetry file holds points for it", async () => {
    const r = run({}, { performance: "local-only" });
    await render(r, telemetry());
    expect(document.querySelector('[data-testid="gpu-stage"][data-stage="st50_physics"]')).toBeNull();
    expect(document.querySelectorAll('[data-testid="chart"]')).toHaveLength(0);
  });

  it("FR-019-27 · a telemetry stage that is itself marked local-only is not charted", async () => {
    const t = telemetry();
    (t.stages[0] as { performance: string }).performance = "local-only";
    await render(run(), t);
    expect(document.querySelectorAll('[data-testid="gpu-stage"]')).toHaveLength(0);
  });

  it("FR-019-27 · the busy chart is labelled 'time-busy fraction, not SM occupancy'", async () => {
    await render();
    expect(chart("busy").textContent).toContain("time-busy fraction, not SM occupancy");
  });

  it("FR-019-27 · every chart is the interactive chart of spec 020: focusable, with a Show data control", async () => {
    await render();
    for (const name of ["busy", "memory", "power", "sm_clock", "throttle"]) {
      expect(within(chart(name)).getByRole("button", { name: /Show data/i }), name).toBeTruthy();
      expect(
        chart(name).getAttribute("tabindex") ??
          chart(name).querySelector("[tabindex='0']")?.getAttribute("tabindex"),
        name,
      ).toBe("0");
    }
  });
});

describe("the data behind the charts (FR-019-27, FR-019-31)", () => {
  it("FR-019-27 · busy: the table holds the utilisation of every point in percent", async () => {
    await render();
    const table = await dataTable("busy");
    expect(
      Array.from(table.querySelectorAll("thead th"))
        .map((h) => h.textContent)
        .join(" "),
    ).toContain("%");
    expect(column(table, 0)).toEqual(["0", "2", "4"]);
    expect(column(table, 1)).toEqual(["12", "88.5", "90"]);
  });

  it("FR-019-27 · memory: the values are in GiB (1, 2, 2) and the header says so; the reference line is the card's total memory, 16 GB", async () => {
    await render();
    const table = await dataTable("memory");
    expect(
      Array.from(table.querySelectorAll("thead th"))
        .map((h) => h.textContent)
        .join(" "),
    ).toMatch(/GiB|GB/);
    expect(column(table, 1)).toEqual(["1", "2", "2"]);
    const ref = chart("memory").querySelector('[data-testid="chart-reference"][data-ref="vram_total"]');
    expect(ref?.getAttribute("data-value")).toBe("17171480576");
    expect(ref?.textContent).toContain("16 GB");
  });

  it("FR-019-27 · the memory reference is the run card's total, never a constant: a 24 GiB card draws 24 GB", async () => {
    const r = run({
      gpu: {
        backend: "nvml",
        name: "G",
        driver: "1",
        vram_total_bytes: 25_769_803_776,
        power_limit_enforced_w: 140,
      },
    });
    await render(r);
    const ref = chart("memory").querySelector('[data-ref="vram_total"]');
    expect(ref?.getAttribute("data-value")).toBe("25769803776");
    expect(ref?.textContent).toContain("24 GB");
    expect(chart("power").querySelector('[data-ref="power_limit"]')?.getAttribute("data-value")).toBe("140");
  });

  it("FR-019-27 · power: the values in watts and the reference line at the enforced limit, 175 W", async () => {
    await render();
    const table = await dataTable("power");
    expect(
      Array.from(table.querySelectorAll("thead th"))
        .map((h) => h.textContent)
        .join(" "),
    ).toContain("W");
    expect(column(table, 1).slice(0, 2)).toEqual(["31.5", "97.2"]);
    const ref = chart("power").querySelector('[data-testid="chart-reference"][data-ref="power_limit"]');
    expect(ref?.getAttribute("data-value")).toBe("175");
    expect(ref?.textContent).toContain("175 W");
  });

  it("FR-019-27 · SM clock in MHz", async () => {
    await render();
    const table = await dataTable("sm_clock");
    expect(
      Array.from(table.querySelectorAll("thead th"))
        .map((h) => h.textContent)
        .join(" "),
    ).toContain("MHz");
    expect(column(table, 1)).toEqual(["1410", "1785", "1770"]);
  });

  it("FR-019-27 · throttle: a stacked band with one series per reason, set by the NVML bit of each point's clocks_event_mask (4 = software power cap)", async () => {
    await render();
    const band = chart("throttle");
    const series = Array.from(band.querySelectorAll("[data-series]")).map((s) =>
      s.getAttribute("data-series"),
    );
    expect(series.sort()).toEqual(["hw_slowdown", "hw_thermal", "power_brake", "sw_power_cap", "sw_thermal"]);
    const table = await dataTable("throttle");
    const heads = Array.from(table.querySelectorAll("thead th")).map(
      (h) => h.getAttribute("data-series") ?? h.textContent?.trim(),
    );
    const col = (name: string) =>
      heads.findIndex((h) => h === name || (h ?? "").toLowerCase().includes(name.replace("_", " ")));
    // masks 1, 4, 4: the idle bit (1) is not a throttle reason; the power-cap bit (4) is
    expect(column(table, col("sw_power_cap"))).toEqual(["0", "1", "1"]);
    for (const other of ["sw_thermal", "hw_thermal", "hw_slowdown", "power_brake"])
      expect(column(table, col(other)), other).toEqual(["0", "0", "0"]);
  });

  it("FR-019-27 · each of the five reasons is read from its own NVML bit (0x4, 0x20, 0x40, 0x8, 0x80)", async () => {
    const t = telemetry();
    (t.stages[0] as { points: Array<Record<string, number | null>> }).points = [
      0x4,
      0x20,
      0x40,
      0x8,
      0x80,
      0x4 | 0x20,
      0x1 | 0x2,
    ].map((mask, i) => ({
      t_s: i * 2,
      util_pct: 50,
      power_w: 100,
      sm_clock_mhz: 1500,
      temp_c: 60,
      mem_used_bytes: 1_073_741_824,
      clocks_event_mask: mask,
    }));
    await render(run(), t);
    const table = await dataTable("throttle");
    const heads = Array.from(table.querySelectorAll("thead th")).map(
      (h) => h.getAttribute("data-series") ?? "",
    );
    const col = (name: string) => heads.indexOf(name);
    expect(column(table, col("sw_power_cap"))).toEqual(["1", "0", "0", "0", "0", "1", "0"]);
    expect(column(table, col("sw_thermal"))).toEqual(["0", "1", "0", "0", "0", "1", "0"]);
    expect(column(table, col("hw_thermal"))).toEqual(["0", "0", "1", "0", "0", "0", "0"]);
    expect(column(table, col("hw_slowdown"))).toEqual(["0", "0", "0", "1", "0", "0", "0"]);
    expect(column(table, col("power_brake"))).toEqual(["0", "0", "0", "0", "1", "0", "0"]);
  });

  it("FR-019-31 · a null power reading is a gap: the table says 'not available on this GPU' for it, the chart counts one missing point, and no 0 is invented", async () => {
    await render();
    const table = await dataTable("power");
    expect(column(table, 1)[2]).toBe(NA);
    expect(chart("power").getAttribute("data-missing")).toBe("1");
    expect(column(table, 1)).not.toContain("0");
    expect(chart("busy").getAttribute("data-missing")).toBe("0");
  });

  it("FR-019-31 · a field that is null in every point replaces its chart by 'not available on this GPU'", async () => {
    const t = telemetry();
    for (const p of (t.stages[0] as { points: Array<Record<string, number | null>> }).points)
      p.sm_clock_mhz = null;
    await render(run(), t);
    expect(chart("sm_clock")).toBeNull();
    expect(
      document.querySelector(
        '[data-testid="gpu-stage"] [data-testid="chart-unavailable"][data-chart="sm_clock"]',
      )?.textContent,
    ).toContain(NA);
  });

  it("FR-019-31 · a field absent from the points is treated like a null one, and a stage with no point has no chart and says so", async () => {
    const t = telemetry();
    for (const p of (t.stages[0] as { points: Array<Record<string, number | null>> }).points) delete p.temp_c;
    await render(run(), t);
    expect(chart("busy")).not.toBeNull();
    const none = telemetry();
    (none.stages[0] as { points: unknown[] }).points = [];
    document.body.innerHTML = "";
    await render(run(), none);
    expect(document.querySelectorAll('[data-testid="chart"]')).toHaveLength(0);
    expect(document.body.textContent).toContain(NA);
  });

  it("FR-019-31 · the power reference line is not drawn when the run card has no enforced limit; the chart says 'not available on this GPU' for the limit", async () => {
    const r = run({
      gpu: {
        backend: "nvml",
        name: "G",
        driver: "1",
        vram_total_bytes: 17_171_480_576,
        power_limit_enforced_w: null,
      },
    });
    await render(r);
    expect(chart("power").querySelector('[data-ref="power_limit"]')).toBeNull();
    expect(chart("power").textContent).toContain(NA);
  });
});

describe("busy % beside power at limit (FR-019-28)", () => {
  it("FR-019-28 · the busy chart carries the stage's power-at-limit fraction as a percentage (0.0625 reads 6.25 %)", async () => {
    await render();
    const p = chart("busy").querySelector('[data-testid="power-at-limit"]');
    expect(p).not.toBeNull();
    expect(p?.textContent).toMatch(/6\.25\s?%/);
  });

  it("FR-019-28 · when the fraction is not recorded the chart still shows the field, reading 'not available on this GPU', never 0 %", async () => {
    const r = run({}, { telemetry: stageSummary({ power_at_limit_frac: null }) });
    await render(r);
    const p = chart("busy").querySelector('[data-testid="power-at-limit"]');
    expect(p?.textContent).toContain(NA);
    expect(p?.textContent).not.toMatch(/\b0\s?%/);
  });

  it("FR-019-28 · no element that shows a busy percentage exists outside a busy chart that has its power-at-limit field", async () => {
    await render();
    for (const el of Array.from(document.querySelectorAll('[data-testid="busy-value"]'))) {
      expect(
        el.closest('[data-chart="busy"]')?.querySelector('[data-testid="power-at-limit"]'),
      ).not.toBeNull();
    }
    expect(chart("busy").querySelectorAll('[data-testid="power-at-limit"]')).toHaveLength(1);
  });
});

describe("How measured (FR-019-29)", () => {
  const open = async (name = "busy") => {
    const user = userEvent.setup();
    const button = within(chart(name)).getByTestId("how-measured");
    await user.click(button);
    return { user, button };
  };

  it("FR-019-29 · the popover states that run's sampling rate and the definitions of utilisation, power averaging and energy", async () => {
    await render(run({}, { telemetry: stageSummary({ sample_hz: 4 }) }));
    await open();
    const pop = screen.getByTestId("how-measured-popover");
    expect(pop.textContent).toMatch(/\b4\s?Hz/);
    expect(pop.textContent?.toLowerCase()).toContain("utilisation");
    expect(pop.textContent?.toLowerCase()).toContain("power averaging");
    expect(pop.textContent?.toLowerCase()).toMatch(/difference of the total.energy counter/);
  });

  it("FR-019-29 · another run, another rate: 1 Hz reads 1 Hz", async () => {
    await render(run({}, { telemetry: stageSummary({ sample_hz: 1 }) }));
    await open();
    expect(screen.getByTestId("how-measured-popover").textContent).toMatch(/\b1\s?Hz/);
    expect(screen.getByTestId("how-measured-popover").textContent).not.toMatch(/\b2\s?Hz/);
  });

  it("FR-019-29 · links to the NVML reference pages, opening in a new tab safely", async () => {
    await render();
    await open();
    const links = Array.from(screen.getByTestId("how-measured-popover").querySelectorAll("a"));
    expect(links.length).toBeGreaterThan(0);
    for (const a of links) {
      expect(new URL(a.getAttribute("href") ?? "").hostname).toBe("docs.nvidia.com");
      expect(a.getAttribute("href")).toContain("nvml-api");
      expect(a.getAttribute("rel")).toMatch(/noopener/);
    }
  });

  it("FR-019-29 · Escape closes the popover and returns the focus to its button; it is a button with an accessible name", async () => {
    await render();
    const { user, button } = await open();
    expect(button.getAttribute("aria-expanded")).toBe("true");
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("how-measured-popover")).toBeNull();
    expect(document.activeElement).toBe(button);
    expect(button.textContent ?? button.getAttribute("aria-label")).toMatch(/How measured/i);
  });

  it("FR-019-29 · with no recorded sampling rate the popover says so instead of inventing one", async () => {
    await render(run({}, { telemetry: stageSummary({ sample_hz: null }) }));
    await open();
    expect(screen.getByTestId("how-measured-popover").textContent).toContain(NA);
    expect(screen.getByTestId("how-measured-popover").textContent).not.toMatch(/\bnull\b|NaN|undefined/);
  });
});
