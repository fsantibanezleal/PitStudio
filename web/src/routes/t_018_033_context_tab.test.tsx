// T-018-033 [red] · FR-018-17, FR-000-09, FR-000-10: the Context tab of a case page.
//
// Expected component API:
//   module  ~/cases/ContextTab      export  function ContextTab(props: {
//                                      caseId: string;                    // canonical id
//                                      registry: CaseRegistry;            // DC-018-01 document
//                                      sources: SourceEntry[];            // entries of data/sources.yaml: { id, kind: "real" | "synthetic", title, spdx, landing_url, card, ... }
//                                    })
//   Active language = the i18n language of the shell. DOM contract:
//     - the case question (`question[lang]`) and the validity range (`validity[lang]`) as text;
//     - one `[data-source="<id>"]` per id of `registry.cases[caseId].sources`, containing the registry id, the SPDX licence of the
//       source entry (verbatim) and the word "real" or "synthetic" from the entry's `kind`; a link to the source's dataset-card page whose
//       href starts with `/knowledge` and contains the id;
//     - every `synthetic_data` entry of the case with its `label[lang]`; every entry whose `validation` is "unvalidated" carries the exact
//       text "calibrated synthetic — not validated against real data" (FR-000-09, em dash); entries validated against a real reference do
//       not; no entry of the tab makes a C2ST or TSTR claim unless it is validated against real data;
//     - links to the method pages `/methods/m01/` ... of the case's methods (`M1` -> `/methods/m01/`, `M12` -> `/methods/m12/`) and at least
//       one link whose href starts with `/theory`.
// Oracles: the valid case registry example (DC-018-01) and hand-written source entries; FR-000-09 literal text.
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContextTab } from "~/cases/ContextTab";
import { type CaseRegistryJson, loadCaseRegistry, SOURCES } from "~/test-support/fixtures";
import { props, renderApp } from "~/test-support/render";

const registry = loadCaseRegistry();
const LABEL = "calibrated synthetic — not validated against real data";

function count(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

async function tab(
  caseId: string,
  reg: CaseRegistryJson = registry,
  lang: "en" | "es" = "en",
  sources = SOURCES,
) {
  return renderApp(<ContextTab caseId={caseId} registry={props(reg)} sources={props(sources)} />, { lang });
}

describe("Context tab content (FR-018-17)", () => {
  it("FR-018-17 · shows the case question and the validity range", async () => {
    const { container } = await tab("A1");
    expect(container.textContent).toContain(registry.cases.A1?.question.en);
    expect(container.textContent).toContain(registry.cases.A1?.validity.en);
  });

  it("FR-018-17 · shows the question and the validity range in Spanish when the language is ES", async () => {
    const { container } = await tab("C1", registry, "es");
    expect(container.textContent).toContain(registry.cases.C1?.question.es);
    expect(container.textContent).toContain(registry.cases.C1?.validity.es);
    expect(container.textContent).not.toContain(registry.cases.C1?.question.en);
  });

  it("FR-018-17 · lists every data source with registry id, SPDX licence and real or synthetic label", async () => {
    const { container } = await tab("C1");
    const rows = [...container.querySelectorAll<HTMLElement>("[data-source]")];
    expect(rows.map((r) => r.dataset.source)).toEqual(registry.cases.C1?.sources);
    for (const row of rows) {
      const source = SOURCES.find((s) => s.id === row.dataset.source);
      expect(row.textContent).toContain(source?.id);
      expect(row.textContent).toContain(source?.spdx);
      expect(row.textContent).toMatch(/\breal\b/i);
    }
  });

  it("FR-018-17 · labels a synthetic source as synthetic and never as real", async () => {
    const { container } = await tab("B2");
    const row = container.querySelector<HTMLElement>('[data-source="makehuman-exports"]');
    expect(row).not.toBeNull();
    expect(row?.textContent).toMatch(/\bsynthetic\b/i);
    expect(row?.textContent).not.toMatch(/\breal\b/i);
    expect(row?.textContent).toContain("CC0-1.0");
  });

  it("FR-018-17 · shows the licence of each source verbatim (public-domain Bingham terrain, share-alike MineLib)", async () => {
    const a1 = await tab("A1");
    expect(a1.container.querySelector('[data-source="usgs-3dep-bingham"]')?.textContent).toContain(
      "LicenseRef-USGov-PD",
    );
    a1.unmount();
    const e1 = await tab("E1");
    expect(e1.container.querySelector('[data-source="minelib-marvin"]')?.textContent).toContain(
      "CC-BY-SA-4.0",
    );
  });

  it("FR-018-17 · a case without real sources lists none and still shows its synthetic data", async () => {
    const { container } = await tab("D2");
    expect(container.querySelectorAll("[data-source]")).toHaveLength(0);
    expect(container.textContent).toContain(registry.cases.D2?.synthetic_data[0]?.label.en);
  });
});

describe("synthetic labelling (FR-018-17, FR-000-09)", () => {
  it("FR-000-09 · every unvalidated synthetic data type carries the exact label (A3 has two, A1 has one)", async () => {
    const a3 = await tab("A3");
    expect(count(a3.container.textContent ?? "", LABEL)).toBe(2);
    expect(a3.container.textContent).toContain(registry.cases.A3?.synthetic_data[0]?.label.en);
    expect(a3.container.textContent).toContain(registry.cases.A3?.synthetic_data[1]?.label.en);
    a3.unmount();
    const a1 = await tab("A1");
    expect(count(a1.container.textContent ?? "", LABEL)).toBe(1);
  });

  it("FR-000-09 · a synthetic data type validated against a real reference does not carry the label (D1)", async () => {
    const { container } = await tab("D1");
    expect(registry.cases.D1?.synthetic_data[0]?.validation).toBe("validated-against-real");
    expect(container.textContent).toContain(registry.cases.D1?.synthetic_data[0]?.label.en);
    expect(count(container.textContent ?? "", LABEL)).toBe(0);
  });

  it("FR-000-09 · makes no C2ST or TSTR claim for an unvalidated data type", async () => {
    for (const id of ["A1", "A3", "B1", "C2", "C3", "E2"]) {
      const { container, unmount } = await tab(id);
      expect(container.textContent, id).toContain(registry.cases[id]?.synthetic_data[0]?.label.en);
      expect(container.textContent, id).not.toMatch(/C2ST|TSTR/);
      unmount();
    }
  });

  it("FR-000-09 · the label is shown for every case whose synthetic data are all unvalidated", async () => {
    for (const id of ["A1", "A2", "A3", "B1", "B2", "C2", "C3", "D2", "E1", "E2"]) {
      const expected = (registry.cases[id]?.synthetic_data ?? []).filter(
        (s) => s.validation === "unvalidated",
      ).length;
      const { container, unmount } = await tab(id);
      expect(count(container.textContent ?? "", LABEL), id).toBe(expected);
      unmount();
    }
  });
});

describe("links (FR-018-17)", () => {
  it("FR-018-17 · links to the method page of every method of the case and to a theory page", async () => {
    await tab("A1");
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    for (const m of registry.cases.A1?.methods ?? []) {
      const n = Number(m.slice(1));
      expect(hrefs).toContain(`/methods/m${String(n).padStart(2, "0")}/`);
    }
    expect(hrefs.some((h) => h?.startsWith("/theory"))).toBe(true);
  });

  it("FR-018-17 · two-digit method ids link to /methods/m12/ and /methods/m23/", async () => {
    await tab("D1");
    expect(screen.getAllByRole("link").map((a) => a.getAttribute("href"))).toContain("/methods/m12/");
    const e2 = await tab("E2");
    expect(
      within(e2.container)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toContain("/methods/m23/");
  });

  it("FR-018-17 · links each real source to its dataset-card page under /knowledge", async () => {
    const { container } = await tab("C1");
    for (const id of registry.cases.C1?.sources ?? []) {
      const row = container.querySelector<HTMLElement>(`[data-source="${id}"]`) as HTMLElement;
      const hrefs = within(row)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href") ?? "");
      expect(
        hrefs.some((h) => h.startsWith("/knowledge") && h.includes(id)),
        id,
      ).toBe(true);
    }
  });
});

describe("sources carry a URL (FR-000-10)", () => {
  it("FR-000-10 · every source row links to the publisher's landing URL", async () => {
    const { container } = await tab("C1");
    const rows = container.querySelectorAll<HTMLElement>("[data-source]");
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      const source = SOURCES.find((s) => s.id === row.dataset.source);
      const hrefs = within(row)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href"));
      expect(hrefs, row.dataset.source).toContain(source?.landing_url);
    }
  });

  it("FR-000-10 · a landing URL that is not https is never made a link", async () => {
    const sources = SOURCES.map((s) =>
      s.id === "usgs-3dep-bingham" ? { ...s, landing_url: "javascript:alert(1)" } : s,
    );
    const { container } = await tab("A1", registry, "en", sources);
    const row = container.querySelector<HTMLElement>('[data-source="usgs-3dep-bingham"]');
    expect(row).not.toBeNull();
    for (const a of container.querySelectorAll("a")) {
      expect(a.getAttribute("href")).not.toMatch(/^\s*(javascript|data|vbscript):/i);
    }
  });
});

describe("Context tab hostile inputs (FR-018-17)", () => {
  it("FR-018-17 · renders markup in the question, validity range or source title as text", async () => {
    const hostile = structuredClone(registry) as CaseRegistryJson;
    const evil = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
    (hostile.cases.A1 as { question: { en: string } }).question.en = evil;
    (hostile.cases.A1 as { validity: { en: string } }).validity.en = evil;
    const sources = SOURCES.map((s) => (s.id === "usgs-3dep-bingham" ? { ...s, title: evil } : s));
    const { container } = await tab("A1", hostile, "en", sources);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain(evil);
  });

  it("FR-018-17 · does not throw when the source registry lacks an id the case lists, and still shows that id", async () => {
    const { container } = await tab("A1", registry, "en", []);
    expect(container.textContent).toContain("usgs-3dep-bingham");
  });
});
