import { expect, type Page } from "@playwright/test";

/** The demo passphrase the build was made with (same env var as the build). Unset → no gate. */
export const PASSPHRASE = process.env.ACCESS_PASSPHRASE?.trim() ?? "";

export const ROUTES = ["", "cases", "studio", "theory", "methods", "results", "knowledge"];

/** Opens a page (relative to the base path) and passes the access gate when the build has one. */
export async function open(page: Page, path = ""): Promise<void> {
  await page.goto(path);
  if (!PASSPHRASE) return;
  const input = page.getByLabel("Passphrase");
  const main = page.locator("main h1");
  await expect(main.or(input).first()).toBeVisible();
  if (await input.isVisible()) {
    await input.fill(PASSPHRASE);
    await page.getByRole("button", { name: "Enter" }).click();
    await expect(input).toBeHidden();
  }
}
