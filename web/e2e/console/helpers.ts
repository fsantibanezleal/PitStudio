// Shared helpers of the console's browser tests (T-003-040, T-003-041). Not a spec file.
//
// THE UI CONTRACT these tests assume (the implementer builds `web/console/` to it; it is the spec's FR-003-28..30 made concrete):
//   * served at `<console>/ui/` (the Playwright baseURL ends with `/ui/`); the built files embed the marker `pitstudio-console-build`;
//     every request the UI makes goes to its own origin;
//   * the shell's header: a button named /^Theme:/ that cycles system, light, dark (stores `fsl:theme`), and a select labelled
//     "Language" with `en` and `es` (stores `fsl:lang`, `?lang=` wins), `html[data-theme]` and `html[lang]` follow;
//   * `main h1` = "PitStudio console" (English); a tablist named "Console sections" with the tabs "Recipes", "Queue", "Runs" and
//     "New job"; every API failure shows an element with role="alert" holding a non-empty text, and the UI stays usable;
//   * Recipes tab: a table named "Recipes" (columns Id, Case, Stages, Status), one row per recipe file, the Status cell reads
//     "valid" or "invalid" (an invalid row also shows its first error); the id is a link/button that opens a region named
//     "Recipe details" with the recipe as text;
//   * Queue tab: a table named "Queue" (Job, Recipe, State, Run, Stage, Shards); each queued or running row has a button named
//     "Cancel job <job id>";
//   * Runs tab: a table named "Runs" (Run, Recipe, State, Stages, Valid); the run id is a link/button that opens a region named
//     "Run details" containing a region "Manifest" (the manifest as text, stage ids included), a region "Artefacts" with one
//     element `[data-testid="artefact-<artefact id>"]` per artefact whose preview/link uses the artefact endpoint
//     (`/runs/<run id>/artefacts/<artefact id>`; a `<video>` for video/mp4), and a region "Telemetry" holding
//     `[data-testid="telemetry-chart"]` with a numeric attribute `data-points` that grows as telemetry events arrive over
//     `GET /runs/<run id>/events` (opened when the run is opened, closed when it is closed);
//   * New job tab: a form named "Run form" with a select "Recipe" (one option per VALID recipe id), a text input "Profile"
//     (default `test-profile` is NOT assumed: the test types it), a group "Stages" with one checkbox per stage key of the chosen
//     recipe (label = `id` or `id@variant`), checkboxes "Force" and "Rerun check", and a button "Queue job" that sends exactly one
//     `POST /jobs` with the job request ({recipe, profile, stages?, force?, rerun_check?}) and then shows role="status" text
//     containing the new job id; the new job appears in the Queue table.
// The fixture console is started by `tests/support/console_fixture_server.py` (see that file for the fixture data).
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

export const RUN_ID = "20261007T120000Z-pub-case";
export const BROKEN_RUN_ID = "20261008T090000Z-broken-manifest";
export const OTHER_RUN_ID = "20261009T090000Z-other";
export const CLIP_BYTES = 300000;
export const MARKUP = [
  "<img src=x onerror=window.__pwned=1>",
  "<script>window.__pwned=1</script>",
  '"><svg onload=window.__pwned=1>',
  '<a href="javascript:window.__pwned=1">click</a>',
];

export type Panel = "Recipes" | "Queue" | "Runs" | "New job";
export const PANELS: Panel[] = ["Recipes", "Queue", "Runs", "New job"];

/** Collects every request URL and every uncaught page error and dialog of a page. */
export function monitor(page: Page): {
  requests: () => string[];
  errors: () => string[];
  dialogs: () => string[];
  consoleErrors: () => string[];
} {
  const requests: string[] = [];
  const errors: string[] = [];
  const dialogs: string[] = [];
  const consoleErrors: string[] = [];
  page.context().on("request", (r) => requests.push(`${r.method()} ${r.url()}`));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("dialog", (d) => {
    dialogs.push(d.message());
    void d.dismiss();
  });
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  return {
    requests: () => [...requests],
    errors: () => [...errors],
    dialogs: () => [...dialogs],
    consoleErrors: () => [...consoleErrors],
  };
}

export async function prefs(page: Page, theme: "light" | "dark", lang: "en" | "es"): Promise<void> {
  await page.context().addInitScript(
    ([t, l]) => {
      try {
        localStorage.setItem("fsl:theme", t as string);
        localStorage.setItem("fsl:lang", l as string);
      } catch {
        /* storage blocked */
      }
    },
    [theme, lang],
  );
}

/** Opens the console UI and waits for its first heading. */
export async function openConsole(page: Page, search = ""): Promise<void> {
  await page.goto(search);
  await expect(page.locator("main h1")).toBeVisible();
}

export async function openPanel(page: Page, panel: Panel): Promise<void> {
  const tab = page
    .getByRole("tablist", { name: "Console sections" })
    .getByRole("tab", { name: panel, exact: true });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}

export async function openRun(page: Page, runId: string): Promise<void> {
  await openPanel(page, "Runs");
  await page
    .getByRole("table", { name: "Runs" })
    .getByRole("link", { name: runId })
    .or(page.getByRole("table", { name: "Runs" }).getByRole("button", { name: runId }))
    .first()
    .click();
  await expect(page.getByRole("region", { name: "Run details" })).toBeVisible();
}

export function apiUrl(baseURL: string | undefined, path: string): string {
  return new URL(path, baseURL ?? "http://127.0.0.1:4180/ui/").toString();
}

export async function axeBlocking(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.length}`);
}
