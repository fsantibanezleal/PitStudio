// T-020-034 [red] · FR-020-27: the Cosmos tab shows, per question type, balanced accuracy with its 95 % CI for Cosmos Reason 2, Qwen3-VL-2B and the detector + geometric rule, the Q8_0 versus BF16 agreement against 95 %, the McNemar
// p-value of Cosmos versus Qwen, and the attribution "Built on NVIDIA Cosmos"; no Cosmos result is a headline KPI on `/` or on a case page. E2E half (the headline rule on the built pages): web/e2e/t_020_034_cosmos_headline.spec.ts.
//
// Expected API: `~/results/tabs/CosmosTab` (web/src/results/tabs/CosmosTab.tsx): named export CosmosTab({ rows: ComparisonRow[] }), the rows of the published `cosmos` bundles (DC-020-02: estimate rows with `group` = the question type,
// `system` = "Cosmos Reason 2" | "Qwen3-VL-2B" | "detector + geometric rule", metric `balanced_accuracy`; a `mcnemar` row per question type; an estimate row of metric `q8_bf16_agreement` with its threshold).
// Hooks: [data-testid="cosmos-type"][data-qtype="<group>"] per question type (in the order of first appearance) holding one [data-testid="cosmos-system"][data-system] per system with [data-field="value"] and [data-field="interval"] ("[lo, hi]", 95 %),
//   "Not yet run" for a system with no row of that type; [data-testid="cosmos-mcnemar"] with the p-value and the verdict of FR-020-22 (never the stored one); [data-testid="q8-agreement"][data-met] with the value and the threshold; [data-testid="cosmos-attribution"].
// Oracles: the valid cosmos bundle of DC-020-02 (specs/020-web-knowledge/contracts/examples/results.valid-cosmos.json: person-in-zone, Cosmos 0.81, Qwen 0.78, McNemar p = 0.27 with b = 31, c = 22, Q8_0 agreement 0.97 against 0.95),
// the decision rule of FR-020-22 (p >= 0.05: "no significant difference"), hand-built variations.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { CosmosTab } from "~/results/tabs/CosmosTab";
import { renderApp } from "~/test-support/render";

const bundle = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../specs/020-web-knowledge/contracts/examples/results.valid-cosmos.json",
    ),
    "utf8",
  ),
) as { rows: Array<Record<string, unknown>> };
const render = (rows: unknown[] = bundle.rows, lang: "en" | "es" = "en") =>
  renderApp(createElement(CosmosTab, { rows: rows as never }), { lang });
const type = (id: string) =>
  document.querySelector<HTMLElement>(`[data-testid="cosmos-type"][data-qtype="${id}"]`) as HTMLElement;
const system = (qtype: string, s: string) =>
  type(qtype).querySelector<HTMLElement>(`[data-testid="cosmos-system"][data-system="${s}"]`) as HTMLElement;
const mc = (b: number, c: number, p: number) => ({
  kind: "mcnemar",
  group: "person-in-zone",
  metric: {
    id: "balanced_accuracy",
    name: { en: "balanced accuracy", es: "exactitud balanceada" },
    unit: "1",
    orientation: "higher-is-better",
  },
  challenger: "Cosmos Reason 2",
  baseline: "Qwen3-VL-2B",
  pairing_unit: { en: "question", es: "pregunta" },
  n: 400,
  b,
  c,
  p_value: p,
});

describe("balanced accuracy per question type (FR-020-27)", () => {
  it("FR-020-27 · the question type of the example has its group, with Cosmos 0.81 and Qwen 0.78 and their 95 % intervals", async () => {
    await render();
    expect(type("person-in-zone")).not.toBeNull();
    const cosmos = system("person-in-zone", "Cosmos Reason 2");
    expect(cosmos.querySelector('[data-field="value"]')?.textContent).toContain("0.81");
    expect(cosmos.querySelector('[data-field="interval"]')?.textContent).toMatch(/0\.77/);
    expect(cosmos.querySelector('[data-field="interval"]')?.textContent).toMatch(/0\.85/);
    expect(cosmos.querySelector('[data-field="interval"]')?.textContent).toMatch(/95/);
    expect(
      system("person-in-zone", "Qwen3-VL-2B").querySelector('[data-field="value"]')?.textContent,
    ).toContain("0.78");
  });

  it("FR-020-27 · the detector + geometric rule has a slot in every question type: 'Not yet run' when it has no row", async () => {
    await render();
    const detector = system("person-in-zone", "detector + geometric rule");
    expect(detector).not.toBeNull();
    expect(detector.textContent).toContain("Not yet run");
    expect(detector.textContent?.match(/\d/g) ?? []).toEqual([]);
  });

  it("FR-020-27 · several question types each get their group and their three systems, in the order of the bundle", async () => {
    const rows = ["person-in-zone", "vehicle-proximity", "bench-condition"].flatMap((g) =>
      ["Cosmos Reason 2", "Qwen3-VL-2B", "detector + geometric rule"].map((s, i) => ({
        kind: "estimate",
        group: g,
        metric: {
          id: "balanced_accuracy",
          name: { en: "balanced accuracy", es: "exactitud balanceada" },
          unit: "1",
          orientation: "higher-is-better",
        },
        system: s,
        n: 400,
        value: 0.6 + i / 10,
        interval: { lo: 0.55 + i / 10, hi: 0.65 + i / 10, level: 0.95, method: "percentile-bootstrap" },
      })),
    );
    await render(rows);
    expect(
      Array.from(document.querySelectorAll('[data-testid="cosmos-type"]')).map((e) =>
        e.getAttribute("data-qtype"),
      ),
    ).toEqual(["person-in-zone", "vehicle-proximity", "bench-condition"]);
    for (const g of ["person-in-zone", "vehicle-proximity", "bench-condition"]) {
      expect(
        system(g, "detector + geometric rule").querySelector('[data-field="value"]')?.textContent,
      ).toContain("0.8");
    }
  });
});

describe("McNemar of Cosmos versus Qwen (FR-020-27, FR-020-22)", () => {
  it("FR-020-27 · shows the p-value of the example (0.27) and, because p >= 0.05, 'no significant difference'", async () => {
    await render();
    const el = type("person-in-zone").querySelector('[data-testid="cosmos-mcnemar"]');
    expect(el?.textContent).toContain("0.27");
    expect(el?.textContent).toContain("no significant difference");
    expect(el?.textContent).not.toMatch(/better than/);
  });

  it("FR-020-27 · a small p-value reads 'Cosmos Reason 2 better than Qwen3-VL-2B' when Cosmos wins more discordant pairs, and the reverse when Qwen does", async () => {
    await render([...bundle.rows.filter((r) => r.kind !== "mcnemar"), mc(40, 8, 0.00001)]);
    expect(type("person-in-zone").querySelector('[data-testid="cosmos-mcnemar"]')?.textContent).toContain(
      "Cosmos Reason 2 better than Qwen3-VL-2B",
    );
    document.body.innerHTML = "";
    await render([...bundle.rows.filter((r) => r.kind !== "mcnemar"), mc(8, 40, 0.00001)]);
    expect(type("person-in-zone").querySelector('[data-testid="cosmos-mcnemar"]')?.textContent).toContain(
      "Qwen3-VL-2B better than Cosmos Reason 2",
    );
  });

  it("FR-020-27 · p exactly 0.05 is no difference, and a stored verdict is ignored", async () => {
    const lying = { ...mc(40, 8, 0.05), verdict: "challenger-better" };
    await render([...bundle.rows.filter((r) => r.kind !== "mcnemar"), lying]);
    expect(type("person-in-zone").querySelector('[data-testid="cosmos-mcnemar"]')?.textContent).toContain(
      "no significant difference",
    );
  });
});

describe("Q8_0 versus BF16 (FR-020-27)", () => {
  it("FR-020-27 · the agreement of the example, 0.97, is shown against 95 % and is met", async () => {
    await render();
    const el = document.querySelector('[data-testid="q8-agreement"]');
    expect(el?.textContent).toContain("0.97");
    expect(el?.textContent).toMatch(/95|0\.95/);
    expect(el?.getAttribute("data-met")).toBe("true");
  });

  it("FR-020-27 · an agreement of 0.93 is not met, and 0.95 exactly is met", async () => {
    const q8 = (v: number) => ({
      ...(bundle.rows.find((r) => (r.metric as { id: string }).id === "q8_bf16_agreement") as object),
      value: v,
    });
    await render([q8(0.93)]);
    expect(document.querySelector('[data-testid="q8-agreement"]')?.getAttribute("data-met")).toBe("false");
    document.body.innerHTML = "";
    await render([q8(0.95)]);
    expect(document.querySelector('[data-testid="q8-agreement"]')?.getAttribute("data-met")).toBe("true");
  });

  it("FR-020-27 · with no agreement row it reads 'Not yet run' and no number", async () => {
    await render([]);
    const el = document.querySelector('[data-testid="q8-agreement"]');
    expect(el?.textContent).toContain("Not yet run");
    expect(el?.textContent?.match(/\d/g) ?? []).toEqual([]);
  });
});

describe("attribution and hostile input (FR-020-27)", () => {
  it("FR-020-27 · the tab carries 'Built on NVIDIA Cosmos', with and without results, in both languages", async () => {
    for (const lang of ["en", "es"] as const) {
      for (const rows of [bundle.rows, []]) {
        const { unmount } = await render(rows, lang);
        expect(
          document.querySelector('[data-testid="cosmos-attribution"]')?.textContent,
          `${lang} ${rows.length}`,
        ).toContain("NVIDIA Cosmos");
        if (lang === "en")
          expect(document.querySelector('[data-testid="cosmos-attribution"]')?.textContent).toContain(
            "Built on NVIDIA Cosmos",
          );
        unmount();
      }
    }
  });

  it("FR-020-27 · hostile rows (NaN, markup in a system name, a null row) neither crash the tab nor print NaN", async () => {
    await render([
      { ...(bundle.rows[0] as object), value: Number.NaN, system: "<img src=x onerror=alert(1)>" },
      null,
      "x",
      { kind: "estimate" },
    ]);
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(document.body.textContent).not.toMatch(/NaN/);
  });
});
