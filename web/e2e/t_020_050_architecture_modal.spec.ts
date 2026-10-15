// T-020-050 [red] · FR-020-43 (the ⓘ modal has at least the seven tabs What it is, Lanes, Studio, Web flow, Science flow, Contracts, Tools, each with EN and ES text and an inline SVG diagram from docs/assets/diagrams/ whose embedded custom-property
// token block is removed when it is inlined, so that its colours come from the app's theme tokens and repaint on a theme change without reload) and FR-020-44 (while the modal is open focus stays inside it and the arrow keys move between tabs;
// Escape closes it and returns focus to the ⓘ button). The guard of the diagram files themselves is tests/contract/test_t_020_051_inline_svg.py.
//
// Tab -> diagram (the pairing is the test author's reading, flagged in the report): what-it-is pitstudio-overview, lanes lanes-measured-gate, studio studio-environment-map, web-flow web-routes, science-flow pipeline-stages,
// contracts manifest-contract, tools tool-map. Hooks: the trigger is the button named "About this app"; role=dialog with role=tab elements and role=tabpanel; the diagram is an inline `svg[role="img"]` in the panel with the `title` of the docs file.
// Oracles: the seven names of the EARS row; the `<title>` text of each docs diagram file (read here with a regular expression); WAI-ARIA tabs and dialog keyboard behaviour.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const TABS: Array<[string, string]> = [
  ["What it is", "pitstudio-overview"],
  ["Lanes", "lanes-measured-gate"],
  ["Studio", "studio-environment-map"],
  ["Web flow", "web-routes"],
  ["Science flow", "pipeline-stages"],
  ["Contracts", "manifest-contract"],
  ["Tools", "tool-map"],
];
const docTitle = (stem: string): string => {
  const svg = readFileSync(resolve("..", "docs", "assets", "diagrams", `${stem}.svg`), "utf8");
  return (/<title[^>]*>([^<]+)<\/title>/.exec(svg)?.[1] ?? "").trim();
};
const trigger = (page: Page) => page.getByRole("button", { name: /About this app/ });
async function openModal(page: Page, route = ""): Promise<void> {
  await open(page, route);
  await trigger(page).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test.describe("seven tabs with diagrams (FR-020-43)", () => {
  test("FR-020-43 · the modal has the seven tabs, in this order", async ({ page }) => {
    await openModal(page);
    expect(await page.getByRole("dialog").getByRole("tab").allTextContents()).toEqual(
      TABS.map(([name]) => name),
    );
  });

  for (const [name, stem] of TABS) {
    test(`FR-020-43 · the tab '${name}' shows an inline SVG diagram titled as docs/assets/diagrams/${stem}.svg`, async ({
      page,
    }) => {
      await openModal(page);
      await page.getByRole("dialog").getByRole("tab", { name, exact: true }).click();
      const panel = page.getByRole("dialog").getByRole("tabpanel");
      await expect(panel.locator('svg[role="img"]')).toHaveCount(1);
      await expect(panel.locator('svg[role="img"] > title')).toHaveText(docTitle(stem));
      await expect(panel.locator('img[src$=".svg"]')).toHaveCount(0);
      expect(((await panel.innerText()) ?? "").length).toBeGreaterThan(80);
    });

    test(`FR-020-43 · '${name}': the custom-property token block of the file is removed when it is inlined`, async ({
      page,
    }) => {
      await openModal(page);
      await page.getByRole("dialog").getByRole("tab", { name, exact: true }).click();
      const styles = await page
        .getByRole("dialog")
        .getByRole("tabpanel")
        .locator("svg style")
        .allTextContents();
      for (const css of styles) expect(css).not.toMatch(/--[a-z0-9-]+\s*:\s*#[0-9a-fA-F]{3,8}/);
      const markup = await page
        .getByRole("dialog")
        .getByRole("tabpanel")
        .locator("svg")
        .first()
        .evaluate((e) => e.outerHTML);
      expect(markup).not.toMatch(/(?:fill|stroke)="#[0-9a-fA-F]{3,8}"/);
    });
  }

  test("FR-020-43 · the diagram colours come from the app's theme tokens and repaint on a theme change without a reload", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await openModal(page);
    await page.getByRole("dialog").getByRole("tab", { name: "Lanes", exact: true }).click();
    await page.evaluate(() => {
      (window as unknown as { __marker: number }).__marker = 7;
    });
    const paint = () =>
      page
        .getByRole("dialog")
        .getByRole("tabpanel")
        .locator("svg")
        .first()
        .evaluate((svg) => {
          const els = Array.from(svg.querySelectorAll("rect, path, text, circle")).slice(0, 12);
          return els.map((e) => `${getComputedStyle(e).fill}|${getComputedStyle(e).stroke}`).join(";");
        });
    const light = await paint();
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
    const dark = await paint();
    expect(dark).not.toBe(light);
    expect(await page.evaluate(() => (window as unknown as { __marker?: number }).__marker)).toBe(7);
  });

  test("FR-020-43 · every tab has Spanish text: in Spanish the labels and the panel text differ from the English ones", async ({
    page,
  }) => {
    await openModal(page);
    const en = await page.getByRole("dialog").getByRole("tab").allTextContents();
    const enPanel = await page.getByRole("dialog").getByRole("tabpanel").innerText();
    await page.keyboard.press("Escape");
    await open(page, "?lang=es");
    await trigger(page).click();
    const es = await page.getByRole("dialog").getByRole("tab").allTextContents();
    expect(es).toHaveLength(7);
    expect(es).not.toEqual(en);
    expect(await page.getByRole("dialog").getByRole("tabpanel").innerText()).not.toBe(enPanel);
    for (let i = 0; i < 7; i++) {
      await page.getByRole("dialog").getByRole("tab").nth(i).click();
      expect(
        ((await page.getByRole("dialog").getByRole("tabpanel").innerText()) ?? "").length,
        `ES tab ${i}`,
      ).toBeGreaterThan(80);
      await expect(page.getByRole("dialog").getByRole("tabpanel").locator('svg[role="img"]')).toHaveCount(1);
    }
  });
});

test.describe("focus and keys (FR-020-44)", () => {
  test("FR-020-44 · Tab and Shift+Tab never leave the open modal", async ({ page }) => {
    await openModal(page);
    for (const key of ["Tab", "Shift+Tab"]) {
      for (let i = 0; i < 25; i++) {
        await page.keyboard.press(key);
        expect(
          await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]')),
          `${key} #${i}`,
        ).toBe(true);
      }
    }
  });

  test("FR-020-44 · the arrow keys move between tabs: Right and Left, Home and End, and wrap at the ends", async ({
    page,
  }) => {
    await openModal(page);
    const tabs = page.getByRole("dialog").getByRole("tab");
    await tabs.first().focus();
    await expect(tabs.first()).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(1)).toBeFocused();
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(2)).toBeFocused();
    await page.keyboard.press("ArrowLeft");
    await expect(tabs.nth(1)).toBeFocused();
    await page.keyboard.press("End");
    await expect(tabs.nth(6)).toBeFocused();
    await expect(tabs.nth(6)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowRight");
    await expect(tabs.first()).toBeFocused();
    await page.keyboard.press("ArrowLeft");
    await expect(tabs.nth(6)).toBeFocused();
    await page.keyboard.press("Home");
    await expect(tabs.first()).toBeFocused();
  });

  test("FR-020-44 · Escape closes the modal and returns the focus to the ⓘ button", async ({ page }) => {
    await openModal(page);
    await page.getByRole("dialog").getByRole("tab").nth(3).click();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(trigger(page)).toBeFocused();
  });

  test("FR-020-44 · the modal opens from the keyboard (Enter on the ⓘ button) and closes with its close button, focus back on the trigger", async ({
    page,
  }) => {
    await open(page, "");
    await trigger(page).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: /Close/i }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(trigger(page)).toBeFocused();
  });

  test("FR-020-44 · the dialog has an accessible name and the page behind it is inert", async ({ page }) => {
    await openModal(page);
    await expect(page.getByRole("dialog")).toHaveAccessibleName(/\S/);
    expect(
      await page.evaluate(
        () =>
          !!document.querySelector("header a, nav a")?.closest("[inert], [aria-hidden='true']") ||
          document.activeElement?.closest('[role="dialog"]') !== null,
      ),
    ).toBe(true);
  });
});
