import { expect, test } from "@playwright/test";

// The deployed site: start page, a prerendered deep route and an unknown route behave like the local build.
test("start page answers", async ({ request }) => {
  const res = await request.get("");
  expect(res.status()).toBe(200);
  expect(await res.text()).toContain("PitStudio");
});

test("a prerendered deep route answers 200", async ({ request }) => {
  const res = await request.get("theory/");
  expect(res.status()).toBe(200);
  expect(await res.text()).toContain("<title>Theory · PitStudio</title>");
});

test("an unknown route answers 404 with the app shell", async ({ request }) => {
  const res = await request.get("no/such/page");
  expect(res.status()).toBe(404);
  expect(await res.text()).toContain("PitStudio");
});

test("the shell renders and states the gate honestly", async ({ page }) => {
  await page.goto("");
  await expect(page.getByRole("banner")).toContainText("PitStudio");
  await expect(page.getByRole("contentinfo")).toContainText("not a security boundary");
});
