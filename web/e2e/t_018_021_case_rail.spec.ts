// T-018-021 [red] · FR-018-02, FR-018-03 (E2E half) on the production build, route `/app/` (Explore); the root `/` lands on the Introduction (SHF-011).
//
// Observation hooks the green commit must provide on `/` (the unit test t_018_021_case_rail.test.tsx fixes the rail DOM):
//   [data-testid="case-rail"]        the rail container (a `nav` or `aside`), holding the `role="group"` / `li[data-case-id]` structure
//   [data-testid="kpi-panel"]        the panel of the selected case; attribute `data-case="<id>"` while a case is selected;
//                                    inside it one `[data-kpi="<kpi id>"]` row per HEADLINE KPI of the case (DC-018-01 `headline: true`)
//                                    showing the KPI name in the active language, and a link to `<base>cases/<id>/`
// Oracles: FR-018-02 / FR-018-03 text; titles, category names and headline KPIs from the valid case registry example (DC-018-01).
import { expect, test } from "@playwright/test";
import { CASE_IDS, GROUPS, headlineKpis, loadCaseRegistry } from "../src/test-support/fixtures";
import { open } from "./helpers";

const registry = loadCaseRegistry();
const BASE = process.env.BASE_PATH ?? "/";

test.describe("case rail (FR-018-02)", () => {
  test("SHF-011 · the root lands on the Introduction with its executive view, not on Explore", async ({ page }) => {
    await open(page, "");
    await expect(page.locator("[data-exec-tabs]")).toBeVisible();
    await expect(page.getByTestId("case-rail")).toHaveCount(0);
  });

  test("FR-018-02 · `/app/` shows 12 cases in 5 labelled groups in the order A, B, C, D, E with titles and links", async ({
    page,
  }) => {
    await open(page, "app/");
    const rail = page.getByTestId("case-rail");
    await expect(rail).toBeVisible();
    const groups = rail.getByRole("group");
    await expect(groups).toHaveCount(5);
    for (const [i, [letter, ids]] of GROUPS.entries()) {
      const group = groups.nth(i);
      await expect(group).toHaveAccessibleName(new RegExp(registry.categories[letter]?.title.en as string));
      await expect(group.locator("li[data-case-id]")).toHaveCount(ids.length);
      for (const [j, id] of ids.entries()) {
        const item = group.locator("li[data-case-id]").nth(j);
        await expect(item).toHaveAttribute("data-case-id", id);
        await expect(item).toContainText(registry.cases[id]?.title.en as string);
        await expect(item.getByRole("link")).toHaveAttribute("href", `${BASE}cases/${id}/`);
      }
    }
    await expect(rail.locator("li[data-case-id]")).toHaveCount(12);
  });

  test("FR-018-02 · the rail follows the active language", async ({ page }) => {
    await open(page, "?lang=es");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    const rail = page.getByTestId("case-rail");
    for (const id of CASE_IDS) {
      await expect(rail.locator(`li[data-case-id="${id}"]`)).toContainText(
        registry.cases[id]?.title.es as string,
      );
    }
    for (const [letter] of GROUPS) {
      await expect(
        rail.getByRole("group", { name: new RegExp(registry.categories[letter]?.title.es as string) }),
      ).toBeVisible();
    }
  });
});

test.describe("case selection (FR-018-03)", () => {
  test("FR-018-03 · selecting a case highlights it and shows its headline KPIs and a link to its page within 200 ms, without playing anything", async ({
    page,
  }) => {
    await open(page, "app/");
    const elapsedMs = await page.evaluate(async () => {
      const button = document.querySelector<HTMLButtonElement>(
        '[data-testid="case-rail"] li[data-case-id="C1"] button',
      );
      if (!button) throw new Error("rail button for C1 not found");
      const t0 = performance.now();
      button.click();
      for (;;) {
        const panel = document.querySelector('[data-testid="kpi-panel"]');
        if (panel?.getAttribute("data-case") === "C1") return performance.now() - t0;
        if (performance.now() - t0 > 3000) return Number.POSITIVE_INFINITY;
        await new Promise((r) => requestAnimationFrame(r));
      }
    });
    expect(elapsedMs).toBeLessThan(200);

    const item = page.getByTestId("case-rail").locator('li[data-case-id="C1"]');
    await expect(item.getByRole("button")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("case-rail").getByRole("button", { pressed: true })).toHaveCount(1);
    const panel = page.getByTestId("kpi-panel");
    for (const kpi of headlineKpis(registry, "C1")) {
      await expect(panel.locator(`[data-kpi="${kpi.id}"]`)).toContainText(kpi.name.en);
    }
    await expect(panel.locator("[data-kpi]")).toHaveCount(headlineKpis(registry, "C1").length);
    await expect(panel.locator(`a[href="${BASE}cases/C1/"]`).first()).toBeVisible();

    expect(new URL(page.url()).pathname).toBe(BASE);
    const anyPlaying = await page.evaluate(() =>
      [...document.querySelectorAll("video")].some((v) => !v.paused),
    );
    expect(anyPlaying).toBe(false);
  });

  test("FR-018-03 · `/?case=B2` opens with B2 highlighted, its headline KPIs and its page link shown", async ({
    page,
  }) => {
    await open(page, "?case=B2");
    const item = page.getByTestId("case-rail").locator('li[data-case-id="B2"]');
    await expect(item.getByRole("button")).toHaveAttribute("aria-pressed", "true");
    const panel = page.getByTestId("kpi-panel");
    await expect(panel).toHaveAttribute("data-case", "B2");
    for (const kpi of headlineKpis(registry, "B2")) {
      await expect(panel.locator(`[data-kpi="${kpi.id}"]`)).toContainText(kpi.name.en);
    }
    await expect(panel.locator(`a[href="${BASE}cases/B2/"]`).first()).toBeVisible();
    const anyPlaying = await page.evaluate(() =>
      [...document.querySelectorAll("video")].some((v) => !v.paused),
    );
    expect(anyPlaying).toBe(false);
  });

  test("FR-018-03 · every known case id in `?case=` selects that case", async ({ page }) => {
    for (const id of CASE_IDS) {
      await open(page, `?case=${id}`);
      await expect(page.getByTestId("kpi-panel")).toHaveAttribute("data-case", id);
      await expect(page.getByTestId("case-rail").locator(`li[data-case-id="${id}"] button`)).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    }
  });
});
