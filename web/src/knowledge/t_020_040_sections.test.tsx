// T-020-040 [red] · FR-020-32 (/knowledge offers the sections Glossary, Equations, Parameters, Datasets, Frameworks, Bibliography, generated at build time, and shows the `minephys` version and commit it was generated from),
// FR-020-36 (datasets: every `data/sources.yaml` entry with id, real or synthetic, SPDX licence, redistribution class, landing URL and dataset-card link, "fetched by the pipeline, never redistributed" for third-party data),
// FR-020-37 (frameworks: every `studio/tools.yaml` entry, the evaluated-not-adopted ones included, linking to `/studio/tools/<id>/`) and FR-020-38 (bibliography: every entry with its DOI or URL, a stable anchor equal to its citation
// key, and the parameters and equations that cite it). E2E half: web/e2e/t_020_040_knowledge.spec.ts.
//
// Expected API (web/src/knowledge/): `KnowledgeView({ bundle: KnowledgeBundle; section?: string })` (KnowledgeView.tsx), `bundle` the knowledge bundle of DC-020-03; `section` one of glossary, equations, parameters, datasets,
//   frameworks, bibliography (default glossary; an unknown value falls back to glossary, FR-020-48). Hooks:
//   nav[data-testid="knowledge-nav"]: a[data-section] x 6 in the order above, names "Glossary", "Equations", "Parameters", "Datasets", "Frameworks", "Bibliography", href `?section=<id>`, aria-current on the active one;
//   [data-testid="knowledge-provenance"]: the `minephys` version and the commit (the 7 first hex characters, the whole commit in its title attribute);
//   datasets: tr[data-dataset="<id>"] with cells id, kind ("real" or "synthetic"), SPDX, redistribution, an a[href=<landing_url>] and an a[href$="<card>"] (the dataset card); `[data-field="provenance"]` "fetched by the pipeline, never redistributed" on every
//     row whose kind is real (third-party data) and not on a synthetic one;
//   frameworks: li[data-framework="<id>"] with the name, the status ("Not yet run" / "Evaluated, not adopted" / done) and, for a studio tool, a[href="/studio/tools/<id>/"]; a component entry (category component) is listed without link (the 20 tool
//     pages are the only ones that exist, FR-019-20);
//   bibliography: article[data-bib="<key>"][id="<key>"] with the authors, title, year, a link `https://doi.org/<doi>` (DOI) or the `url`, and the citing parameters and equations as [data-cited-parameter] / [data-cited-equation] items.
// Oracles: the valid knowledge bundle of DC-020-03 (specs/020-web-knowledge/contracts/examples/knowledge-bundle.valid.json: 3 parameters, 1 equation, 2 glossary terms, 1 dataset, 2 frameworks, 3 bibliography entries, minephys 0.1.0 at
// 89abcdef0123456789abcdef0123456789abcdef) and hand variations.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { KnowledgeView } from "~/knowledge/KnowledgeView";
import { renderApp } from "~/test-support/render";

type Bundle = Record<string, unknown> & {
  datasets: Array<Record<string, unknown>>;
  frameworks: Array<Record<string, unknown>>;
  bibliography: Array<Record<string, unknown>>;
};
const bundle = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../specs/020-web-knowledge/contracts/examples/knowledge-bundle.valid.json",
    ),
    "utf8",
  ),
) as Bundle;
const render = (section?: string, b: unknown = bundle, lang: "en" | "es" = "en") =>
  renderApp(createElement(KnowledgeView, { bundle: b as never, section }), { lang });
const q = (sel: string) => document.querySelector<HTMLElement>(sel);

describe("sections and provenance (FR-020-32)", () => {
  it("FR-020-32 · the navigation offers the six sections in order, linked by ?section=", async () => {
    await render();
    const links = Array.from(
      document.querySelectorAll<HTMLAnchorElement>('[data-testid="knowledge-nav"] a[data-section]'),
    );
    expect(links.map((a) => a.getAttribute("data-section"))).toEqual([
      "glossary",
      "equations",
      "parameters",
      "datasets",
      "frameworks",
      "bibliography",
    ]);
    expect(links.map((a) => a.textContent?.trim())).toEqual([
      "Glossary",
      "Equations",
      "Parameters",
      "Datasets",
      "Frameworks",
      "Bibliography",
    ]);
    for (const a of links)
      expect(a.getAttribute("href")).toContain(`section=${a.getAttribute("data-section")}`);
  });

  it("FR-020-32 · the active section carries aria-current; no section means glossary and an unknown one falls back to it", async () => {
    await render();
    expect(q('a[data-section="glossary"]')?.getAttribute("aria-current")).toBe("page");
    for (const bad of ["nope", "", "../x", "<script>", "datasets".repeat(500)]) {
      document.body.innerHTML = "";
      await render(bad);
      expect(q('a[data-section="glossary"]')?.getAttribute("aria-current"), bad.slice(0, 20)).toBe("page");
    }
    document.body.innerHTML = "";
    await render("frameworks");
    expect(q('a[data-section="frameworks"]')?.getAttribute("aria-current")).toBe("page");
    expect(q('a[data-section="glossary"]')?.hasAttribute("aria-current")).toBe(false);
  });

  it("FR-020-32 · the minephys version and the commit the bundle was generated from are shown", async () => {
    await render();
    const p = q('[data-testid="knowledge-provenance"]');
    expect(p?.textContent).toContain("0.1.0");
    expect(p?.textContent).toContain("89abcde");
    expect(p?.textContent).not.toContain("89abcdef0123456789abcdef0123456789abcdef");
    expect(p?.innerHTML).toContain("89abcdef0123456789abcdef0123456789abcdef");
  });
});

describe("datasets (FR-020-36)", () => {
  it("FR-020-36 · a dataset row shows id, real or synthetic, SPDX licence, redistribution class, landing URL and dataset-card link", async () => {
    await render("datasets");
    const r = q('tr[data-dataset="usgs-3dep-bingham"]');
    const t = r?.textContent ?? "";
    for (const needle of ["usgs-3dep-bingham", "real", "LicenseRef-USGov-PD", "redistributable"])
      expect(t, needle).toContain(needle);
    expect(r?.querySelector('a[href="https://www.usgs.gov/3d-elevation-program"]')).not.toBeNull();
    expect(r?.querySelector('a[href$="data/cards/usgs-3dep-bingham.md"]')).not.toBeNull();
  });

  it("FR-020-36 · third-party (real) data reads 'fetched by the pipeline, never redistributed'; synthetic data does not", async () => {
    const synth = {
      ...bundle.datasets[0],
      id: "makehuman-exports",
      kind: "synthetic",
      spdx: "CC0-1.0",
      card: "data/cards/makehuman-exports.md",
    };
    await render("datasets", { ...bundle, datasets: [...bundle.datasets, synth] });
    expect(q('tr[data-dataset="usgs-3dep-bingham"] [data-field="provenance"]')?.textContent).toContain(
      "fetched by the pipeline, never redistributed",
    );
    expect(q('tr[data-dataset="makehuman-exports"] [data-field="provenance"]')).toBeNull();
  });

  it("FR-020-36 · every dataset of the bundle has a row, once, in the order of the bundle", async () => {
    const many = Array.from({ length: 40 }, (_, i) => ({
      ...bundle.datasets[0],
      id: `ds-${i}`,
      card: `data/cards/ds-${i}.md`,
    }));
    await render("datasets", { ...bundle, datasets: many });
    expect(
      Array.from(document.querySelectorAll("tr[data-dataset]")).map((r) => r.getAttribute("data-dataset")),
    ).toEqual(many.map((d) => d.id));
  });

  it("FR-020-36 · a landing URL that is not https is shown as text, not linked", async () => {
    await render("datasets", {
      ...bundle,
      datasets: [{ ...bundle.datasets[0], landing_url: "javascript:alert(1)" }],
    });
    expect(q("tr[data-dataset] a[href^='javascript']")).toBeNull();
  });

  it("FR-020-36 · an empty list of datasets renders an empty section without error", async () => {
    await render("datasets", { ...bundle, datasets: [] });
    expect(document.querySelectorAll("tr[data-dataset]")).toHaveLength(0);
  });
});

describe("frameworks (FR-020-37)", () => {
  it("FR-020-37 · every entry is listed, the evaluated-not-adopted ones included, each studio tool linking to its page", async () => {
    await render("frameworks");
    const ids = Array.from(document.querySelectorAll("li[data-framework]")).map((e) =>
      e.getAttribute("data-framework"),
    );
    expect(ids).toEqual(["warp", "cuopt"]);
    expect(q('li[data-framework="warp"] a[href="/studio/tools/warp/"]')).not.toBeNull();
    expect(q('li[data-framework="cuopt"] a[href="/studio/tools/cuopt/"]')).not.toBeNull();
    expect(q('li[data-framework="cuopt"]')?.textContent).toContain("Evaluated, not adopted");
    expect(q('li[data-framework="warp"]')?.textContent).toContain("Not yet run");
  });

  it("FR-020-37 · a component entry is listed without a link to a tool page", async () => {
    await render("frameworks", {
      ...bundle,
      frameworks: [
        ...bundle.frameworks,
        {
          id: "minephys",
          name: "minephys",
          category: "component",
          status: "not-yet-run",
          licence_class: "own",
        },
      ],
    });
    expect(q('li[data-framework="minephys"]')).not.toBeNull();
    expect(q('li[data-framework="minephys"] a[href^="/studio/tools/"]')).toBeNull();
  });

  it("FR-020-37 · the 20 studio tools each link to their page, for any ids the bundle holds (encoded)", async () => {
    const tools = Array.from({ length: 20 }, (_, i) => ({
      id: `tool-${i}`,
      name: `Tool ${i}`,
      category: "studio-tool",
      status: "not-yet-run",
      licence_class: "attribution",
    }));
    await render("frameworks", { ...bundle, frameworks: tools });
    for (const t of tools)
      expect(q(`li[data-framework="${t.id}"] a[href="/studio/tools/${t.id}/"]`), t.id).not.toBeNull();
  });
});

describe("bibliography (FR-020-38)", () => {
  it("FR-020-38 · every entry has an anchor equal to its citation key, its authors, title, year and a link", async () => {
    await render("bibliography");
    for (const e of bundle.bibliography) {
      const key = e.key as string;
      const el = q(`article[data-bib="${key}"]`);
      expect(el?.getAttribute("id"), key).toBe(key);
      expect(el?.textContent, key).toContain(e.title as string);
      expect(el?.textContent, key).toContain(String(e.year));
    }
    expect(
      q(
        'article[data-bib="epa2025ghghub"] a[href="https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf"]',
      ),
    ).not.toBeNull();
    expect(
      q('article[data-bib="ouchterlony2005"] a[href="https://doi.org/10.1179/037178405X44539"]'),
    ).not.toBeNull();
  });

  it("FR-020-38 · each entry lists the parameters and the equations that cite it", async () => {
    const b = {
      ...bundle,
      bibliography: bundle.bibliography.map((e) =>
        e.key === "cunningham2005"
          ? {
              ...e,
              cited_by: { parameters: ["kuzram_rock_factor_range"], equations: ["bond_specific_energy"] },
            }
          : e,
      ),
    };
    await render("bibliography", b);
    const el = q('article[data-bib="cunningham2005"]');
    expect(el?.querySelector('[data-cited-parameter="kuzram_rock_factor_range"]')).not.toBeNull();
    expect(el?.querySelector('[data-cited-equation="bond_specific_energy"]')).not.toBeNull();
    expect(
      q(
        'article[data-bib="ouchterlony2005"] [data-cited-parameter], article[data-bib="ouchterlony2005"] [data-cited-equation]',
      ),
    ).toBeNull();
  });

  it("FR-020-38 · a DOI is linked through doi.org, a URL as given, and an entry with neither shows no link", async () => {
    await render("bibliography", {
      ...bundle,
      bibliography: [
        {
          key: "k1",
          entry_type: "article",
          authors: "A",
          title: "T1",
          year: 2000,
          doi: "10.1000/xyz",
          access: "open",
          cited_by: { parameters: [], equations: [] },
        },
        {
          key: "k2",
          entry_type: "article",
          authors: "A",
          title: "T2",
          year: 2001,
          url: "https://example.org/p",
          access: "open",
          cited_by: { parameters: [], equations: [] },
        },
        {
          key: "k3",
          entry_type: "article",
          authors: "A",
          title: "T3",
          year: 2002,
          access: "open",
          cited_by: { parameters: [], equations: [] },
        },
      ],
    });
    expect(q('article[data-bib="k1"] a')?.getAttribute("href")).toBe("https://doi.org/10.1000/xyz");
    expect(q('article[data-bib="k2"] a')?.getAttribute("href")).toBe("https://example.org/p");
    expect(q('article[data-bib="k3"] a')).toBeNull();
  });

  it("FR-020-38 · a hostile title, key or url (markup, javascript:, 5,000 characters) is text and links nothing dangerous", async () => {
    const evil = {
      key: "k<b>x</b>",
      entry_type: "article",
      authors: "<i>A</i>",
      title: `<img src=x onerror=alert(1)>${"t".repeat(5000)}`,
      year: 2000,
      url: "javascript:alert(1)",
      access: "open",
      cited_by: { parameters: [], equations: [] },
    };
    const { container } = await render("bibliography", { ...bundle, bibliography: [evil] });
    expect(container.querySelector("img[src='x'], b, i")).toBeNull();
    expect(container.querySelector("a[href^='javascript']")).toBeNull();
  });
});
