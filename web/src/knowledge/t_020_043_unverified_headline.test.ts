// T-020-043 [red] · FR-020-42 (a headline KPI whose manifest lists an UNVERIFIED knowledge row among its inputs, an input with `kind: knowledge` and the knowledge-table row id as its `id`, is not shown as a headline on `/` or
// `/results` and carries the UNVERIFIED badge wherever it appears) and SC-020-03 (at release no headline KPI depends on an UNVERIFIED value).
//
// Expected API (web/src/knowledge/headline.ts):
//   UNVERIFIED_BADGE = "UNVERIFIED — pinned at specification"
//   unverifiedInputs(inputs: Array<{ id: string; kind: string }> | undefined, rows: Array<{ id: string; verification: string }>): string[]
//       the ids of the inputs that are knowledge inputs (kind "knowledge") naming a row whose verification is exactly "UNVERIFIED", in the order of the inputs, without repeats; inputs of another kind never count, whatever their id;
//   partitionHeadlines<K extends { id: string; inputs?: Array<{ id: string; kind: string }> }>(kpis: K[], rows): { headline: K[]; demoted: Array<K & { unverified: string[] }> }
//       a KPI with at least one unverified input is demoted (and carries the ids in `unverified`, so that the badge can be shown wherever it appears); every other KPI stays a headline; both lists keep the order of `kpis`;
//   badgeFor(kpi, rows): { badge: boolean; ids: string[] }   the badge of a KPI wherever it appears (case page, results row): true exactly when the KPI has an unverified input.
// Oracles: the definition of FR-020-42 written out by hand (a KPI with a `knowledge:` input marked UNVERIFIED), the three rows of the valid knowledge bundle (diesel_co2_kg_per_us_gal verified; kuzram_rock_factor_range and
// beverloo_exponent UNVERIFIED), the algebra of the partition (a permutation that preserves order).
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { badgeFor, partitionHeadlines, UNVERIFIED_BADGE, unverifiedInputs } from "~/knowledge/headline";

const rows = [
  { id: "diesel_co2_kg_per_us_gal", verification: "verified" },
  { id: "kuzram_rock_factor_range", verification: "UNVERIFIED" },
  { id: "beverloo_exponent", verification: "UNVERIFIED" },
];
const sha = "a".repeat(64);
const kn = (id: string) => ({ id, sha256: sha, kind: "knowledge" });
const kpi = (id: string, inputs?: Array<{ id: string; kind: string }>) => ({ id, inputs });

describe("which inputs are unverified (FR-020-42)", () => {
  it("FR-020-42 · the badge text is 'UNVERIFIED — pinned at specification'", () => {
    expect(UNVERIFIED_BADGE).toBe("UNVERIFIED — pinned at specification");
  });

  it("FR-020-42 · a knowledge input naming an UNVERIFIED row counts; one naming a verified row does not", () => {
    expect(unverifiedInputs([kn("kuzram_rock_factor_range")], rows)).toEqual(["kuzram_rock_factor_range"]);
    expect(unverifiedInputs([kn("diesel_co2_kg_per_us_gal")], rows)).toEqual([]);
  });

  it("FR-020-42 · only inputs of kind knowledge count: a source or an artefact with the id of an UNVERIFIED row does not", () => {
    expect(
      unverifiedInputs(
        [
          { id: "kuzram_rock_factor_range", kind: "source" },
          { id: "beverloo_exponent", kind: "artefact" },
        ],
        rows,
      ),
    ).toEqual([]);
  });

  it("FR-020-42 · the ids come in the order of the inputs, once each", () => {
    expect(
      unverifiedInputs(
        [
          kn("beverloo_exponent"),
          kn("diesel_co2_kg_per_us_gal"),
          kn("kuzram_rock_factor_range"),
          kn("beverloo_exponent"),
        ],
        rows,
      ),
    ).toEqual(["beverloo_exponent", "kuzram_rock_factor_range"]);
  });

  it("FR-020-42 · the verification value must be exactly 'UNVERIFIED': 'unverified', 'verified' and anything else are not flagged", () => {
    const odd = [
      { id: "a", verification: "unverified" },
      { id: "b", verification: "verified" },
      { id: "c", verification: "" },
      { id: "d", verification: "UNVERIFIED " },
    ];
    expect(unverifiedInputs(["a", "b", "c", "d"].map(kn), odd)).toEqual([]);
  });

  it("FR-020-42 · no inputs, no rows, an input that names no row: nothing is flagged and nothing throws", () => {
    expect(unverifiedInputs(undefined, rows)).toEqual([]);
    expect(unverifiedInputs([], rows)).toEqual([]);
    expect(unverifiedInputs([kn("kuzram_rock_factor_range")], [])).toEqual([]);
    expect(unverifiedInputs([kn("no-such-row")], rows)).toEqual([]);
  });

  it("FR-020-42 · hostile ids (markup, 5,000 characters, prototype names) are plain strings", () => {
    const hostile = [
      "<img src=x onerror=alert(1)>",
      "x".repeat(5000),
      "__proto__",
      "constructor",
      "toString",
    ];
    expect(unverifiedInputs(hostile.map(kn), rows)).toEqual([]);
    expect(
      unverifiedInputs(
        hostile.map(kn),
        hostile.map((id) => ({ id, verification: "UNVERIFIED" })),
      ),
    ).toEqual(hostile);
  });
});

describe("headline partition (FR-020-42, SC-020-03)", () => {
  const kpis = [
    kpi("throughput", [kn("diesel_co2_kg_per_us_gal")]),
    kpi("x50", [kn("kuzram_rock_factor_range")]),
    kpi("queue_time"),
    kpi("discharge", [kn("beverloo_exponent"), kn("diesel_co2_kg_per_us_gal")]),
    kpi("fos", [{ id: "kuzram_rock_factor_range", kind: "source" }]),
  ];

  it("FR-020-42 · a KPI with an UNVERIFIED knowledge input is demoted; the others stay headlines, in order", () => {
    const { headline, demoted } = partitionHeadlines(kpis, rows);
    expect(headline.map((k) => k.id)).toEqual(["throughput", "queue_time", "fos"]);
    expect(demoted.map((k) => k.id)).toEqual(["x50", "discharge"]);
  });

  it("FR-020-42 · a demoted KPI carries the ids that demoted it", () => {
    const { demoted } = partitionHeadlines(kpis, rows);
    expect(demoted.map((k) => k.unverified)).toEqual([["kuzram_rock_factor_range"], ["beverloo_exponent"]]);
  });

  it("SC-020-03 · with every row verified no KPI is demoted: 0 headline KPIs depend on an UNVERIFIED value", () => {
    const verified = rows.map((r) => ({ ...r, verification: "verified" }));
    const { headline, demoted } = partitionHeadlines(kpis, verified);
    expect(demoted).toEqual([]);
    expect(headline.map((k) => k.id)).toEqual(kpis.map((k) => k.id));
  });

  it("FR-020-42 · the badge follows the KPI wherever it appears: badgeFor is true exactly for the demoted ones", () => {
    expect(badgeFor(kpis[1] as never, rows)).toEqual({ badge: true, ids: ["kuzram_rock_factor_range"] });
    expect(badgeFor(kpis[0] as never, rows)).toEqual({ badge: false, ids: [] });
    expect(badgeFor(kpis[2] as never, rows)).toEqual({ badge: false, ids: [] });
  });

  it("FR-020-42 · an empty list of KPIs gives two empty lists", () => {
    expect(partitionHeadlines([], rows)).toEqual({ headline: [], demoted: [] });
  });

  it("FR-020-42 · the KPI objects are kept as given (no copy loses a field)", () => {
    const k = { id: "x50", inputs: [kn("kuzram_rock_factor_range")], unit: "mm", extra: { a: 1 } };
    const { demoted } = partitionHeadlines([k], rows);
    expect(demoted[0]).toMatchObject({ id: "x50", unit: "mm", extra: { a: 1 } });
  });

  const idPool = ["r1", "r2", "r3", "r4", "r5"];
  const rowsArb = fc.array(
    fc.record({ id: fc.constantFrom(...idPool), verification: fc.constantFrom("verified", "UNVERIFIED") }),
    { maxLength: 8 },
  );
  const kpiArb = fc.array(
    fc.record({
      id: fc.uuid(),
      inputs: fc.array(
        fc.record({
          id: fc.constantFrom(...idPool, "other"),
          kind: fc.constantFrom("knowledge", "source", "artefact"),
        }),
        { maxLength: 4 },
      ),
    }),
    { maxLength: 12 },
  );

  it("FR-020-42 · random KPIs and rows: the two lists are a partition that keeps order, and a KPI is demoted iff it has a knowledge input naming an UNVERIFIED row", () => {
    fc.assert(
      fc.property(kpiArb, rowsArb, (ks, rs) => {
        const { headline, demoted } = partitionHeadlines(ks, rs);
        expect(headline.length + demoted.length).toBe(ks.length);
        const order = new Map(ks.map((k, i) => [k.id, i]));
        for (const list of [headline, demoted])
          for (let i = 1; i < list.length; i++)
            expect(order.get((list[i] as { id: string }).id) as number).toBeGreaterThan(
              order.get((list[i - 1] as { id: string }).id) as number,
            );
        const bad = new Set(rs.filter((r) => r.verification === "UNVERIFIED").map((r) => r.id));
        for (const k of ks) {
          const flagged = k.inputs.some((i) => i.kind === "knowledge" && bad.has(i.id));
          expect(
            demoted.some((d) => d.id === k.id),
            k.id,
          ).toBe(flagged);
          expect(badgeFor(k, rs).badge).toBe(flagged);
        }
      }),
      { numRuns: 200 },
    );
  });
});
