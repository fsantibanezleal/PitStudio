// T-019-036 [red] · FR-019-44 (the "connect to my local studio" control: exactly one GET http://127.0.0.1:<port>/health per press, credentials omitted, 3 s timeout, "connected — console <version>" only for a JSON body with
// status ok and a semantic console_version, otherwise "not connected", nothing else changed and no further request until the next press) and FR-019-45 (an invalid port makes no request and shows an inline message), FR-000-11.
// Unit half: web/src/studio/connect.test.ts.
//
// Stub servers listen on 127.0.0.1 on an ephemeral port inside the test process and answer one of: ok JSON, an HTML page, an 8 MB body, a wrong status, a bad version, nothing at all (hang). Each records every request it gets.
// Hooks (unit half): input[data-testid="connect-port"], button[data-testid="connect-button"], [data-testid="connect-label"], [data-testid="connect-error"]; the control is on every /studio page.
// Oracles: the EARS text; request counts at the stub; the 3 s timeout of `console.optin_timeout_s`; HTTP semantics (a request with credentials omitted carries no Cookie header).
import { createServer, type IncomingMessage, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

type Behaviour = "ok" | "html" | "oversized" | "wrong-status" | "bad-version" | "hang" | "status-500";
interface Seen {
  method?: string;
  url?: string;
  headers: IncomingMessage["headers"];
}
interface Stub {
  port: number;
  requests: Seen[];
  close: () => Promise<void>;
}

async function stub(behaviour: Behaviour): Promise<Stub> {
  const requests: Seen[] = [];
  const server: Server = createServer((req, res) => {
    requests.push({ method: req.method, url: req.url, headers: req.headers });
    const cors = { "access-control-allow-origin": "*", "cache-control": "no-store" };
    if (behaviour === "hang") return; // never answers
    if (behaviour === "html") {
      res.writeHead(200, { ...cors, "content-type": "text/html" });
      return res.end("<!doctype html><title>not a console</title>");
    }
    if (behaviour === "oversized") {
      res.writeHead(200, { ...cors, "content-type": "application/json" });
      res.write('{"status":"ok","console_version":"1.2.3","pad":"');
      const chunk = "x".repeat(65_536);
      let sent = 0;
      const pump = () => {
        while (sent < 8_000_000) {
          sent += chunk.length;
          if (!res.write(chunk)) return void res.once("drain", pump);
        }
        res.end('"}');
      };
      return pump();
    }
    const body =
      behaviour === "wrong-status"
        ? { status: "starting", console_version: "1.2.3" }
        : behaviour === "bad-version"
          ? { status: "ok", console_version: "1.2" }
          : { status: "ok", console_version: "1.2.3" };
    res.writeHead(behaviour === "status-500" ? 500 : 200, { ...cors, "content-type": "application/json" });
    res.end(JSON.stringify(body));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    port,
    requests,
    close: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}

async function freePort(): Promise<number> {
  const s = await stub("ok");
  await s.close();
  return s.port;
}

const label = (page: Page) => page.getByTestId("connect-label");
async function press(page: Page, port: string | number): Promise<void> {
  await page.getByTestId("connect-port").fill(String(port));
  await page.getByTestId("connect-button").click();
}

test.describe("the control is on the studio pages (FR-019-44)", () => {
  for (const route of ["studio/", "studio/tools/warp/", "studio/runs/", "studio/gpu/"]) {
    test(`FR-019-44 · /${route} has the port field and the button, and no request is made by loading it`, async ({
      page,
    }) => {
      const local: string[] = [];
      page.on("request", (r) => {
        if (/127\.0\.0\.1/.test(r.url())) local.push(r.url());
      });
      await open(page, route);
      await expect(page.getByTestId("connect-port")).toBeVisible();
      await expect(page.getByTestId("connect-button")).toBeVisible();
      await expect(page.getByTestId("connect-port")).toHaveAccessibleName(/\S/);
      await page.waitForTimeout(500);
      expect(local).toEqual([]);
    });
  }
});

test.describe("a press (FR-019-44)", () => {
  test("FR-019-44 · a console that answers: one GET /health, no cookie, 'connected — console 1.2.3', and no further request", async ({
    page,
    context,
  }) => {
    const s = await stub("ok");
    try {
      await context.addCookies([{ name: "session", value: "secret", url: `http://127.0.0.1:${s.port}` }]);
      await open(page, "studio/");
      await press(page, s.port);
      await expect(label(page)).toHaveText("connected — console 1.2.3", { timeout: 10_000 });
      await page.waitForTimeout(1500);
      expect(s.requests).toHaveLength(1);
      expect(s.requests[0]?.method).toBe("GET");
      expect(s.requests[0]?.url).toBe("/health");
      expect(s.requests[0]?.headers.host).toBe(`127.0.0.1:${s.port}`);
      expect(s.requests[0]?.headers.cookie).toBeUndefined();
      expect(s.requests[0]?.headers.authorization).toBeUndefined();
    } finally {
      await s.close();
    }
  });

  test("FR-019-44 · each press is one request: a second press makes a second one", async ({ page }) => {
    const s = await stub("ok");
    try {
      await open(page, "studio/");
      await press(page, s.port);
      await expect(label(page)).toHaveText(/connected/, { timeout: 10_000 });
      await page.getByTestId("connect-button").click();
      await expect.poll(() => s.requests.length, { timeout: 10_000 }).toBe(2);
      await page.waitForTimeout(1000);
      expect(s.requests).toHaveLength(2);
    } finally {
      await s.close();
    }
  });

  for (const behaviour of ["html", "wrong-status", "bad-version", "status-500"] as const) {
    test(`FR-019-44 · a console that answers ${behaviour}: 'not connected'`, async ({ page }) => {
      const s = await stub(behaviour);
      try {
        await open(page, "studio/");
        await press(page, s.port);
        await expect(label(page)).toHaveText("not connected", { timeout: 10_000 });
        expect(s.requests).toHaveLength(1);
      } finally {
        await s.close();
      }
    });
  }

  test("FR-019-44 · an 8 MB body is not accepted: 'not connected'", async ({ page }) => {
    const s = await stub("oversized");
    try {
      await open(page, "studio/");
      await press(page, s.port);
      await expect(label(page)).toHaveText("not connected", { timeout: 15_000 });
      expect(s.requests).toHaveLength(1);
    } finally {
      await s.close();
    }
  });

  test("FR-019-44 · a console that never answers is given up after about 3 s: 'not connected', still one request", async ({
    page,
  }) => {
    const s = await stub("hang");
    try {
      await open(page, "studio/");
      const t0 = Date.now();
      await press(page, s.port);
      await expect(label(page)).toHaveText("not connected", { timeout: 10_000 });
      const took = Date.now() - t0;
      expect(took).toBeGreaterThanOrEqual(2500);
      expect(took).toBeLessThan(6000);
      await page.waitForTimeout(1000);
      expect(s.requests).toHaveLength(1);
    } finally {
      await s.close();
    }
  });

  test("FR-019-44 · a refused connection reads 'not connected' and the page shows no uncaught error", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await open(page, "studio/");
    await press(page, await freePort());
    await expect(label(page)).toHaveText("not connected", { timeout: 10_000 });
    expect(errors).toEqual([]);
  });

  test("FR-019-44 · a request blocked by the browser or an extension reads 'not connected'", async ({
    page,
  }) => {
    const s = await stub("ok");
    try {
      await page.route(/127\.0\.0\.1/, (route) => route.abort("blockedbyclient"));
      await open(page, "studio/");
      await press(page, s.port);
      await expect(label(page)).toHaveText("not connected", { timeout: 10_000 });
      expect(s.requests).toHaveLength(0);
    } finally {
      await s.close();
    }
  });

  test("FR-019-44 · a failed attempt changes nothing else on the page", async ({ page }) => {
    await open(page, "studio/");
    const before = await page.locator("main").evaluate((m) => {
      const clone = m.cloneNode(true) as HTMLElement;
      for (const el of clone.querySelectorAll('[data-testid="connect-label"], [data-testid="connect-port"]'))
        el.remove();
      return clone.innerHTML;
    });
    await press(page, await freePort());
    await expect(label(page)).toHaveText("not connected", { timeout: 10_000 });
    const after = await page.locator("main").evaluate((m) => {
      const clone = m.cloneNode(true) as HTMLElement;
      for (const el of clone.querySelectorAll('[data-testid="connect-label"], [data-testid="connect-port"]'))
        el.remove();
      return clone.innerHTML;
    });
    expect(after).toBe(before);
  });
});

test.describe("an invalid port (FR-019-45)", () => {
  test("FR-019-45 · abc, 80, 65536, <port>/x, <port>@host, ' <port>' and an empty field: no request at all and an inline message", async ({
    page,
  }) => {
    const s = await stub("ok");
    try {
      const local: string[] = [];
      page.on("request", (r) => {
        if (
          /127\.0\.0\.1|localhost:\d+/.test(r.url()) &&
          !r.url().startsWith(page.url().split("/").slice(0, 3).join("/"))
        )
          local.push(r.url());
      });
      await open(page, "studio/");
      for (const text of [
        "",
        "abc",
        "80",
        "1023",
        "65536",
        `${s.port}/x`,
        `${s.port}@host`,
        ` ${s.port}`,
        `${s.port} `,
        "-1",
        "1e4",
      ]) {
        await page.getByTestId("connect-port").fill(text);
        await page.getByTestId("connect-button").click();
        await expect(page.getByTestId("connect-error"), JSON.stringify(text)).toBeVisible();
        await expect(page.getByTestId("connect-error")).toContainText(/1024/);
        await expect(page.getByTestId("connect-error")).toContainText(/65535/);
      }
      await page.waitForTimeout(500);
      expect(s.requests).toHaveLength(0);
      expect(local).toEqual([]);
    } finally {
      await s.close();
    }
  });

  test("FR-019-45 · the message goes away when the port is corrected and a press then connects", async ({
    page,
  }) => {
    const s = await stub("ok");
    try {
      await open(page, "studio/");
      await press(page, "80");
      await expect(page.getByTestId("connect-error")).toBeVisible();
      await press(page, s.port);
      await expect(page.getByTestId("connect-error")).toHaveCount(0);
      await expect(label(page)).toHaveText("connected — console 1.2.3", { timeout: 10_000 });
    } finally {
      await s.close();
    }
  });
});
