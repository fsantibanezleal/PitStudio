// T-019-010 [red] · FR-019-01 (one node per registry entry: 17 studio tools plus the evaluated-not-adopted group; lane as colour together with a label, ring badge, licence icon,
// edges labelled with the artefact kind and dashed while planned), FR-019-05 (accessible name, Tab order in band order, activation by click, Enter and Space opens the tool page)
// and US-019-1 (the map and the data table describe the same graph). Unit half: web/src/studio/t_019_010_tool_map.test.tsx.
//
// Hooks on `/studio/` once the React Flow map is mounted (the static SVG of FR-019-04 is then hidden or removed):
//   [data-testid="tool-map"][data-ready="true"]                         the interactive map
//     a/[role="link"] [data-testid="tool-node"][data-tool][data-lane][data-ring][data-licence-class][data-status][data-band][data-order]   one per entry, with the accessible
//                                                                       name "<name> — lane <lane>, ring <ring>, licence <class>, status <status>"
//     [data-testid="map-edge"][data-from][data-to][data-kind][data-state]  one per declared edge, its label holds the kind and "planned" or "observed in run <id>"
//   table[data-testid="tool-table"] tr[data-tool] (prerendered, FR-019-04): td cells Tool, Environment, Lane, Ring, Licence class, Status, Inbound, Outbound
// Oracles: the 20 tool ids and the statuses and licence classes of spec section 7.1; the value domains of the registry schema (lanes, rings, licence classes, statuses, artefact
// kinds); the table of the same page as the second description of the same graph; the band order of FR-019-02.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const IDS = [
  "openusd",
  "warp",
  "newton",
  "mujoco-warp",
  "physx-ovphysx",
  "ovrtx",
  "isaac-sim-replicator",
  "isaac-lab",
  "kit-usd-composer-explorer",
  "cosmos-reason-2",
  "pytorch",
  "onnx-runtime",
  "tensorrt",
  "nvenc-ffmpeg",
  "nsight-nvml",
  "threejs-r3f-3d-tiles",
  "rapier-webgpu-pyodide",
  "cuopt",
  "physicsnemo",
  "cosmos-predict-transfer",
];
const NOT_ADOPTED = ["cuopt", "physicsnemo", "cosmos-predict-transfer"];
const REFERENCE_ONLY = [
  "physx-ovphysx",
  "ovrtx",
  "isaac-sim-replicator",
  "kit-usd-composer-explorer",
  "tensorrt",
];
const BANDS = ["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"];
const NAME =
  /^.+ — lane (live|replay|local-only), ring (Adopt|Trial|Assess|Hold), licence (public-domain|open-no-attribution|own|attribution|share-alike|display-only|reference-only), status (not-yet-run|done|evaluated-not-adopted)$/;
const KINDS = [
  "video",
  "image",
  "figure",
  "point-cloud",
  "mesh",
  "tiles",
  "splat",
  "onnx",
  "table",
  "trace",
  "shard",
  "field",
  "text",
  "model-card",
  "telemetry",
  "usd",
];

async function openMap(page: Page): Promise<void> {
  await open(page, "studio/");
  await expect(page.getByTestId("tool-map")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
}
const flowNodes = (page: Page) => page.getByTestId("tool-map").locator('[data-testid="tool-node"]');

test.describe("nodes and encodings (FR-019-01)", () => {
  test("FR-019-01 · the interactive map has exactly the 20 registry ids: the 17 studio tools and the evaluated-not-adopted entries", async ({
    page,
  }) => {
    await openMap(page);
    const ids = await flowNodes(page).evaluateAll((els) => els.map((e) => e.getAttribute("data-tool")));
    expect([...ids].sort()).toEqual([...IDS].sort());
    for (const id of NOT_ADOPTED)
      await expect(page.getByTestId("tool-map").locator(`[data-tool="${id}"]`)).toHaveAttribute(
        "data-status",
        "evaluated-not-adopted",
      );
    await expect(page.getByTestId("tool-map").getByText("Evaluated, not adopted").first()).toBeVisible();
  });

  test("FR-019-01 · every node has a lane label in words, a ring badge and a licence icon; the reference-only tools of section 7.1 carry that class", async ({
    page,
  }) => {
    await openMap(page);
    for (const id of IDS) {
      const n = page.getByTestId("tool-map").locator(`[data-testid="tool-node"][data-tool="${id}"]`);
      await expect(n.getByTestId("lane-label")).toHaveText(/live|replay|local[- ]only/i);
      await expect(n.getByTestId("ring-badge")).toHaveText(/^(Adopt|Trial|Assess|Hold)$/);
      await expect(n.getByTestId("licence-icon").locator("svg")).toHaveCount(1);
    }
    for (const id of REFERENCE_ONLY)
      await expect(page.getByTestId("tool-map").locator(`[data-tool="${id}"]`)).toHaveAttribute(
        "data-licence-class",
        "reference-only",
      );
  });

  test("FR-019-01 · the lane is encoded by colour too: nodes of one lane share a colour and the three lanes have three different ones, in light and dark", async ({
    page,
  }) => {
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await openMap(page);
      const rows = await flowNodes(page).evaluateAll((els) =>
        els.map((e) => ({
          lane: e.getAttribute("data-lane"),
          colour: getComputedStyle(e).borderLeftColor + "|" + getComputedStyle(e).backgroundColor,
        })),
      );
      const byLane = new Map<string, Set<string>>();
      for (const r of rows) byLane.set(r.lane ?? "", (byLane.get(r.lane ?? "") ?? new Set()).add(r.colour));
      expect([...byLane.keys()].sort()).toEqual(["live", "local-only", "replay"]);
      for (const [lane, set] of byLane) expect(set.size, `${scheme}: one colour for ${lane}`).toBe(1);
      expect(new Set([...byLane.values()].map((s) => [...s][0])).size, `${scheme}: three colours`).toBe(3);
    }
  });

  test("FR-019-01 · each edge is labelled with an artefact kind; with no published run every edge is planned and dashed", async ({
    page,
  }) => {
    await openMap(page);
    const edges = page.getByTestId("tool-map").locator('[data-testid="map-edge"]');
    expect(await edges.count()).toBeGreaterThan(0);
    const rows = await edges.evaluateAll((els) =>
      els.map((e) => ({
        kind: e.getAttribute("data-kind"),
        state: e.getAttribute("data-state"),
        text: e.textContent ?? "",
        dash: getComputedStyle(e.querySelector("path, line, polyline") ?? e).strokeDasharray,
      })),
    );
    for (const r of rows) {
      expect(KINDS).toContain(r.kind);
      expect(r.text).toContain(r.kind ?? "?");
      expect(["observed", "planned"]).toContain(r.state);
      if (r.state === "planned") {
        expect(r.text).toContain("planned");
        expect(r.dash).not.toBe("none");
      } else {
        expect(r.text).toMatch(/observed in run \S+/);
        expect(r.dash).toBe("none");
      }
    }
  });

  test("US-019-1 · the map and the data table of the same page agree on lane, ring, licence class and status of every tool", async ({
    page,
  }) => {
    await openMap(page);
    for (const id of IDS) {
      const n = page.getByTestId("tool-map").locator(`[data-testid="tool-node"][data-tool="${id}"]`);
      const cells = await page
        .locator(`[data-testid="tool-table"] tr[data-tool="${id}"] td`)
        .allTextContents();
      expect(cells.length, id).toBeGreaterThanOrEqual(8);
      const lane = await n.getAttribute("data-lane");
      expect(cells[2], id).toMatch(new RegExp((lane ?? "").replace("-", "[- ]"), "i"));
      expect(cells[3], id).toBe(await n.getAttribute("data-ring"));
      expect(cells[4], id).toBe(await n.getAttribute("data-licence-class"));
    }
  });
});

test.describe("keyboard and activation (FR-019-05)", () => {
  test("FR-019-05 · every node has the accessible name '<name> — lane <lane>, ring <ring>, licence <class>, status <status>'", async ({
    page,
  }) => {
    await openMap(page);
    for (const id of IDS) {
      const n = page.getByTestId("tool-map").locator(`[data-testid="tool-node"][data-tool="${id}"]`);
      const name = (await n.getAttribute("aria-label")) ?? "";
      expect(name, id).toMatch(NAME);
      expect(name, id).toContain(`lane ${await n.getAttribute("data-lane")},`);
      expect(name, id).toContain(`status ${await n.getAttribute("data-status")}`);
    }
  });

  test("FR-019-05 · Tab visits the nodes in band order, then the order within the band, and no node is skipped", async ({
    page,
  }) => {
    await openMap(page);
    const meta = await flowNodes(page).evaluateAll((els) =>
      els.map((e) => ({
        id: e.getAttribute("data-tool") ?? "",
        band: e.getAttribute("data-band") ?? "",
        order: Number(e.getAttribute("data-order")),
      })),
    );
    await flowNodes(page).first().focus();
    const visited: string[] = [];
    for (let i = 0; i < IDS.length + 6 && visited.length < IDS.length; i++) {
      const id = await page.evaluate(
        () =>
          (document.activeElement as HTMLElement | null)
            ?.closest('[data-testid="tool-node"]')
            ?.getAttribute("data-tool") ?? null,
      );
      if (id && !visited.includes(id)) visited.push(id);
      await page.keyboard.press("Tab");
    }
    expect(new Set(visited).size).toBe(IDS.length);
    const rank = (id: string) => {
      const m = meta.find((x) => x.id === id);
      return BANDS.indexOf(m?.band ?? "") * 1000 + (m?.order ?? 0);
    };
    const map = visited.filter((id) => !NOT_ADOPTED.includes(id));
    expect(map.map(rank)).toEqual([...map.map(rank)].sort((a, b) => a - b));
    const out = visited.filter((id) => NOT_ADOPTED.includes(id));
    expect(out.map(rank)).toEqual([...out.map(rank)].sort((a, b) => a - b));
  });

  for (const how of ["click", "Enter", "Space"] as const) {
    test(`FR-019-05 · ${how} on a node opens /studio/tools/<id>/`, async ({ page }) => {
      await openMap(page);
      const node = page.getByTestId("tool-map").locator('[data-testid="tool-node"][data-tool="warp"]');
      if (how === "click") await node.click();
      else {
        await node.focus();
        await page.keyboard.press(how === "Space" ? "Space" : "Enter");
      }
      await expect(page).toHaveURL(/\/studio\/tools\/warp\/?$/);
    });
  }

  test("FR-019-05 · a focused node shows a visible focus indicator", async ({ page }) => {
    await openMap(page);
    const node = page.getByTestId("tool-map").locator('[data-testid="tool-node"][data-tool="openusd"]');
    await node.focus();
    const outline = await node.evaluate((e) => {
      const s = getComputedStyle(e);
      return { style: s.outlineStyle, width: parseFloat(s.outlineWidth), shadow: s.boxShadow };
    });
    expect((outline.style !== "none" && outline.width > 0) || outline.shadow !== "none").toBe(true);
  });
});
