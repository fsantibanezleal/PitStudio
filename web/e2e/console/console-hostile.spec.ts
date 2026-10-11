// T-003-041 · FR-003-30: the console UI under failing API calls and injected markup (tests/support/console_fixture_server.py).
//
// Expected behaviour (UI contract in ./helpers.ts): if an API call fails (4xx, 5xx, network error, invalid body) or a manifest or recipe
// string contains markup (e.g. `<img src=x onerror=...>`), the UI shows an error message (an element with role="alert" and a
// non-empty text), does not crash (no uncaught page error, the heading and the tabs stay usable) and renders the string as TEXT:
// no injected element exists and no injected script runs (`window.__pwned` stays undefined, no dialog opens).
// The fixture store carries the markup of ./helpers.ts MARKUP in: the description of recipe a2-haulage, the `notes` of the run
// 20261007T120000Z-pub-case, a parameter of its first stage, the `log_tail` of its failed stage, and the seed of the invalid
// recipe broken-one. Oracles: Playwright's page-error, dialog and DOM queries; stubbed responses written by hand.
import { expect, type Page, type Route, test } from "@playwright/test";
import { BROKEN_RUN_ID, MARKUP, monitor, openConsole, openPanel, openRun, RUN_ID } from "./helpers";

async function pwned(page: Page): Promise<unknown> {
  return page.evaluate(() => (window as unknown as { __pwned?: unknown }).__pwned);
}

async function injectedNodes(page: Page): Promise<number> {
  return page
    .locator('img[src="x"], svg[onload], a[href^="javascript:"], main script, [onerror], [onload]')
    .count();
}

async function stillUsable(page: Page): Promise<void> {
  await expect(page.locator("main h1")).toBeVisible();
  await openPanel(page, "Queue");
  await openPanel(page, "Recipes");
}

const problem = (status: number, detail: string) => ({
  status,
  contentType: "application/problem+json",
  body: JSON.stringify({ type: "about:blank", title: "Stubbed failure", status, detail }),
});

test.describe("markup in manifest and recipe strings is text", () => {
  test("FR-003-30 · the recipe description is shown literally", async ({ page }) => {
    const m = monitor(page);
    await openConsole(page);
    await openPanel(page, "Recipes");
    await page
      .getByRole("table", { name: "Recipes" })
      .getByRole("row")
      .filter({ hasText: "a2-haulage" })
      .getByRole("link", { name: "a2-haulage" })
      .or(page.getByRole("button", { name: "a2-haulage" }))
      .first()
      .click();
    const details = page.getByRole("region", { name: "Recipe details" });
    await expect(details).toContainText(MARKUP[0] as string);
    await page.waitForTimeout(800);
    expect(await pwned(page)).toBeUndefined();
    expect(await injectedNodes(page)).toBe(0);
    expect(m.dialogs()).toEqual([]);
    expect(m.errors()).toEqual([]);
  });

  test("FR-003-30 · manifest notes, parameters and log tails are shown literally", async ({ page }) => {
    const m = monitor(page);
    await openConsole(page);
    await openRun(page, RUN_ID);
    const manifest = page.getByRole("region", { name: "Manifest" });
    for (const s of MARKUP) await expect(manifest).toContainText(s);
    await page.waitForTimeout(1200);
    expect(await pwned(page)).toBeUndefined();
    expect(await injectedNodes(page)).toBe(0);
    expect(m.dialogs()).toEqual([]);
    expect(m.errors()).toEqual([]);
    // the text, not an element, is what the visitor sees
    expect(await manifest.locator("img").count()).toBe(0);
  });

  test("FR-003-30 · the error list of an invalid recipe does not execute the markup of its values", async ({
    page,
  }) => {
    const m = monitor(page);
    await openConsole(page);
    await openPanel(page, "Recipes");
    await expect(
      page.getByRole("table", { name: "Recipes" }).getByRole("row").filter({ hasText: "broken-one" }),
    ).toContainText("invalid");
    await page.waitForTimeout(800);
    expect(await pwned(page)).toBeUndefined();
    expect(await injectedNodes(page)).toBe(0);
    expect(m.dialogs()).toEqual([]);
  });

  test("FR-003-30 · a problem body whose detail is markup is rendered as text", async ({ page }) => {
    const m = monitor(page);
    await page.route(/\/queue$/, (route: Route) => route.fulfill(problem(500, MARKUP[0] as string)));
    await openConsole(page);
    await openPanel(page, "Queue");
    const alert = page.getByRole("alert").first();
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("onerror");
    await page.waitForTimeout(800);
    expect(await pwned(page)).toBeUndefined();
    expect(await injectedNodes(page)).toBe(0);
    expect(m.dialogs()).toEqual([]);
    expect(m.errors()).toEqual([]);
  });
});

const LISTS: Array<[name: string, pattern: RegExp, panel: "Recipes" | "Queue" | "Runs"]> = [
  ["recipes", /\/recipes$/, "Recipes"],
  ["queue", /\/queue$/, "Queue"],
  ["runs", /\/runs$/, "Runs"],
];

test.describe("failing API calls", () => {
  for (const [name, pattern, panel] of LISTS) {
    for (const status of [400, 403, 404, 409, 422, 429, 500, 503]) {
      test(`FR-003-30 · ${name} answering ${status} shows an error and the UI keeps working`, async ({
        page,
      }) => {
        const m = monitor(page);
        await page.route(pattern, (route) => route.fulfill(problem(status, `stubbed ${status}`)));
        await openConsole(page);
        await openPanel(page, panel);
        await expect(page.getByRole("alert").first()).toBeVisible();
        expect(((await page.getByRole("alert").first().innerText()) ?? "").trim().length).toBeGreaterThan(0);
        expect(m.errors()).toEqual([]);
        await stillUsable(page);
      });
    }

    test(`FR-003-30 · ${name} unreachable (network error) shows an error and the UI keeps working`, async ({
      page,
    }) => {
      const m = monitor(page);
      await page.route(pattern, (route) => route.abort("failed"));
      await openConsole(page);
      await openPanel(page, panel);
      await expect(page.getByRole("alert").first()).toBeVisible();
      expect(m.errors()).toEqual([]);
      await stillUsable(page);
    });

    for (const [label, body, contentType] of [
      ["not JSON", "this is not json", "application/json"],
      [
        "an HTML page",
        "<html><body><h1>proxy error</h1><script>window.__pwned=1</script></body></html>",
        "text/html",
      ],
      ["a schema-invalid object", JSON.stringify({ nonsense: true }), "application/json"],
      ["a JSON array", "[1,2,3]", "application/json"],
      ["null", "null", "application/json"],
      ["an empty body", "", "application/json"],
      ["a wrong shape", JSON.stringify({ recipes: "x", jobs: 5, runs: { a: 1 } }), "application/json"],
    ] as const) {
      test(`FR-003-30 · ${name} answering 200 with ${label} shows an error and the UI keeps working`, async ({
        page,
      }) => {
        const m = monitor(page);
        await page.route(pattern, (route) => route.fulfill({ status: 200, contentType, body }));
        await openConsole(page);
        await openPanel(page, panel);
        await expect(page.getByRole("alert").first()).toBeVisible();
        expect(m.errors()).toEqual([]);
        expect(await pwned(page)).toBeUndefined();
        await stillUsable(page);
      });
    }
  }

  test("FR-003-30 · a run whose manifest is invalid (409 from the real console) shows an error, not a crash", async ({
    page,
  }) => {
    const m = monitor(page);
    await openConsole(page);
    await openPanel(page, "Runs");
    await page
      .getByRole("table", { name: "Runs" })
      .getByRole("row")
      .filter({ hasText: "broken-manifest" })
      .getByRole("link", { name: BROKEN_RUN_ID })
      .or(page.getByRole("button", { name: BROKEN_RUN_ID }))
      .first()
      .click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    expect(m.errors()).toEqual([]);
    await stillUsable(page);
  });

  for (const [label, fulfill] of [
    ["a 500", (route: Route) => route.fulfill(problem(500, "stream broke"))],
    ["a dropped connection", (route: Route) => route.abort("failed")],
    [
      "a garbage event stream",
      (route: Route) =>
        route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: "id: x\nevent: event\ndata: {not json\n\nevent: telemetry\ndata: <img src=x onerror=window.__pwned=1>\n\n",
        }),
    ],
    [
      "an HTML page",
      (route: Route) =>
        route.fulfill({ status: 200, contentType: "text/html", body: "<script>window.__pwned=1</script>" }),
    ],
  ] as const) {
    test(`FR-003-30 · the event stream failing with ${label} does not crash the run view`, async ({
      page,
    }) => {
      const m = monitor(page);
      await page.route(/\/runs\/[^/]+\/events$/, fulfill);
      await openConsole(page);
      await openRun(page, RUN_ID);
      await expect(page.getByRole("region", { name: "Manifest" })).toBeVisible();
      await page.waitForTimeout(1500);
      expect(m.errors()).toEqual([]);
      expect(await pwned(page)).toBeUndefined();
      expect(await injectedNodes(page)).toBe(0);
      await stillUsable(page);
    });
  }

  for (const status of [400, 403, 409, 413, 415, 422, 429, 500, 503]) {
    test(`FR-003-30 · queueing a job answered with ${status} shows the error and never claims success`, async ({
      page,
    }) => {
      const m = monitor(page);
      await page.route(/\/jobs$/, (route) =>
        route.request().method() === "POST"
          ? route.fulfill(problem(status, `stubbed ${status} ${MARKUP[0]}`))
          : route.continue(),
      );
      await openConsole(page);
      await openPanel(page, "New job");
      const form = page.getByRole("form", { name: "Run form" });
      await form.getByLabel("Recipe").selectOption("a2-haulage");
      await form.getByLabel("Profile").fill("test-profile");
      await form.getByRole("button", { name: "Queue job" }).click();
      await expect(page.getByRole("alert").first()).toBeVisible();
      await expect(page.getByRole("status").filter({ hasText: /\d{8}T\d{6}Z-[0-9a-f]{8}/ })).toHaveCount(0);
      expect(await pwned(page)).toBeUndefined();
      expect(m.errors()).toEqual([]);
      await stillUsable(page);
    });
  }

  test("FR-003-30 · queueing a job with the network down shows an error", async ({ page }) => {
    const m = monitor(page);
    await page.route(/\/jobs$/, (route) =>
      route.request().method() === "POST" ? route.abort("failed") : route.continue(),
    );
    await openConsole(page);
    await openPanel(page, "New job");
    const form = page.getByRole("form", { name: "Run form" });
    await form.getByLabel("Recipe").selectOption("a2-haulage");
    await form.getByLabel("Profile").fill("test-profile");
    await form.getByRole("button", { name: "Queue job" }).click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    expect(m.errors()).toEqual([]);
  });

  test("FR-003-30 · hostile profile text is sent as data, refused by the console and shown as text", async ({
    page,
  }) => {
    const m = monitor(page);
    await openConsole(page);
    await openPanel(page, "New job");
    const form = page.getByRole("form", { name: "Run form" });
    await form.getByLabel("Recipe").selectOption("a2-haulage");
    await form.getByLabel("Profile").fill(`"><script>window.__pwned=1</script>`);
    await form.getByRole("button", { name: "Queue job" }).click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    await page.waitForTimeout(600);
    expect(await pwned(page)).toBeUndefined();
    expect(await injectedNodes(page)).toBe(0);
    expect(m.dialogs()).toEqual([]);
    expect(m.errors()).toEqual([]);
  });

  test("FR-003-30 · cancelling a job that is already finished (409) shows the error and keeps the queue visible", async ({
    page,
  }) => {
    const m = monitor(page);
    await page.route(/\/jobs\/[^/]+\/cancel$/, (route) =>
      route.fulfill(problem(409, "job already finished")),
    );
    await openConsole(page);
    await openPanel(page, "Queue");
    await page
      .getByRole("button", { name: /^Cancel job / })
      .first()
      .click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByRole("table", { name: "Queue" })).toBeVisible();
    expect(m.errors()).toEqual([]);
  });
});
