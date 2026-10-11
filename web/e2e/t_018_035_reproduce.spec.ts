// T-018-035 [red] · FR-018-19, FR-018-20 (E2E half): the "Reproduce this" block on every `/cases/<id>/` page of the production build.
// Component contract: see web/src/routes/t_018_035_reproduce.test.tsx (`[data-command]` lines, copy button, heading).
// The state to expect is derived from the repository, not from the app: a case whose recipe file `studio/recipes/cases/<id>.yaml`
// exists at build time shows the recipe path and the three commands; one without shows "Not yet run — recipe planned" and no command.
// (No case recipe is committed yet, so today every page must show the planned state; the commands branch is covered by the unit test.)
// The block is on the page whatever sub-tab is open and comes after the tab panel (the page "ends with" it).
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { CASE_IDS, CASE_TABS } from "../src/test-support/fixtures";
import { open } from "./helpers";

function recipeExists(id: string): boolean {
  return existsSync(
    fileURLToPath(new URL(`../../studio/recipes/cases/${id.toLowerCase()}.yaml`, import.meta.url)),
  );
}

test.describe("Reproduce this (FR-018-19, FR-018-20)", () => {
  test("FR-018-19 · every case page ends with a 'Reproduce this' block after its tab panel", async ({
    page,
  }) => {
    for (const id of CASE_IDS) {
      await open(page, `cases/${id}/`);
      const heading = page.getByRole("heading", { name: "Reproduce this" });
      await expect(heading).toBeVisible();
      const panel = await page.getByRole("tabpanel").boundingBox();
      const head = await heading.boundingBox();
      expect(
        head && panel && head.y >= panel.y + panel.height - 1,
        `${id}: block must follow the panel`,
      ).toBe(true);
    }
  });

  test("FR-018-19 · the block is present on every sub-tab", async ({ page }) => {
    for (const [, param] of CASE_TABS) {
      await open(page, `cases/A1/?tab=${param}`);
      await expect(page.getByRole("heading", { name: "Reproduce this" })).toBeVisible();
    }
  });

  test("FR-018-19 · with a recipe: path, three commands and a copy button; without: 'Not yet run — recipe planned' and no command", async ({
    page,
  }) => {
    for (const id of CASE_IDS) {
      await open(page, `cases/${id}/`);
      const path = `studio/recipes/cases/${id.toLowerCase()}.yaml`;
      const commands = page.locator("[data-command]");
      if (recipeExists(id)) {
        await expect(page.getByText(path).first()).toBeVisible();
        await expect(commands).toHaveCount(3);
        await expect(commands.nth(0)).toHaveText(`uv run studio plan ${path} --profile laptop-rtx5000ada`);
        await expect(commands.nth(1)).toHaveText(`uv run studio run ${path} --profile laptop-rtx5000ada`);
        await expect(commands.nth(2)).toHaveText(
          /^uv run studio publish (<run-id>|[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]*)$/,
        );
        await expect(page.getByRole("button", { name: /copy/i })).toBeVisible();
      } else {
        await expect(page.getByText("Not yet run — recipe planned")).toBeVisible();
        await expect(commands).toHaveCount(0);
        await expect(page.getByText("uv run")).toHaveCount(0);
        await expect(page.getByRole("button", { name: /copy/i })).toHaveCount(0);
      }
    }
  });

  test("FR-018-19 · the page text contains no absolute path, host name or user name", async ({ page }) => {
    await open(page, "cases/A1/");
    await expect(page.getByRole("heading", { name: "Reproduce this" })).toBeVisible();
    const text = await page.locator("main").innerText();
    expect(text).not.toMatch(/[A-Za-z]:[\\/]/);
    expect(text).not.toMatch(/(^|[\s"'=(,:])\/(home|Users|root|tmp|var|mnt|opt|srv)\//);
    expect(text).not.toContain("file:/");
  });
});
