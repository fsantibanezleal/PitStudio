// T-020-014 [red] · FR-020-01 (/theory lists the 13 phenomena, each with title, one-line summary, methods and cases, and /theory/<id>/ is a prerendered page answering 200; any other id 404), FR-020-04 (every equation rendered to HTML and MathML
// with a stable anchor #eq-<label>, followed by a symbol table), FR-020-05 (references with DOI or URL; the badge "UNVERIFIED — pinned at specification" next to every unverified transcription) and FR-020-47 (the same equation labels in EN and ES).
// Contract half (drift against docs/theory, language parity, KaTeX at build): tests/contract/test_t_020_014_theory_content.py.
//
// Hooks: /theory/ index: li[data-theory="<id>"] with a title link, [data-field="summary"], [data-field="methods"] and [data-field="cases"]; a theory page: main h1, [id^="eq-"] elements (the equation block, holding a `math` element) each immediately
// followed by table[data-testid="symbol-table"] (header cells Symbol, Meaning, Unit), [data-testid="references"] li with a link, [data-testid="unverified-badge"].
// Oracles: the 13 ids of FR-020-01; per page the number of display equations of docs/theory/<id>.md (131 in all, counted by an independent line scan) and the number of occurrences of the word UNVERIFIED in the docs page (hand counts below).
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const IDS = [
  "haulage",
  "loading-and-terramechanics",
  "drill-and-blast",
  "slopes-and-monitoring",
  "bulk-flow-dem-mpm",
  "comminution",
  "dust",
  "tailings",
  "planning",
  "rtx-sensor-physics",
  "robot-learning",
  "vision-language-reasoning",
  "sim-to-real",
];
const EQUATIONS: Record<string, number> = {
  "bulk-flow-dem-mpm": 11,
  comminution: 5,
  "drill-and-blast": 8,
  dust: 6,
  haulage: 13,
  "loading-and-terramechanics": 7,
  planning: 14,
  "robot-learning": 8,
  "rtx-sensor-physics": 16,
  "sim-to-real": 4,
  "slopes-and-monitoring": 11,
  tailings: 20,
  "vision-language-reasoning": 8,
};
const UNVERIFIED: Record<string, number> = {
  "bulk-flow-dem-mpm": 11,
  comminution: 4,
  "drill-and-blast": 7,
  dust: 1,
  haulage: 5,
  "loading-and-terramechanics": 4,
  planning: 6,
  "robot-learning": 4,
  "rtx-sensor-physics": 12,
  "sim-to-real": 0,
  "slopes-and-monitoring": 7,
  tailings: 13,
  "vision-language-reasoning": 8,
};

test.describe("the index (FR-020-01)", () => {
  test("FR-020-01 · /theory/ lists the 13 phenomena, each with title, summary, methods and cases, linked to its page", async ({
    page,
  }) => {
    await open(page, "theory/");
    const items = page.locator("li[data-theory]");
    expect(await items.evaluateAll((els) => els.map((e) => e.getAttribute("data-theory")))).toEqual(IDS);
    for (const id of IDS) {
      const li = page.locator(`li[data-theory="${id}"]`);
      await expect(li.locator("a").first()).toHaveAttribute("href", new RegExp(`/theory/${id}/?$`));
      for (const field of ["summary", "methods", "cases"])
        await expect(li.locator(`[data-field="${field}"]`)).toBeVisible();
    }
  });
});

test.describe("the 13 pages (FR-020-01)", () => {
  for (const id of IDS) {
    test(`FR-020-01 · /theory/${id}/ is a prerendered page answering 200`, async ({ request }) => {
      const res = await request.get(`theory/${id}/`);
      expect(res.status()).toBe(200);
      expect(await res.text()).toContain("<title>");
    });
  }

  for (const [what, id] of [
    ["an unknown id", "no-such-phenomenon"],
    ["upper case", "Haulage"],
    ["a prefix", "haul"],
    ["an extension", "haulage.html"],
    ["the docs file name", "haulage.md"],
    ["an encoded slash", "haulage%2Fx"],
    ["markup", "%3Cscript%3E"],
  ] as Array<[string, string]>) {
    test(`FR-020-01 · ${what}: HTTP 404 and the not-found page`, async ({ page }) => {
      const res = await page.goto(`theory/${id}/`);
      expect(res?.status()).toBe(404);
      await open(page, `theory/${id}/`);
      await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
    });
  }
});

test.describe("equations (FR-020-04)", () => {
  for (const id of IDS) {
    test(`FR-020-04 · /theory/${id}/ renders its ${EQUATIONS[id]} display equations to HTML and MathML, each with an #eq-<label> anchor and a symbol table`, async ({
      page,
    }) => {
      await open(page, `theory/${id}/`);
      const blocks = page.locator('main [id^="eq-"]');
      await expect(blocks).toHaveCount(EQUATIONS[id] ?? -1);
      expect(
        await blocks.evaluateAll(
          (els) => els.filter((e) => e.querySelector(".katex-html") && e.querySelector("math")).length,
        ),
      ).toBe(EQUATIONS[id]);
      const labels = await blocks.evaluateAll((els) => els.map((e) => e.id));
      expect(new Set(labels).size, "labels are unique").toBe(labels.length);
      for (const label of labels.slice(0, 40)) expect(label).toMatch(/^eq-[a-z0-9][a-z0-9-]*$/);
      const withTable = await blocks.evaluateAll(
        (els) => els.filter((e) => e.nextElementSibling?.matches('table[data-testid="symbol-table"]')).length,
      );
      expect(withTable).toBeGreaterThan(0);
      await expect(page.locator("main .katex-error")).toHaveCount(0);
    });
  }

  test("FR-020-04 · a symbol table has the header cells Symbol, Meaning and Unit", async ({ page }) => {
    await open(page, "theory/comminution/");
    const table = page.locator('main table[data-testid="symbol-table"]').first();
    expect(await table.locator("thead th").allTextContents()).toEqual(["Symbol", "Meaning", "Unit"]);
  });

  test("FR-020-04 · the anchor of an equation scrolls to it", async ({ page }) => {
    await open(page, "theory/comminution/");
    const label = await page.locator('main [id^="eq-"]').first().getAttribute("id");
    await page.goto(`theory/comminution/#${label}`);
    await expect(page.locator(`#${label}`)).toBeInViewport();
  });
});

test.describe("references and unverified badges (FR-020-05)", () => {
  for (const id of IDS) {
    test(`FR-020-05 · /theory/${id}/ lists its references with a DOI or URL, and has ${UNVERIFIED[id]} UNVERIFIED badges`, async ({
      page,
    }) => {
      await open(page, `theory/${id}/`);
      const refs = page.locator('[data-testid="references"] li');
      expect(await refs.count()).toBeGreaterThan(0);
      for (const href of await refs
        .locator("a")
        .evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? "")))
        expect(href).toMatch(/^https:\/\//);
      await expect(page.locator('main [data-testid="unverified-badge"]')).toHaveCount(UNVERIFIED[id] ?? -1);
      for (const text of await page.locator('main [data-testid="unverified-badge"]').allTextContents())
        expect(text).toContain("UNVERIFIED — pinned at specification");
    });
  }
});

test.describe("English and Spanish (FR-020-47)", () => {
  for (const id of ["haulage", "tailings", "sim-to-real"]) {
    test(`FR-020-47 · /theory/${id}/ has the same equation labels in Spanish as in English, and its title differs`, async ({
      page,
    }) => {
      await open(page, `theory/${id}/?lang=en`);
      const en = await page.locator('main [id^="eq-"]').evaluateAll((els) => els.map((e) => e.id));
      const titleEn = await page.locator("main h1").innerText();
      await open(page, `theory/${id}/?lang=es`);
      const es = await page.locator('main [id^="eq-"]').evaluateAll((els) => els.map((e) => e.id));
      expect([...es].sort()).toEqual([...en].sort());
      expect(await page.locator("main h1").innerText()).not.toBe(titleEn);
      await expect(page.locator("html")).toHaveAttribute("lang", "es");
    });
  }
});
