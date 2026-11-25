// T-020-042 [red] · FR-020-35 (the glossary search matches either language ignoring case and accents), FR-020-41 (hostile queries, typed or from ?q=, are matched as literal text and truncated to 2,000 characters, highlights are escaped
// text, no error) and NFR-020-08 (search latency) on the built /knowledge glossary. Unit half: web/src/knowledge/t_020_042_search.test.ts.
//
// The glossary on the page is generated at build time from docs/reference/glossary.md (FR-020-32), so these terms are the oracle: "Angle of repose" / "Ángulo de reposo", "Blast design" / "Diseño de tronadura (voladura)",
// "Comminution" / "Conminución", "Cut-off grade" / "Ley de corte". Hooks: li[data-term] with [data-field="term-en"] and [data-field="term-es"], [data-testid="search"], [data-testid="no-match"], mark.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const term = (page: Page, en: string) =>
  page
    .locator(`li[data-term]`)
    .filter({ has: page.locator('[data-field="term-en"]', { hasText: new RegExp(`^${en}$`) }) });
const GLOSSARY = "knowledge/?section=glossary";

test.describe("search in both languages (FR-020-35)", () => {
  test("FR-020-35 · typing the Spanish term 'ANGULO DE REPOSO' (upper case, no accent) finds 'Angle of repose'", async ({
    page,
  }) => {
    await open(page, GLOSSARY);
    await page.getByTestId("search").fill("ANGULO DE REPOSO");
    await expect(term(page, "Angle of repose")).toHaveCount(1);
    expect(await page.locator("li[data-term]").count()).toBeLessThan(5);
  });

  for (const [query, english] of [
    ["tronadura", "Blast design"],
    ["conminucion", "Comminution"],
    ["Ley de Corte", "Cut-off grade"],
    ["comminution", "Comminution"],
    ["CUT-OFF", "Cut-off grade"],
  ] as Array<[string, string]>) {
    test(`FR-020-35 · '${query}' finds '${english}'`, async ({ page }) => {
      await open(page, `${GLOSSARY}&q=${encodeURIComponent(query)}`);
      await expect(term(page, english)).toHaveCount(1);
      await expect(page.getByTestId("search")).toHaveValue(query);
    });
  }

  test("FR-020-35 · every term shows both its English and its Spanish name", async ({ page }) => {
    await open(page, GLOSSARY);
    const n = await page.locator("li[data-term]").count();
    expect(n).toBeGreaterThan(20);
    for (const row of await page
      .locator("li[data-term]")
      .evaluateAll((els) =>
        els.map((e) => [
          e.querySelector('[data-field="term-en"]')?.textContent?.trim() ?? "",
          e.querySelector('[data-field="term-es"]')?.textContent?.trim() ?? "",
        ]),
      )) {
      expect(row[0]?.length).toBeGreaterThan(0);
      expect(row[1]?.length).toBeGreaterThan(0);
    }
  });

  test("FR-020-35 · a query with no match says 'No matching terms'", async ({ page }) => {
    await open(page, `${GLOSSARY}&q=zzzzqqqq`);
    await expect(page.getByTestId("no-match")).toContainText("No matching terms");
    await expect(page.locator("li[data-term]")).toHaveCount(0);
  });

  test("FR-020-35 · the results narrow as the query grows: 'a' keeps at least as many terms as 'an'", async ({
    page,
  }) => {
    await open(page, GLOSSARY);
    await page.getByTestId("search").fill("a");
    const a = await page.locator("li[data-term]").count();
    await page.getByTestId("search").fill("an");
    expect(await page.locator("li[data-term]").count()).toBeLessThanOrEqual(a);
  });
});

test.describe("hostile queries (FR-020-41)", () => {
  const HOSTILE: Array<[string, string]> = [
    ["markup", '<img src=x onerror="window.__pwned=1">'],
    ["a script", "<script>window.__pwned=1</script>"],
    ["regex metacharacters", ".*"],
    ["an open parenthesis", "("],
    ["a character class", "[a-z]+"],
    ["a backslash", "\\"],
    ["an alternation", "angle|bench"],
    ["a null byte", "angle%00"],
    ["20,000 characters", "x".repeat(20_000)],
  ];
  for (const [what, query] of HOSTILE) {
    test(`FR-020-41 · ${what} in ?q=: no uncaught error, nothing executes, no request derived from it`, async ({
      page,
    }) => {
      const errors: string[] = [];
      const urls: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("request", (r) => {
        if (!r.isNavigationRequest()) urls.push(r.url());
      });
      await open(page, `${GLOSSARY}&q=${encodeURIComponent(query)}`);
      await expect(page.getByTestId("search")).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
      expect(errors).toEqual([]);
      await expect(page.locator("main img[src='x'], main script")).toHaveCount(0);
      expect(urls.filter((u) => /xxxxxxxxxx|onerror|pwned/.test(decodeURIComponent(u)))).toEqual([]);
      expect(((await page.getByTestId("search").inputValue()) ?? "").length).toBeLessThanOrEqual(2000);
    });
  }

  test("FR-020-41 · a typed regular expression matches itself, not the terms it would match as a pattern", async ({
    page,
  }) => {
    await open(page, GLOSSARY);
    await page.getByTestId("search").fill(".*");
    await expect(page.locator("li[data-term]")).toHaveCount(0);
    await page.getByTestId("search").fill("(");
    expect(await page.locator("li[data-term]").count()).toBeGreaterThan(0); // terms such as 'Peak particle velocity (PPV)' hold a parenthesis
  });

  test("FR-020-41 · highlights are mark elements holding only the matched text", async ({ page }) => {
    await open(page, `${GLOSSARY}&q=angle`);
    const marks = await page.locator("li[data-term] mark").allTextContents();
    expect(marks.length).toBeGreaterThan(0);
    for (const m of marks) expect(m.toLowerCase()).toBe("angle");
  });

  test("FR-020-41 · the search field limits itself to 2,000 characters", async ({ page }) => {
    await open(page, GLOSSARY);
    await expect(page.getByTestId("search")).toHaveAttribute("maxlength", "2000");
  });
});
