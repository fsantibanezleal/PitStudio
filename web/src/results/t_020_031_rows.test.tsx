// T-020-031 [red] · FR-020-20, FR-020-21, FR-020-31 (unit half): results tabs, comparison rows and "Not yet run".
//
// Expected modules and API (the test fixes them):
//   ~/results/tabs            export const RESULTS_TAB_IDS: readonly string[]
//                               = learned-vs-classical, sim-to-real, parity, dr-ablation, isaac-lab, cosmos, acceleration   (FR-020-20 order;
//                               the first five are the `tab` enum of the results bundle schema DC-020-02)
//                             export function parseResultsTab(search: string): string
//                               value of the FIRST `tab` parameter of a query string ("?tab=parity" or "tab=parity") when it is exactly one of the
//                               ids; otherwise the default, the first id. Unknown, empty, upper-case, markup, control-character, "__proto__" and
//                               over-long (> 2,000 characters) values give the default and never throw.
//   ~/results/ComparisonRows  export function ComparisonRows(props: { rows: ComparisonRow[] })     rows as in results.schema.json
//                               (paired_row, mcnemar_row, single_event_row, estimate_row); active language from the shell's i18n.
//     DOM: one `[data-comparison-row="paired" | "mcnemar" | "single-event" | "estimate"]` per row, in order, no extra summary row. A row shows
//       - the metric name (`metric.name[lang]`), its unit text and its orientation as words matching /higher is better/i or /lower is better/i;
//       - paired / mcnemar / single-event: challenger and baseline labels; estimate: the system label;
//       - paired: the pairing unit (`pairing_unit[lang]`), "n = <n>", the 95 % interval lo and hi with its method as words
//         ("paired t" or "paired bootstrap") and the verdict; mcnemar: n, the discordant counts "b = .." and "c = .." and the p-value;
//       - the verdict is DERIVED by the decision rule of FR-020-22 from the interval (oriented by the metric) or from p and b, c, never copied
//         from the stored field: "<challenger> better than <baseline>" only when the oriented interval has lo > 0, "<baseline> better than
//         <challenger>" only when hi < 0, otherwise "no significant difference"; McNemar needs p < 0.05 and takes the direction from b versus c;
//         single-event rows say "single real event — no significance test" and show no interval and no "better than";
//       - several rows that share a `group` are shown together, and nothing computes a composite score.
//   ~/results/NotYetRun       export function NotYetRun(props: { items: Array<{ id: string; title: string; reports: string; criterion: string }> })
//     DOM: one `[data-pending="<id>"]` per item containing its title, the text "Not yet run", `reports` (what will be reported) and `criterion`
//       (the pre-registered acceptance criterion), and no other number (no placeholder value).
// Oracles: FR-020-21 / FR-020-22 / FR-020-31 text; hand-written rows with known intervals and counts.
import { within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComparisonRows } from "~/results/ComparisonRows";
import { NotYetRun } from "~/results/NotYetRun";
import { parseResultsTab, RESULTS_TAB_IDS } from "~/results/tabs";
import { props, renderApp } from "~/test-support/render";

const name = (en: string, es: string) => ({ en, es });
const higher = { id: "map50", name: name("mAP50", "mAP50"), unit: "1", orientation: "higher-is-better" };
const lower = {
  id: "queue_time",
  name: name("Queue time", "Tiempo de cola"),
  unit: "min",
  orientation: "lower-is-better",
};

function paired(over: Record<string, unknown> = {}) {
  return {
    kind: "paired",
    metric: higher,
    challenger: "PPO policy",
    baseline: "Match-factor greedy",
    pairing_unit: name("seed", "semilla"),
    n: 40,
    interval: { lo: 1.25, hi: 3.5, level: 0.95, method: "paired-t" },
    verdict: "challenger-better",
    ...over,
  };
}

async function rows(list: unknown[], lang: "en" | "es" = "en") {
  return renderApp(<ComparisonRows rows={props(list)} />, { lang });
}

function row(container: HTMLElement, index = 0): HTMLElement {
  const all = container.querySelectorAll<HTMLElement>("[data-comparison-row]");
  const el = all[index];
  if (!el) throw new Error(`no row ${index}`);
  return el;
}

describe("results tabs (FR-020-20)", () => {
  it("FR-020-20 · lists the seven tabs in the order of the spec", () => {
    expect([...RESULTS_TAB_IDS]).toEqual([
      "learned-vs-classical",
      "sim-to-real",
      "parity",
      "dr-ablation",
      "isaac-lab",
      "cosmos",
      "acceleration",
    ]);
  });

  it("FR-020-20 · ?tab= selects exactly the listed ids", () => {
    expect(RESULTS_TAB_IDS).toHaveLength(7);
    for (const id of RESULTS_TAB_IDS) {
      expect(parseResultsTab(`?tab=${id}`)).toBe(id);
      expect(parseResultsTab(`tab=${id}&x=1`)).toBe(id);
      expect(parseResultsTab(`?x=1&tab=${id}`)).toBe(id);
    }
  });

  it("FR-020-20 · an absent, unknown or hostile ?tab= falls back to the first tab and never throws", () => {
    const first = "learned-vs-classical";
    const hostile = [
      "",
      "?",
      "?tab=",
      "?tab=nope",
      "?tab=PARITY",
      "?tab=Parity",
      "?tab=%00",
      "?tab=%3Cscript%3E",
      "?tab=__proto__",
      "?tab=constructor",
      "?tab=../results",
      `?tab=${"a".repeat(3000)}`,
      `?tab=${"parity".repeat(500)}`,
      "?tab=parity%20",
      "?tab=%E2%80%AEparity",
      "?other=parity",
    ];
    for (const search of hostile) expect(parseResultsTab(search), search.slice(0, 40)).toBe(first);
  });

  it("FR-020-20 · the first tab parameter wins when it is repeated", () => {
    expect(parseResultsTab("?tab=parity&tab=cosmos")).toBe("parity");
    expect(parseResultsTab("?tab=nope&tab=cosmos")).toBe("learned-vs-classical");
  });
});

describe("comparison rows (FR-020-21)", () => {
  it("FR-020-21 · a paired row shows metric, unit, orientation, challenger, baseline, pairing unit, n, the 95 % interval with its method and the verdict", async () => {
    const { container } = await rows([paired()]);
    const r = row(container);
    expect(r.dataset.comparisonRow).toBe("paired");
    const text = r.textContent ?? "";
    expect(text).toContain("mAP50");
    expect(text).toMatch(/higher is better/i);
    expect(text).toContain("PPO policy");
    expect(text).toContain("Match-factor greedy");
    expect(text).toContain("seed");
    expect(text).toMatch(/\bn\s*=\s*40\b/);
    expect(text).toMatch(/95\s?%/);
    expect(text).toContain("1.25");
    expect(text).toContain("3.5");
    expect(text).toMatch(/paired[ -]t\b/i);
    expect(text).toContain("PPO policy better than Match-factor greedy");
  });

  it("FR-020-21 · names the paired bootstrap when the interval was bootstrapped", async () => {
    const { container } = await rows([
      paired({ interval: { lo: -0.5, hi: 2, level: 0.95, method: "paired-bootstrap", resamples: 10000 } }),
    ]);
    expect(row(container).textContent).toMatch(/paired[ -]bootstrap/i);
    expect(row(container).textContent).not.toMatch(/paired[ -]t\b/i);
  });

  it("FR-020-21 · shows the unit and the lower-is-better orientation", async () => {
    const { container } = await rows([
      paired({ metric: lower, interval: { lo: -3, hi: -1, level: 0.95, method: "paired-t" } }),
    ]);
    const text = row(container).textContent ?? "";
    expect(text).toContain("Queue time");
    expect(text).toContain("min");
    expect(text).toMatch(/lower is better/i);
  });

  it("FR-020-21 · shows the row in Spanish names when the language is ES", async () => {
    const { container } = await rows(
      [paired({ metric: lower, interval: { lo: -3, hi: -1, level: 0.95, method: "paired-t" } })],
      "es",
    );
    expect(row(container).textContent).toContain("Tiempo de cola");
    expect(row(container).textContent).toContain("semilla");
  });

  it("FR-020-21 · a result with several axes shows all of them together and no composite score", async () => {
    const axes = [
      { id: "accuracy", name: name("Accuracy", "Exactitud"), unit: "%", orientation: "higher-is-better" },
      { id: "latency", name: name("Latency", "Latencia"), unit: "ms", orientation: "lower-is-better" },
      {
        id: "size",
        name: name("Model size", "Tamaño del modelo"),
        unit: "MB",
        orientation: "lower-is-better",
      },
      {
        id: "robustness",
        name: name("Robustness drop", "Caída de robustez"),
        unit: "pp",
        orientation: "lower-is-better",
      },
    ];
    const list = axes.map((metric) => paired({ group: "detector-nano", metric }));
    const { container } = await rows(list);
    const all = container.querySelectorAll("[data-comparison-row]");
    expect(all).toHaveLength(4);
    for (const axis of axes) expect(container.textContent).toContain(axis.name.en);
    expect(container.textContent).not.toMatch(/composite|overall|total score|combined score|weighted/i);
    expect(container.textContent).not.toMatch(/\bscore\b/i);
  });
});

describe("verdict is derived by the decision rule (FR-020-21, FR-020-22)", () => {
  const interval = (lo: number, hi: number) => ({ lo, hi, level: 0.95, method: "paired-t" });

  it("FR-020-21 · higher is better: lo > 0 gives the challenger, hi < 0 the baseline, an interval that straddles or touches 0 gives no difference", async () => {
    const cases: Array<[number, number, string]> = [
      [0.5, 2, "PPO policy better than Match-factor greedy"],
      [-2, -0.5, "Match-factor greedy better than PPO policy"],
      [-1, 1, "no significant difference"],
      [0, 2, "no significant difference"],
      [-2, 0, "no significant difference"],
    ];
    for (const [lo, hi, expected] of cases) {
      const { container, unmount } = await rows([
        paired({ interval: interval(lo, hi), verdict: "no-significant-difference" }),
      ]);
      const text = row(container).textContent ?? "";
      expect(text, `[${lo}, ${hi}]`).toContain(expected);
      if (expected === "no significant difference") expect(text).not.toMatch(/better than/);
      else expect(text).not.toContain("no significant difference");
      unmount();
    }
  });

  it("FR-020-21 · lower is better orients the interval: hi < 0 gives the challenger, lo > 0 the baseline", async () => {
    const cases: Array<[number, number, string]> = [
      [-3, -1, "PPO policy better than Match-factor greedy"],
      [1, 3, "Match-factor greedy better than PPO policy"],
      [-1, 1, "no significant difference"],
    ];
    for (const [lo, hi, expected] of cases) {
      const { container, unmount } = await rows([
        paired({ metric: lower, interval: interval(lo, hi), verdict: "no-significant-difference" }),
      ]);
      expect(row(container).textContent, `[${lo}, ${hi}]`).toContain(expected);
      unmount();
    }
  });

  it("FR-020-21 · a stored verdict that contradicts the interval is not shown", async () => {
    const { container } = await rows([paired({ interval: interval(-1, 1), verdict: "challenger-better" })]);
    expect(row(container).textContent).toContain("no significant difference");
    expect(row(container).textContent).not.toMatch(/better than/);
  });

  it("FR-020-21 · a McNemar row needs p < 0.05 and takes the direction from the discordant counts", async () => {
    const mc = (b: number, c: number, p: number) => ({
      kind: "mcnemar",
      metric: {
        id: "agreement",
        name: name("Answer correct", "Respuesta correcta"),
        unit: "1",
        orientation: "higher-is-better",
      },
      challenger: "Cosmos Reason 2",
      baseline: "Qwen3-VL-2B",
      pairing_unit: name("question", "pregunta"),
      n: 120,
      b,
      c,
      p_value: p,
      verdict: "no-significant-difference",
    });
    const { container } = await rows([mc(18, 4, 0.012), mc(3, 15, 0.014), mc(12, 5, 0.143), mc(9, 9, 1)]);
    const texts = [0, 1, 2, 3].map((i) => row(container, i).textContent ?? "");
    expect(texts[0]).toContain("Cosmos Reason 2 better than Qwen3-VL-2B");
    expect(texts[0]).toMatch(/\bb\s*=\s*18\b/);
    expect(texts[0]).toMatch(/\bc\s*=\s*4\b/);
    expect(texts[0]).toContain("0.012");
    expect(texts[1]).toContain("Qwen3-VL-2B better than Cosmos Reason 2");
    expect(texts[2]).toContain("no significant difference");
    expect(texts[2]).not.toMatch(/better than/);
    expect(texts[3]).toContain("no significant difference");
  });

  it("FR-020-21 · a single real event shows both values, 'single real event — no significance test' and no interval or 'better than'", async () => {
    const { container } = await rows([
      {
        kind: "single-event",
        metric: {
          id: "lead_time",
          name: name("Lead time", "Tiempo de anticipación"),
          unit: "h",
          orientation: "higher-is-better",
        },
        challenger: "Inverse velocity",
        baseline: "Bayesian band",
        n: 1,
        challenger_value: 31.5,
        baseline_value: 12.25,
        verdict: "single-real-event",
      },
    ]);
    const r = row(container);
    expect(r.dataset.comparisonRow).toBe("single-event");
    expect(r.textContent).toContain("single real event — no significance test");
    expect(r.textContent).toContain("31.5");
    expect(r.textContent).toContain("12.25");
    expect(r.textContent).not.toMatch(/better than/);
    expect(r.textContent).not.toMatch(/95\s?%/);
  });

  it("FR-020-21 · an estimate row shows the system, its value, interval and the pre-registered threshold", async () => {
    const { container } = await rows([
      {
        kind: "estimate",
        metric: {
          id: "iou_ratio",
          name: name("TSTR/TRTR IoU ratio", "Razón IoU TSTR/TRTR"),
          unit: "1",
          orientation: "higher-is-better",
        },
        system: "U-Net on synthetic piles",
        n: 5,
        value: 0.93,
        interval: { lo: 0.9, hi: 0.96, level: 0.95, method: "paired-t" },
        threshold: { comparator: "ge", value: 0.8 },
      },
    ]);
    const r = row(container);
    expect(r.dataset.comparisonRow).toBe("estimate");
    expect(r.textContent).toContain("U-Net on synthetic piles");
    expect(r.textContent).toContain("0.93");
    expect(r.textContent).toContain("0.8");
  });
});

describe("hostile rows (FR-020-21)", () => {
  it("FR-020-21 · renders markup in labels as text", async () => {
    const evil = '<img src=x onerror="alert(1)">';
    const { container } = await rows([paired({ challenger: evil, baseline: evil })]);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain(evil);
  });

  it("FR-020-21 · an empty list renders no row and no number", async () => {
    const one = await rows([paired()]);
    expect(one.container.querySelectorAll("[data-comparison-row]")).toHaveLength(1);
    one.unmount();
    const { container } = await rows([]);
    expect(container.querySelectorAll("[data-comparison-row]")).toHaveLength(0);
    expect(container.textContent).not.toMatch(/NaN|undefined|null/);
  });

  it("FR-020-21 · a non-finite interval bound never prints NaN or Infinity and never claims a winner", async () => {
    for (const interval of [
      { lo: Number.NaN, hi: 2, level: 0.95, method: "paired-t" },
      { lo: 1, hi: Number.POSITIVE_INFINITY, level: 0.95, method: "paired-t" },
    ]) {
      const { container, unmount } = await rows([paired({ interval })]);
      expect(container.querySelectorAll("[data-comparison-row]")).toHaveLength(1);
      expect(container.textContent).toContain("mAP50");
      expect(container.textContent).not.toMatch(/NaN|Infinity/);
      expect(container.textContent).not.toMatch(/better than/);
      unmount();
    }
  });
});

describe("Not yet run (FR-020-31)", () => {
  const items = [
    {
      id: "ppo-dispatch",
      title: "PPO dispatch versus match-factor greedy",
      reports: "Paired difference in tonnes per hour over 40 seeds, 95 % interval",
      criterion: "Lower bound of the interval above 0 on at least 4 of 5 fleet sizes",
    },
    {
      id: "gns-granular",
      title: "GNS surrogate versus the DEM solver",
      reports: "Run-out error on held-out piles",
      criterion: "Median run-out error below 5 %",
    },
  ];

  it("FR-020-31 · shows 'Not yet run' with what will be reported and the pre-registered criterion, for each item", async () => {
    const { container } = await renderApp(<NotYetRun items={items} />);
    for (const item of items) {
      const el = container.querySelector<HTMLElement>(`[data-pending="${item.id}"]`);
      expect(el, item.id).not.toBeNull();
      const text = el?.textContent ?? "";
      expect(text).toContain(item.title);
      expect(text).toContain("Not yet run");
      expect(text).toContain(item.reports);
      expect(text).toContain(item.criterion);
    }
    expect(container.querySelectorAll("[data-pending]")).toHaveLength(2);
  });

  it("FR-020-31 · shows no placeholder number: removing the quoted texts leaves no digit", async () => {
    const { container } = await renderApp(<NotYetRun items={items} />);
    let text = container.textContent ?? "";
    expect(text.match(/Not yet run/g)).toHaveLength(items.length);
    for (const item of items)
      text = text.replace(item.title, "").replace(item.reports, "").replace(item.criterion, "");
    expect(text).not.toMatch(/\d/);
    expect(container.querySelectorAll("[data-comparison-row]")).toHaveLength(0);
    expect(within(container).queryAllByRole("table")).toHaveLength(0);
  });

  it("FR-020-31 · renders item text as text and an empty list as nothing", async () => {
    const evil = '<img src=x onerror="alert(1)">';
    const hostile = await renderApp(
      <NotYetRun items={[{ id: "x", title: evil, reports: evil, criterion: evil }]} />,
    );
    expect(hostile.container.querySelector("img")).toBeNull();
    expect(hostile.container.querySelectorAll("[data-pending]")).toHaveLength(1);
    expect(hostile.container.textContent).toContain(evil);
    hostile.unmount();
    const empty = await renderApp(<NotYetRun items={[]} />);
    expect(empty.container.querySelectorAll("[data-pending]")).toHaveLength(0);
  });
});
