// T-020-020 [red] · FR-020-17 (/methods lists M1 to M23 from the method registry with tier, implementation and SPDX licence, lane, cases, learned flag and status) and FR-020-18 (each method page shows what the method computes, its baseline and
// comparison design (metric with unit and orientation, pairing unit, number of pairs), its pre-registered acceptance criterion as recorded in the registry, its lane with the measured gate values or the word "estimate", a link to the case
// Simulate tab where it runs live, its docs page, and its status, "Not yet run" until a published result exists). E2E half: web/e2e/t_020_020_methods.spec.ts.
//
// Expected API (web/src/methods/):
//   MethodsIndex.tsx   MethodsIndex({ methods: MethodEntry[]; statuses?: Record<string, "pass" | "fail" | "not-yet-run"> }) (DC-020-01 entries): table[data-testid="methods-table"] with tr[data-method="<M id>"] in registry order, cells
//       [data-field="id|name|tiers|implementation|spdx|lanes|cases|learned|status"], the id linking to `/methods/<m01..m23>/` (the id lower-cased with its number padded to two digits); learned shows "learned" or "classical" wording
//       and `data-learned`; status defaults to "Not yet run".
//   MethodPage.tsx     MethodPage({ method: MethodEntry; measurement?: LaneMeasurement | null; status?: "pass" | "fail" | "not-yet-run" }): h1 = the method name in the active language; [data-testid="computes"] the implementation text;
//       [data-testid="design"] (only for a method with a `comparison`): baseline, metric with unit symbol and orientation words, pairing unit, n; [data-testid="criterion"] the recorded criterion text in the active language with its requirement
//       (SC-nnn-nn) and spec; [data-testid="lane"]: each lane of the method, and the measured gate values of `measurement` (interaction_ms, run_ms_t2, max_asset_bytes and the measuring tier, date and browser) or the word "estimate" when there is none;
//       [data-testid="simulate-links"]: one a[href="/cases/<case>/?tab=simulate"] per case of the method when its lanes include `live`, none otherwise; [data-testid="docs-link"] the docs page of the registry; [data-testid="status"].
// Oracles: the valid method registry of DC-020-01 (specs/020-web-knowledge/contracts/examples/methods.valid.json: 23 entries; M2 classical, lanes live and precompute, cases A1 A2 B1 C3; M4 learned with its comparison design and criterion SC-007-01),
// the lane-measurement record of DC-018-06 (hand-built), the EARS text.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { screen } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { MethodPage } from "~/methods/MethodPage";
import { MethodsIndex } from "~/methods/MethodsIndex";
import { renderApp } from "~/test-support/render";

type Method = {
  id: string;
  name: { en: string; es: string };
  tiers: string[];
  implementation: string;
  spdx: string[];
  lanes: string[];
  learned: boolean;
  cases: string[];
  docs_page: string;
  comparison?: {
    baseline: { en: string; es: string };
    metric: { name: { en: string; es: string }; unit: string; orientation: string };
    pairing_unit: { en: string; es: string };
    n: number;
  };
  criterion?: { text: { en: string; es: string }; requirement: string; spec: string };
};
const methods = (
  JSON.parse(
    readFileSync(
      resolve(
        dirname(fileURLToPath(import.meta.url)),
        "../../../specs/020-web-knowledge/contracts/examples/methods.valid.json",
      ),
      "utf8",
    ),
  ) as { methods: Method[] }
).methods;
const byId = (id: string) => methods.find((m) => m.id === id) as Method;
const MEASURED = {
  web_drivable: true,
  max_asset_bytes: 1_048_576,
  interaction_ms: 4,
  run_ms_t2: 120,
  trace_bytes: null,
  measured: { tier: "T2", date: "2026-10-11", browser: "chromium" },
};
const page = (m: Method, extra: Record<string, unknown> = {}, lang: "en" | "es" = "en") =>
  renderApp(createElement(MethodPage, { method: m as never, ...extra }), { lang });
const q = (sel: string) => document.querySelector<HTMLElement>(sel);

describe("the method index (FR-020-17)", () => {
  it("FR-020-17 · lists the 23 methods M1 to M23 in the order of the registry", async () => {
    await renderApp(createElement(MethodsIndex, { methods: methods as never }));
    const ids = Array.from(document.querySelectorAll("tr[data-method]")).map((r) =>
      r.getAttribute("data-method"),
    );
    expect(ids).toEqual(Array.from({ length: 23 }, (_, i) => `M${i + 1}`));
  });

  it("FR-020-17 · a row shows tier, implementation, SPDX licence, lane, cases, learned flag and status", async () => {
    await renderApp(createElement(MethodsIndex, { methods: methods as never }));
    const f = (id: string, name: string) =>
      q(`tr[data-method="${id}"] [data-field="${name}"]`)?.textContent ?? "";
    expect(f("M4", "name")).toContain("PPO dispatch");
    expect(f("M4", "tiers")).toContain("sota");
    expect(f("M4", "implementation")).toContain("PyTorch PPO in a vectorised environment");
    expect(f("M4", "spdx")).toContain("Apache-2.0");
    expect(f("M4", "spdx")).toContain("BSD-3-Clause");
    expect(f("M4", "lanes")).toMatch(/precompute/);
    expect(f("M4", "lanes")).toMatch(/live/);
    expect(f("M4", "cases")).toContain("A1");
    expect(q('tr[data-method="M4"] [data-field="learned"]')?.getAttribute("data-learned")).toBe("true");
    expect(q('tr[data-method="M2"] [data-field="learned"]')?.getAttribute("data-learned")).toBe("false");
    expect(f("M2", "cases")).toMatch(/A1.*A2.*B1.*C3/);
    expect(f("M4", "status")).toContain("Not yet run");
  });

  it("FR-020-17 · each id links to its page: M2 to /methods/m02/, M23 to /methods/m23/", async () => {
    await renderApp(createElement(MethodsIndex, { methods: methods as never }));
    expect(q('tr[data-method="M2"] a')?.getAttribute("href")).toBe("/methods/m02/");
    expect(q('tr[data-method="M23"] a')?.getAttribute("href")).toBe("/methods/m23/");
    expect(q('tr[data-method="M10"] a')?.getAttribute("href")).toBe("/methods/m10/");
  });

  it("FR-020-17 · a computed status replaces 'Not yet run' for the method that has one", async () => {
    await renderApp(
      createElement(MethodsIndex, { methods: methods as never, statuses: { M4: "pass", M5: "fail" } }),
    );
    expect(q('tr[data-method="M4"] [data-field="status"]')?.textContent).toMatch(/pass/i);
    expect(q('tr[data-method="M5"] [data-field="status"]')?.textContent).toMatch(/fail/i);
    expect(q('tr[data-method="M8"] [data-field="status"]')?.textContent).toContain("Not yet run");
  });

  it("FR-020-17 · the names follow the language", async () => {
    await renderApp(createElement(MethodsIndex, { methods: methods as never }), { lang: "es" });
    expect(q('tr[data-method="M4"] [data-field="name"]')?.textContent).toContain("Despacho con PPO");
  });

  it("FR-020-17 · hostile registry text (markup in a name or an implementation) is escaped", async () => {
    const evil = methods.map((m, i) =>
      i === 0
        ? {
            ...m,
            name: { en: "<img src=x onerror=alert(1)>", es: "<b>x</b>" },
            implementation: "<script>alert(1)</script>",
          }
        : m,
    );
    const { container } = await renderApp(createElement(MethodsIndex, { methods: evil as never }));
    expect(container.querySelector("img[src='x'], b, script")).toBeNull();
  });
});

describe("a method page (FR-020-18)", () => {
  it("FR-020-18 · shows what the method computes, its name and its docs page", async () => {
    await page(byId("M4"));
    expect(q("h1")?.textContent).toContain("PPO dispatch");
    expect(q('[data-testid="computes"]')?.textContent).toContain(
      "PyTorch PPO in a vectorised environment, ONNX in the browser",
    );
    expect(q('[data-testid="docs-link"] a, a[data-testid="docs-link"]')?.getAttribute("href")).toContain(
      "docs/methods/m04-ppo-dispatch.md",
    );
  });

  it("FR-020-18 · a learned method shows its baseline and comparison design: metric with unit and orientation, pairing unit, n", async () => {
    await page(byId("M4"));
    const d = q('[data-testid="design"]')?.textContent ?? "";
    for (const needle of ["SPTF and two-stage LP", "throughput", "t/h", "seed", "30"])
      expect(d, needle).toContain(needle);
    expect(d.toLowerCase()).toMatch(/higher is better|higher-is-better/);
  });

  it("FR-020-18 · its pre-registered criterion is shown as recorded, with the success criterion and the owning spec", async () => {
    await page(byId("M4"));
    const c = q('[data-testid="criterion"]')?.textContent ?? "";
    expect(c).toContain(
      "beats SPTF or LP only if the paired 95 % CI of the t/h difference excludes 0 (>= 30 paired seeds)",
    );
    expect(c).toContain("SC-007-01");
    expect(c).toContain("007-haulage-dispatch");
  });

  it("FR-020-18 · in Spanish the design and the criterion are in Spanish", async () => {
    await page(byId("M4"), {}, "es");
    expect(q('[data-testid="criterion"]')?.textContent).toContain(
      "supera a SPTF o LP solo si el IC pareado de 95 %",
    );
    expect(q('[data-testid="design"]')?.textContent).toContain("SPTF y LP en dos etapas");
    expect(q('[data-testid="design"]')?.textContent).toContain("semilla");
  });

  it("FR-020-18 · a classical method has no comparison design and no criterion block, and says so without a placeholder number", async () => {
    await page(byId("M2"));
    expect(q('[data-testid="design"]')).toBeNull();
    expect(q('[data-testid="criterion"]')).toBeNull();
    expect(q("main, body")?.textContent).not.toMatch(/undefined|null|NaN/);
  });

  it("FR-020-18 · the lane shows the measured gate values (interaction 4 ms, run 120 ms at T2, 1,048,576 bytes, the tier, date and browser) when there is a measurement", async () => {
    await page(byId("M4"), { measurement: MEASURED });
    const l = q('[data-testid="lane"]')?.textContent ?? "";
    for (const needle of ["precompute", "live", "4", "120", "T2", "2026-10-11", "chromium"])
      expect(l, needle).toContain(needle);
    expect(l).toMatch(/1[,.  ]?048[,.  ]?576|1\.0\d? MB|1 MiB/);
    expect(l).not.toContain("estimate");
  });

  it("FR-020-18 · without a measurement the lane reads 'estimate'", async () => {
    await page(byId("M4"));
    expect(q('[data-testid="lane"]')?.textContent).toContain("estimate");
    await page(byId("M4"), { measurement: null });
    expect(q('[data-testid="lane"]')?.textContent).toContain("estimate");
  });

  it("FR-020-18 · a method that runs live links to the Simulate tab of each of its cases: M2 to A1, A2, B1 and C3", async () => {
    await page(byId("M2"));
    const hrefs = Array.from(document.querySelectorAll('[data-testid="simulate-links"] a')).map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).toEqual([
      "/cases/A1/?tab=simulate",
      "/cases/A2/?tab=simulate",
      "/cases/B1/?tab=simulate",
      "/cases/C3/?tab=simulate",
    ]);
  });

  it("FR-020-18 · a method with no live lane has no Simulate link (M22 Cosmos: precompute only)", async () => {
    await page(byId("M22"));
    expect(document.querySelectorAll('[data-testid="simulate-links"] a')).toHaveLength(0);
  });

  it("FR-020-18 · the status is 'Not yet run' until a published result exists, then pass or fail", async () => {
    await page(byId("M4"));
    expect(q('[data-testid="status"]')?.textContent).toContain("Not yet run");
    await page(byId("M4"), { status: "pass" });
    expect(screen.getAllByTestId("status").at(-1)?.textContent).toMatch(/pass/i);
    await page(byId("M4"), { status: "fail" });
    expect(screen.getAllByTestId("status").at(-1)?.textContent).toMatch(/fail/i);
  });

  it("FR-020-18 · hostile registry text and a hostile case id are escaped or refused", async () => {
    const evil = {
      ...byId("M2"),
      implementation: "<img src=x onerror=alert(1)>",
      cases: ["A1", "../../etc", "A2<script>"],
    };
    const { container } = await page(evil as never);
    expect(container.querySelector("img[src='x'], script")).toBeNull();
    const hrefs = Array.from(container.querySelectorAll('[data-testid="simulate-links"] a')).map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).toEqual(["/cases/A1/?tab=simulate"]);
  });
});
