// The pure functions of the studio index build (DC-019-03): the layout of the tool map (FR-019-02), the observed or planned state of
// each handoff edge (FR-019-06) and the join of the published artefacts to their tool pages (P-019-02). The script
// `web/scripts/build-studio-index.mjs` calls them at build time; nothing runs in the browser to place a node.

export interface ToolmapBand {
  id: string;
  tools: string[];
}
export interface ToolmapEdge {
  from: string;
  to: string;
  kind: string;
}
export interface Toolmap {
  bands: ToolmapBand[];
  edges: ToolmapEdge[];
}

export interface Position {
  band: string;
  order: number;
  group: "map" | "not-adopted";
  x_px: number;
  y_px: number;
}

export interface ArtefactLike {
  id: string;
  run_id: string;
  producer: { tool: string };
  inputs: ReadonlyArray<{ id: string; kind: string }>;
}

export interface IndexEdge extends ToolmapEdge {
  state: "observed" | "planned";
  evidence?: { run_id: string; from_artefact: string; to_artefact: string };
}

const BAND_X0 = 40;
const BAND_DX = 200;
const ROW_Y0 = 80;
const ROW_DY = 80;

/**
 * A position for every tool of the registry that the tool map lists. The map group sits at x = 40 + 200 x (band index) and
 * y = 80 + 80 x (index in the band); the evaluated-not-adopted tools of a band are placed under every row of the band, in its order. The result depends only on the tool map and on the statuses, never on the order of the registry.
 */
export function layoutTools(
  toolmap: Toolmap,
  tools: ReadonlyArray<{ id: string; status: string }>,
): Record<string, Position> {
  const notAdopted = new Set(tools.filter((t) => t.status === "evaluated-not-adopted").map((t) => t.id));
  const known = new Set(tools.map((t) => t.id));
  const out: Record<string, Position> = {};
  for (const [bandIndex, band] of toolmap.bands.entries()) {
    let extra = 0;
    for (const [order, id] of band.tools.entries()) {
      if (!known.has(id)) continue;
      const isNotAdopted = notAdopted.has(id);
      // A map tool sits on its own row; the evaluated-not-adopted tools sit under every row of the band, in the band's order.
      const row = isNotAdopted ? band.tools.length + extra++ : order;
      out[id] = {
        band: band.id,
        order,
        group: isNotAdopted ? "not-adopted" : "map",
        x_px: BAND_X0 + BAND_DX * bandIndex,
        y_px: ROW_Y0 + ROW_DY * row,
      };
    }
  }
  return out;
}

/** One result per declared edge, in the declared order; observed when an artefact of `to` lists an artefact of `from` as input. */
export function deriveEdges(edges: readonly ToolmapEdge[], artefacts: readonly ArtefactLike[]): IndexEdge[] {
  const byId = new Map<string, ArtefactLike>();
  for (const a of artefacts) byId.set(a.id, a);
  return edges.map((edge) => {
    let best: { run: string; to: string; from: string } | null = null;
    for (const y of artefacts) {
      if (y.producer.tool !== edge.to) continue;
      for (const input of y.inputs) {
        if (input.kind !== "artefact") continue;
        const x = byId.get(input.id);
        if (!x || x.producer.tool !== edge.from) continue;
        const candidate = { run: y.run_id, to: y.id, from: x.id };
        if (best === null || before(candidate, best)) best = candidate;
      }
    }
    const base = { from: edge.from, to: edge.to, kind: edge.kind };
    if (best === null) return { ...base, state: "planned" as const };
    return {
      ...base,
      state: "observed" as const,
      evidence: { run_id: best.run, from_artefact: best.from, to_artefact: best.to },
    };
  });
}

/** Smallest witness by (run id, target artefact id, source artefact id), compared as strings. */
function before(
  a: { run: string; to: string; from: string },
  b: { run: string; to: string; from: string },
): boolean {
  if (a.run !== b.run) return a.run < b.run;
  if (a.to !== b.to) return a.to < b.to;
  return a.from < b.from;
}

/** Per tool the ids of the artefacts it produced, sorted; an artefact of an unknown producer appears nowhere. */
export function joinArtefacts(
  toolIds: readonly string[],
  artefacts: readonly ArtefactLike[],
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const id of toolIds) out[id] = [];
  for (const a of artefacts) {
    const list = Object.hasOwn(out, a.producer.tool) ? out[a.producer.tool] : undefined;
    if (list && !list.includes(a.id)) list.push(a.id);
  }
  for (const list of Object.values(out)) list.sort();
  return out;
}
