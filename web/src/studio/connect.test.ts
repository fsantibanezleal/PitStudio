// T-019-036 [red] · FR-019-45 (hostile): the port field of the "connect to my local studio" control accepts only a decimal integer in 1024..65535; anything else (abc, 80, 65536, 8765/x, 8765@host, " 8765") makes no
// request and shows an inline validation message. FR-019-44 (unit half): exactly one GET http://127.0.0.1:<port>/health per press, credentials "omit", a 3 s timeout, the labels "connected — console <version>" and "not connected".
// E2E half against stub servers: web/e2e/t_019_036_connect.spec.ts.
//
// Expected API:
//   `~/studio/connect` (web/src/studio/connect.ts):
//     validatePort(text: string): number | null        the integer when `text` is exactly 1 to 5 ASCII digits denoting 1024..65535 (no sign, space, separator, exponent, fraction, non-ASCII digit; a string of any length is judged
//                                                      without throwing), else null
//     connectLocal(port: number, options?: { fetchImpl?: typeof fetch; timeoutMs?: number }): Promise<{ connected: boolean; label: string; version?: string }>
//                                                      one `fetchImpl("http://127.0.0.1:<port>/health", { credentials: "omit", signal })` (GET), a timeout of `timeoutMs` (default 3000) that aborts it, and the label
//                                                      "connected — console <version>" only when the body is JSON with `status === "ok"` and `console_version` a string matching ^[0-9]+\.[0-9]+\.[0-9]+$, else "not connected";
//                                                      it never throws and never makes a second request.
//   `~/studio/ConnectControl` (web/src/studio/ConnectControl.tsx): named export ConnectControl({ fetchImpl?: typeof fetch; timeoutMs?: number }) rendering `input[data-testid="connect-port"]` (with a label), `button[data-testid="connect-button"]`,
//     `[data-testid="connect-error"]` (inline validation message, shown only for an invalid port, `role="alert"`) and `[data-testid="connect-label"]` (`aria-live="polite"`, the result label); Enter in the field presses the button;
//     nothing is requested on render or while typing.
// Oracles: the EARS text; the port range of the unprivileged ports (1024..65535); hand tables of hostile strings.
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { ConnectControl } from "~/studio/ConnectControl";
import { connectLocal, validatePort } from "~/studio/connect";
import { renderApp } from "~/test-support/render";

const ok = (body: unknown, init: ResponseInit = {}) =>
  new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
const spy = (impl: (url: string, init?: RequestInit) => Promise<Response>) =>
  vi.fn(impl as unknown as typeof fetch);

describe("validatePort (FR-019-45)", () => {
  for (const [text, port] of [
    ["1024", 1024],
    ["8765", 8765],
    ["49152", 49152],
    ["65535", 65535],
  ] as Array<[string, number]>) {
    it(`FR-019-45 · '${text}' is the port ${port}`, () => {
      expect(validatePort(text)).toBe(port);
    });
  }

  const hostile = [
    "",
    " ",
    "abc",
    "80",
    "1023",
    "0",
    "65536",
    "99999",
    "100000",
    "-8765",
    "+8765",
    "8765/x",
    "8765@host",
    " 8765",
    "8765 ",
    "8765\n",
    "\t8765",
    "8765.0",
    "8.765e3",
    "1e4",
    "0x2243",
    "8 765",
    "8,765",
    "8765,1",
    "NaN",
    "Infinity",
    "localhost:8765",
    "127.0.0.1:8765",
    "http://127.0.0.1:8765",
    "8765:8765",
    "8765;rm",
    "8765\u0000",
    "８７６５", // fullwidth digits
    "٨٧٦٥", // Arabic-Indic digits
    `${String.fromCharCode(0x202e)}8765`,
    "9".repeat(400),
    "1".repeat(100_000),
    "<script>alert(1)</script>",
    "8765%00",
    "constructor",
    "__proto__",
  ];
  for (const text of hostile) {
    it(`FR-019-45 · ${JSON.stringify(text.length > 24 ? `${text.slice(0, 24)}…(${text.length})` : text)} is rejected`, () => {
      expect(validatePort(text)).toBeNull();
    });
  }

  it("FR-019-45 · every integer from 1024 to 65535 is accepted and everything just outside is rejected (exhaustive)", () => {
    for (let p = 1024; p <= 65535; p += 1)
      if (validatePort(String(p)) !== p) throw new Error(`rejected ${p}`);
    for (const p of [0, 1, 79, 80, 443, 1023, 65536, 65537, 70000, 123456])
      expect(validatePort(String(p)), String(p)).toBeNull();
  });
});

describe("connectLocal (FR-019-44)", () => {
  it("FR-019-44 · makes exactly one GET to http://127.0.0.1:<port>/health with credentials omitted and a signal", async () => {
    const f = spy(async () => ok({ status: "ok", console_version: "1.2.3" }));
    const res = await connectLocal(8765, { fetchImpl: f });
    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8765/health");
    expect(init.credentials).toBe("omit");
    expect((init.method ?? "GET").toUpperCase()).toBe("GET");
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(res).toMatchObject({ connected: true, version: "1.2.3", label: "connected — console 1.2.3" });
  });

  it("FR-019-44 · the port is part of the address: 49152 is asked at 127.0.0.1:49152, never at localhost", async () => {
    const f = spy(async () => ok({ status: "ok", console_version: "0.0.1" }));
    await connectLocal(49152, { fetchImpl: f });
    expect(f.mock.calls[0]?.[0]).toBe("http://127.0.0.1:49152/health");
  });

  const bodies: Array<[string, () => Response]> = [
    ["status not ok", () => ok({ status: "starting", console_version: "1.2.3" })],
    ["status missing", () => ok({ console_version: "1.2.3" })],
    ["version missing", () => ok({ status: "ok" })],
    ["two-part version", () => ok({ status: "ok", console_version: "1.2" })],
    ["four-part version", () => ok({ status: "ok", console_version: "1.2.3.4" })],
    ["v-prefixed version", () => ok({ status: "ok", console_version: "v1.2.3" })],
    ["pre-release version", () => ok({ status: "ok", console_version: "1.2.3-beta.1" })],
    ["version with a trailing newline", () => ok({ status: "ok", console_version: "1.2.3\n" })],
    ["numeric version", () => ok({ status: "ok", console_version: 1.23 })],
    ["version that is markup", () => ok({ status: "ok", console_version: "<img src=x onerror=alert(1)>" })],
    [
      "a one-megabyte version string",
      () => ok({ status: "ok", console_version: `1.2.${"3".repeat(1_000_000)}` }),
    ],
    ["status as a boolean", () => ok({ status: true, console_version: "1.2.3" })],
    [
      "an HTML page",
      () => ok("<!doctype html><title>x</title>", { headers: { "content-type": "text/html" } }),
    ],
    ["invalid JSON", () => ok("{ not json")],
    ["an empty body", () => ok("")],
    ["a JSON array", () => ok([{ status: "ok", console_version: "1.2.3" }])],
    ["JSON null", () => ok("null")],
    ["a JSON string", () => ok('"ok"')],
    ["an HTTP 500 with an ok body", () => ok({ status: "ok", console_version: "1.2.3" }, { status: 500 })],
    ["an HTTP 404", () => ok("not found", { status: 404 })],
  ];
  for (const [what, make] of bodies) {
    it(`FR-019-44 · ${what}: 'not connected'`, async () => {
      const f = spy(async () => make());
      const res = await connectLocal(8765, { fetchImpl: f });
      expect(res.label).toBe("not connected");
      expect(res.connected).toBe(false);
      expect(f).toHaveBeenCalledTimes(1);
    });
  }

  it("FR-019-44 · a refused connection, a blocked request and a declined permission give 'not connected' and no exception", async () => {
    for (const error of [
      new TypeError("Failed to fetch"),
      new DOMException("denied", "NotAllowedError"),
      new DOMException("blocked", "SecurityError"),
      new Error("x"),
    ]) {
      const f = spy(async () => {
        throw error;
      });
      await expect(connectLocal(8765, { fetchImpl: f })).resolves.toMatchObject({
        connected: false,
        label: "not connected",
      });
      expect(f).toHaveBeenCalledTimes(1);
    }
  });

  it("FR-019-44 · a service that never answers is given up after the timeout (3 s by default): 'not connected', still one request", async () => {
    const f = spy(
      (_url, init) =>
        new Promise<Response>((_, reject) =>
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
        ),
    );
    const t0 = performance.now();
    const res = await connectLocal(8765, { fetchImpl: f });
    const took = performance.now() - t0;
    expect(res.label).toBe("not connected");
    expect(took).toBeGreaterThanOrEqual(2900);
    expect(took).toBeLessThan(4500);
    expect(f).toHaveBeenCalledTimes(1);
  }, 10_000);

  it("FR-019-44 · the timeout is the given one: 150 ms", async () => {
    const f = spy(
      (_url, init) =>
        new Promise<Response>((_, reject) =>
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
        ),
    );
    const t0 = performance.now();
    const res = await connectLocal(8765, { fetchImpl: f, timeoutMs: 150 });
    expect(res.label).toBe("not connected");
    expect(performance.now() - t0).toBeLessThan(1500);
  });

  it("FR-019-44 · a service that ignores the abort signal and answers late is still 'not connected' (the answer after the timeout is not used)", async () => {
    const f = spy(
      () =>
        new Promise<Response>((resolve) =>
          setTimeout(() => resolve(ok({ status: "ok", console_version: "1.2.3" })), 400),
        ),
    );
    const res = await connectLocal(8765, { fetchImpl: f, timeoutMs: 100 });
    expect(res.label).toBe("not connected");
  });
});

describe("the control (FR-019-44, FR-019-45)", () => {
  const render = (f: typeof fetch, extra: Record<string, unknown> = {}) =>
    renderApp(createElement(ConnectControl, { fetchImpl: f, ...extra }));
  const port = () => screen.getByTestId("connect-port") as HTMLInputElement;

  it("FR-019-44 · nothing is requested on render or while typing", async () => {
    const f = spy(async () => ok({ status: "ok", console_version: "1.2.3" }));
    await render(f);
    const user = userEvent.setup();
    await user.type(port(), "8765");
    expect(f).not.toHaveBeenCalled();
    expect(screen.queryByTestId("connect-error")).toBeNull();
  });

  it("FR-019-44 · pressing the button with a valid port makes one request and shows 'connected — console <version>'", async () => {
    const f = spy(async () => ok({ status: "ok", console_version: "2.10.3" }));
    await render(f);
    const user = userEvent.setup();
    await user.type(port(), "8765");
    await user.click(screen.getByTestId("connect-button"));
    expect(f).toHaveBeenCalledTimes(1);
    expect(f.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8765/health");
    expect(await screen.findByText("connected — console 2.10.3")).toBeTruthy();
    expect(screen.getByTestId("connect-label").getAttribute("aria-live")).toBe("polite");
  });

  it("FR-019-44 · each press is one request: three presses, three requests, and none in between", async () => {
    const f = spy(async () => ok({ status: "ok", console_version: "1.0.0" }));
    await render(f);
    const user = userEvent.setup();
    await user.type(port(), "8765");
    await user.click(screen.getByTestId("connect-button"));
    await screen.findByText(/connected/);
    await new Promise((r) => setTimeout(r, 300));
    expect(f).toHaveBeenCalledTimes(1);
    await user.click(screen.getByTestId("connect-button"));
    await user.click(screen.getByTestId("connect-button"));
    await new Promise((r) => setTimeout(r, 300));
    expect(f).toHaveBeenCalledTimes(3);
  });

  it("FR-019-44 · Enter in the port field presses the button", async () => {
    const f = spy(async () => ok({ status: "ok", console_version: "1.0.0" }));
    await render(f);
    const user = userEvent.setup();
    await user.type(port(), "8765{Enter}");
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("FR-019-44 · a failed attempt reads 'not connected' and changes nothing else; a later success replaces it", async () => {
    let n = 0;
    const f = spy(async () => {
      n += 1;
      if (n === 1) throw new TypeError("Failed to fetch");
      return ok({ status: "ok", console_version: "1.0.0" });
    });
    await render(f);
    const user = userEvent.setup();
    await user.type(port(), "8765");
    await user.click(screen.getByTestId("connect-button"));
    expect((await screen.findByTestId("connect-label")).textContent).toBe("not connected");
    expect(port().value).toBe("8765");
    await user.click(screen.getByTestId("connect-button"));
    expect(await screen.findByText("connected — console 1.0.0")).toBeTruthy();
  });

  const bad = [
    "",
    "abc",
    "80",
    "65536",
    "8765/x",
    "8765@host",
    " 8765",
    "-1",
    "1e4",
    "8765\u0000",
    "9".repeat(2000),
    "<img src=x>",
  ];
  for (const text of bad) {
    it(`FR-019-45 · ${JSON.stringify(text.length > 20 ? `${text.slice(0, 20)}…` : text)}: no request, an inline validation message, and the field is marked invalid`, async () => {
      const f = spy(async () => ok({ status: "ok", console_version: "1.0.0" }));
      await render(f);
      fireEvent.change(port(), { target: { value: text } });
      fireEvent.click(screen.getByTestId("connect-button"));
      expect(f).not.toHaveBeenCalled();
      const error = screen.getByTestId("connect-error");
      expect(error.getAttribute("role")).toBe("alert");
      expect(error.textContent?.length ?? 0).toBeGreaterThan(0);
      expect(error.textContent).toMatch(/1024/);
      expect(error.textContent).toMatch(/65535/);
      expect(port().getAttribute("aria-invalid")).toBe("true");
      expect(document.querySelector("img[src='x']")).toBeNull();
    });
  }

  it("FR-019-45 · correcting the port clears the message and a press then makes the request", async () => {
    const f = spy(async () => ok({ status: "ok", console_version: "1.0.0" }));
    await render(f);
    const user = userEvent.setup();
    await user.type(port(), "80");
    await user.click(screen.getByTestId("connect-button"));
    expect(screen.getByTestId("connect-error")).toBeTruthy();
    await user.clear(port());
    await user.type(port(), "8765");
    await user.click(screen.getByTestId("connect-button"));
    expect(screen.queryByTestId("connect-error")).toBeNull();
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("FR-019-44 · the label never repeats what the server sent beyond a validated version", async () => {
    const f = spy(async () =>
      ok({ status: "ok", console_version: "1.2.3", message: "<b>hello</b>", extra: "x".repeat(10_000) }),
    );
    await render(f);
    const user = userEvent.setup();
    await user.type(port(), "8765");
    await user.click(screen.getByTestId("connect-button"));
    const label = await screen.findByTestId("connect-label");
    expect(label.textContent).toBe("connected — console 1.2.3");
    expect(document.querySelector("b")).toBeNull();
  });
});
