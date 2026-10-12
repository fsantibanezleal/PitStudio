// T-003-040 · FR-003-28, FR-003-29, NFR-003-03: the console UI against a fixture console (tests/support/console_fixture_server.py).
//
// Expected behaviour (see the UI contract at the top of ./helpers.ts):
//   FR-003-28  the UI is a separate web entry built into web/build/console/ with base /ui/, embeds the build marker
//              `pitstudio-console-build`, is served by the console at /ui/ with same-origin requests only, and reuses the shell's
//              theme (light/dark) and i18n (English default, Spanish);
//   FR-003-29  it shows recipes, the queue, runs with their manifests, a live telemetry chart fed by the event stream, artefact
//              previews from the artefact endpoint, a cancel action and a run form that posts a job request; each action is ONE API call;
//   NFR-003-03 axe finds no serious or critical violation in either theme and either language, on every panel.
// Oracles: the fixture store's known content (recipes a2-haulage / bench-one valid, broken-one and not-yaml invalid; run
// 20261007T120000Z-pub-case with artefacts a2-clip (video/mp4, 300,000 bytes) and a2-notes; a second run; a damaged one; one queued
// job), Playwright's request log, axe-core (the reference accessibility engine).
import { expect, type Page, test } from "@playwright/test";
import {
  apiUrl,
  axeBlocking,
  CLIP_BYTES,
  monitor,
  OTHER_RUN_ID,
  openConsole,
  openPanel,
  openRun,
  PANELS,
  prefs,
  RUN_ID,
} from "./helpers";

test.describe("the console entry", () => {
  test("FR-003-28 · /ui/ is served by the console and its build embeds the marker pitstudio-console-build", async ({
    request,
    baseURL,
  }) => {
    const res = await request.get("");
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("text/html");
    const html = await res.text();
    const refs = [...html.matchAll(/(?:src|href)="([^"#]+)"/g)]
      .map((m) => m[1] as string)
      .filter((u) => !u.startsWith("http") && !u.startsWith("data:"));
    let all = html;
    for (const ref of refs) {
      const r = await request.get(new URL(ref, baseURL).toString());
      if (r.ok()) all += await r.text();
    }
    expect(all).toContain("pitstudio-console-build");
  });

  test("FR-003-28 · every request of the UI goes to its own origin", async ({ page, baseURL }) => {
    const m = monitor(page);
    await openConsole(page);
    for (const panel of PANELS) await openPanel(page, panel);
    await openRun(page, RUN_ID);
    await page.waitForTimeout(1500);
    const own = new URL(baseURL ?? "http://127.0.0.1:4180/ui/").origin;
    const foreign = m.requests().filter((r) => {
      const url = r.split(" ")[1] ?? "";
      return /^https?:/.test(url) && new URL(url).origin !== own;
    });
    expect(foreign).toEqual([]);
    expect(m.errors()).toEqual([]);
  });

  test("FR-003-28 · English is the default language", async ({ page }) => {
    await openConsole(page);
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("main h1")).toHaveText("PitStudio console");
    await expect(page.getByRole("tablist", { name: "Console sections" })).toBeVisible();
  });

  test("FR-003-28 · Spanish via the language switch, persisted, and ?lang= wins", async ({ page }) => {
    await openConsole(page);
    const english = await page.locator("main h1").innerText();
    await page.getByLabel("Language").selectOption("es");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    expect(await page.locator("main h1").innerText()).not.toBe(english);
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await page.goto("?lang=en");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("main h1")).toHaveText("PitStudio console");
  });

  test("FR-003-28 · the theme follows the shell: stored choice, toggle cycle and persistence", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await openConsole(page);
    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-theme", "light");
    const toggle = page.getByRole("button", { name: /^Theme:/ });
    await toggle.click(); // system -> light
    await toggle.click(); // light -> dark
    await expect(html).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "dark");
  });
});

test.describe("what the console shows", () => {
  test("FR-003-29 · recipes: valid and invalid files with their status and details", async ({ page }) => {
    await openConsole(page);
    await openPanel(page, "Recipes");
    const table = page.getByRole("table", { name: "Recipes" });
    for (const id of ["a2-haulage", "bench-one"]) {
      await expect(table.getByRole("row").filter({ hasText: id })).toContainText("valid");
      await expect(table.getByRole("row").filter({ hasText: id })).not.toContainText("invalid");
    }
    await expect(table.getByRole("row").filter({ hasText: "broken-one" })).toContainText("invalid");
    await expect(table.getByRole("row").filter({ hasText: "not-yaml" })).toContainText("invalid");
    await table
      .getByRole("row")
      .filter({ hasText: "bench-one" })
      .getByRole("link", { name: "bench-one" })
      .or(table.getByRole("button", { name: "bench-one" }))
      .first()
      .click();
    const details = page.getByRole("region", { name: "Recipe details" });
    await expect(details).toContainText("s64_bench");
  });

  test("FR-003-29 · queue: the fixture job is listed with its state", async ({ page }) => {
    await openConsole(page);
    await openPanel(page, "Queue");
    const row = page
      .getByRole("table", { name: "Queue" })
      .getByRole("row")
      .filter({ hasText: "a2-haulage" })
      .first();
    await expect(row).toContainText("queued");
    await expect(row.getByRole("button", { name: /^Cancel job / })).toBeVisible();
  });

  test("FR-003-29 · runs: the list shows valid and damaged runs, and a run opens with its manifest", async ({
    page,
  }) => {
    await openConsole(page);
    await openPanel(page, "Runs");
    const table = page.getByRole("table", { name: "Runs" });
    await expect(table).toContainText(RUN_ID);
    await expect(table).toContainText(OTHER_RUN_ID);
    await expect(table.getByRole("row").filter({ hasText: "broken-manifest" })).toContainText(
      /invalid|false|no/i,
    );
    await openRun(page, RUN_ID);
    const manifest = page.getByRole("region", { name: "Manifest" });
    await expect(manifest).toContainText("pub-case");
    for (const stage of ["st50_physics", "st56_encode", "st53_sensors"])
      await expect(manifest).toContainText(stage);
  });

  test("FR-003-29 · artefacts are previewed from the artefact endpoint", async ({
    page,
    request,
    baseURL,
  }) => {
    await openConsole(page);
    await openRun(page, RUN_ID);
    const artefacts = page.getByRole("region", { name: "Artefacts" });
    const clip = artefacts.locator('[data-testid="artefact-a2-clip"]');
    const notes = artefacts.locator('[data-testid="artefact-a2-notes"]');
    await expect(clip).toBeVisible();
    await expect(notes).toBeVisible();
    const src = await clip
      .locator("video, video source, a, img")
      .evaluateAll((els) => els.map((e) => e.getAttribute("src") ?? e.getAttribute("href") ?? ""));
    expect(src.some((s) => s.includes(`/runs/${RUN_ID}/artefacts/a2-clip`))).toBe(true);
    await expect(clip.locator("video")).toHaveCount(1);
    const res = await request.get(apiUrl(baseURL, `/runs/${RUN_ID}/artefacts/a2-clip`));
    expect(res.status()).toBe(200);
    expect(Number(res.headers()["content-length"])).toBe(CLIP_BYTES);
  });

  test("FR-003-29 · the telemetry chart is fed by the event stream of the opened run", async ({ page }) => {
    const m = monitor(page);
    await openConsole(page);
    await openRun(page, RUN_ID);
    const chart = page.getByRole("region", { name: "Telemetry" }).locator('[data-testid="telemetry-chart"]');
    await expect(chart).toBeVisible();
    await expect
      .poll(async () => Number(await chart.getAttribute("data-points")), { timeout: 10_000 })
      .toBeGreaterThanOrEqual(2);
    expect(m.requests().some((r) => r.startsWith("GET") && r.includes(`/runs/${RUN_ID}/events`))).toBe(true);
    const first = Number(await chart.getAttribute("data-points"));
    await expect
      .poll(async () => Number(await chart.getAttribute("data-points")), { timeout: 10_000 })
      .toBeGreaterThan(first);
  });

  test("FR-003-29 · the run form posts exactly one job request and the job appears in the queue", async ({
    page,
  }) => {
    const m = monitor(page);
    await openConsole(page);
    await openPanel(page, "New job");
    const form = page.getByRole("form", { name: "Run form" });
    await form.getByLabel("Recipe").selectOption("a2-haulage");
    await form.getByLabel("Profile").fill("test-profile");
    await form.getByRole("group", { name: "Stages" }).getByLabel("s10_preprocess").check();
    await form.getByLabel("Force").check();
    await form.getByLabel("Rerun check").check();
    const posted = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/jobs");
    await form.getByRole("button", { name: "Queue job" }).click();
    const req = await posted;
    expect(JSON.parse(req.postData() ?? "{}")).toEqual({
      recipe: "a2-haulage",
      profile: "test-profile",
      stages: [{ id: "s10_preprocess" }],
      force: true,
      rerun_check: true,
    });
    const status = page.getByRole("status");
    await expect(status).toContainText(/\d{8}T\d{6}Z-[0-9a-f]{8}/);
    expect(m.requests().filter((r) => r.startsWith("POST") && r.endsWith("/jobs"))).toHaveLength(1);
    const jobId = /\d{8}T\d{6}Z-[0-9a-f]{8}/.exec((await status.innerText()) ?? "")?.[0] ?? "";
    await openPanel(page, "Queue");
    await expect(page.getByRole("table", { name: "Queue" })).toContainText(jobId);
  });

  test("FR-003-29 · without ticking any stage the request names none (all stages) and defaults the flags", async ({
    page,
  }) => {
    await openConsole(page);
    await openPanel(page, "New job");
    const form = page.getByRole("form", { name: "Run form" });
    await form.getByLabel("Recipe").selectOption("bench-one");
    await form.getByLabel("Profile").fill("test-profile");
    const posted = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/jobs");
    await form.getByRole("button", { name: "Queue job" }).click();
    const body = JSON.parse((await posted).postData() ?? "{}") as Record<string, unknown>;
    expect(body.recipe).toBe("bench-one");
    expect(body.profile).toBe("test-profile");
    expect(body.stages ?? null).toBeNull();
    expect(body.force ?? false).toBe(false);
    expect(body.rerun_check ?? false).toBe(false);
    expect(
      Object.keys(body).every((k) => ["recipe", "profile", "stages", "force", "rerun_check"].includes(k)),
    ).toBe(true);
  });

  test("FR-003-29 · cancelling a queued job is one API call and the queue shows it cancelled", async ({
    page,
  }) => {
    const m = monitor(page);
    await openConsole(page);
    await openPanel(page, "New job");
    const form = page.getByRole("form", { name: "Run form" });
    await form.getByLabel("Recipe").selectOption("bench-one");
    await form.getByLabel("Profile").fill("test-profile");
    await form.getByRole("button", { name: "Queue job" }).click();
    const jobId = /\d{8}T\d{6}Z-[0-9a-f]{8}/.exec(await page.getByRole("status").innerText())?.[0] ?? "";
    expect(jobId).not.toBe("");
    await openPanel(page, "Queue");
    const cancelled = page.waitForRequest(
      (r) => r.method() === "POST" && new URL(r.url()).pathname === `/jobs/${jobId}/cancel`,
    );
    await page.getByRole("button", { name: `Cancel job ${jobId}` }).click();
    await cancelled;
    await expect(
      page.getByRole("table", { name: "Queue" }).getByRole("row").filter({ hasText: jobId }),
    ).toContainText("cancelled");
    expect(
      m.requests().filter((r) => r.startsWith("POST") && r.endsWith(`/jobs/${jobId}/cancel`)),
    ).toHaveLength(1);
  });
});

async function localise(page: Page, lang: "en" | "es"): Promise<void> {
  // panels are opened with the English labels, then the language is switched (the switch itself is labelled "Language" in English)
  if (lang === "en") return;
  await page.getByLabel("Language").selectOption("es");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
}

test.describe("accessibility", () => {
  for (const theme of ["light", "dark"] as const) {
    for (const lang of ["en", "es"] as const) {
      for (const panel of PANELS) {
        test(`NFR-003-03 · no serious or critical axe violations: ${panel}, ${theme}, ${lang}`, async ({
          page,
        }) => {
          await prefs(page, theme, "en");
          await openConsole(page, "?lang=en");
          await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
          await openPanel(page, panel);
          if (panel === "Runs") await expect(page.getByRole("table", { name: "Runs" })).toBeVisible();
          await localise(page, lang);
          expect(await axeBlocking(page)).toEqual([]);
        });
      }
      test(`NFR-003-03 · no serious or critical axe violations: run details, ${theme}, ${lang}`, async ({
        page,
      }) => {
        await prefs(page, theme, "en");
        await openConsole(page, "?lang=en");
        await openRun(page, RUN_ID);
        await expect(page.getByRole("region", { name: "Manifest" })).toBeVisible();
        await localise(page, lang);
        expect(await axeBlocking(page)).toEqual([]);
      });
    }
  }
});
