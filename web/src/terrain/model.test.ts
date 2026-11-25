// The published terrain of the 3D view (FR-018-01): which artefacts form the LOD-0 tileset, the detail tileset and the sources.
// Oracles: the manifest rules of data-model 001 (an artefact belongs to a case when `cases` is absent or lists it), hand-written records
// shaped like the ones `studio publish` writes for the web-terrain run, and the byte sums by hand.
import { describe, expect, it } from "vitest";
import type { ArtefactRecord } from "~/cases/types";
import { assetUrl, licenceLabel, megabytes, terrainModel } from "./model";

const RUN = "20261123T120000Z-web-terrain-bingham";
const base = (over: Partial<ArtefactRecord> & { id: string; path: string }): ArtefactRecord => ({
  run_id: RUN,
  git_sha: "a".repeat(40),
  bytes: 1000,
  sha256: "b".repeat(64),
  kind: "tiles",
  producer: { tool: "openusd", stage: { id: "s60_export" } },
  inputs: [
    { id: "usgs-3dep-bingham", sha256: "c".repeat(64), kind: "source" },
    { id: "usda-naip-bingham", sha256: "d".repeat(64), kind: "source" },
  ],
  lane: "static",
  licence_class: "public-domain",
  spdx: "LicenseRef-USGov-PD",
  ...over,
});

const published: ArtefactRecord[] = [
  base({ id: "bingham-lod0-tileset", path: `assets/${RUN}/tiles/lod0/tileset.json`, bytes: 240 }),
  base({ id: "bingham-lod0-lod0", path: `assets/${RUN}/tiles/lod0/lod0.glb`, bytes: 428_000 }),
  base({ id: "bingham-detail-tileset", path: `assets/${RUN}/tiles/detail/tileset.json`, bytes: 6_500 }),
  base({
    id: "bingham-detail-lod1-l1-0-0",
    path: `assets/${RUN}/tiles/detail/lod1/l1-0-0.glb`,
    bytes: 100_000,
  }),
  base({
    id: "bingham-detail-lod2-l2-0-0",
    path: `assets/${RUN}/tiles/detail/lod2/l2-0-0.glb`,
    bytes: 900_000,
  }),
  base({
    id: "bingham-textures-rock-normal",
    path: `assets/${RUN}/tiles/textures/rock-normal.jpg`,
    kind: "image",
    spdx: "CC0-1.0",
    licence_class: "open-no-attribution",
    inputs: [{ id: "polyhaven-rock-boulder-dry", sha256: "e".repeat(64), kind: "source" }],
  }),
];

describe("terrainModel", () => {
  it("finds the LOD-0 tileset, the detail tileset and the byte size of the detail files", () => {
    const m = terrainModel(published, "A1", "/PitStudio/");
    expect(m?.runId).toBe(RUN);
    expect(m?.lod0.url).toBe(`/PitStudio/assets/${RUN}/tiles/lod0/tileset.json`);
    expect(m?.detail?.url).toBe(`/PitStudio/assets/${RUN}/tiles/detail/tileset.json`);
    expect(m?.detail?.bytes).toBe(6_500 + 100_000 + 900_000);
    expect(m?.lane).toBe("static");
  });

  it("lists every source once with the licence of the artefact that names it", () => {
    const m = terrainModel(published, "A1", "/");
    expect(m?.sources).toEqual([
      { id: "usgs-3dep-bingham", licence: "public domain (US Government work)" },
      { id: "usda-naip-bingham", licence: "public domain (US Government work)" },
      { id: "polyhaven-rock-boulder-dry", licence: "CC0 1.0 (public domain dedication)" },
    ]);
  });

  it("is null without a tileset and for a case the tileset does not name", () => {
    expect(terrainModel([], "A1", "/")).toBeNull();
    expect(terrainModel(published.slice(1), "A1", "/")).toBeNull();
    const own = published.map((a) => ({ ...a, cases: ["B1"] }));
    expect(terrainModel(own, "A1", "/")).toBeNull();
    expect(terrainModel(own, "B1", "/")?.runId).toBe(RUN);
    expect(terrainModel(own, null, "/")?.runId).toBe(RUN); // Explore before a case is picked
  });

  it("takes the newest run when two runs publish a tileset", () => {
    const newer = "20261201T000000Z-web-terrain-bingham";
    const both = [
      ...published,
      base({ id: "bingham-lod0-tileset-2", run_id: newer, path: `assets/${newer}/tiles/lod0/tileset.json` }),
    ];
    expect(terrainModel(both, "A1", "/")?.runId).toBe(newer);
    expect(terrainModel(both, "A1", "/")?.detail).toBeNull();
  });

  it("accepts a path written relative to assets/ (the fixture form) and refuses a hostile path", () => {
    const fixture = base({
      id: "bingham-lod0-tileset",
      path: "tiles/lod0/tileset.json",
      run_id: "20261001T000000Z-x",
    });
    expect(terrainModel([fixture], "A1", "/")?.lod0.url).toBe("/assets/tiles/lod0/tileset.json");
    for (const path of [
      "/etc/tiles/lod0/tileset.json",
      "../tiles/lod0/tileset.json",
      "http://x/lod0/tileset.json",
      "alod0/tileset.json",
    ])
      expect(terrainModel([{ ...fixture, path }], "A1", "/")).toBeNull();
    expect(assetUrl("/", "tiles/%2e%2e/x")).toBeNull();
  });
});

describe("labels", () => {
  it("names the licences a visitor reads and falls back to the SPDX id", () => {
    expect(licenceLabel("LicenseRef-USGov-PD")).toBe("public domain (US Government work)");
    expect(licenceLabel("Apache-2.0")).toBe("Apache-2.0");
  });
  it("writes megabytes with one decimal", () => {
    expect(megabytes(1_006_500)).toBe("1.0 MB");
    expect(megabytes(26_311_697)).toBe("26.3 MB");
  });
});
