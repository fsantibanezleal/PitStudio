// T-018-103 · FR-018-80 in a real browser: on each of the 12 case pages the Built with section is collapsed on load, its summary row counts
// the used and planned chips that stay in the document, it opens on a click and on Enter or Space, and the state is not kept on a reload.
// Run against a deployed site with LIVE_URL=https://host/ (it must end with a slash).
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const CASES = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];

if (process.env.LIVE_URL) test.use({ baseURL: process.env.LIVE_URL });

for (const [lang, used, planned] of [
  ["en", "used", "planned"],
  ["es", "usados", "planificados"],
] as const)
  for (const id of CASES) {
    test(`FR-018-80 · ${id} · ${lang} · Built with is collapsed on load, counts the chips, opens by click, Enter and Space`, async ({
      page,
    }) => {
      await open(page, `cases/${id}/?lang=${lang}`);
      const section = page.getByTestId("built-with");
      const details = section.locator("details");
      const summary = details.locator("summary");
      await expect(summary).toBeVisible();
      await expect(details).not.toHaveAttribute("open", /.*/);
      await expect(section.locator("[data-chip]").first()).toBeHidden();

      // the chips are in the document: the counts match them
      const states = await section
        .locator("[data-chip]")
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-status")));
      expect(states.length).toBeGreaterThan(0);
      const nUsed = states.filter((s) => s === "used").length;
      const nPlanned = states.filter((s) => s === "planned").length;
      await expect(section.getByTestId("built-with-counts")).toHaveText(
        `${nUsed} ${used}, ${nPlanned} ${planned}`,
      );

      await summary.click();
      await expect(details).toHaveAttribute("open", "");
      await expect(section.locator("[data-chip]").first()).toBeVisible();
      await summary.click();
      await expect(details).not.toHaveAttribute("open", /.*/);
      for (const key of ["Enter", "Space"]) {
        await summary.focus();
        await page.keyboard.press(key);
        await expect(details).toHaveAttribute("open", "");
        await page.keyboard.press(key);
        await expect(details).not.toHaveAttribute("open", /.*/);
      }

      // the state is not stored: open it, reload, it is collapsed again
      await summary.click();
      await expect(details).toHaveAttribute("open", "");
      await page.reload();
      await expect(page.getByTestId("built-with").locator("details")).not.toHaveAttribute("open", /.*/);
    });
  }
