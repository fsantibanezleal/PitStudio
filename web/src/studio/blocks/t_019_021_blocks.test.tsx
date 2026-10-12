// T-019-021 [red] · FR-019-09 (Identity: version, release date, licence, class, ring, environment, capability-probe status, public metrics or "measured locally, not published (licence)",
// NVIDIA notice), FR-019-11 (Role in mining: role and the cases that use the tool, linked), FR-019-16 (Where it ran), FR-019-17 (Limits and failures), FR-019-18 (Reproduce),
// FR-019-19 (Alternatives rejected) and FR-019-42 (probe status never "pass" without a passing probe).
//
// Expected API (web/src/studio/blocks/*.tsx, each a named export rendering `section[data-block="<id>"]` with an h2 title; `ToolEntry` is the registry entry of DC-001-03,
// `InfoEntry` the tool's entry of the studio index (DC-019-03: version { value, release_date, from, lock? }, probe, artefacts), `RunCard` the published run manifest (DC-001-01)):
//   Identity.tsx     IdentityBlock({ tool, info })                     data-block="identity"      [data-testid="probe-status"][data-status="pass|fail|skip|not-probed"]
//   Role.tsx         RoleBlock({ tool, cases: CaseRegistryJson })      data-block="role"          the role text and one a[href="/cases/<id>/"] per case whose `tools` lists the tool
//   WhereRan.tsx     WhereRanBlock({ artefacts: Artefact[], runs: RunCard[] })   data-block="where-ran"   li[data-artefact="<id>"] per artefact
//   Limits.tsx       LimitsBlock({ tool, runs })                       data-block="limits"        li[data-testid="limit"] for the recorded notice, li[data-testid="failed-variant"] per failed or rejected variant
//   Reproduce.tsx    ReproduceBlock({ tool, runs })                    data-block="reproduce"     [data-run="<run id>"] with [data-command] lines
//   Alternatives.tsx AlternativesBlock({ tool })                       data-block="alternatives"  li[data-testid="alternative"] with its name and its reason
// Oracles: the strings of the EARS rows; hand-built registry entries, index entries and run cards (web/src/test-support/studio-fixtures.ts: the valid run card of DC-001-01 as base);
// the GiB arithmetic of FR-019-16 (17,171,480,576 / 2^30 = 15.99 -> 16, the reference machine of spec section 7.3). Assumptions flagged in the report: the registry schema has no `limits` field,
// so the recorded limit is its `notice`; the NVIDIA notice is shown when the name contains NVIDIA or an SPDX id is a NVIDIA or TensorRT licence reference; a failed or rejected variant is a
// stage of the tool with status failed or an attempt with an error class; the Reproduce command is `uv run studio run <recipe path> --profile <profile>` of the run card (as the case pages do).
import { within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { AlternativesBlock } from "~/studio/blocks/Alternatives";
import { IdentityBlock } from "~/studio/blocks/Identity";
import { LimitsBlock } from "~/studio/blocks/Limits";
import { ReproduceBlock } from "~/studio/blocks/Reproduce";
import { RoleBlock } from "~/studio/blocks/Role";
import { WhereRanBlock } from "~/studio/blocks/WhereRan";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { indexTool, makeRunCard, makeStage, makeTool, toolArtefact } from "~/test-support/studio-fixtures";

const block = (id: string) =>
  document.querySelector<HTMLElement>(`section[data-block="${id}"]`) as HTMLElement;
const text = (id: string) => block(id).textContent ?? "";
const NOT_RUN = "measured locally, not published (licence)";
// Paths and names are composed at run time so that no machine path or identity is written in this file.
const WIN_PATH = ["C", ":\\Users\\alice\\work\\cases\\a2.yaml"].join("");
const POSIX_PATH = ["", "home", "alice", "profile.yaml"].join("/");
const LEAK = new RegExp(["[A-Za-z]", ":[\\\\\\\\/]|^/home/|alice|build-host-07"].join(""), "i");

describe("Identity (FR-019-09, FR-019-42)", () => {
  const tool = makeTool("warp", {
    name: "NVIDIA Warp",
    spdx: ["Apache-2.0"],
    licence_class: "attribution",
    ring: "Adopt",
    envs: ["studio"],
  });
  const pass = indexTool("warp", {
    version: { value: "1.10.0", release_date: "2026-08-01", from: "lock", lock: "studio/uv.lock" },
    probe: {
      status: "pass",
      name: "warp_newton",
      date: "2026-10-03",
      gpu: "NVIDIA RTX 5000 Ada Generation Laptop GPU",
      driver: "582.78",
      metrics: { stage_open_s: 0.42 },
    },
  });
  const render = (t = tool, info = pass) =>
    renderApp(createElement(IdentityBlock, { tool: t as never, info: info as never }));

  it("FR-019-09 · shows the version resolved from the lock, its release date, the licence (SPDX), the class, the ring and the environment", async () => {
    await render();
    const t = text("identity");
    for (const needle of ["1.10.0", "2026-08-01", "Apache-2.0", "attribution", "Adopt", "studio"])
      expect(t, needle).toContain(needle);
    expect(block("identity").querySelector("h2")?.textContent).toBe("Identity");
  });

  it("FR-019-09 · a missing release date (null) is not written as 'null' or 'undefined'", async () => {
    await render(tool, { ...pass, version: { ...pass.version, release_date: null } });
    expect(text("identity")).not.toMatch(/null|undefined|Invalid Date|NaN/);
    expect(text("identity")).toContain("1.10.0");
  });

  it("FR-019-09 · a passing probe shows its date, GPU and driver and the public metrics", async () => {
    await render();
    const probe = within(block("identity")).getByTestId("probe-status");
    expect(probe.getAttribute("data-status")).toBe("pass");
    for (const needle of [
      "pass",
      "2026-10-03",
      "NVIDIA RTX 5000 Ada Generation Laptop GPU",
      "582.78",
      "stage_open_s",
      "0.42",
    ])
      expect(probe.textContent, needle).toContain(needle);
  });

  it("FR-019-09 · a tool whose performance is local-only shows 'measured locally, not published (licence)' and none of the numbers, even if the index carries some", async () => {
    await render(
      makeTool("ovrtx", {
        name: "ovrtx",
        performance: "local-only",
        licence_class: "reference-only",
        spdx: ["LicenseRef-NvidiaProprietary"],
      }),
      {
        ...indexTool("ovrtx"),
        probe: {
          status: "pass",
          name: "ovrtx",
          date: "2026-10-03",
          gpu: "G",
          driver: "1",
          metrics: { render_ms: 12.5 },
        },
      },
    );
    expect(text("identity")).toContain(NOT_RUN);
    expect(text("identity")).not.toContain("12.5");
    expect(text("identity")).not.toContain("render_ms");
  });

  it("FR-019-09 · metrics given as the licence sentence are shown as that sentence", async () => {
    await render(tool, { ...pass, probe: { ...pass.probe, metrics: NOT_RUN } });
    expect(text("identity")).toContain(NOT_RUN);
  });

  it("FR-019-09 · NVIDIA tools carry the non-affiliation notice, others do not", async () => {
    await render();
    expect(text("identity")).toContain("Not affiliated with or endorsed by NVIDIA");
    document.body.innerHTML = "";
    await render(makeTool("pytorch", { name: "PyTorch" }), indexTool("pytorch"));
    expect(text("identity")).not.toMatch(/NVIDIA/);
    document.body.innerHTML = "";
    await render(
      makeTool("tensorrt", {
        name: "TensorRT",
        spdx: ["LicenseRef-TensorRT-SLA"],
        licence_class: "reference-only",
      }),
      indexTool("tensorrt"),
    );
    expect(text("identity")).toContain("Not affiliated with or endorsed by NVIDIA");
  });

  it("FR-019-42 · no probe for the tool: 'not probed', never 'pass'", async () => {
    await render(tool, { ...pass, probe: { status: "not-probed" } });
    const probe = within(block("identity")).getByTestId("probe-status");
    expect(probe.getAttribute("data-status")).toBe("not-probed");
    expect(probe.textContent).toContain("not probed");
    expect(probe.textContent).not.toMatch(/\bpass\b/i);
  });

  it("FR-019-42 · a failed probe reads 'probe failed' with its scrubbed error text, never 'pass'", async () => {
    await render(tool, {
      ...pass,
      probe: {
        status: "fail",
        name: "warp_newton",
        date: "2026-10-03",
        gpu: "G",
        driver: "1",
        error: "CUDA error: out of memory at <repo>/studio/probes/warp.py:41",
      },
    });
    const probe = within(block("identity")).getByTestId("probe-status");
    expect(probe.getAttribute("data-status")).toBe("fail");
    expect(probe.textContent).toContain("probe failed");
    expect(probe.textContent).toContain("CUDA error: out of memory at <repo>/studio/probes/warp.py:41");
    expect(probe.textContent).not.toMatch(/\bpass\b/i);
  });

  it("FR-019-42 · a skipped probe reads 'probe skipped', never 'pass'", async () => {
    await render(tool, {
      ...pass,
      probe: { status: "skip", name: "warp_newton", date: "2026-10-03", gpu: "G", driver: "1" },
    });
    const probe = within(block("identity")).getByTestId("probe-status");
    expect(probe.getAttribute("data-status")).toBe("skip");
    expect(probe.textContent).toContain("probe skipped");
    expect(probe.textContent).not.toMatch(/\bpass\b/i);
  });

  it("FR-019-42 · an error text with markup or more than 200 characters is escaped text and truncated, nothing executes", async () => {
    await render(tool, {
      ...pass,
      probe: {
        status: "fail",
        name: "p",
        date: "2026-10-03",
        gpu: "G",
        driver: "1",
        error: `<img src=x onerror=alert(1)>${"e".repeat(5000)}`,
      },
    });
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(text("identity").length).toBeLessThan(2500);
  });
});

describe("Role in mining (FR-019-11)", () => {
  const cases = loadCaseRegistry();
  const usedBy = (id: string) =>
    Object.entries(cases.cases)
      .filter(([, c]) => id in c.tools)
      .map(([k]) => k);

  it("FR-019-11 · shows the role and links every case of the case registry that lists the tool, to /cases/<id>/", async () => {
    await renderApp(
      createElement(RoleBlock, {
        tool: makeTool("warp", { role: "GPU kernels for granular flow." }) as never,
        cases: cases as never,
      }),
    );
    expect(text("role")).toContain("GPU kernels for granular flow.");
    const hrefs = Array.from(block("role").querySelectorAll("a")).map((a) => a.getAttribute("href"));
    const expected = usedBy("warp");
    expect(expected.length).toBeGreaterThan(0);
    expect([...hrefs].sort()).toEqual(expected.map((id) => `/cases/${id}/`).sort());
    expect(block("role").querySelector("h2")?.textContent).toBe("Role in mining");
  });

  it("FR-019-11 · hand check against the tool matrix: Warp is named by A3, C2, C3 and D1", async () => {
    await renderApp(createElement(RoleBlock, { tool: makeTool("warp") as never, cases: cases as never }));
    const linked = Array.from(block("role").querySelectorAll("a")).map((a) => a.textContent?.trim() ?? "");
    for (const id of ["A3", "C2", "C3", "D1"]) expect(linked.join(" ")).toContain(id);
  });

  it("FR-019-11 · a tool that no case lists links no case and does not pretend otherwise", async () => {
    await renderApp(createElement(RoleBlock, { tool: makeTool("cuopt") as never, cases: cases as never }));
    expect(block("role").querySelectorAll("a")).toHaveLength(0);
    expect(text("role")).not.toMatch(/undefined|null/);
  });

  it("FR-019-11 · a hostile role (markup, 5,000 characters) is text", async () => {
    await renderApp(
      createElement(RoleBlock, {
        tool: makeTool("warp", { role: `<b>x</b>${"r".repeat(5000)}` }) as never,
        cases: cases as never,
      }),
    );
    expect(block("role").querySelector("b")).toBeNull();
  });
});

describe("Where it ran (FR-019-16)", () => {
  const card = (id: string, gpu: unknown, created = "2026-10-07T12:00:00Z") =>
    makeRunCard({ run_id: id, created, gpu } as never);
  const gpu = {
    backend: "nvml",
    name: "NVIDIA RTX 5000 Ada Generation Laptop GPU",
    driver: "582.78",
    vram_total_bytes: 17_171_480_576,
    power_limit_enforced_w: 175,
  };

  it("FR-019-16 · a live artefact reads 'Live in your browser'", async () => {
    await renderApp(
      createElement(WhereRanBlock, {
        artefacts: [toolArtefact("a-live", "warp", { lane: "live" })] as never,
        runs: [],
      }),
    );
    expect(text("where-ran")).toContain("Live in your browser");
    expect(text("where-ran")).not.toContain("Precomputed");
  });

  it("FR-019-16 · a replay or static artefact reads 'Precomputed on <GPU> (<GB> GB, power limit <W> W) on <date>', the memory in GiB (16 GB on the reference machine)", async () => {
    const run = card("r1", gpu);
    await renderApp(
      createElement(WhereRanBlock, {
        artefacts: [
          toolArtefact("a-replay", "warp", { run_id: "r1", lane: "replay" }),
          toolArtefact("a-static", "warp", {
            run_id: "r1",
            lane: "static",
            kind: "image",
            budget_class: "own-code",
          }),
        ] as never,
        runs: [run],
      }),
    );
    for (const id of ["a-replay", "a-static"]) {
      const li = block("where-ran").querySelector(`li[data-artefact="${id}"]`);
      expect(li?.textContent, id).toContain(
        "Precomputed on NVIDIA RTX 5000 Ada Generation Laptop GPU (16 GB, power limit 175 W) on 2026-10-07",
      );
    }
  });

  it("FR-019-16 · the memory is the run card's total, never a constant: 24 GiB and 8 GiB read 24 GB and 8 GB; a fractional power limit keeps its fraction", async () => {
    const runs = [
      card("r24", { ...gpu, vram_total_bytes: 25_769_803_776, power_limit_enforced_w: 87.5 }),
      card("r8", { ...gpu, vram_total_bytes: 8_589_934_592 }),
    ];
    await renderApp(
      createElement(WhereRanBlock, {
        artefacts: [
          toolArtefact("x24", "warp", { run_id: "r24" }),
          toolArtefact("x8", "warp", { run_id: "r8" }),
        ] as never,
        runs,
      }),
    );
    expect(block("where-ran").querySelector('li[data-artefact="x24"]')?.textContent).toContain(
      "(24 GB, power limit 87.5 W)",
    );
    expect(block("where-ran").querySelector('li[data-artefact="x8"]')?.textContent).toContain(
      "(8 GB, power limit 175 W)",
    );
  });

  it("FR-019-16 · the date is the UTC date of the run's creation time", async () => {
    await renderApp(
      createElement(WhereRanBlock, {
        artefacts: [toolArtefact("a", "warp", { run_id: "rz" })] as never,
        runs: [card("rz", gpu, "2026-10-07T23:59:59-03:00")],
      }),
    );
    expect(text("where-ran")).toContain("on 2026-10-08");
  });

  it("FR-019-16 · a missing run card, a run without a GPU or a null power limit never prints null, undefined or NaN", async () => {
    await renderApp(
      createElement(WhereRanBlock, {
        artefacts: [
          toolArtefact("no-run", "warp", { run_id: "gone" }),
          toolArtefact("no-gpu", "warp", { run_id: "rn" }),
          toolArtefact("no-limit", "warp", { run_id: "rl" }),
        ] as never,
        runs: [card("rn", null), card("rl", { ...gpu, power_limit_enforced_w: null })],
      }),
    );
    expect(text("where-ran")).not.toMatch(/null|undefined|NaN|Invalid Date/);
    expect(block("where-ran").querySelectorAll("li[data-artefact]")).toHaveLength(3);
  });

  it("FR-019-16 · with no artefact the block has no list entry", async () => {
    await renderApp(createElement(WhereRanBlock, { artefacts: [], runs: [] }));
    expect(block("where-ran").querySelectorAll("li[data-artefact]")).toHaveLength(0);
  });
});

describe("Limits and failures (FR-019-17)", () => {
  const failed = makeStage("s62_accel", "tensorrt", {
    key: { id: "s62_accel", variant: "fp8" },
    status: "failed",
    error_class: "invalid-result",
    exit_code: 3,
    attempts: [{ n: 1, error_class: "invalid-result", duration_s: 41.5 }],
    params: { precision: "fp8" },
    log_tail: "parity check failed: max deviation 0.083 > 0.01",
  });
  const retried = makeStage("s62_accel", "tensorrt", {
    key: { id: "s62_accel", variant: "fp16" },
    status: "succeeded",
    attempts: [
      { n: 1, error_class: "oom", duration_s: 12.25 },
      { n: 2, error_class: null, duration_s: 33 },
    ],
  });
  const fine = makeStage("s62_accel", "tensorrt", {
    key: { id: "s62_accel", variant: "fp32" },
    status: "succeeded",
    attempts: [{ n: 1, error_class: null, duration_s: 20 }],
  });
  const other = makeStage("s30_train", "pytorch", {
    status: "failed",
    error_class: "oom",
    exit_code: 137,
    attempts: [{ n: 1, error_class: "oom", duration_s: 99 }],
  });
  const run = makeRunCard({
    run_id: "20261009T080000Z-trt",
    stages: [failed, retried, fine, other],
  } as never);

  it("FR-019-17 · lists the registry's recorded limit (its notice)", async () => {
    await renderApp(
      createElement(LimitsBlock, {
        tool: makeTool("tensorrt", { notice: "Proprietary runtime: engines are never published." }) as never,
        runs: [],
      }),
    );
    expect(block("limits").querySelector('[data-testid="limit"]')?.textContent).toContain(
      "Proprietary runtime: engines are never published.",
    );
    expect(block("limits").querySelector("h2")?.textContent).toBe("Limits and failures");
  });

  it("FR-019-17 · lists every failed or rejected variant of this tool's published runs with its numbers, and no variant of another tool", async () => {
    await renderApp(createElement(LimitsBlock, { tool: makeTool("tensorrt") as never, runs: [run] }));
    const items = Array.from(block("limits").querySelectorAll('[data-testid="failed-variant"]')).map(
      (e) => e.textContent ?? "",
    );
    const rejected = items.find((i) => i.includes("fp8")) ?? "";
    for (const needle of ["s62_accel", "fp8", "invalid-result", "41.5", "20261009T080000Z-trt", "0.083"])
      expect(rejected, needle).toContain(needle);
    expect(rejected, "the exit code 3").toMatch(/\b3\b/);
    const retriedItem = items.find((i) => i.includes("fp16")) ?? "";
    for (const needle of ["oom", "12.25"]) expect(retriedItem, needle).toContain(needle);
    expect(items.some((i) => i.includes("fp32"))).toBe(false);
    expect(items.some((i) => i.includes("s30_train"))).toBe(false);
    expect(items).toHaveLength(2);
  });

  it("FR-019-17 · with no recorded limit and no failure the block says so without inventing any", async () => {
    await renderApp(createElement(LimitsBlock, { tool: makeTool("tensorrt") as never, runs: [] }));
    expect(block("limits").querySelectorAll('[data-testid="failed-variant"]')).toHaveLength(0);
    expect(text("limits")).not.toMatch(/undefined|null/);
  });

  it("FR-019-17 · a log tail with markup is text and long text is truncated", async () => {
    const hostile = makeStage("s62_accel", "tensorrt", {
      status: "failed",
      error_class: "invalid-result",
      log_tail: `<script>alert(1)</script>${"L".repeat(4000)}`,
      attempts: [{ n: 1, error_class: "invalid-result" }],
    });
    await renderApp(
      createElement(LimitsBlock, {
        tool: makeTool("tensorrt") as never,
        runs: [makeRunCard({ stages: [hostile] } as never)],
      }),
    );
    expect(block("limits").querySelector("script")).toBeNull();
    expect(text("limits").length).toBeLessThan(2500);
  });
});

describe("Reproduce (FR-019-18)", () => {
  const run = (id: string, over: Record<string, unknown> = {}) =>
    makeRunCard({
      run_id: id,
      recipe: { id: "a2-haulage", path: "cases/a2-haulage.yaml", sha256: "e".repeat(64) },
      profile: "laptop-rtx5000ada",
      stages: [makeStage("st56_encode", "nvenc-ffmpeg")],
      ...over,
    } as never);

  it("FR-019-18 · shows, per published run of the tool, the runner command with the run's recipe and profile", async () => {
    await renderApp(
      createElement(ReproduceBlock, {
        tool: makeTool("nvenc-ffmpeg") as never,
        runs: [run("20261007T120000Z-a2")],
      }),
    );
    const r = block("reproduce").querySelector('[data-run="20261007T120000Z-a2"]');
    expect(r).not.toBeNull();
    const commands = Array.from((r as Element).querySelectorAll("[data-command]")).map((c) => c.textContent);
    expect(commands).toContain("uv run studio run cases/a2-haulage.yaml --profile laptop-rtx5000ada");
    expect(block("reproduce").querySelector("h2")?.textContent).toBe("Reproduce");
  });

  it("FR-019-18 · only runs that contain a stage of this tool are listed", async () => {
    await renderApp(
      createElement(ReproduceBlock, { tool: makeTool("warp") as never, runs: [run("20261007T120000Z-a2")] }),
    );
    expect(block("reproduce").querySelectorAll("[data-run]")).toHaveLength(0);
  });

  it("FR-019-18 · a reference-only tool says it needs an NVIDIA RTX GPU and acceptance of the NVIDIA terms", async () => {
    await renderApp(
      createElement(ReproduceBlock, {
        tool: makeTool("ovrtx", { licence_class: "reference-only" }) as never,
        runs: [],
      }),
    );
    expect(text("reproduce")).toContain("needs an NVIDIA RTX GPU and acceptance of the NVIDIA terms");
  });

  it("FR-019-18 · an open tool does not carry that requirement", async () => {
    await renderApp(createElement(ReproduceBlock, { tool: makeTool("pytorch") as never, runs: [] }));
    expect(text("reproduce")).not.toContain("acceptance of the NVIDIA terms");
  });

  it("FR-019-18 · no absolute path, host name or user name reaches the page, whatever the run card holds", async () => {
    const dirty = run("20261007T120000Z-a2", {
      recipe: { id: "a2", path: WIN_PATH, sha256: "e".repeat(64) },
      profile: POSIX_PATH,
      notes: [`ran on host build-host-07 as user alice in ${WIN_PATH}`],
    });
    await renderApp(
      createElement(ReproduceBlock, { tool: makeTool("nvenc-ffmpeg") as never, runs: [dirty] }),
    );
    expect(text("reproduce")).not.toMatch(LEAK);
  });
});

describe("Alternatives rejected (FR-019-19)", () => {
  it("FR-019-19 · lists each rejected alternative with its reason, in the registry's order", async () => {
    const alternatives = [
      { name: "OR-Tools routing", reason: "same batch formulation" },
      { name: "Gurobi", reason: "proprietary solver" },
    ];
    await renderApp(
      createElement(AlternativesBlock, {
        tool: makeTool("cuopt", { alternatives_rejected: alternatives }) as never,
      }),
    );
    const items = Array.from(block("alternatives").querySelectorAll('[data-testid="alternative"]'));
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("OR-Tools routing");
    expect(items[0]?.textContent).toContain("same batch formulation");
    expect(items[1]?.textContent).toContain("Gurobi");
    expect(items[1]?.textContent).toContain("proprietary solver");
    expect(block("alternatives").querySelector("h2")?.textContent).toBe("Alternatives rejected");
  });

  it("FR-019-19 · a tool with no recorded alternatives lists none and prints no placeholder text of a value", async () => {
    await renderApp(createElement(AlternativesBlock, { tool: makeTool("warp") as never }));
    expect(block("alternatives").querySelectorAll('[data-testid="alternative"]')).toHaveLength(0);
    expect(text("alternatives")).not.toMatch(/undefined|null/);
  });

  it("FR-019-19 · names and reasons with markup are text", async () => {
    await renderApp(
      createElement(AlternativesBlock, {
        tool: makeTool("warp", {
          alternatives_rejected: [{ name: "<i>x</i>", reason: "<script>alert(1)</script>" }],
        }) as never,
      }),
    );
    expect(block("alternatives").querySelector("i, script")).toBeNull();
  });
});
