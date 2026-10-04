import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { open, PASSPHRASE, ROUTES } from "./helpers";

test.describe("deep links (Pages layout)", () => {
  for (const route of ROUTES) {
    test(`/${route} is a prerendered page (200)`, async ({ request }) => {
      const res = await request.get(route ? `${route}/` : "");
      expect(res.status()).toBe(200);
      expect(res.headers()["content-type"]).toContain("text/html");
      expect(await res.text()).toContain("<title>");
    });
  }

  test("an unknown URL gets 404 and the app's not-found page", async ({ page }) => {
    const res = await page.goto("no/such/page");
    expect(res?.status()).toBe(404);
    if (PASSPHRASE) await open(page, "no/such/page");
    await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  });
});

test.describe("access gate", () => {
  test.skip(!PASSPHRASE, "this build has no access gate");

  test("FR-000-04 · locks the workbench, says it is not security, and unlocks for the session", async ({
    page,
  }) => {
    await page.goto("");
    const input = page.getByLabel("Passphrase");
    await expect(input).toBeVisible();
    await expect(page.getByText(/not a security boundary/).first()).toBeVisible();
    await expect(page.locator("main h1")).toHaveText("Demo access");

    await input.fill("definitely wrong");
    await page.getByRole("button", { name: "Enter" }).click();
    await expect(page.getByRole("alert")).toBeVisible();

    await input.fill(PASSPHRASE);
    await page.getByRole("button", { name: "Enter" }).click();
    await expect(page.locator("main h1")).toHaveText("Explore an open pit");

    await page.goto("theory/");
    await expect(page.locator("main h1")).toHaveText("Theory");
  });

  test("FR-000-04 · hostile input does not break the gate", async ({ page }) => {
    await page.goto("");
    const input = page.getByLabel("Passphrase");
    for (const value of ["<img src=x onerror=alert(1)>", "' OR 1=1 --", "x".repeat(20_000), "\u0000￿"]) {
      await input.fill(value);
      await page.getByRole("button", { name: "Enter" }).click();
      await expect(page.getByRole("alert")).toBeVisible();
    }
    await expect(page.locator("main h1")).toHaveText("Demo access");
  });
});

test.describe("shell", () => {
  test("navigation reaches every section", async ({ page }) => {
    await open(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    const sections: [label: string, heading: string][] = [
      ["Cases", "Cases"],
      ["Studio", "Studio"],
      ["Theory", "Theory"],
      ["Methods", "Methods"],
      ["Results", "Results"],
      ["Knowledge", "Knowledge"],
      ["Explore", "Explore an open pit"],
    ];
    for (const [label, heading] of sections) {
      await nav.getByRole("link", { name: label, exact: true }).click();
      await expect(page.locator("main h1")).toHaveText(heading);
    }
  });

  test("FR-000-03 · theme toggle cycles and persists", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await open(page);
    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-theme", "light");
    const toggle = page.getByRole("button", { name: /^Theme:/ });
    await toggle.click(); // system → light
    await toggle.click(); // light → dark
    await expect(html).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "dark");
  });

  test("FR-000-03 · language switch to Spanish, persisted, and ?lang= wins", async ({ page }) => {
    await open(page);
    await page.getByLabel("Language").selectOption("es");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await expect(page.getByRole("navigation", { name: "Principal" })).toBeVisible();
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await page.goto("?lang=en");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  });

  test("the ⓘ view opens with seven tabs and closes with Escape", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: /About this app/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("tab")).toHaveCount(7);
    await dialog.getByRole("tab", { name: "Lanes" }).click();
    await expect(dialog.getByRole("tabpanel")).toContainText("WebGPU");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("footer shows version, commit, build date and the honesty notes", async ({ page }) => {
    await open(page);
    const footer = page.getByRole("contentinfo");
    await expect(footer).toContainText(/Version \d+\.\d{2}\.\d{3}/);
    await expect(footer).toContainText("Not affiliated with or endorsed by NVIDIA");
    await expect(footer).toContainText("No data, models or simulation results are published yet.");
  });
});

test.describe("accessibility", () => {
  for (const theme of ["light", "dark"] as const) {
    for (const lang of ["en", "es"]) {
      test(`NFR-000-02 · no serious or critical axe violations — ${theme}, ${lang}`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await open(page, `?lang=${lang}`);
        await expect(page.locator("html")).toHaveAttribute("lang", lang);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(blocking.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
      });
    }
  }
});
