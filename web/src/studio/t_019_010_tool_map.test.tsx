// T-019-010 [red] · FR-019-01 (tool map: one node per registry entry, the 17 studio tools plus the evaluated-not-adopted entries in a separate labelled group; lane as colour
// together with a text label, ring badge, a lucide icon distinct per licence class, edges labelled with the artefact kind) and FR-019-05 (accessible name of a node, Tab order
// in band order, activation opens the tool page), FR-019-06 (edge drawn solid with "observed in run <id>", dashed with "planned"), FR-019-04 (data table of the same graph),
// FR-019-13 ("Not yet run" on the map node). E2E half (React Flow nodes, keyboard, colours): web/e2e/t_019_010_tool_map.spec.ts.
//
// Expected API: `~/studio/StaticMap` (web/src/studio/StaticMap.tsx): named export StaticMap({ tools: ToolEntry[]; index: StudioIndex }), the prerendered static SVG and table of the
// same graph (FR-019-04). `ToolEntry` is the registry entry (DC-001-03) and `StudioIndex` the generated index (DC-019-03, specs/019-web-studio/contracts/studio-index.schema.json).
// Hooks:
//   <section data-testid="static-map">
//     svg [role="img"] with, per edge, g[data-testid="map-edge"][data-from][data-to][data-kind][data-state="observed"|"planned"], solid when observed (no stroke-dasharray)
//       and dashed when planned (stroke-dasharray set), carrying the text of its kind and "observed in run <run id>" or "planned"
//     per tool an anchor a[data-testid="tool-node"][data-tool][data-lane][data-ring][data-licence-class][data-status][data-x][data-y][href="/studio/tools/<id>/"]
//       (data-x, data-y: the build-time position x_px, y_px of the index) whose aria-label is
//       "<name> — lane <lane>, ring <ring>, licence <class>, status <status>" (values as in the registry), and inside it [data-testid="lane-label"] (the lane in words),
//       [data-testid="ring-badge"] (the ring), [data-testid="licence-icon"] holding a lucide svg, and the text "Not yet run" when the status is not-yet-run
//     the evaluated-not-adopted entries in g[data-testid="not-adopted-group"] labelled "Evaluated, not adopted", the others in g[data-testid="map-group"]
//   <table data-testid="tool-table"> columns Tool, Environment, Lane, Ring, Licence class, Status, Inbound handoffs, Outbound handoffs; one row tr[data-tool] per entry
// Oracles: hand-built registry (web/src/test-support/studio-fixtures.ts) in which lane, ring and licence class rotate over all values; the EARS strings.
import { screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { StaticMap } from "~/studio/StaticMap";
import { renderApp } from "~/test-support/render";
import {
  ADOPTED_IDS,
  BAND_IDS,
  indexTool,
  LICENCE_CLASSES,
  makeIndex,
  makeRegistry,
  NOT_ADOPTED_IDS,
  STUDIO_TOOLS,
  TOOL_IDS,
} from "~/test-support/studio-fixtures";

const registry = makeRegistry({ warp: { status: "done" } });
const index = makeIndex({
  edges: [
    {
      from: "openusd",
      to: "warp",
      kind: "usd",
      state: "observed",
      evidence: { run_id: "20261005T101500Z-b2-sdg", from_artefact: "a", to_artefact: "b" },
    },
    { from: "openusd", to: "isaac-sim-replicator", kind: "usd", state: "planned" },
    { from: "isaac-sim-replicator", to: "pytorch", kind: "table", state: "planned" },
    { from: "pytorch", to: "onnx-runtime", kind: "onnx", state: "planned" },
  ],
});
const render = (lang: "en" | "es" = "en") =>
  renderApp(createElement(StaticMap, { tools: registry as never, index: index as never }), { lang });
const nodes = () => Array.from(document.querySelectorAll<HTMLElement>('[data-testid="tool-node"]'));
const node = (id: string) =>
  document.querySelector<HTMLElement>(`[data-testid="tool-node"][data-tool="${id}"]`) as HTMLElement;

describe("one node per registry entry (FR-019-01)", () => {
  it("FR-019-01 · 17 studio tools in the map group and the 3 evaluated-not-adopted entries in a separate labelled group", async () => {
    await render();
    const map = screen.getByTestId("map-group");
    const out = screen.getByTestId("not-adopted-group");
    const ids = (root: HTMLElement) =>
      Array.from(root.querySelectorAll("[data-tool]"))
        .map((n) => n.getAttribute("data-tool"))
        .sort();
    expect(ids(map)).toEqual([...ADOPTED_IDS].sort());
    expect(ids(out)).toEqual([...NOT_ADOPTED_IDS].sort());
    expect(nodes()).toHaveLength(20);
    expect(out.getAttribute("aria-label") ?? out.textContent).toContain("Evaluated, not adopted");
  });

  it("FR-019-01 · each node carries lane, ring, licence class and status of its registry entry", async () => {
    await render();
    for (const t of registry) {
      const n = node(t.id);
      expect(n.getAttribute("data-lane"), t.id).toBe(t.lane);
      expect(n.getAttribute("data-ring"), t.id).toBe(t.ring);
      expect(n.getAttribute("data-licence-class"), t.id).toBe(t.licence_class);
      expect(n.getAttribute("data-status"), t.id).toBe(t.status);
    }
  });

  it("FR-019-01 · the lane is also written in words (not colour alone) and the ring is a text badge", async () => {
    await render();
    for (const t of registry) {
      const lane = within(node(t.id)).getByTestId("lane-label").textContent ?? "";
      expect(lane, t.id).toMatch(
        t.lane === "local-only" ? /local[- ]only/i : new RegExp(`^\\s*${t.lane}\\s*$`, "i"),
      );
      expect(within(node(t.id)).getByTestId("ring-badge").textContent, t.id).toBe(t.ring);
    }
  });

  it("FR-019-01 · the licence class is shown by a lucide icon, one distinct icon per class, the same icon for the same class", async () => {
    await render();
    const iconOf = (id: string) => {
      const svg = within(node(id)).getByTestId("licence-icon").querySelector("svg");
      expect(svg, id).not.toBeNull();
      return (
        (svg?.getAttribute("class") ?? "")
          .split(/\s+/)
          .find((c) => c.startsWith("lucide-") && c !== "lucide") ?? ""
      );
    };
    const byClass = new Map<string, Set<string>>();
    for (const t of registry) {
      const set = byClass.get(t.licence_class) ?? new Set<string>();
      set.add(iconOf(t.id));
      byClass.set(t.licence_class, set);
    }
    expect([...byClass.keys()].sort()).toEqual([...LICENCE_CLASSES].sort());
    for (const [cls, icons] of byClass) expect(icons.size, `one icon for ${cls}`).toBe(1);
    const all = [...byClass.values()].map((s) => [...s][0]);
    expect(new Set(all).size, "seven distinct icons").toBe(LICENCE_CLASSES.length);
    expect(all.every((i) => (i ?? "").length > 0)).toBe(true);
  });

  it("FR-019-13 · a tool that has not run says 'Not yet run' on its node; a done tool and an evaluated tool do not", async () => {
    await render();
    expect(node("openusd").textContent).toContain("Not yet run");
    expect(node("warp").textContent).not.toContain("Not yet run");
    expect(node("cuopt").textContent).not.toContain("Not yet run");
  });

  it("FR-019-01 · a hostile name (markup, 5,000 characters) is text in the node and in its accessible name, and executes nothing", async () => {
    const hostile = makeRegistry({ warp: { name: `<img src=x onerror=alert(1)>${"w".repeat(5000)}` } });
    await renderApp(createElement(StaticMap, { tools: hostile as never, index: index as never }));
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(node("warp").getAttribute("aria-label")).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("accessible names, keyboard order and activation (FR-019-05)", () => {
  it("FR-019-05 · a node is named '<name> — lane <lane>, ring <ring>, licence <class>, status <status>'", async () => {
    await render();
    for (const t of registry) {
      expect(node(t.id).getAttribute("aria-label"), t.id).toBe(
        `${t.name} — lane ${t.lane}, ring ${t.ring}, licence ${t.licence_class}, status ${t.status}`,
      );
    }
  });

  it("FR-019-05 · every node is a link to its tool page and is reachable by Tab (no negative tabindex)", async () => {
    await render();
    for (const t of registry) {
      const n = node(t.id);
      expect(n.tagName.toLowerCase()).toBe("a");
      expect(n.getAttribute("href")).toBe(`/studio/tools/${t.id}/`);
      expect(n.getAttribute("tabindex") ?? "0").not.toMatch(/^-/);
    }
  });

  it("FR-019-05 · the DOM (Tab) order of the map group follows the bands scene, physics, sensors-synthetic-data, training, acceleration, encoding, web, then the order within the band", async () => {
    await render();
    const seen = Array.from(screen.getByTestId("map-group").querySelectorAll("[data-tool]")).map(
      (n) => n.getAttribute("data-tool") as string,
    );
    const key = (id: string) => {
      const p = index.tools.find((t) => t.id === id)?.position;
      return (BAND_IDS.indexOf(p?.band as never) as number) * 1000 + (p?.order ?? 0);
    };
    expect(seen).toEqual([...seen].sort((a, b) => key(a) - key(b)));
    expect(seen).toHaveLength(17);
  });
});

describe("edges (FR-019-01, FR-019-06)", () => {
  it("FR-019-01 · each handoff is drawn once and labelled with the artefact kind it carries", async () => {
    await render();
    const edges = Array.from(document.querySelectorAll<SVGGElement>('[data-testid="map-edge"]'));
    expect(edges).toHaveLength(index.edges.length);
    for (const e of index.edges) {
      const g = edges.find(
        (x) => x.getAttribute("data-from") === e.from && x.getAttribute("data-to") === e.to,
      );
      expect(g, `${e.from} -> ${e.to}`).toBeDefined();
      expect(g?.getAttribute("data-kind")).toBe(e.kind);
      expect(g?.textContent).toContain(e.kind);
    }
  });

  it("FR-019-06 · an observed edge is solid and reads 'observed in run <run id>'; a planned edge is dashed and reads 'planned'", async () => {
    await render();
    const edge = (from: string, to: string) =>
      Array.from(document.querySelectorAll<SVGGElement>('[data-testid="map-edge"]')).find(
        (x) => x.getAttribute("data-from") === from && x.getAttribute("data-to") === to,
      ) as SVGGElement;
    const observed = edge("openusd", "warp");
    expect(observed.getAttribute("data-state")).toBe("observed");
    expect(observed.textContent).toContain("observed in run 20261005T101500Z-b2-sdg");
    expect(observed.querySelector("[stroke-dasharray]")).toBeNull();
    const planned = edge("openusd", "isaac-sim-replicator");
    expect(planned.getAttribute("data-state")).toBe("planned");
    expect(planned.textContent).toContain("planned");
    expect(planned.querySelector("[stroke-dasharray]")).not.toBeNull();
  });
});

describe("the data table of the same graph (FR-019-04)", () => {
  it("FR-019-04 · the table has the eight columns and one row per entry with the values of the registry", async () => {
    await render();
    const table = screen.getByTestId("tool-table");
    const heads = Array.from(table.querySelectorAll("thead th")).map((h) => h.textContent?.trim());
    expect(heads).toEqual([
      "Tool",
      "Environment",
      "Lane",
      "Ring",
      "Licence class",
      "Status",
      "Inbound handoffs",
      "Outbound handoffs",
    ]);
    const rows = Array.from(table.querySelectorAll<HTMLElement>("tbody tr[data-tool]"));
    expect(rows.map((r) => r.getAttribute("data-tool")).sort()).toEqual([...TOOL_IDS].sort());
    for (const t of registry) {
      const cells = Array.from(
        (table.querySelector(`tr[data-tool="${t.id}"]`) as HTMLElement).querySelectorAll("td, th"),
      ).map((c) => c.textContent ?? "");
      expect(cells[0], t.id).toContain(t.name);
      expect(cells[1], t.id).toBe(t.envs.join(", "));
      expect(cells[2], t.id).toMatch(new RegExp(t.lane === "local-only" ? "local[- ]only" : t.lane, "i"));
      expect(cells[3], t.id).toBe(t.ring);
      expect(cells[4], t.id).toBe(t.licence_class);
      expect(cells[5], t.id).toContain(
        t.status === "done"
          ? "Done"
          : t.status === "evaluated-not-adopted"
            ? "Evaluated, not adopted"
            : "Not yet run",
      );
    }
  });

  it("FR-019-04 · inbound and outbound handoffs list the neighbouring tools of the edges, and a tool without edges lists none", async () => {
    await render();
    const row = (id: string) =>
      Array.from(document.querySelectorAll(`[data-testid="tool-table"] tr[data-tool="${id}"] td`)).map(
        (c) => c.textContent ?? "",
      );
    expect(row("openusd")[7]).toContain("warp");
    expect(row("openusd")[7]).toContain("isaac-sim-replicator");
    expect(row("openusd")[6]).not.toMatch(/warp|pytorch|onnx/);
    expect(row("warp")[6]).toContain("openusd");
    expect(row("pytorch")[6]).toContain("isaac-sim-replicator");
    expect(row("pytorch")[7]).toContain("onnx-runtime");
    expect(row("nvenc-ffmpeg")[6] + row("nvenc-ffmpeg")[7]).not.toMatch(
      /openusd|warp|pytorch|onnx-runtime|isaac-sim-replicator/,
    );
  });

  it("FR-019-04 · the text is translated: the Spanish table and group headings differ from the English ones", async () => {
    await render();
    const en = Array.from(document.querySelectorAll('[data-testid="tool-table"] thead th')).map(
      (h) => h.textContent,
    );
    document.body.innerHTML = "";
    await render("es");
    const es = Array.from(document.querySelectorAll('[data-testid="tool-table"] thead th')).map(
      (h) => h.textContent,
    );
    expect(es).toHaveLength(en.length);
    expect(es).not.toEqual(en);
  });
});

describe("index positions are used as given", () => {
  it("FR-019-02 · the nodes are placed at the build-time positions of the index (no layout is computed in the browser)", async () => {
    const moved = makeIndex({
      tools: TOOL_IDS.map((id) =>
        indexTool(id, { position: { band: "scene", order: 0, group: "map", x_px: 1234, y_px: 4321 } }),
      ),
    });
    await renderApp(createElement(StaticMap, { tools: registry as never, index: moved as never }));
    const n = node("openusd");
    expect(n.getAttribute("data-x")).toBe("1234");
    expect(n.getAttribute("data-y")).toBe("4321");
    expect(STUDIO_TOOLS).toHaveLength(20);
  });
});
