// T-018-036 [red] · FR-018-41 (a numeric control that receives an empty, non-numeric, NaN, infinite or out-of-range value keeps its last valid value, shows an inline
// message with the allowed range and unit and sends no engine request), FR-018-40 (a control that produced a request above the engine's size cap is already clamped to
// the cap with a visible note) and FR-018-42 (the URL parameters case, tab, t, tier, renderer and lang: unknown, malformed, non-finite, negative or longer than 2,000
// characters are ignored, `t` is clamped to [0, duration], no uncaught error, no resource requested from the value).
//
// Hooks (the engine panel contract of web/e2e/support/simulate.ts, plus two the test author adds, flagged in the report):
//   input[data-control="<name>"][data-min][data-max][data-unit]      numeric control; a control that sets a SIZE of an engine request also carries data-cap="<cap>"
//                                                                    (the size cap of spec 018 section 7.1; data-max equals it)
//   [data-testid="control-message"][data-control="<name>"]           inline message of a rejected value: the allowed range (min and max) and the unit
//   [data-testid="control-note"][data-control="<name>"]              visible note of a value clamped to the cap: names the cap
//   [data-testid="sim-clock"][data-t][data-duration]                  the page clock (T-018-041); `?t=` seeds it
//   [data-testid="case-rail"] li[data-case-id] button[aria-pressed]   case selection of `/` (T-018-021)
//   [data-testid="tier-badge"][data-tier]                             the tier in use
// Oracles: the EARS text; the numeric domain of each control as it declares it (data-min / data-max / data-cap are the oracle for the check of each value);
// the size caps of the engine table, section 7.1 (geotech slices 200 and 10^5 samples, plume grid 256, watershed 1024, volume grid 2048, mincut 10^5 blocks); hostile
// strings written below. The parity report served is the valid example of the spec with the analytical engines marked as passing, so the panels are LIVE.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Locator, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { enginePanel, openSimulate } from "./support/simulate";
import { type FixtureVideo, makeFixtureVideo, routeVideo, stubCapabilities } from "./support/video-fixture";

const REPORT = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../specs/018-web-cases/contracts/examples/parity-report.valid.json",
);
const LIVE_ENGINES = ["blasting", "geotech", "mincut", "des", "plume", "watershed", "volume"];

/** The valid example report with every analytical engine used below marked as passing (a hand-built fixture). */
function parityBody(): string {
  const report = JSON.parse(readFileSync(REPORT, "utf8")) as { engines: Array<Record<string, unknown>> };
  const template = report.engines.find((e) => e.engine === "blasting") as Record<string, unknown>;
  const kept = report.engines.filter(
    (e) => !LIVE_ENGINES.includes(e.engine as string) || e.verdict === "pass",
  );
  const present = new Set(kept.map((e) => e.engine));
  for (const id of LIVE_ENGINES) if (!present.has(id)) kept.push({ ...template, engine: id });
  return JSON.stringify({ ...report, engines: kept });
}

async function serveParity(page: Page): Promise<void> {
  const body = parityBody();
  await page.route("**/assets/parity-report.json", (route) =>
    route.fulfill({ contentType: "application/json", body }),
  );
}

interface Control {
  name: string;
  min: number;
  max: number;
  unit: string;
  cap: number | null;
  value: number;
}

async function controlsOf(panel: Locator): Promise<Control[]> {
  return panel.locator("input[data-control]").evaluateAll((els) =>
    els.map((el) => {
      const e = el as HTMLInputElement;
      const cap = e.getAttribute("data-cap");
      return {
        name: e.getAttribute("data-control") ?? "",
        min: Number(e.getAttribute("data-min")),
        max: Number(e.getAttribute("data-max")),
        unit: e.getAttribute("data-unit") ?? "",
        cap: cap === null ? null : Number(cap),
        value: Number(e.value),
      };
    }),
  );
}

/** Puts `text` into a control the way a paste does (native setter, input and change events), then commits with Enter. */
async function enter(input: Locator, text: string): Promise<void> {
  await input.evaluate((el, v) => {
    const e = el as HTMLInputElement;
    e.focus();
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(e, v);
    e.dispatchEvent(new Event("input", { bubbles: true }));
    e.dispatchEvent(new Event("change", { bubbles: true }));
  }, text);
  await input.press("Enter");
}

/** Numbers written in a message, with the thousands separators of any locale removed. */
function numbersIn(text: string): number[] {
  const flat = text.replace(/−/g, "-").replace(/(\d)[,   ](?=\d{3}(?!\d))/g, "$1");
  return [...flat.matchAll(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi)].map((m) => Number(m[0]));
}

const NON_NUMERIC = [
  "",
  " ",
  "abc",
  "NaN",
  "Infinity",
  "-Infinity",
  "1e999",
  "-1e999",
  "--5",
  "1,5.5",
  "0x10",
  "1e",
  ".",
  "٣", // Arabic-Indic digit three
  "５", // fullwidth digit five
  "<script>alert(1)</script>",
  "'; DROP TABLE x;--",
  "9".repeat(400),
  "\u0000",
  "\u202e12",
];

async function waitDone(panel: Locator): Promise<void> {
  await expect(panel).toHaveAttribute("data-state", /^(done|replay)$/, { timeout: 90_000 });
}

/** One TypeScript engine per case whose panel runs LIVE on tier T2 with the served parity report. */
const PANELS: Array<[string, string]> = [
  ["A1", "des"],
  ["C1", "geotech"],
  ["D1", "blasting"],
  ["E1", "mincut"],
];

test.describe("hostile numeric controls (FR-018-41)", () => {
  for (const [caseId, engine] of PANELS) {
    test(`FR-018-41 · ${caseId}/${engine}: an empty, non-numeric, NaN or infinite value keeps the last valid value, shows the range and unit, and sends no request`, async ({
      page,
    }) => {
      test.setTimeout(240_000);
      await serveParity(page);
      await openSimulate(page, caseId, "&tier=t2");
      const panel = enginePanel(page, engine);
      await waitDone(panel);
      const controls = await controlsOf(panel);
      expect(controls.length, `${engine} has numeric controls`).toBeGreaterThan(0);
      for (const ctl of controls) {
        const input = panel.locator(`input[data-control="${ctl.name}"]`);
        const message = panel.locator(`[data-testid="control-message"][data-control="${ctl.name}"]`);
        await expect(message, `${ctl.name} starts without a message`).toHaveCount(0);
        for (const text of NON_NUMERIC) {
          const label = `${engine}.${ctl.name} <- ${JSON.stringify(text.slice(0, 12))}`;
          const before = Number(await panel.getAttribute("data-requests"));
          await enter(input, text);
          await expect(message.first(), label).toBeVisible();
          const shown = await input.inputValue();
          expect(shown, `${label}: the control shows a number again`).not.toBe("");
          expect(Number(shown), `${label}: last valid value kept`).toBe(ctl.value);
          const said = (await message.first().textContent()) ?? "";
          expect(numbersIn(said), `${label}: the message gives the allowed range`).toEqual(
            expect.arrayContaining([ctl.min, ctl.max]),
          );
          expect(said, `${label}: the message gives the unit`).toContain(ctl.unit);
          await page.waitForTimeout(150);
          expect(Number(await panel.getAttribute("data-requests")), `${label}: no engine request`).toBe(
            before,
          );
        }
      }
    });

    test(`FR-018-41 · ${caseId}/${engine}: a value below the minimum or above the maximum is rejected the same way, and the bounds themselves are accepted`, async ({
      page,
    }) => {
      test.setTimeout(240_000);
      await serveParity(page);
      await openSimulate(page, caseId, "&tier=t2");
      const panel = enginePanel(page, engine);
      await waitDone(panel);
      const controls = await controlsOf(panel);
      expect(controls.length).toBeGreaterThan(0);
      for (const ctl of controls) {
        const input = panel.locator(`input[data-control="${ctl.name}"]`);
        const message = panel.locator(`[data-testid="control-message"][data-control="${ctl.name}"]`);
        const tooLow = [ctl.min - Math.max(1, Math.abs(ctl.min)) * 0.01, "-1e308"];
        // a size control clamps to its cap instead (FR-018-40, next block), so only the others are checked above the maximum
        const tooHigh = ctl.cap === null ? [ctl.max + Math.max(1, Math.abs(ctl.max)) * 0.01, "1e308"] : [];
        for (const raw of [...tooLow, ...tooHigh]) {
          const text = String(raw);
          const label = `${engine}.${ctl.name} <- ${text}`;
          const before = Number(await panel.getAttribute("data-requests"));
          await enter(input, text);
          await expect(message.first(), label).toBeVisible();
          expect(Number(await input.inputValue()), `${label}: last valid value kept`).toBe(ctl.value);
          expect(numbersIn((await message.first().textContent()) ?? ""), label).toEqual(
            expect.arrayContaining([ctl.min, ctl.max]),
          );
          await page.waitForTimeout(150);
          expect(Number(await panel.getAttribute("data-requests")), `${label}: no engine request`).toBe(
            before,
          );
        }
      }
      // the lower bound of the first control is a valid value: it is accepted, the message goes away and exactly one request is sent
      const first = controls[0] as Control;
      const input = panel.locator(`input[data-control="${first.name}"]`);
      const before = Number(await panel.getAttribute("data-requests"));
      await enter(input, String(first.min));
      await expect
        .poll(async () => Number(await panel.getAttribute("data-requests")), { timeout: 30_000 })
        .toBeGreaterThan(before);
      await expect(
        panel.locator(`[data-testid="control-message"][data-control="${first.name}"]`),
      ).toHaveCount(0);
      expect(Number(await input.inputValue())).toBe(first.min);
    });
  }

  test("FR-018-41 · after a rejected value a valid one is accepted: the message disappears and the engine runs again", async ({
    page,
  }) => {
    await serveParity(page);
    await openSimulate(page, "D1", "&tier=t2");
    const panel = enginePanel(page, "blasting");
    await waitDone(panel);
    const ctl = (await controlsOf(panel))[0] as Control;
    const input = panel.locator(`input[data-control="${ctl.name}"]`);
    const message = panel.locator(`[data-testid="control-message"][data-control="${ctl.name}"]`);
    await enter(input, "NaN");
    await expect(message.first()).toBeVisible();
    const before = Number(await panel.getAttribute("data-requests"));
    const mid = ctl.min + (ctl.max - ctl.min) * 0.5;
    await enter(input, String(Math.abs(mid - ctl.value) > 1e-9 ? mid : ctl.min + (ctl.max - ctl.min) * 0.25));
    await expect(message).toHaveCount(0);
    await expect
      .poll(async () => Number(await panel.getAttribute("data-requests")), { timeout: 30_000 })
      .toBe(before + 1);
  });
});

test.describe("size caps (FR-018-40)", () => {
  /** Engines of the table of section 7.1 whose cap is a number a control sets. */
  const CAPPED: Array<[string, string, number[]]> = [
    ["C1", "geotech", [200, 100_000]],
    ["C3", "plume", [256]],
    ["D1", "watershed", [1024]],
    ["E2", "volume", [2048]],
    ["E1", "mincut", [100_000]],
  ];
  for (const [caseId, engine, caps] of CAPPED) {
    test(`FR-018-40 · ${caseId}/${engine}: a size above the cap is clamped to the cap with a visible note, and the engine does not answer E_SIZE`, async ({
      page,
    }) => {
      test.setTimeout(300_000);
      await serveParity(page);
      await openSimulate(page, caseId, "&tier=t2");
      const panel = enginePanel(page, engine);
      await waitDone(panel);
      const sized = (await controlsOf(panel)).filter((c) => c.cap !== null);
      expect(sized.length, `${engine} has a size control`).toBeGreaterThan(0);
      expect(sized.map((c) => c.cap as number).sort((a, b) => a - b)).toEqual(
        expect.arrayContaining([caps[0] as number]),
      );
      for (const ctl of sized) {
        const cap = ctl.cap as number;
        expect(caps, `${ctl.name}: the declared cap is one of section 7.1`).toContain(cap);
        expect(ctl.max, `${ctl.name}: the control's maximum is the cap`).toBe(cap);
        const input = panel.locator(`input[data-control="${ctl.name}"]`);
        for (const raw of [cap + 1, cap * 10, 1e12]) {
          await enter(input, String(raw));
          await expect
            .poll(async () => Number(await input.inputValue()), {
              message: `${ctl.name} <- ${raw}`,
              timeout: 10_000,
            })
            .toBe(cap);
          const note = panel.locator(`[data-testid="control-note"][data-control="${ctl.name}"]`);
          await expect(note.first()).toBeVisible();
          expect(numbersIn((await note.first().textContent()) ?? "")).toContain(cap);
          await waitDone(panel);
          await expect(panel).not.toHaveAttribute("data-state", "error");
          await expect(panel.getByTestId("engine-notice")).not.toContainText(/E_SIZE/);
        }
      }
    });
  }
});

// FR-018-42 -----------------------------------------------------------------------------------------------------------------------------------------------------
const SENTINEL = "zq9f2c";
const HOSTILE_VALUES: Array<[string, string]> = [
  ["unknown", `${SENTINEL}-unknown`],
  ["path traversal", `..%2F..%2F${SENTINEL}`],
  ["absolute url", `https%3A%2F%2Fevil.example%2F${SENTINEL}`],
  ["malformed percent escape", `%E0%A4%A${SENTINEL}`],
  ["null byte", `%00${SENTINEL}`],
  ["right-to-left override", `%E2%80%AE${SENTINEL}`],
  ["markup", `%3Cscript%3Ealert(1)%3C%2Fscript%3E${SENTINEL}`],
  ["longer than 2,000 characters", `${SENTINEL}${"a".repeat(2100)}`],
];

interface Watch {
  errors: string[];
  derived: (needles: RegExp) => string[];
}

function watch(page: Page): Watch {
  const errors: string[] = [];
  const urls: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (!r.isNavigationRequest()) urls.push(r.url());
  });
  return { errors, derived: (needles) => urls.filter((u) => needles.test(safeDecode(u))) };
}

function safeDecode(s: string): string {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

const NEEDLE = new RegExp(`${SENTINEL}|evil\\.example|a{100}`);

test.describe("hostile URL parameters (FR-018-42)", () => {
  for (const param of ["case", "tab", "tier", "renderer", "lang"]) {
    for (const [what, value] of HOSTILE_VALUES) {
      test(`FR-018-42 · ?${param}= ${what}: ignored, the page renders, no uncaught error, no resource requested from the value`, async ({
        page,
      }) => {
        const seen = watch(page);
        await open(page, `?${param}=${value}`);
        await expect(page.locator("main h1")).toBeVisible();
        await expect(page.getByTestId("case-rail")).toBeVisible();
        // ignored means the page is what it is without the parameter
        await expect(page.getByTestId("case-rail").getByRole("button", { pressed: true })).toHaveCount(0);
        await expect(page.locator("html")).toHaveAttribute("lang", /^(en|es)$/);
        await expect(page.getByTestId("tier-badge")).toHaveAttribute("data-tier", /^(t0|t1|t2)$/);
        await page.waitForTimeout(500);
        expect(seen.errors).toEqual([]);
        expect(seen.derived(NEEDLE)).toEqual([]);
      });
    }
  }

  test("FR-018-42 · a case page with a hostile tab shows its first tab and is usable", async ({ page }) => {
    for (const [, value] of HOSTILE_VALUES) {
      const seen = watch(page);
      await open(page, `cases/A1/?tab=${value}&tier=${value}&renderer=${value}&lang=${value}`);
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.getByRole("tab", { selected: true })).toHaveCount(1);
      await expect(page.getByRole("tab").first()).toHaveAttribute("aria-selected", "true");
      await page.waitForTimeout(300);
      expect(seen.errors).toEqual([]);
      expect(seen.derived(NEEDLE)).toEqual([]);
    }
  });

  test("FR-018-42 · a known id with more than 2,000 characters around it is still unknown: nothing is selected", async ({
    page,
  }) => {
    await open(page, `?case=A1${"%20".repeat(1100)}`);
    await expect(page.getByTestId("case-rail")).toBeVisible();
    await expect(page.getByTestId("case-rail").getByRole("button", { pressed: true })).toHaveCount(0);
    await open(page, "?case=A1");
    await expect(page.getByTestId("kpi-panel")).toHaveAttribute("data-case", "A1");
  });

  test("FR-018-42 · tier: a forced tier is honoured (control), an unknown one gives the probed tier", async ({
    page,
  }) => {
    await open(page, "");
    const probed = (await page.getByTestId("tier-badge").getAttribute("data-tier")) as string;
    await open(page, "?tier=t0");
    await expect(page.getByTestId("tier-badge")).toHaveAttribute("data-tier", "t0");
    for (const value of ["t9", "T-1", "NaN", "t1".repeat(1100), "%E2%80%AEt0"]) {
      await open(page, `?tier=${value}`);
      await expect(page.getByTestId("tier-badge")).toHaveAttribute("data-tier", probed);
    }
  });

  test("FR-018-42 · lang: a known language is honoured (control), an unknown one keeps the default", async ({
    page,
  }) => {
    await open(page, "?lang=es");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await open(page, "?lang=en");
    for (const value of [
      "xx",
      "e",
      "ES-es-valid-but-not-supported",
      "en".repeat(1100),
      "%E2%80%AEes",
      "NaN",
    ]) {
      await open(page, `?lang=${value}`);
      await expect(page.locator("html")).toHaveAttribute("lang", "en");
    }
  });
});

test.describe("the time parameter t (FR-018-42)", () => {
  let video: FixtureVideo;
  test.beforeAll(async ({ browser }) => {
    video = await makeFixtureVideo(browser);
  });

  const SUPPORTED = { supported: true, smooth: true, powerEfficient: true };
  const clock = (page: Page) =>
    page.evaluate(() => {
      const el = document.querySelector('[data-testid="sim-clock"]') as HTMLElement;
      return {
        t: Number(el.dataset.t),
        duration: Number(el.dataset.duration),
        playing: el.dataset.playing === "true",
      };
    });

  async function openAt(page: Page, t: string): Promise<Watch> {
    const seen = watch(page);
    await stubCapabilities(page, { av1: SUPPORTED, h264: SUPPORTED });
    await routeVideo(page, video);
    await open(page, `cases/C2/?tab=replay&t=${t}`);
    await expect(page.getByTestId("sim-clock")).toBeVisible();
    return seen;
  }

  test("FR-018-42 · a valid t seeds the clock paused (control)", async ({ page }) => {
    await openAt(page, "0.5");
    const state = await clock(page);
    expect(state.duration).toBeGreaterThan(0.5);
    expect(state.t).toBeCloseTo(0.5, 6);
    expect(state.playing).toBe(false);
  });

  test("FR-018-42 · t above the duration is clamped to the duration", async ({ page }) => {
    await openAt(page, "1000000000");
    const state = await clock(page);
    expect(state.t).toBe(state.duration);
  });

  for (const [what, value] of [
    ["negative", "-5"],
    ["minus zero point five", "-0.5"],
    ["negative infinity", "-Infinity"],
  ] as Array<[string, string]>) {
    test(`FR-018-42 · t ${what} is ignored: the clock stays at 0`, async ({ page }) => {
      const seen = await openAt(page, value);
      expect((await clock(page)).t).toBe(0);
      expect(seen.errors).toEqual([]);
    });
  }

  for (const [what, value] of [
    ["not a number", "abc"],
    ["NaN", "NaN"],
    ["Infinity", "Infinity"],
    ["1e999", "1e999"],
    ["hexadecimal", "0x10"],
    ["empty", ""],
    ["markup", "%3Cscript%3E"],
    ["null byte", "%00"],
    ["fullwidth digit", "%EF%BC%95"],
  ] as Array<[string, string]>) {
    test(`FR-018-42 · t ${what} is ignored or clamped: the clock holds a finite time in [0, duration], and nothing else breaks`, async ({
      page,
    }) => {
      const seen = await openAt(page, value);
      const state = await clock(page);
      expect(Number.isFinite(state.t)).toBe(true);
      expect(state.t).toBeGreaterThanOrEqual(0);
      expect(state.t).toBeLessThanOrEqual(state.duration);
      expect(state.playing).toBe(false);
      expect(seen.errors).toEqual([]);
    });
  }

  test("FR-018-42 · a numerically valid t of more than 2,000 characters is ignored (it would read 0.5)", async ({
    page,
  }) => {
    const seen = await openAt(page, `0.5${"0".repeat(2100)}`);
    expect((await clock(page)).t).toBe(0);
    expect(seen.errors).toEqual([]);
    expect(seen.derived(/0{100}/)).toEqual([]);
  });

  test("FR-018-42 · no resource is requested from the value of t", async ({ page }) => {
    const seen = await openAt(page, "123456.789");
    await page.waitForTimeout(300);
    expect(seen.derived(/123456\.789/)).toEqual([]);
  });
});
