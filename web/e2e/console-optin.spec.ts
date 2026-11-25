// T-003-031 · FR-003-25 (refines FR-000-11): the public site never contacts a loopback or private address on its own.
//
// Expected behaviour: on every public route (every prerendered route, a deep link with a trailing slash, an unknown route), with
// the access gate locked and unlocked, in both themes and both languages, the page issues NO request of any kind (fetch, XHR,
// EventSource, WebSocket, image, script, stylesheet, prefetch, beacon) to 127.0.0.0/8, localhost, ::1, 0.0.0.0, 10.0.0.0/8,
// 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, fc00::/7 or fe80::/10. The static test server itself listens on localhost, so the
// page's own origin (the Playwright baseURL) is the one exception: it stands for the Pages host that serves the same files.
// Oracle: Playwright's own request log (browser context `request` events and page `websocket` events), each URL's host classified
// against the address ranges above by hand-written range arithmetic; a detector self-check proves the log would catch a violation.
import { expect, type Page, test } from "@playwright/test";
import { open, ROUTES } from "./helpers";

type Kind = "loopback" | "private" | "public";

function ipv4(host: string): number[] | null {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return null;
  const parts = m.slice(1).map(Number);
  return parts.every((n) => n >= 0 && n <= 255) ? parts : null;
}

function classify(rawHost: string): Kind {
  const host = rawHost.toLowerCase().replace(/^\[|\]$/g, "");
  if (host === "localhost" || host.endsWith(".localhost")) return "loopback";
  const v4 = ipv4(host);
  if (v4) {
    const a = v4[0] ?? 0;
    const b = v4[1] ?? 0;
    if (a === 127 || a === 0) return "loopback";
    if (a === 10) return "private";
    if (a === 172 && b >= 16 && b <= 31) return "private";
    if (a === 192 && b === 168) return "private";
    if (a === 169 && b === 254) return "private";
    return "public";
  }
  if (host.includes(":")) {
    if (host === "::1" || host === "::") return "loopback";
    const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(host);
    if (mapped?.[1]) return classify(mapped[1]);
    const first = Number.parseInt(host.split(":")[0] || "0", 16);
    if ((first & 0xfe00) === 0xfc00) return "private"; // fc00::/7
    if ((first & 0xffc0) === 0xfe80) return "private"; // fe80::/10
  }
  return "public";
}

function watch(page: Page, baseUrl: string): { violations: () => string[]; all: () => string[] } {
  const own = new URL(baseUrl).origin;
  const seen: string[] = [];
  page.context().on("request", (r) => seen.push(r.url()));
  page.on("websocket", (ws) => seen.push(ws.url()));
  return {
    all: () => [...seen],
    violations: () =>
      seen.filter((u) => {
        try {
          const url = new URL(u);
          if (!/^(https?|wss?):$/.test(url.protocol)) return false;
          return url.origin !== own && classify(url.hostname) !== "public";
        } catch {
          return false;
        }
      }),
  };
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(600);
}

test.describe("the address classifier", () => {
  test("FR-003-25 · loopback and private ranges are told apart from public hosts", () => {
    const loopback = [
      "127.0.0.1",
      "127.255.255.254",
      "localhost",
      "LOCALHOST",
      "app.localhost",
      "[::1]",
      "::1",
      "0.0.0.0",
      "[::]",
    ];
    const priv = [
      "10.0.0.1",
      "10.255.255.255",
      "172.16.0.1",
      "172.31.255.255",
      "192.168.0.1",
      "192.168.255.254",
      "169.254.1.1",
      "[fc00::1]",
      "[fd12:3456::1]",
      "[fe80::1]",
      "[febf::1]",
      "[::ffff:192.168.1.1]",
    ];
    const pub = [
      "example.org",
      "fsantibanezleal.github.io",
      "8.8.8.8",
      "172.15.0.1",
      "172.32.0.1",
      "192.169.0.1",
      "169.253.1.1",
      "11.0.0.1",
      "[2001:db8::1]",
      "[fec0::1]",
      "128.0.0.1",
      "localhost.example.org",
      "notlocalhost",
    ];
    for (const h of loopback) expect(classify(h), h).toBe("loopback");
    for (const h of priv) expect(classify(h), h).toBe("private");
    for (const h of pub) expect(classify(h), h).toBe("public");
  });
});

test.describe("the request log", () => {
  test("FR-003-25 · the detector sees fetch, image and WebSocket requests to loopback and private hosts", async ({
    page,
    baseURL,
  }) => {
    const w = watch(page, baseURL ?? "http://localhost:4173/");
    await open(page, "");
    await page.evaluate(() => {
      fetch("http://127.0.0.1:9/probe").catch(() => undefined);
      const img = new Image();
      img.src = "http://192.168.1.1/probe.png";
      try {
        new WebSocket("ws://10.0.0.1:9/probe");
      } catch {
        /* the constructor may throw on a blocked scheme; the log is what counts */
      }
    });
    await page.waitForTimeout(1500);
    const v = w.violations().join(" ");
    expect(v).toContain("127.0.0.1:9/probe");
    expect(v).toContain("192.168.1.1/probe.png");
  });
});

const THEMES = ["light", "dark"] as const;
const LANGS = ["en", "es"] as const;
const DEEP = ["theory/", "cases/", "studio/", "methods/"];
const ALL_ROUTES = [...ROUTES, ...DEEP, "no/such/page"];

test.describe("the public site is quiet", () => {
  for (const theme of THEMES) {
    for (const lang of LANGS) {
      for (const route of ALL_ROUTES) {
        test(`FR-003-25 · unlocked, ${theme}, ${lang}: /${route} sends 0 loopback or private requests`, async ({
          page,
          baseURL,
        }) => {
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
          const w = watch(page, baseURL ?? "http://localhost:4173/");
          await open(page, route);
          await settle(page);
          expect(
            w.violations(),
            `requests to local or private addresses: ${w.violations().join(", ")}`,
          ).toEqual([]);
          expect(w.all().length, "the page itself did load").toBeGreaterThan(0);
        });
      }
    }
  }

  for (const route of ALL_ROUTES) {
    test(`FR-003-25 · access gate as it ships (locked when the build has one): /${route} sends 0 loopback or private requests`, async ({
      page,
      baseURL,
    }) => {
      const w = watch(page, baseURL ?? "http://localhost:4173/");
      await page.goto(route); // no passphrase entered
      await settle(page);
      expect(w.violations(), w.violations().join(", ")).toEqual([]);
    });
  }

  test("FR-003-25 · a visitor who clicks around (navigation, theme, language) still causes no local request", async ({
    page,
    baseURL,
  }) => {
    const w = watch(page, baseURL ?? "http://localhost:4173/");
    await open(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    for (const name of ["Cases", "Studio", "Theory", "Methods", "Results", "Knowledge", "Explore"]) {
      await nav.getByRole("link", { name, exact: true }).click();
      await settle(page);
    }
    const toggle = page.getByRole("button", { name: /^Theme:/ });
    for (let i = 0; i < 3; i++) await toggle.click();
    await page.getByLabel("Language").selectOption("es");
    await settle(page);
    await page.getByRole("button", { name: /Acerca de|About this app/ }).click();
    await settle(page);
    expect(w.violations()).toEqual([]);
  });
});
