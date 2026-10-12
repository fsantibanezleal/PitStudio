// T-020-016 [red] · FR-020-14 (a figure control that receives an empty, non-numeric, NaN, infinite or out-of-range value keeps its last valid value, shows the allowed range and unit inline and does not call the engine) and FR-020-48 (`?tab=`,
// `?q=`, `?module=`, `?status=` and `?lang=` on /theory, /methods, /results and /knowledge, when unknown, malformed or longer than 2,000 characters, fall back to the default, render normally, raise no uncaught error and request no resource derived
// from the value).
//
// Hooks: figures as in T-020-015 (input[data-control][data-min][data-max][data-unit], [data-testid="figure"][data-digest]), plus per control a message [data-testid="control-message"][data-control="<id>"] (the allowed range and the unit) and the
// engine-call counter [data-testid="figure"][data-calls] (the number of calls of the engine so far: 1 after the first draw, +1 per accepted change, never for a rejected value); the tabs of /results are role=tab (`?tab=`), the knowledge sections
// `a[data-section]`, the filters of the parameter section select[data-testid="filter-module"] and select[data-testid="filter-status"], the search field [data-testid="search"].
// Oracles: the EARS text; hostile values written below (empty, abc, NaN, 1e309, -1, markup, 20,000 characters); the default of each parameter (the first tab, the glossary section, no filter, English).
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const FIGURE_PAGES: Array<[string, string]> = [
  ["ppo-clip", "robot-learning"],
  ["ritter-dam-break", "tailings"],
  ["beverloo-discharge", "bulk-flow-dem-mpm"],
  ["c2st-auc", "sim-to-real"],
  ["mcnemar", "vision-language-reasoning"],
];
const HOSTILE = [
  "",
  " ",
  "abc",
  "NaN",
  "Infinity",
  "-Infinity",
  "1e309",
  "-1",
  "-1e309",
  "0x10",
  "1,5",
  "<script>window.__pwned=1</script>",
  "9".repeat(400),
  "\u0000",
];
const calls = async (page: Page, id: string) =>
  Number(await page.locator(`[data-testid="figure"][data-figure="${id}"]`).getAttribute("data-calls"));

async function enter(input: import("@playwright/test").Locator, text: string): Promise<void> {
  await input.evaluate((el, v) => {
    const e = el as HTMLInputElement;
    e.focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(e, v);
    e.dispatchEvent(new Event("input", { bubbles: true }));
    e.dispatchEvent(new Event("change", { bubbles: true }));
  }, text);
  await input.press("Enter");
}

test.describe("hostile figure controls (FR-020-14)", () => {
  for (const [id, topic] of FIGURE_PAGES) {
    test(`FR-020-14 · ${id}: every range control rejects the hostile values, keeps its last valid value, shows its range and unit, and the engine is not called`, async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await open(page, `theory/${topic}/`);
      const fig = page.locator(`[data-testid="figure"][data-figure="${id}"]`);
      await expect(fig).toBeVisible();
      const controls = fig.locator("input[data-control]");
      const n = await controls.count();
      expect(n).toBeGreaterThan(0);
      for (let i = 0; i < n; i++) {
        const input = controls.nth(i);
        const name = (await input.getAttribute("data-control")) ?? "";
        const min = Number(await input.getAttribute("data-min"));
        const max = Number(await input.getAttribute("data-max"));
        const unit = (await input.getAttribute("data-unit")) ?? "";
        const last = Number(await input.inputValue());
        const digest = await fig.getAttribute("data-digest");
        const before = await calls(page, id);
        for (const text of [
          ...HOSTILE,
          String(min - Math.max(1, Math.abs(min))),
          String(max + Math.max(1, Math.abs(max))),
        ]) {
          await enter(input, text);
          const message = fig.locator(`[data-testid="control-message"][data-control="${name}"]`);
          await expect(message, `${name} <- ${JSON.stringify(text.slice(0, 12))}`).toBeVisible();
          expect(Number(await input.inputValue()), `${name}: last valid value kept`).toBe(last);
          const said = (await message.textContent()) ?? "";
          expect(said).toContain(unit);
          expect(said.replace(/[,   ]/g, "")).toContain(String(min));
          expect(said.replace(/[,   ]/g, "")).toContain(String(max));
        }
        await page.waitForTimeout(150);
        expect(await calls(page, id), `${name}: no engine call`).toBe(before);
        await expect(fig).toHaveAttribute("data-digest", digest ?? "");
      }
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
    });
  }

  test("FR-020-14 · a valid value after a rejected one is accepted, the message goes away and the engine is called once", async ({
    page,
  }) => {
    await open(page, "theory/robot-learning/");
    const fig = page.locator('[data-testid="figure"][data-figure="ppo-clip"]');
    const input = fig.locator('input[data-control="clip_epsilon"]');
    await enter(input, "abc");
    await expect(fig.locator('[data-testid="control-message"]')).toBeVisible();
    const before = await calls(page, "ppo-clip");
    const mid =
      (Number(await input.getAttribute("data-min")) + Number(await input.getAttribute("data-max"))) / 2;
    await enter(input, String(mid));
    await expect(fig.locator('[data-testid="control-message"]')).toHaveCount(0);
    await expect.poll(() => calls(page, "ppo-clip")).toBe(before + 1);
  });
});

test.describe("hostile URL parameters on the content routes (FR-020-48)", () => {
  const VALUES: Array<[string, string]> = [
    ["unknown", "zz-sentinel-8e41"],
    ["markup", "%3Cscript%3Ewindow.__pwned%3D1%3C%2Fscript%3E-sentinel-8e41"],
    ["a null byte", "%00sentinel-8e41"],
    ["a traversal", "..%2F..%2Fsentinel-8e41"],
    ["negative", "-1"],
    ["not finite", "NaN"],
    ["longer than 2,000 characters", `${"a".repeat(2100)}sentinel-8e41`],
  ];
  const ROUTES: Array<[string, string[]]> = [
    ["theory/", ["tab", "q", "lang"]],
    ["theory/haulage/", ["tab", "q", "lang"]],
    ["methods/", ["tab", "q", "module", "status", "lang"]],
    ["methods/m04/", ["tab", "lang"]],
    ["results/", ["tab", "q", "module", "status", "lang"]],
    ["knowledge/", ["tab", "q", "module", "status", "lang"]],
  ];
  for (const [route, params] of ROUTES) {
    for (const param of params) {
      for (const [what, value] of VALUES) {
        test(`FR-020-48 · /${route}?${param}= ${what}: default page, no uncaught error, nothing requested from the value`, async ({
          page,
        }) => {
          const errors: string[] = [];
          const urls: string[] = [];
          page.on("pageerror", (e) => errors.push(e.message));
          page.on("request", (r) => {
            if (!r.isNavigationRequest()) urls.push(r.url());
          });
          await open(page, `${route}?${param}=${value}`);
          await expect(page.locator("main h1")).toBeVisible();
          await expect(page.locator("main h1")).not.toHaveText("Page not found");
          await page.waitForLoadState("networkidle");
          expect(
            await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
          ).toBeUndefined();
          expect(errors).toEqual([]);
          expect(urls.filter((u) => /sentinel-8e41|a{50}/.test(decodeURIComponent(u)))).toEqual([]);
          await expect(page.locator("html")).toHaveAttribute("lang", /^(en|es)$/);
        });
      }
    }
  }

  test("FR-020-48 · the results page falls back to its first tab, the knowledge page to the glossary, the methods page to no filter", async ({
    page,
  }) => {
    await open(page, "results/?tab=zz-sentinel-8e41");
    await expect(page.getByRole("tab", { selected: true })).toHaveText(/Learned vs classical|Aprendido/);
    await open(page, "knowledge/?section=zz-sentinel-8e41");
    await expect(page.locator('a[data-section="glossary"]')).toHaveAttribute("aria-current", "page");
    await open(page, "methods/?module=zz-sentinel-8e41&status=zz");
    await expect(page.locator("tr[data-method]")).toHaveCount(23);
  });

  test("FR-020-48 · a valid parameter is honoured (control): ?tab=cosmos selects the Cosmos tab, ?lang=es switches the language", async ({
    page,
  }) => {
    await open(page, "results/?tab=cosmos");
    await expect(page.getByRole("tab", { selected: true })).toContainText(/Cosmos/);
    await open(page, "results/?lang=es");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
  });
});
