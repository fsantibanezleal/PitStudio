// Shared, locked E2E support (first used by T-018-020; also T-018-023 and T-018-037). Not a test file.
//
// A tiny but valid 3D Tiles 1.1 tileset (one root tile whose content is a glTF 2.0 binary holding one triangle), the web-manifest records that list it as the
// Bingham Canyon LOD-0 terrain (source `usgs-3dep-bingham`, public domain, STATIC), and the page routes that serve them. Used where a real LOD-0 tileset does not exist yet.
//   artefact id `bingham-lod0-tileset`, kind `tiles`, path `tiles/lod0/tileset.json`, budget class `tiles-glb`, lane static, spdx LicenseRef-USGov-PD,
//   input `usgs-3dep-bingham`; tile content `tiles/lod0/lod0.glb` (served through the same route family, referenced by the tileset URI).
// Scene hooks observed with it (see t_018_020): [data-testid="scene-canvas"][data-renderer="webgpu"|"webgl2"], [data-testid="provenance-chip"],
// window.__pitstudio.renderers = [{ canvasId, kind, purpose }].
import { createHash } from "node:crypto";
import type { Page } from "@playwright/test";
import { makeArtefact, makeWebIndex } from "../../src/test-support/fixtures";

/** glTF 2.0 binary with one triangle (0,0,0) (1,0,0) (0,1,0): a spec-conformant minimal GLB (glTF 2.0 section 4: header, JSON chunk, BIN chunk). */
export function makeTriangleGlb(): Buffer {
  const json = Buffer.from(
    JSON.stringify({
      asset: { version: "2.0" },
      scene: 0,
      scenes: [{ nodes: [0] }],
      nodes: [{ mesh: 0 }],
      meshes: [{ primitives: [{ attributes: { POSITION: 0 } }] }],
      accessors: [
        { bufferView: 0, componentType: 5126, count: 3, type: "VEC3", min: [0, 0, 0], max: [1, 1, 0] },
      ],
      bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: 36 }],
      buffers: [{ byteLength: 36 }],
    }),
  );
  const padded = Buffer.concat([json, Buffer.alloc((4 - (json.length % 4)) % 4, 0x20)]);
  const bin = Buffer.alloc(36);
  [0, 0, 0, 1, 0, 0, 0, 1, 0].forEach((v, i) => {
    bin.writeFloatLE(v, i * 4);
  });
  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + padded.length + 8 + bin.length, 8);
  const jsonHead = Buffer.alloc(8);
  jsonHead.writeUInt32LE(padded.length, 0);
  jsonHead.writeUInt32LE(0x4e4f534a, 4);
  const binHead = Buffer.alloc(8);
  binHead.writeUInt32LE(bin.length, 0);
  binHead.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, jsonHead, padded, binHead, bin]);
}

export const TILESET = {
  asset: { version: "1.1" },
  geometricError: 500,
  root: {
    boundingVolume: { box: [0.5, 0.5, 0, 10, 0, 0, 0, 10, 0, 0, 0, 10] },
    geometricError: 0,
    refine: "ADD",
    content: { uri: "lod0.glb" },
  },
};

export interface TileRoutes {
  requested: () => string[];
}

/** Serves the manifest with the LOD-0 tileset and the tileset and tile files; returns the list of tile requests seen. */
export async function routeTiles(page: Page): Promise<TileRoutes> {
  const tileset = Buffer.from(JSON.stringify(TILESET));
  const glb = makeTriangleGlb();
  const requested: string[] = [];
  const manifest = makeWebIndex([
    makeArtefact({
      id: "bingham-lod0-tileset",
      kind: "tiles",
      path: "tiles/lod0/tileset.json",
      bytes: tileset.length,
      sha256: createHash("sha256").update(tileset).digest("hex"),
      cases: [],
      lane: "static",
      budget_class: "tiles-glb",
      licence_class: "public-domain",
      spdx: "LicenseRef-USGov-PD",
      inputs: [{ id: "usgs-3dep-bingham", sha256: "a".repeat(64), kind: "source" }],
      producer: { tool: "openusd", stage: { id: "st40_compose" } },
    }),
  ]);
  await page.route("**/assets/manifest.json", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }),
  );
  await page.route("**/assets/tiles/lod0/tileset.json", (route) => {
    requested.push("tileset");
    return route.fulfill({ contentType: "application/json", body: tileset });
  });
  await page.route("**/assets/tiles/lod0/*.glb", (route) => {
    requested.push("glb");
    return route.fulfill({ contentType: "model/gltf-binary", body: glb });
  });
  return { requested: () => [...requested] };
}
