// T-020-042 [red] · FR-020-35 (glossary: for every term the EN term, the ES term, the definition in the active language and its source where one exists; search matches either language ignoring case and accents), FR-020-41 (a query
// with markup, regular-expression metacharacters, control or bidirectional characters, or more than 2,000 characters is matched as literal text, truncated to 2,000 characters, highlights are escaped text, no error), P-020-32 (search
// normalisation and refinement) and NFR-020-08 (search latency over 10^4 rows: p95 <= 100 ms over 50 queries; the browser half is web/e2e/t_020_042_search.spec.ts).
//
// Expected API (web/src/knowledge/):
//   search.ts            normalise(text: string): string   lower-case with accents removed (Unicode NFD without combining marks U+0300..U+036F);
//                        truncateQuery(query: string): string   the first 2,000 characters (UTF-16 units) of the query;
//                        searchRows<T>(rows: T[], query: string, fields: (row: T) => string[]): T[]   the rows, in order, one of whose fields contains the normalised, truncated query as a LITERAL substring of its normalised text;
//                        an empty (or whitespace-only) query keeps every row; it never throws and builds no regular expression from the query;
//                        highlight(text: string, query: string): Array<{ text: string; match: boolean }>   the text cut into segments in which exactly the (normalised, literal) occurrences of the query are `match: true`; concatenated, the segments give the text back.
//   GlossarySection.tsx  GlossarySection({ entries: GlossaryEntry[] }), entries of the knowledge bundle (id, origin, term_en, term_es, definition_en, definition_es, citation?); the query is the `q` parameter of the URL;
//                        hooks: li[data-term="<id>"] with [data-field="term-en"], [data-field="term-es"], [data-field="definition"] (the definition of the ACTIVE language), [data-field="source"] (the citation key, only when there is one),
//                        `mark` elements around the matched text of the terms and the definition, [data-testid="search"] (type=search, value = q, maxlength 2000), [data-testid="no-match"] "No matching terms".
// Oracles: hand cases from the valid knowledge bundle (match_factor / Factor de acoplamiento, ppv / Velocidad peak de partícula) and the glossary of docs/reference/glossary.md; the normalisation written out here with String.normalize;
// the algebra of the properties (case and accent invariance, refinement is monotone); the timing bound of NFR-020-08.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { screen } from "@testing-library/react";
import fc from "fast-check";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { GlossarySection } from "~/knowledge/GlossarySection";
import { highlight, normalise, searchRows, truncateQuery } from "~/knowledge/search";
import { renderApp } from "~/test-support/render";

const bundle = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../specs/020-web-knowledge/contracts/examples/knowledge-bundle.valid.json",
    ),
    "utf8",
  ),
) as {
  glossary: Array<{
    id: string;
    term_en: string;
    term_es: string;
    definition_en: string;
    definition_es: string;
    citation?: string;
  }>;
};
const strip = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "");
const fields = (e: { term_en: string; term_es: string; definition_en: string; definition_es: string }) => [
  e.term_en,
  e.term_es,
  e.definition_en,
  e.definition_es,
];
const find = (q: string, rows = bundle.glossary) => searchRows(rows, q, fields).map((r) => r.id);

describe("normalisation and literal matching (FR-020-35, FR-020-41)", () => {
  it("FR-020-35 · normalise lower-cases and strips accents: 'Velocidad peak de partícula ÁÑÜ' becomes 'velocidad peak de particula anu'", () => {
    expect(normalise("Velocidad peak de partícula ÁÑÜ")).toBe("velocidad peak de particula anu");
    expect(normalise("")).toBe("");
    expect(normalise("ABC def 123")).toBe("abc def 123");
  });

  it("FR-020-35 · either language matches, ignoring case and accents: 'acoplamiento', 'ACOPLAMIENTO', 'factor de acopl' find the match factor; 'particula' finds the PPV", () => {
    expect(find("acoplamiento")).toEqual(["match_factor"]);
    expect(find("ACOPLAMIENTO")).toEqual(["match_factor"]);
    expect(find("factor de acopl")).toEqual(["match_factor"]);
    expect(find("particula")).toEqual(["ppv"]);
    expect(find("PARTÍCULA")).toEqual(["ppv"]);
    expect(find("peak particle")).toEqual(["ppv"]);
    expect(find("match")).toEqual(["match_factor"]);
  });

  it("FR-020-35 · it matches inside the definitions of both languages", () => {
    expect(find("tasa de servicio")).toEqual(["match_factor"]);
    expect(find("service rate")).toEqual(["match_factor"]);
    expect(find("vibracion del terreno")).toEqual(["ppv"]);
  });

  it("FR-020-35 · an empty or blank query keeps every row, in order", () => {
    expect(find("")).toEqual(["match_factor", "ppv"]);
    expect(find("   ")).toEqual(["match_factor", "ppv"]);
  });

  it("FR-020-35 · a query that matches nothing gives no row", () => {
    expect(find("zzzzzz")).toEqual([]);
  });

  const hostile = [
    "<b>",
    "<script>alert(1)</script>",
    ".*",
    "(",
    "[a-z]+",
    "\\",
    "^match$",
    "match|ppv",
    "${x}",
    "a{2",
    "?",
    "+",
    "\u0000",
    "\u0007",
    "match factor\n",
    "x".repeat(20_000),
    "😀",
    "\ud800",
  ];
  for (const q of hostile) {
    it(`FR-020-41 · the query ${JSON.stringify(q.length > 20 ? `${q.slice(0, 20)}…(${q.length})` : q)} is literal: it throws nothing and matches only text that contains it`, () => {
      const hits = find(q);
      for (const id of hits) {
        const e = bundle.glossary.find((g) => g.id === id) as (typeof bundle.glossary)[number];
        expect(
          fields(e).some((f) => normalise(f).includes(normalise(truncateQuery(q)))),
          q.slice(0, 20),
        ).toBe(true);
      }
      expect(() => highlight("some text", q)).not.toThrow();
    });
  }

  it("FR-020-41 · regular-expression metacharacters match themselves: 'ppv' finds the PPV but '.pv' and 'p+v' do not; a row holding '(PPV)' is found by '(ppv)'", () => {
    expect(find("ppv")).toEqual(["ppv"]);
    expect(find(".pv")).toEqual([]);
    expect(find("p+v")).toEqual([]);
    expect(find("(ppv)")).toEqual(["ppv"]);
    expect(find("(")).toEqual(["ppv"]);
  });

  it("FR-020-41 · a control or bidirectional character is part of the literal query: the RLO character does not match a row that lacks it", () => {
    const rlo = String.fromCharCode(0x202e);
    expect(find(`${rlo}match`)).toEqual([]);
    const rows = [{ id: "x", term_en: `ab${rlo}cd`, term_es: "", definition_en: "", definition_es: "" }];
    expect(find(`b${rlo}c`, rows as never)).toEqual(["x"]);
  });

  it("FR-020-41 · the query is truncated to 2,000 characters: 20,000 x give the results of 2,000 x, and a row that holds 2,000 x matches", () => {
    expect(truncateQuery("x".repeat(20_000))).toBe("x".repeat(2000));
    expect(truncateQuery("short")).toBe("short");
    const rows = [
      { id: "long", term_en: "x".repeat(2000), term_es: "", definition_en: "", definition_es: "" },
      { id: "short", term_en: "x".repeat(1999), term_es: "", definition_en: "", definition_es: "" },
    ];
    expect(find("x".repeat(20_000), rows as never)).toEqual(["long"]);
    expect(find("x".repeat(2000), rows as never)).toEqual(["long"]);
  });

  it("FR-020-41 · highlight returns segments that concatenate back to the text, with exactly the occurrences marked, as plain strings", () => {
    const segs = highlight("Match factor, match FACTOR <b>x</b>", "factor");
    expect(segs.map((s) => s.text).join("")).toBe("Match factor, match FACTOR <b>x</b>");
    expect(segs.filter((s) => s.match).map((s) => s.text)).toEqual(["factor", "FACTOR"]);
    const accent = highlight("Velocidad peak de partícula", "PARTICULA");
    expect(accent.filter((s) => s.match).map((s) => s.text)).toEqual(["partícula"]);
    expect(highlight("abc", "").every((s) => !s.match)).toBe(true);
    expect(
      highlight("<b>", "<b>")
        .filter((s) => s.match)
        .map((s) => s.text),
    ).toEqual(["<b>"]);
  });
});

describe("properties (P-020-32)", () => {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789 áéíóúñü";
  const text = fc.array(fc.constantFrom(...alphabet), { minLength: 0, maxLength: 24 }).map((a) => a.join(""));
  const rows = fc
    .array(text, { minLength: 1, maxLength: 30 })
    .map((ts) => ts.map((t, i) => ({ id: `r${i}`, t })));
  const run = (rs: Array<{ id: string; t: string }>, q: string) =>
    searchRows(rs, q, (r) => [r.t]).map((r) => r.id);

  it("P-020-32 · the results do not depend on case or accents: results(q) = results(upper(q)) = results(strip-accents(q))", () => {
    fc.assert(
      fc.property(rows, text, (rs, q) => {
        const base = run(rs, q);
        expect(run(rs, q.toUpperCase())).toEqual(base);
        expect(run(rs, strip(q))).toEqual(base);
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-32 · refinement: appending characters to the query never adds results", () => {
    fc.assert(
      fc.property(rows, text, text, (rs, q, more) => {
        const wider = new Set(run(rs, q));
        for (const id of run(rs, q + more)) expect(wider.has(id)).toBe(true);
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-32 · matching is literal substring matching: the results are exactly the rows whose normalised text contains the normalised query", () => {
    fc.assert(
      fc.property(rows, text, (rs, q) => {
        const expected = rs
          .filter((r) => normalise(r.t).includes(normalise(q.trim() === "" ? "" : q)))
          .map((r) => r.id);
        expect(run(rs, q.trim() === "" ? "" : q)).toEqual(expected);
      }),
      { numRuns: 200 },
    );
  });
});

describe("latency (NFR-020-08)", () => {
  it("NFR-020-08 · over 10^4 rows the p95 of 50 queries is at most 100 ms", () => {
    const words = [
      "haulage",
      "bench",
      "comminution",
      "fragmentation",
      "slope",
      "tailings",
      "dust",
      "blast",
      "mill",
      "crusher",
      "ángulo",
      "conminución",
      "tronadura",
    ];
    const rs = Array.from({ length: 10_000 }, (_, i) => ({
      id: `r${i}`,
      a: `${words[i % words.length]} term ${i}`,
      b: `${words[(i * 7) % words.length]} definition number ${i} with some longer text about open pit mining`,
      c: `ref${i % 97}`,
    }));
    const times: number[] = [];
    for (let q = 0; q < 50; q++) {
      const query = [
        `${words[q % words.length]}`,
        "term 12",
        "definition number 9",
        "ÁNGULO",
        "mill",
        "zzzz",
      ][q % 6] as string;
      const t0 = performance.now();
      searchRows(rs, query, (r) => [r.a, r.b, r.c]);
      times.push(performance.now() - t0);
    }
    times.sort((x, y) => x - y);
    expect(times[Math.ceil(0.95 * times.length) - 1] as number).toBeLessThanOrEqual(100);
  });
});

describe("the glossary section (FR-020-35, FR-020-41)", () => {
  const render = (query = "", lang: "en" | "es" = "en", entries: unknown[] = bundle.glossary) =>
    renderApp(createElement(GlossarySection, { entries: entries as never }), {
      lang,
      route: `/knowledge/?section=glossary${query}`,
    });
  const terms = () =>
    Array.from(document.querySelectorAll("li[data-term]")).map((e) => e.getAttribute("data-term"));
  const f = (id: string, name: string) =>
    document.querySelector(`li[data-term="${id}"] [data-field="${name}"]`);

  it("FR-020-35 · every term shows its EN term, its ES term, its definition in the active language and its source when it has one", async () => {
    await render();
    expect(terms()).toEqual(["match_factor", "ppv"]);
    expect(f("match_factor", "term-en")?.textContent).toBe("Match factor");
    expect(f("match_factor", "term-es")?.textContent).toBe("Factor de acoplamiento");
    expect(f("match_factor", "definition")?.textContent).toContain(
      "Ratio of truck arrival rate to shovel service rate.",
    );
    expect(f("match_factor", "source")?.textContent).toContain("burt2014");
    expect(f("ppv", "source")).toBeNull();
  });

  it("FR-020-35 · the definition follows the language: Spanish shows the Spanish definition", async () => {
    await render("", "es");
    expect(f("match_factor", "definition")?.textContent).toContain(
      "Razón entre la tasa de llegada de camiones y la tasa de servicio de la pala.",
    );
    expect(f("match_factor", "definition")?.textContent).not.toContain("Ratio of truck");
  });

  it("FR-020-35 · ?q= filters in both languages, ignoring case and accents, and the search field shows it", async () => {
    await render("&q=PARTICULA");
    expect(terms()).toEqual(["ppv"]);
    expect((screen.getByTestId("search") as HTMLInputElement).value).toBe("PARTICULA");
    expect(screen.getByTestId("search").getAttribute("maxlength")).toBe("2000");
    document.body.innerHTML = "";
    await render("&q=acoplamiento");
    expect(terms()).toEqual(["match_factor"]);
  });

  it("FR-020-35 · a query with no match says 'No matching terms'", async () => {
    await render("&q=zzzz");
    expect(terms()).toEqual([]);
    expect(screen.getByTestId("no-match").textContent).toContain("No matching terms");
  });

  it("FR-020-41 · highlights are mark elements around escaped text: '<b>' in the query highlights nothing and creates no element", async () => {
    await render(`&q=${encodeURIComponent("<b>")}`);
    expect(document.querySelector("li[data-term] b")).toBeNull();
    document.body.innerHTML = "";
    await render("&q=factor");
    const marks = Array.from(document.querySelectorAll("li[data-term] mark")).map((m) =>
      m.textContent?.toLowerCase(),
    );
    expect(marks.length).toBeGreaterThan(0);
    for (const m of marks) expect(m).toBe("factor");
  });

  it("FR-020-41 · markup in the glossary text itself stays text, also when highlighted", async () => {
    const entries = [
      {
        id: "evil",
        origin: "docs",
        term_en: "<img src=x onerror=alert(1)> factor",
        term_es: "<b>x</b>",
        definition_en: "<script>alert(1)</script> factor",
        definition_es: "<i>y</i>",
      },
    ];
    const { container } = await render("&q=factor", "en", entries);
    expect(container.querySelector("img[src='x'], b, i, script")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("FR-020-41 · a 20,000-character query and a query of metacharacters render normally", async () => {
    for (const q of ["x".repeat(20_000), ".*", "(", "[", "\\", "a{2"]) {
      document.body.innerHTML = "";
      await render(`&q=${encodeURIComponent(q)}`);
      expect(document.querySelector('[data-testid="search"]')).not.toBeNull();
    }
  });
});

describe("the real glossary of the docs (FR-020-35)", () => {
  const md = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), "../../../docs/reference/glossary.md"),
    "utf8",
  );
  const real = [...md.matchAll(/^\| ([^|]+) \| ([^|]+) \| ([^|]+) \|$/gm)]
    .map((m, i) => ({
      id: `t${i}`,
      term_en: (m[1] as string).trim(),
      term_es: (m[2] as string).trim(),
      definition_en: (m[3] as string).trim(),
      definition_es: (m[3] as string).trim(),
    }))
    .filter((e) => e.term_en !== "EN term" && !e.term_en.startsWith("---"));

  it("FR-020-35 · searching the Spanish term 'angulo de reposo' (no accent, any case) finds the English term 'Angle of repose'", () => {
    expect(real.length).toBeGreaterThan(20);
    const hits = searchRows(real, "ANGULO DE REPOSO", fields).map((r) => r.term_en);
    expect(hits).toContain("Angle of repose");
  });

  it("FR-020-35 · 'tronadura' finds the blast design term, 'conminucion' finds comminution, 'ley de corte' the cut-off grade", () => {
    expect(searchRows(real, "tronadura", fields).map((r) => r.term_en)).toContain("Blast design");
    expect(searchRows(real, "conminucion", fields).map((r) => r.term_en)).toContain("Comminution");
    expect(searchRows(real, "Ley de Corte", fields).map((r) => r.term_en)).toContain("Cut-off grade");
  });
});
