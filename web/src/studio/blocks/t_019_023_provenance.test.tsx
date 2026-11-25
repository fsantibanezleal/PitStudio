// T-019-023 [red] · FR-019-15 (provenance chips on each artefact: run id, recipe SHA-256 first 12 hex, git SHA 7 hex, GPU model, driver, wall time, peak VRAM, energy in J and the throttle shares per clocks-event reason;
// for a stage with `performance: local-only` the wall-time, VRAM, energy and throttle chips are replaced by "measured locally, not published (licence)") and FR-019-37 (every artefact produced by `cosmos-reason-2`
// shows "Built on NVIDIA Cosmos" and the label "display-only"), FR-000-08. E2E half: web/e2e/t_019_023_provenance.spec.ts.
//
// Expected API:
//   `~/studio/blocks/Provenance` (web/src/studio/blocks/Provenance.tsx): named export ProvenanceChips({ artefact: ArtefactRecord; run: RunCard | null }) rendering `[data-testid="provenance"]` with chips
//     `[data-chip="<id>"]` (text = label and value, `data-value` = the number or text shown in the chip's unit): run (the run id), recipe (first 12 hex of recipe.sha256), git (first 7 hex of the artefact's git_sha),
//     gpu (run.gpu.name), driver (run.gpu.driver), wall (seconds, stage.wall_s), vram (peak VRAM in GiB = mem_used_peak_bytes / 2^30), energy (J), and one `throttle-<reason>` per reason of clocks_event_frac:
//     sw_power_cap, sw_thermal, hw_thermal, hw_slowdown, power_brake (percent of samples = fraction x 100; `idle` is not a throttle reason and has no chip). The stage of the artefact is the stage of the run card whose
//     key.id (and key.variant when the artefact's producer.stage has one) equals producer.stage. For a local-only stage the four kinds wall, vram, energy and throttle-* are absent and one
//     `[data-chip="local-only"]` holds "measured locally, not published (licence)"; no number of the stage appears anywhere in the chips.
//   `~/cards/ArtefactCard` (existing): for an artefact whose producer.tool is `cosmos-reason-2` it also shows "Built on NVIDIA Cosmos" and the label "display-only"; for no other tool.
// Oracles: the valid run card of DC-001-01 (stage st56_encode with a known telemetry summary: wall 42.5 s, peak VRAM 2,147,483,648 B = 2 GiB, energy 3034.5 J, clocks_event_frac sw_power_cap 0 ... idle 0.02, recipe sha eeee...,
// GPU "NVIDIA RTX 5000 Ada Generation Laptop GPU", driver 582.78) and hand-set shares 0.125, 0.5, 0.01, 0.25 (12.5, 50, 1 and 25 percent).
import { within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { ArtefactCard } from "~/cards/ArtefactCard";
import { ProvenanceChips } from "~/studio/blocks/Provenance";
import { GIT_SHA, makeArtefact } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { loadRunCardExample, makeRunCard, makeStage } from "~/test-support/studio-fixtures";

const NOT_PUBLISHED = "measured locally, not published (licence)";
const example = loadRunCardExample();
const stage = example.stages[0] as Record<string, unknown>;
const tele = stage.telemetry as Record<string, unknown>;
const artefact = (over: Record<string, unknown> = {}) =>
  makeArtefact({
    id: "a2-haul-clip",
    run_id: example.run_id,
    producer: { tool: "nvenc-ffmpeg", stage: { id: "st56_encode" } },
    ...over,
  } as never);
const chip = (id: string) =>
  document.querySelector<HTMLElement>(`[data-testid="provenance"] [data-chip="${id}"]`);
const chips = () =>
  Array.from(document.querySelectorAll('[data-testid="provenance"] [data-chip]')).map((c) =>
    c.getAttribute("data-chip"),
  );
const renderChips = (a = artefact(), run: unknown = example) =>
  renderApp(createElement(ProvenanceChips, { artefact: a as never, run: run as never }));

describe("provenance chips (FR-019-15)", () => {
  it("FR-019-15 · a public stage shows run id, recipe digest (12 hex), git SHA (7 hex), GPU, driver, wall time, peak VRAM, energy", async () => {
    await renderChips();
    expect(chip("run")?.textContent).toContain(example.run_id);
    expect(chip("recipe")?.textContent).toContain("eeeeeeeeeeee");
    expect(chip("recipe")?.textContent).not.toContain("eeeeeeeeeeeee");
    expect(chip("git")?.textContent).toContain(GIT_SHA.slice(0, 7));
    expect(chip("git")?.textContent).not.toContain(GIT_SHA.slice(0, 8));
    expect(chip("gpu")?.textContent).toContain("NVIDIA RTX 5000 Ada Generation Laptop GPU");
    expect(chip("driver")?.textContent).toContain("582.78");
    expect(chip("wall")?.getAttribute("data-value")).toBe("42.5");
    expect(chip("wall")?.textContent).toContain("42.5");
    expect(chip("vram")?.getAttribute("data-value")).toBe("2");
    expect(chip("energy")?.getAttribute("data-value")).toBe("3034.5");
    expect(chip("energy")?.textContent).toContain("3034.5");
    expect(document.querySelector('[data-chip="local-only"]')).toBeNull();
  });

  it("FR-019-15 · the throttle shares are percent of samples per reason: software power cap, software thermal, hardware thermal, hardware slowdown, power brake", async () => {
    const run = makeRunCard({
      stages: [
        makeStage("st56_encode", "nvenc-ffmpeg", {
          telemetry: {
            ...tele,
            clocks_event_frac: {
              sw_power_cap: 0.125,
              sw_thermal: 0,
              hw_thermal: 0.5,
              hw_slowdown: 0.01,
              power_brake: 0.25,
              idle: 0.02,
            },
          },
        }),
      ],
    } as never);
    await renderChips(artefact(), run);
    const value = (reason: string) => chip(`throttle-${reason}`)?.getAttribute("data-value");
    expect(value("sw_power_cap")).toBe("12.5");
    expect(value("sw_thermal")).toBe("0");
    expect(value("hw_thermal")).toBe("50");
    expect(value("hw_slowdown")).toBe("1");
    expect(value("power_brake")).toBe("25");
    expect(chip("throttle-idle")).toBeNull();
    expect(chip("throttle-sw_power_cap")?.textContent).toMatch(/12\.5\s?%/);
    expect(chip("throttle-sw_power_cap")?.textContent?.toLowerCase()).toContain("software power cap");
    expect(chip("throttle-hw_slowdown")?.textContent?.toLowerCase()).toContain("hardware slowdown");
  });

  it("FR-019-15 · the peak VRAM is in GiB: 3.5 GiB reads 3.5", async () => {
    const run = makeRunCard({
      stages: [
        makeStage("st56_encode", "nvenc-ffmpeg", {
          telemetry: { ...tele, mem_used_peak_bytes: 3_758_096_384 },
        }),
      ],
    } as never);
    await renderChips(artefact(), run);
    expect(chip("vram")?.getAttribute("data-value")).toBe("3.5");
  });

  it("FR-019-15 · a local-only stage replaces wall time, VRAM, energy and throttle chips by 'measured locally, not published (licence)' and shows none of its numbers", async () => {
    const leaky = makeStage("st53_sensors", "ovrtx", {
      performance: "local-only",
      wall_s: 99.25,
      telemetry: {
        ...tele,
        energy_j: 777.5,
        mem_used_peak_bytes: 5_368_709_120,
        clocks_event_frac: {
          sw_power_cap: 0.7,
          sw_thermal: 0,
          hw_thermal: 0,
          hw_slowdown: 0,
          power_brake: 0,
          idle: 0,
        },
      },
    });
    await renderChips(
      artefact({ producer: { tool: "ovrtx", stage: { id: "st53_sensors" } } }),
      makeRunCard({ stages: [leaky] } as never),
    );
    expect(chip("local-only")?.textContent).toContain(NOT_PUBLISHED);
    for (const gone of [
      "wall",
      "vram",
      "energy",
      "throttle-sw_power_cap",
      "throttle-sw_thermal",
      "throttle-hw_thermal",
      "throttle-hw_slowdown",
      "throttle-power_brake",
    ])
      expect(chip(gone), gone).toBeNull();
    const all = document.querySelector('[data-testid="provenance"]')?.textContent ?? "";
    for (const number of ["99.25", "777.5", "5", "70"])
      expect(all.split(/\s+/), number).not.toContain(number);
    expect(chip("run")).not.toBeNull();
    expect(chip("gpu")).not.toBeNull();
    expect(chip("driver")).not.toBeNull();
  });

  it("FR-019-15 · a stage whose telemetry is the licence sentence shows that sentence once and no numeric chip", async () => {
    const run = makeRunCard({
      stages: [makeStage("st53_sensors", "ovrtx", { performance: "local-only", telemetry: NOT_PUBLISHED })],
    } as never);
    await renderChips(artefact({ producer: { tool: "ovrtx", stage: { id: "st53_sensors" } } }), run);
    expect(document.querySelectorAll('[data-chip="local-only"]')).toHaveLength(1);
    expect(chips().filter((c) => /^(wall|vram|energy|throttle)/.test(c ?? ""))).toEqual([]);
  });

  it("FR-019-15 · null telemetry fields show no chip for that field and never print 0, null or undefined", async () => {
    const run = makeRunCard({
      stages: [
        makeStage("st56_encode", "nvenc-ffmpeg", {
          wall_s: undefined,
          telemetry: { ...tele, energy_j: null, mem_used_peak_bytes: null, clocks_event_frac: null },
        }),
      ],
    } as never);
    await renderChips(artefact(), run);
    for (const gone of ["wall", "vram", "energy", "throttle-sw_power_cap"])
      expect(chip(gone), gone).toBeNull();
    expect(document.querySelector('[data-testid="provenance"]')?.textContent).not.toMatch(
      /null|undefined|NaN/,
    );
  });

  it("FR-019-15 · the stage is matched by id and variant: two variants of one stage give each artefact its own numbers", async () => {
    const a = makeStage("s62_accel", "tensorrt", {
      key: { id: "s62_accel", variant: "fp16" },
      wall_s: 10,
      telemetry: { ...tele, energy_j: 100 },
    });
    const b = makeStage("s62_accel", "tensorrt", {
      key: { id: "s62_accel", variant: "fp8" },
      wall_s: 20,
      telemetry: { ...tele, energy_j: 200 },
    });
    const run = makeRunCard({ stages: [a, b] } as never);
    await renderChips(
      artefact({ producer: { tool: "tensorrt", stage: { id: "s62_accel", variant: "fp8" } } }),
      run,
    );
    expect(chip("wall")?.getAttribute("data-value")).toBe("20");
    expect(chip("energy")?.getAttribute("data-value")).toBe("200");
  });

  it("FR-019-15 · an artefact whose run card is not available still shows the chips it can (run id, git SHA) and no number it cannot know", async () => {
    await renderChips(artefact({ run_id: "gone-run" }), null);
    expect(chip("run")?.textContent).toContain("gone-run");
    expect(chip("git")?.textContent).toContain(GIT_SHA.slice(0, 7));
    expect(chips().filter((c) => /^(wall|vram|energy|throttle|gpu|driver|recipe)/.test(c ?? ""))).toEqual([]);
  });

  it("FR-019-15 · a hostile GPU name or run id is text, truncated after 200 characters", async () => {
    const run = makeRunCard({
      gpu: {
        backend: "nvml",
        name: `<img src=x onerror=alert(1)>${"g".repeat(900)}`,
        driver: "1",
        vram_total_bytes: 1,
        power_limit_enforced_w: 1,
      },
    } as never);
    await renderChips(artefact(), run);
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect((chip("gpu")?.textContent ?? "").length).toBeLessThan(400);
  });
});

describe("Built on NVIDIA Cosmos (FR-019-37)", () => {
  const cosmos = makeArtefact({
    id: "cosmos-caption-b1",
    producer: { tool: "cosmos-reason-2", stage: { id: "st59c_captions" } },
    kind: "text",
    cases: ["B1"],
  } as never);

  it("FR-019-37 · an artefact produced by cosmos-reason-2 shows 'Built on NVIDIA Cosmos' and the label 'display-only'", async () => {
    await renderApp(createElement(ArtefactCard, { artefact: cosmos as never }));
    const card = document.querySelector("article[data-artefact]") as HTMLElement;
    expect(card.textContent).toContain("Built on NVIDIA Cosmos");
    expect(within(card).getByText(/display-only/)).toBeTruthy();
  });

  it("FR-019-37 · no other tool's artefact carries the Cosmos attribution", async () => {
    await renderApp(
      createElement(ArtefactCard, {
        artefact: makeArtefact({
          id: "other",
          producer: { tool: "warp", stage: { id: "st50_physics" } },
        }) as never,
      }),
    );
    expect((document.querySelector("article[data-artefact]") as HTMLElement).textContent).not.toMatch(
      /Cosmos|display-only/,
    );
  });

  it("FR-019-37 · the attribution is present in every language and on every Cosmos artefact", async () => {
    for (const lang of ["en", "es"] as const) {
      const { unmount } = await renderApp(
        createElement(
          "div",
          null,
          [cosmos, { ...cosmos, id: "cosmos-vqa-b2" }].map((a) =>
            createElement(ArtefactCard, { key: a.id, artefact: a as never }),
          ),
        ),
        { lang },
      );
      const cards = Array.from(document.querySelectorAll("article[data-artefact]"));
      expect(cards).toHaveLength(2);
      for (const c of cards) {
        expect(c.textContent, lang).toContain("NVIDIA Cosmos");
        expect(c.textContent, lang).toMatch(/display-only|solo visualización|solo para mostrar/i);
      }
      unmount();
    }
  });
});
