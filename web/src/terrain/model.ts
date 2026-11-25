// The published terrain of the 3D view (FR-018-01, ADR-0038): which manifest artefacts are the LOD-0 tileset, the detail tileset
// and the sources behind them. Pure functions, no three.js: this file is part of the initial JavaScript of the case pages.
import { appliesToCase } from "~/cases/manifest";
import type { ArtefactRecord } from "~/cases/types";

export interface TerrainSource {
  id: string;
  /** The licence as a visitor reads it, from the SPDX id of the artefact that lists the source. */
  licence: string;
}

export interface TerrainModel {
  runId: string;
  /** The first-view tileset: one whole-site tile, a few hundred kilobytes. */
  lod0: { url: string; artefact: ArtefactRecord };
  /** The refinement tileset, loaded only after a user action; null when the run publishes none. */
  detail: { url: string; bytes: number } | null;
  lane: ArtefactRecord["lane"];
  sources: TerrainSource[];
}

const LICENCE_LABELS: Readonly<Record<string, string>> = {
  "LicenseRef-USGov-PD": "public domain (US Government work)",
  "CC0-1.0": "CC0 1.0 (public domain dedication)",
};

export function licenceLabel(spdx: string): string {
  return LICENCE_LABELS[spdx] ?? spdx;
}

/**
 * URL of a manifest path. Published runs write `assets/<run>/...` (relative to the site base); older fixtures write the path
 * relative to `assets/`, so both are accepted. A path that fails the path rules of the asset loader is never turned into a URL.
 */
export function assetUrl(base: string, path: string): string | null {
  if (
    path.length === 0 ||
    path.length > 2000 ||
    path.startsWith("/") ||
    path.includes("\\") ||
    path.includes("..") ||
    path.includes("\u0000") ||
    /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(path) ||
    /%(2f|5c|2e|00)/i.test(path)
  )
    return null;
  return path.startsWith("assets/") ? `${base}${path}` : `${base}assets/${path}`;
}

const isTiles = (a: ArtefactRecord) => a.kind === "tiles";
const endsWith = (a: ArtefactRecord, suffix: string) => a.path.endsWith(suffix);

/**
 * The newest run's terrain for a case, or null when no tileset is published (the view then says "Not yet run"). A `null` case id is
 * the Explore route before a case is picked: the pit is the same for every case, so any published tileset applies.
 */
export function terrainModel(
  artefacts: readonly ArtefactRecord[],
  caseId: string | null,
  base: string,
): TerrainModel | null {
  const candidates = artefacts
    .filter(
      (a) => isTiles(a) && endsWith(a, "/lod0/tileset.json") && (caseId === null || appliesToCase(a, caseId)),
    )
    .sort((a, b) => (a.run_id < b.run_id ? 1 : a.run_id > b.run_id ? -1 : 0));
  const lod0 = candidates[0];
  if (!lod0) return null;
  const lod0Url = assetUrl(base, lod0.path);
  if (!lod0Url) return null;
  const sameRun = artefacts.filter((a) => a.run_id === lod0.run_id);
  const detailSet = sameRun.find((a) => isTiles(a) && endsWith(a, "/detail/tileset.json"));
  const detailUrl = detailSet ? assetUrl(base, detailSet.path) : null;
  const detailBytes = sameRun
    .filter((a) => isTiles(a) && a.path.includes("/detail/"))
    .reduce((sum, a) => sum + a.bytes, 0);
  const sources: TerrainSource[] = [];
  for (const a of [lod0, ...sameRun.filter((x) => x !== lod0 && (isTiles(x) || x.kind === "image"))]) {
    for (const input of a.inputs ?? []) {
      if (input.kind === "source" && !sources.some((s) => s.id === input.id))
        sources.push({ id: input.id, licence: licenceLabel(a.spdx) });
    }
  }
  return {
    runId: lod0.run_id,
    lod0: { url: lod0Url, artefact: lod0 },
    detail: detailSet && detailUrl ? { url: detailUrl, bytes: detailBytes } : null,
    lane: lod0.lane,
    sources,
  };
}

/** Megabytes with one decimal, as the load button says it. */
export function megabytes(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}
