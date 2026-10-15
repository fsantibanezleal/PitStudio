// @vitest-environment node
//
// T-007-014 (TypeScript half) · hostile scenario bundles and disconnected networks in the twin: FR-007-03, FR-007-04.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-03 (the adapter and the TypeScript twin reject a hostile bundle before simulating with `InvalidScenario` listing every violation (JSON path, value,
// rule), never clipping, defaulting or coercing a value: schema violation; NaN or infinite number; a count <= 0 (trucks, loaders, dumps, loader spots); more than 40 trucks in a `live` bundle or 400
// otherwise; segment length <= 0 m; |grade| >= 100 %; rolling resistance < 0 %; speed limit <= 0 km/h; unknown dispatcher, variate profile, truck class or loader class; duplicate node, segment or
// truck id), FR-007-04 (`DisconnectedNetwork` naming every unreachable (origin, destination, truck class) triple, within 1 s for networks of <= 10^4 segments), section 8 (a violation at `/horizon_s`
// is `InvalidHorizon`; class parameters must equal the engine pin). The Python half is tests/pipeline/test_t_007_014_scenario_hostile.py; both halves use the same cases.
//
// Oracle: the spec's hostile examples with the JSON pointers of their index; hand-modified copies of the valid example bundle (one violation each); the reachability rule of the engine's graph
// (a vehicle with a larger width class than the segment cannot use it; a one-way segment only from a to b), worked out by hand for the five-node smoke network.
//
// Expected API (module `~/engines/des/scenario`; errors in `~/engines/des/errors`):
//   InvalidScenario { violations: { path: string; value: unknown; rule: string }[] }   InvalidHorizon { violations }   DisconnectedNetwork { triples: [number, number, string][] }
//   validateBundle(bundle: unknown): void       same rules and pointers as the Python `validate_bundle` (duplicates at the later occurrence; non-finite numbers at the number); never mutates
//   checkConnectivity(bundle): void             same rule as the Python `check_connectivity`

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DisconnectedNetwork, InvalidHorizon, InvalidScenario } from "~/engines/des/errors";
import { checkConnectivity, validateBundle } from "~/engines/des/scenario";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
const EX = resolve(REPO, "specs/007-haulage-dispatch/contracts/examples");
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf-8"));
// biome-ignore lint/suspicious/noExplicitAny: bundles are plain JSON here
type B = Record<string, any>;
const smoke = (): B => readJson(resolve(EX, "haul-scenario.valid.json"));
const index = readJson(resolve(EX, "index.json")).examples as {
  file: string;
  valid: boolean;
  rule?: string;
  pointer?: string;
}[];
const hostile = index.filter(
  (e) => e.file.startsWith("haul-scenario.") && !e.valid && e.rule !== "FR-007-13",
);
const valid = index.filter((e) => e.file.startsWith("haul-scenario.") && e.valid).map((e) => e.file);

function reject(b: unknown): InvalidScenario {
  const before = structuredClone(b);
  let err: unknown;
  try {
    validateBundle(b);
  } catch (e) {
    err = e;
  }
  expect(err).toBeInstanceOf(InvalidScenario);
  expect(b).toEqual(before); // nothing clipped, defaulted or coerced
  const e = err as InvalidScenario;
  expect(e.violations.length).toBeGreaterThan(0);
  const keys = e.violations.map((v) => `${v.path}|${v.rule}`);
  expect(new Set(keys).size).toBe(keys.length);
  return e;
}
const paths = (e: InvalidScenario) => e.violations.map((v) => v.path);
function setPath(b: B, pointer: string, value: unknown): B {
  const parts = pointer.replace(/^\//, "").split("/");
  // biome-ignore lint/suspicious/noExplicitAny: walking JSON
  let node: any = b;
  for (const p of parts.slice(0, -1)) node = node[p];
  node[parts[parts.length - 1] as string] = value;
  return b;
}

describe("valid bundles", () => {
  for (const name of valid) {
    it(`FR-007-03 · ${name} is accepted unchanged and is connected`, () => {
      const b = readJson(resolve(EX, name));
      const before = structuredClone(b);
      validateBundle(b);
      checkConnectivity(b);
      expect(b).toEqual(before);
    });
  }
});

describe("the contract's hostile examples", () => {
  for (const e of hostile) {
    it(`FR-007-03 · ${e.file} is rejected at ${JSON.stringify(e.pointer)}`, () => {
      expect(paths(reject(readJson(resolve(EX, e.file))))).toContain(e.pointer);
    });
  }

  it("FR-007-03 · a horizon over seven days is InvalidHorizon", () => {
    const e = index.find((x) => x.rule === "FR-007-13" && x.file.startsWith("haul-scenario."));
    expect(e).toBeDefined();
    let err: unknown;
    try {
      validateBundle(readJson(resolve(EX, (e as { file: string }).file)));
    } catch (x) {
      err = x;
    }
    expect(err).toBeInstanceOf(InvalidHorizon);
    expect((err as InvalidHorizon).violations.map((v) => v.path)).toContain("/horizon_s");
  });
});

describe("one violation per case", () => {
  const numeric: [string, unknown][] = [
    ["/network/segments/0/grade_pct", Number.NaN],
    ["/network/segments/0/grade_pct", Number.POSITIVE_INFINITY],
    ["/network/segments/0/grade_pct", 100],
    ["/network/segments/0/grade_pct", -100],
    ["/network/segments/0/grade_pct", 100.001],
    ["/network/segments/0/length_m", 0],
    ["/network/segments/0/length_m", -5],
    ["/network/segments/0/length_m", Number.POSITIVE_INFINITY],
    ["/network/segments/0/length_m", Number.NaN],
    ["/network/segments/0/rolling_resistance_pct", -0.001],
    ["/network/segments/0/rolling_resistance_pct", Number.NaN],
    ["/network/segments/0/speed_limit_kmh", 0],
    ["/network/segments/0/speed_limit_kmh", -10],
    ["/network/segments/0/speed_limit_kmh", Number.NaN],
    ["/loaders/0/n_spots", 0],
    ["/loaders/0/n_spots", -1],
    ["/loaders/0/n_spots", "2"],
    ["/loaders/0/n_spots", 1.5],
    ["/loaders/0/n_spots", null],
  ];
  for (const [pointer, value] of numeric) {
    it(`FR-007-03 · ${pointer} = ${String(value)} is rejected at its own pointer`, () => {
      const e = reject(setPath(smoke(), pointer, value));
      expect(paths(e)).toContain(pointer);
      const v = e.violations.find((x) => x.path === pointer);
      expect(Object.is(v?.value, value)).toBe(true);
    });
  }

  for (const [pointer, value] of [
    ["/network/segments/0/grade_pct", 99.999],
    ["/network/segments/0/grade_pct", -99.999],
    ["/network/segments/0/rolling_resistance_pct", 0],
    ["/network/segments/0/speed_limit_kmh", 0.001],
    ["/network/segments/0/length_m", 0.001],
  ] as [string, number][]) {
    it(`FR-007-03 · ${pointer} = ${value} just inside the bound is accepted`, () => {
      validateBundle(setPath(smoke(), pointer, value));
    });
  }

  for (const [pointer, value] of [
    ["/dispatcher/id", "teleport"],
    ["/variate_profile", "lognormal"],
    ["/fleet/0/truck_class", "CAT_999Z"],
    ["/loaders/0/loader_class", "SHOVEL_99"],
    ["/equipment/truck_classes/0/name", "CAT_999Z"],
  ] as [string, string][]) {
    it(`FR-007-03 · unknown value at ${pointer}`, () => {
      expect(paths(reject(setPath(smoke(), pointer, value)))).toContain(pointer);
    });
  }

  for (const key of ["fleet", "loaders", "dumps"]) {
    it(`FR-007-03 · an empty ${key} list is rejected`, () => {
      const b = smoke();
      b[key] = [];
      expect(paths(reject(b))).toContain(`/${key}`);
    });
  }

  for (const [live, n, ok] of [
    [true, 40, true],
    [true, 41, false],
    [false, 41, true],
    [false, 400, true],
    [false, 401, false],
    [true, 400, false],
  ] as [boolean, number, boolean][]) {
    it(`FR-007-03 · fleet of ${n} in a bundle with live = ${live} is ${ok ? "accepted" : "rejected"}`, () => {
      const b = smoke();
      b.live = live;
      b.fleet = Array.from({ length: n }, (_, i) => ({
        id: i + 1,
        truck_class: "CAT_793F",
        start_loader: i % 2 === 0 ? 1 : 2,
      }));
      if (ok) validateBundle(b);
      else expect(paths(reject(b))).toContain("/fleet");
    });
  }

  for (const pointer of ["/network/nodes/1/id", "/network/segments/1/id", "/fleet/1/id"]) {
    it(`FR-007-03 · a duplicate id is reported at the later occurrence ${pointer}`, () => {
      expect(paths(reject(setPath(smoke(), pointer, 1)))).toContain(pointer);
    });
  }

  it("FR-007-03 · a duplicate dump is rejected", () => {
    const b = smoke();
    b.dumps = [4, 4];
    expect(paths(reject(b))).toContain("/dumps");
  });

  for (const [pointer, value] of [
    ["/network/segments/0/a", 99],
    ["/loaders/0/node", 99],
    ["/dumps/0", 99],
    ["/fleet/0/start_loader", 3],
  ] as [string, number][]) {
    it(`FR-007-03 · a dangling reference at ${pointer} is rejected`, () => {
      expect(paths(reject(setPath(smoke(), pointer, value)))).toContain(pointer);
    });
  }

  for (const [pointer, value] of [
    ["/equipment/truck_classes/0/payload_mean_t", 228],
    ["/equipment/truck_classes/0/rimpull_kn/0/force_kn", 1],
    ["/equipment/loader_classes/0/pass_t", 46],
  ] as [string, number][]) {
    it(`FR-007-03 · a class parameter that differs from the engine catalog is rejected at ${pointer}`, () => {
      expect(paths(reject(setPath(smoke(), pointer, value)))).toContain(pointer);
    });
  }

  it("FR-007-03 · documents that are not objects are rejected at the root", () => {
    for (const bad of [[], null, 3, "bundle"]) {
      let err: unknown;
      try {
        validateBundle(bad);
      } catch (e) {
        err = e;
      }
      expect(err).toBeInstanceOf(InvalidScenario);
      expect(paths(err as InvalidScenario)).toContain("");
    }
  });

  it("FR-007-03 · every violation of a bundle is listed and nothing else", () => {
    const b = smoke();
    b.network.segments[0].grade_pct = Number.NaN;
    b.network.segments[1].length_m = 0;
    b.fleet[1].id = 1;
    b.dispatcher.id = "teleport";
    b.loaders[0].n_spots = 0;
    const e = reject(b);
    const expected = [
      "/network/segments/0/grade_pct",
      "/network/segments/1/length_m",
      "/fleet/1/id",
      "/dispatcher/id",
      "/loaders/0/n_spots",
    ];
    for (const p of expected) expect(paths(e)).toContain(p);
    for (const p of paths(e))
      expect(expected.some((x) => p === x || p.startsWith(`${x}/`) || x.startsWith(`${p}/`))).toBe(true);
  });
});

describe("FR-007-04 · disconnected networks", () => {
  function disconnected(b: B): string[] {
    let err: unknown;
    try {
      checkConnectivity(b);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(DisconnectedNetwork);
    return (err as DisconnectedNetwork).triples.map((t) => t.join(",")).sort();
  }
  const T = (...x: [number, number][]) => x.map(([a, b]) => `${a},${b},CAT_793F`).sort();

  it("FR-007-04 · an isolated dump names every unreachable pair in both directions", () => {
    const b = smoke();
    b.network.segments = b.network.segments.filter((s: B) => s.id !== 4);
    expect(disconnected(b)).toEqual(T([1, 5], [2, 5], [5, 1], [5, 2]));
  });

  it("FR-007-04 · a one-way road makes the way back unreachable", () => {
    const b = smoke();
    b.network.segments.find((s: B) => s.id === 3).one_way = true;
    expect(disconnected(b)).toEqual(T([4, 1], [4, 2]));
  });

  it("FR-007-04 · a one-way road in the wrong direction blocks the way in", () => {
    const b = smoke();
    const s = b.network.segments.find((x: B) => x.id === 3);
    [s.a, s.b] = [s.b, s.a];
    s.polyline_m.reverse();
    s.grade_pct = -s.grade_pct;
    s.one_way = true;
    expect(disconnected(b)).toEqual(T([1, 4], [2, 4]));
  });

  it("FR-007-04 · a segment narrower than the truck class cannot be used", () => {
    const b = smoke();
    b.network.segments.find((s: B) => s.id === 2).width_class = 1;
    expect(disconnected(b)).toEqual(T([2, 4], [2, 5], [4, 2], [5, 2]));
  });

  it("FR-007-04 · two islands name every cross pair", () => {
    const b = smoke();
    b.network.segments = b.network.segments.filter((s: B) => s.id !== 1 && s.id !== 2);
    expect(disconnected(b)).toEqual(T([1, 4], [1, 5], [2, 4], [2, 5], [4, 1], [4, 2], [5, 1], [5, 2]));
  });

  it("FR-007-04 · a network of 9,660 segments is checked within one second", () => {
    const side = 70;
    const b = smoke();
    const id = (r: number, c: number) => r * side + c + 1;
    const nodes: B[] = [];
    const segs: B[] = [];
    for (let r = 0; r < side; r++) {
      for (let c = 0; c < side; c++) {
        const face = (r === 0 && c === 0) || (r === 0 && c === side - 1);
        const dump = r === side - 1 && (c === 0 || c === side - 1);
        nodes.push({
          id: id(r, c),
          kind: face ? "face" : dump ? "dump" : "junction",
          pos_m: [100 * c, 100 * r, 1000],
        });
      }
    }
    let k = 0;
    for (let r = 0; r < side; r++) {
      for (let c = 0; c < side; c++) {
        for (const [dr, dc] of [
          [0, 1],
          [1, 0],
        ] as [number, number][]) {
          if (r + dr < side && c + dc < side) {
            k++;
            segs.push({
              id: k,
              a: id(r, c),
              b: id(r + dr, c + dc),
              polyline_m: [
                [100 * c, 100 * r, 1000],
                [100 * (c + dc), 100 * (r + dr), 1000],
              ],
              length_m: 100,
              grade_pct: 0,
              width_class: 2,
              one_way: false,
              speed_limit_kmh: 40,
              rolling_resistance_pct: 2,
              zone_id: null,
              single_lane_op: false,
            });
          }
        }
      }
    }
    b.network = { nodes, segments: segs, zones: [], junctions: [] };
    b.loaders = [
      { node: id(0, 0), loader_class: "SHOVEL_45", n_spots: 1, destination_dump: id(side - 1, 0) },
      {
        node: id(0, side - 1),
        loader_class: "SHOVEL_45",
        n_spots: 1,
        destination_dump: id(side - 1, side - 1),
      },
    ];
    b.dumps = [id(side - 1, 0), id(side - 1, side - 1)];
    b.fleet = [{ id: 1, truck_class: "CAT_793F", start_loader: id(0, 0) }];
    expect(segs.length).toBe(9660);
    const t0 = performance.now();
    checkConnectivity(b);
    expect(performance.now() - t0).toBeLessThan(1000);
    b.network.segments = segs.filter((s) => s.a !== id(side - 1, 0) && s.b !== id(side - 1, 0));
    const t1 = performance.now();
    const got = disconnected(b);
    expect(performance.now() - t1).toBeLessThan(1000);
    expect(got).toEqual(
      T(
        [id(0, 0), id(side - 1, 0)],
        [id(0, side - 1), id(side - 1, 0)],
        [id(side - 1, 0), id(0, 0)],
        [id(side - 1, 0), id(0, side - 1)],
      ),
    );
  });
});
