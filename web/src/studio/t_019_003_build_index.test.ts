// T-019-003 [red] · FR-019-02 (build-time layout: positions from the band and the order, byte-identical for identical inputs, no layout library in the browser),
// FR-019-06 (observed edge: an artefact of B lists an input artefact of A; otherwise planned), P-019-01 (layout determinism under permutation), P-019-02 (artefact
// partition over the tool pages) and P-019-05 (observed-edge derivation invariant to the order and duplication of artefacts).
//
// Expected API: `~/studio/buildIndex` (web/src/studio/buildIndex.ts, pure functions; the script web/scripts/build-studio-index.mjs calls them, the spec plan puts the
// join in the script and names no TypeScript module: flagged in the report):
//   layoutTools(toolmap: ToolmapJson, tools: Array<{ id: string; status: string }>): Record<string, Position>
//       Position = { band: string; order: number; group: "map" | "not-adopted"; x_px: number; y_px: number }; band = the band that lists the tool in the tool map,
//       order = its index in that band's list, group "not-adopted" iff the registry status is `evaluated-not-adopted`; x_px, y_px integers in 0..20000; bands left to
//       right in the order of the tool map; within a band, `order` top to bottom; no two tools at the same point. For the map group of the spec's example,
//       x_px = 40 + 200 * band index and y_px = 80 + 80 * order (hand check against studio-index.valid.json: openusd (40, 80), warp (240, 80), isaac-sim-replicator (440, 160)).
//   deriveEdges(edges, artefacts): Array<{ from, to, kind, state: "observed" | "planned", evidence?: { run_id, from_artefact, to_artefact } }>
//       one output per declared edge, in the declared order; "observed" iff some artefact y with producer.tool === edge.to has an input {kind: "artefact", id: x} where
//       the manifest holds an artefact x with producer.tool === edge.from; the evidence is the smallest witness by (run_id of y, y.id, x.id) compared as strings, so that
//       the result does not depend on the order of the manifest (P-019-05).
//   joinArtefacts(toolIds: string[], artefacts): Record<string, string[]>     per tool the ids of the artefacts whose producer.tool is that id, sorted ascending;
//       artefacts of an unknown producer appear nowhere (P-019-02).
// Oracles: hand-built registries, tool maps and manifests; the spec example of the studio index for the positions; for the properties, the relations written next to
// each generator (set equality, permutation invariance).
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { deriveEdges, joinArtefacts, layoutTools } from "~/studio/buildIndex";
import { type ArtefactJson, makeArtefact } from "~/test-support/fixtures";
import {
  BAND_IDS,
  loadStudioIndexExample,
  loadToolmapExample,
  makeToolmap,
  type ToolmapJson,
} from "~/test-support/studio-fixtures";

const status = (id: string, adopted = true) => ({
  id,
  status: adopted ? "not-yet-run" : "evaluated-not-adopted",
});
const art = (id: string, tool: string, inputs: string[] = [], run = "20261011T083000Z-a1"): ArtefactJson =>
  makeArtefact({
    id,
    run_id: run,
    producer: { tool, stage: { id: "st50_physics" } },
    inputs: inputs.map((i) => ({ id: i, sha256: "a".repeat(64), kind: "artefact" as const })),
  });

describe("layout of the map (FR-019-02)", () => {
  const example = loadToolmapExample();
  const tools = example.bands
    .flatMap((b) => b.tools)
    .map((id) => status(id, !["cuopt", "physicsnemo", "cosmos-predict-transfer"].includes(id)));
  const layout = layoutTools(example, tools);

  it("FR-019-02 · every tool of the map gets a position, with its band, its index in the band and its group", () => {
    expect(Object.keys(layout).sort()).toEqual(tools.map((t) => t.id).sort());
    example.bands.forEach((band) => {
      band.tools.forEach((id, order) => {
        expect(layout[id]?.band, id).toBe(band.id);
        expect(layout[id]?.order, id).toBe(order);
      });
    });
    expect(layout.cuopt?.group).toBe("not-adopted");
    expect(layout.openusd?.group).toBe("map");
  });

  it("FR-019-02 · the map group follows x = 40 + 200 * band index and y = 80 + 80 * order, as the spec example of the studio index shows", () => {
    const sample = loadStudioIndexExample();
    for (const t of sample.tools.filter((t) => t.position.group === "map")) {
      expect(layout[t.id], t.id).toMatchObject({ x_px: t.position.x_px, y_px: t.position.y_px });
    }
    expect(layout.openusd).toMatchObject({ x_px: 40, y_px: 80 });
    expect(layout.warp).toMatchObject({ x_px: 240, y_px: 80 });
    expect(layout["isaac-sim-replicator"]).toMatchObject({ x_px: 440, y_px: 160 });
  });

  it("FR-019-02 · positions are integers in 0..20000, bands go left to right in map order, orders go top to bottom, and no two nodes share a point", () => {
    const seen = new Set<string>();
    for (const [id, p] of Object.entries(layout)) {
      expect(Number.isInteger(p.x_px) && Number.isInteger(p.y_px), id).toBe(true);
      expect(p.x_px >= 0 && p.x_px <= 20_000 && p.y_px >= 0 && p.y_px <= 20_000, id).toBe(true);
      const key = `${p.x_px},${p.y_px}`;
      expect(seen.has(key), `${id} at ${key}`).toBe(false);
      seen.add(key);
    }
    for (const a of Object.values(layout)) {
      for (const b of Object.values(layout)) {
        if (a.group === "map" && b.group === "map") {
          if (BAND_IDS.indexOf(a.band as never) < BAND_IDS.indexOf(b.band as never))
            expect(a.x_px).toBeLessThan(b.x_px);
          if (a.band === b.band && a.order < b.order) expect(a.y_px).toBeLessThan(b.y_px);
        }
      }
    }
  });

  it("FR-019-02 · identical inputs give byte-identical output", () => {
    expect(JSON.stringify(layoutTools(example, tools))).toBe(
      JSON.stringify(layoutTools(structuredClone(example), structuredClone(tools))),
    );
  });

  it("FR-019-02 · no layout library is a dependency of the web app (nothing runs in the browser to place nodes)", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, resolve } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const pkg = JSON.parse(
      readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../../package.json"), "utf8"),
    ) as {
      dependencies: Record<string, string>;
    };
    for (const lib of [
      "elkjs",
      "dagre",
      "@dagrejs/dagre",
      "d3-force",
      "d3-hierarchy",
      "cytoscape",
      "@dagrejs/graphlib",
    ]) {
      expect(Object.keys(pkg.dependencies), lib).not.toContain(lib);
    }
  });

  it("FR-019-02 · a tool listed in a different order of its band moves, the others keep their band", () => {
    const map = makeToolmap();
    const physics = map.bands.find((b) => b.id === "physics") as ToolmapJson["bands"][number];
    const reordered = structuredClone(map);
    const r = reordered.bands.find((b) => b.id === "physics") as ToolmapJson["bands"][number];
    r.tools = [...physics.tools].reverse();
    const all = map.bands.flatMap((b) => b.tools).map((id) => status(id));
    const before = layoutTools(map, all);
    const after = layoutTools(reordered, all);
    expect(before.warp?.order).toBe(0);
    expect(after.warp?.order).toBe(physics.tools.length - 1);
    expect(after.warp?.band).toBe("physics");
    expect(after.openusd).toEqual(before.openusd);
  });
});

describe("P-019-01 layout determinism under permutation", () => {
  const registryAndMap = fc
    .tuple(
      fc.integer({ min: 1, max: 40 }),
      fc.array(fc.integer({ min: 0, max: BAND_IDS.length - 1 }), { minLength: 40, maxLength: 40 }),
      fc.array(fc.boolean(), { minLength: 40, maxLength: 40 }),
    )
    .map(([n, bands, flags]) => {
      const ids = Array.from({ length: n }, (_, i) => `tool-${i}`);
      const toolmap: ToolmapJson = {
        bands: BAND_IDS.map((b) => ({ id: b, tools: [] as string[] })),
        edges: [],
      };
      for (const [i, id] of ids.entries())
        (toolmap.bands[bands[i] as number] as { tools: string[] }).tools.push(id);
      for (let i = 1; i < n; i++)
        toolmap.edges.push({ from: ids[i - 1] as string, to: ids[i] as string, kind: "table" });
      return { toolmap, tools: ids.map((id, i) => status(id, flags[i] ?? true)) };
    });

  it("P-019-01 · permuting the registry entries and the edges leaves every position, keyed by tool id, unchanged", () => {
    fc.assert(
      fc.property(registryAndMap, fc.integer({ min: 0, max: 1_000_000 }), ({ toolmap, tools }, seed) => {
        const rotate = <T>(xs: T[]): T[] =>
          xs.length === 0 ? xs : [...xs.slice(seed % xs.length), ...xs.slice(0, seed % xs.length)].reverse();
        const permuted = { ...toolmap, edges: rotate(toolmap.edges) };
        const a = layoutTools(toolmap, tools);
        const b = layoutTools(permuted, rotate(tools));
        expect(Object.keys(b).sort()).toEqual(Object.keys(a).sort());
        for (const id of Object.keys(a)) expect(b[id]).toEqual(a[id]);
      }),
      { numRuns: 200 },
    );
  });

  it("P-019-01 · no two tools share a point and every coordinate is an integer in range, for registries of 1 to 40 tools", () => {
    fc.assert(
      fc.property(registryAndMap, ({ toolmap, tools }) => {
        const layout = layoutTools(toolmap, tools);
        const points = Object.values(layout).map((p) => `${p.x_px},${p.y_px}`);
        expect(new Set(points).size).toBe(points.length);
        for (const p of Object.values(layout)) {
          expect(Number.isInteger(p.x_px) && p.x_px >= 0 && p.x_px <= 20_000).toBe(true);
          expect(Number.isInteger(p.y_px) && p.y_px >= 0 && p.y_px <= 20_000).toBe(true);
        }
      }),
      { numRuns: 200 },
    );
  });
});

describe("observed and planned edges (FR-019-06)", () => {
  const edge = (from: string, to: string, kind = "usd") => ({ from, to, kind });

  it("FR-019-06 · an edge A -> B is observed when an artefact of B lists an artefact of A as input, with the run and the two artefacts as evidence", () => {
    const out = deriveEdges(
      [edge("openusd", "warp")],
      [art("scene-1", "openusd"), art("sim-1", "warp", ["scene-1"], "r-2")],
    );
    expect(out).toEqual([
      {
        ...edge("openusd", "warp"),
        state: "observed",
        evidence: { run_id: "r-2", from_artefact: "scene-1", to_artefact: "sim-1" },
      },
    ]);
  });

  it("FR-019-06 · otherwise it is planned and carries no evidence", () => {
    const out = deriveEdges([edge("openusd", "warp")], [art("scene-1", "openusd"), art("sim-1", "warp")]);
    expect(out).toEqual([{ ...edge("openusd", "warp"), state: "planned" }]);
    expect(deriveEdges([edge("openusd", "warp")], [])).toEqual([
      { ...edge("openusd", "warp"), state: "planned" },
    ]);
  });

  it("FR-019-06 · the direction matters: the artefact of A listing an artefact of B observes B -> A, not A -> B", () => {
    const manifest = [art("sim-1", "warp"), art("scene-1", "openusd", ["sim-1"])];
    const [ab, ba] = deriveEdges([edge("openusd", "warp"), edge("warp", "openusd")], manifest);
    expect(ab?.state).toBe("planned");
    expect(ba?.state).toBe("observed");
  });

  it("FR-019-06 · an input that is a source or a knowledge record, or an artefact absent from the manifest, does not observe an edge", () => {
    const sim = makeArtefact({
      id: "sim-1",
      producer: { tool: "warp", stage: { id: "st50_physics" } },
      inputs: [
        { id: "scene-1", sha256: "a".repeat(64), kind: "source" },
        { id: "scene-1", sha256: "a".repeat(64), kind: "knowledge" },
        { id: "ghost", sha256: "a".repeat(64), kind: "artefact" },
      ],
    });
    expect(deriveEdges([edge("openusd", "warp")], [art("scene-1", "openusd"), sim])[0]?.state).toBe(
      "planned",
    );
  });

  it("FR-019-06 · the evidence is the smallest witness by run id, then target artefact id, then source artefact id", () => {
    const manifest = [
      art("a-2", "openusd"),
      art("a-1", "openusd"),
      art("w-9", "warp", ["a-2"], "r-1"),
      art("w-3", "warp", ["a-2", "a-1"], "r-2"),
      art("w-0", "warp", ["a-2"], "r-2"),
    ];
    expect(deriveEdges([edge("openusd", "warp")], manifest)[0]?.evidence).toEqual({
      run_id: "r-1",
      from_artefact: "a-2",
      to_artefact: "w-9",
    });
    expect(
      deriveEdges([edge("openusd", "warp")], manifest.slice(0, 2).concat(manifest.slice(3)))[0]?.evidence,
    ).toEqual({
      run_id: "r-2",
      from_artefact: "a-2",
      to_artefact: "w-0",
    });
  });

  it("FR-019-06 · one result per declared edge, in the declared order, also for tools that no manifest names", () => {
    const edges = [edge("a", "b"), edge("c", "d", "table"), edge("b", "c", "onnx")];
    expect(deriveEdges(edges, []).map((e) => `${e.from}>${e.to}:${e.state}`)).toEqual([
      "a>b:planned",
      "c>d:planned",
      "b>c:planned",
    ]);
    expect(deriveEdges([], [art("x", "a")])).toEqual([]);
  });

  describe("P-019-05 invariance to the order and duplication of the manifest", () => {
    const toolIds = ["t0", "t1", "t2", "t3"];
    const manifest = fc
      .array(
        fc.record({
          n: fc.integer({ min: 0, max: 7 }),
          tool: fc.constantFrom(...toolIds),
          run: fc.constantFrom("r-1", "r-2", "r-3"),
          inputs: fc.array(fc.integer({ min: 0, max: 7 }), { maxLength: 3 }),
        }),
        { maxLength: 24 },
      )
      .map((rows) => {
        const byId = new Map<number, ArtefactJson>();
        for (const r of rows)
          byId.set(
            r.n,
            art(
              `x-${r.n}`,
              r.tool,
              r.inputs.map((i) => `x-${i}`),
              r.run,
            ),
          );
        return [...byId.values()];
      });
    const edges = [edge("t0", "t1"), edge("t1", "t2"), edge("t2", "t0"), edge("t3", "t3"), edge("t0", "t3")];

    it("P-019-05 · shuffling and duplicating the artefacts leaves every edge, state and evidence unchanged", () => {
      fc.assert(
        fc.property(manifest, fc.integer({ min: 0, max: 1_000_000 }), (artefacts, seed) => {
          const base = deriveEdges(edges, artefacts);
          const doubled = [...artefacts, ...artefacts.filter((_, i) => (i + seed) % 2 === 0)];
          const shuffled = doubled
            .map((a, i) => ({ a, k: ((i + 1) * 2654435761 + seed) % 1000003 }))
            .sort((x, y) => x.k - y.k)
            .map((x) => x.a);
          expect(deriveEdges(edges, shuffled)).toEqual(base);
        }),
        { numRuns: 200 },
      );
    });

    it("P-019-05 · every observed edge has a valid witness and every planned edge has none (hand relation)", () => {
      fc.assert(
        fc.property(manifest, (artefacts) => {
          const byId = new Map(artefacts.map((a) => [a.id, a]));
          for (const e of deriveEdges(edges, artefacts)) {
            const witnesses = artefacts.filter(
              (y) =>
                y.producer.tool === e.to &&
                y.inputs.some((i) => i.kind === "artefact" && byId.get(i.id)?.producer.tool === e.from),
            );
            expect(e.state === "observed").toBe(witnesses.length > 0);
            if (e.state === "observed") {
              const y = byId.get(e.evidence?.to_artefact ?? "");
              expect(y?.producer.tool).toBe(e.to);
              expect(y?.run_id).toBe(e.evidence?.run_id);
              expect(byId.get(e.evidence?.from_artefact ?? "")?.producer.tool).toBe(e.from);
            }
          }
        }),
        { numRuns: 200 },
      );
    });
  });
});

describe("artefact partition over the tool pages (P-019-02)", () => {
  it("P-019-02 · each artefact whose producer is a registry id is listed under that tool, sorted, and unknown producers appear nowhere", () => {
    const out = joinArtefacts(
      ["warp", "newton"],
      [art("b", "warp"), art("a", "warp"), art("c", "newton"), art("z", "unknown-tool")],
    );
    expect(out).toEqual({ warp: ["a", "b"], newton: ["c"] });
  });

  it("P-019-02 · a tool with no artefact has an empty list, and an empty manifest gives empty lists for all", () => {
    expect(joinArtefacts(["warp"], [])).toEqual({ warp: [] });
    expect(joinArtefacts([], [art("a", "warp")])).toEqual({});
  });

  it("P-019-02 · random manifests of up to 1000 artefacts: the lists are disjoint and their union is the set of known-producer artefacts", () => {
    const ids = ["t0", "t1", "t2", "t3", "t4"];
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(...ids, "other", "t-unknown"), { maxLength: 1000 }),
        fc.shuffledSubarray(ids, { minLength: 1 }),
        (producers, known) => {
          const manifest = producers.map((tool, i) => art(`a-${String(i).padStart(4, "0")}`, tool));
          const out = joinArtefacts(known, manifest);
          const listed = Object.values(out).flat();
          expect(new Set(listed).size, "no artefact on two pages").toBe(listed.length);
          const expected = manifest.filter((a) => known.includes(a.producer.tool)).map((a) => a.id);
          expect([...listed].sort()).toEqual([...expected].sort());
          for (const [tool, list] of Object.entries(out)) {
            expect(list).toEqual([...list].sort());
            for (const id of list) expect(manifest.find((a) => a.id === id)?.producer.tool).toBe(tool);
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
