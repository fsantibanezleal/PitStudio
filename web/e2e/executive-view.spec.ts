import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

// The Introduction opens on the executive view (problem context first): five sub-tabs from the committed content file,
// both languages, light and dark, each sub-tab by link, the onward links, and the old App links.

interface Text {
  en: string;
  es: string;
}
const content = JSON.parse(readFileSync(resolve("content/executive.json"), "utf8")) as {
  title: Text;
  key_statement: Text;
  sources: { url: string; title: Text }[];
  illustrations: Record<string, { caption: Text }>;
};

const LANG_KEY = "fsl:lang";
const SECTIONS = [
  { id: "pain", en: "The pain", es: "El problema" },
  { id: "context", en: "The context", es: "El contexto" },
  { id: "situation", en: "The current situation", es: "La situación actual" },
  { id: "trends", en: "The trends", es: "Las tendencias" },
  { id: "proposal", en: "The proposal", es: "La propuesta" },
] as const;
type Lang = "en" | "es";

async function start(page: Page, lang: Lang, path = "") {
  await page.addInitScript(
    ([key, value]) => {
      try {
        localStorage.setItem(key as string, value as string);
      } catch {
        // storage blocked
      }
    },
    [LANG_KEY, lang],
  );
  await open(page, path);
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
}

test.describe("the root opens the Introduction on its executive view", () => {
  for (const lang of ["en", "es"] as const) {
    test(`${lang}: the title from the content file and the five sub-tabs, the first open`, async ({
      page,
    }) => {
      const errors: string[] = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      page.on("pageerror", (e) => errors.push(String(e)));
      await start(page, lang);
      await expect(page.locator("main h1")).toHaveText(lang === "en" ? "Introduction" : "Introducción");
      await expect(page.locator("[data-executive-view]")).toHaveAttribute("data-executive-valid", "true");
      await expect(page.getByRole("heading", { level: 2, name: content.title[lang] })).toBeVisible();
      await expect(page.locator('[data-exec-field="key_statement"]')).toHaveText(content.key_statement[lang]);
      const executiveTabs = page.locator("[data-exec-tabs]").getByRole("tab");
      await expect(executiveTabs).toHaveCount(5);
      for (const [i, section] of SECTIONS.entries()) {
        await expect(executiveTabs.nth(i)).toHaveText(section[lang]);
      }
      await expect(executiveTabs.first()).toHaveAttribute("aria-selected", "true");
      expect(errors).toEqual([]);
    });
  }

  test("the navigation lists the Introduction and the App; the App stays leftmost", async ({ page }) => {
    await open(page);
    const links = page.getByRole("navigation", { name: "Main" }).getByRole("link");
    await expect(links.nth(0)).toHaveText("Explore");
    await expect(links.nth(1)).toHaveText("Introduction");
  });
});

test.describe("every sub-tab opens by link", () => {
  for (const lang of ["en", "es"] as const) {
    for (const section of SECTIONS) {
      test(`${lang}: ?section=${section.id}`, async ({ page }) => {
        await start(page, lang, `?section=${section.id}`);
        const tab = page.locator("[data-exec-tabs]").getByRole("tab", { name: section[lang] });
        await expect(tab).toHaveAttribute("aria-selected", "true");
        await expect(page.locator("[data-exec-key-message]:visible")).toHaveCount(1);
        await expect(page.locator("[data-exec-key-message]:visible")).not.toBeEmpty();
      });
    }
  }

  test("choosing a sub-tab puts it in the address, so the link can be shared", async ({ page }) => {
    await open(page);
    await page.locator("[data-exec-tabs]").getByRole("tab", { name: "The trends" }).click();
    await expect(page).toHaveURL(/section=trends/);
    await page.reload();
    await expect(page.locator("[data-exec-tabs]").getByRole("tab", { name: "The trends" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("the sources are listed as links", async ({ page }) => {
    await open(page);
    const notes = page.locator("[data-exec-notes] a[data-exec-source-title]");
    expect(await notes.count()).toBeGreaterThan(3);
    for (const href of await notes.evaluateAll((all) => all.map((a) => a.getAttribute("href")))) {
      expect(href).toMatch(/^https:\/\//);
    }
  });
});

test.describe("the illustrations follow the theme", () => {
  for (const [id, sub] of [
    ["pain", "pain"],
    ["situation", "situation"],
    ["proposal", "proposal"],
  ] as const) {
    test(`${id}: inline, labelled in the displayed language, coloured by the theme in light and dark`, async ({
      page,
    }) => {
      const fills: string[] = [];
      for (const theme of ["light", "dark"] as const) {
        await page.emulateMedia({ colorScheme: theme });
        await open(page, `?section=${sub}`);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        const art = page.locator(`[data-exec-illustration="${id}"] svg`);
        await expect(art).toBeVisible();
        await expect(page.locator(`[data-exec-illustration="${id}"] img`)).toHaveCount(0);
        await expect(page.locator(`[data-exec-illustration="${id}"] figcaption`)).toHaveText(
          content.illustrations[id]?.caption.en ?? "",
        );
        const background = await art
          .locator("rect")
          .first()
          .evaluate((r) => getComputedStyle(r).fill);
        fills.push(background);
        const hard = await art.evaluate(
          (svg) =>
            [...svg.querySelectorAll("[fill],[stroke]")].filter((n) =>
              /#|rgb\(/.test(`${n.getAttribute("fill")}${n.getAttribute("stroke")}`),
            ).length,
        );
        expect(hard).toBe(0);
      }
      expect(fills[0]).not.toEqual(fills[1]);
    });
  }

  test("the labels of the drawing show in Spanish with the language switched", async ({ page }) => {
    await start(page, "es", "?section=pain");
    const labels = page.locator('[data-exec-illustration="pain"] text:visible');
    expect(await labels.count()).toBeGreaterThanOrEqual(6);
    await expect(labels.first()).toBeVisible();
    await expect(page.locator('[data-exec-illustration="pain"] text[data-lang="en"]:visible')).toHaveCount(0);
  });
});

test.describe("onward links and old App links", () => {
  test("How the work explores this problem opens the technical view, Open the App opens the App", async ({
    page,
  }) => {
    await open(page);
    await page.getByRole("link", { name: "How the work explores this problem" }).click();
    await expect(page.getByRole("tab", { name: "Technical view" })).toHaveAttribute("aria-selected", "true");
    await expect(page).toHaveURL(/view=technical/);
    await page.getByRole("link", { name: "Open the App" }).click();
    await expect(page).toHaveURL(/\/app\/?$/);
    await expect(page.locator("main h1")).toHaveText("Explore an open pit");
  });

  test("the executive view own Open the App link goes to the App", async ({ page }) => {
    await open(page);
    await page.locator('[data-exec-link="app"]').click();
    await expect(page.locator("main h1")).toHaveText("Explore an open pit");
  });

  test("an old App link (/?case=B2) is forwarded to /app with its query kept", async ({ page }) => {
    await open(page, "?case=B2");
    await expect(page).toHaveURL(/\/app\/?\?case=B2/);
    await expect(page.locator("main h1")).toHaveText("Explore an open pit");
  });

  test("/app/ is a prerendered page (200)", async ({ request }) => {
    const res = await request.get("app/");
    expect(res.status()).toBe(200);
  });
});

// Full-page screenshots of every sub-tab, light and dark, English and Spanish (EXECUTIVE_SHOTS=<folder>).
test.describe("screenshots", () => {
  const folder = process.env.EXECUTIVE_SHOTS;
  test.skip(!folder, "set EXECUTIVE_SHOTS to a folder to write the screenshots");
  test.use({ viewport: { width: 1280, height: 900 } });

  for (const lang of ["en", "es"] as const) {
    for (const theme of ["light", "dark"] as const) {
      for (const [i, section] of SECTIONS.entries()) {
        test(`${lang} ${theme} ${i + 1}-${section.id}`, async ({ page }) => {
          mkdirSync(folder ?? ".", { recursive: true });
          await page.emulateMedia({ colorScheme: theme });
          await start(page, lang, `?section=${section.id}`);
          await expect(
            page.locator("[data-exec-tabs]").getByRole("tab", { name: section[lang] }),
          ).toHaveAttribute("aria-selected", "true");
          if (section.id === "pain" || section.id === "situation" || section.id === "proposal") {
            await expect(page.locator(`[data-exec-illustration="${section.id}"] svg`)).toBeVisible();
          }
          await page.screenshot({
            path: resolve(folder ?? ".", `executive-${i + 1}-${section.id}-${theme}-${lang}.png`),
            fullPage: true,
          });
        });
      }
    }
  }
});
