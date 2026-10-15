// The opt-in "connect to my local studio" control (FR-019-44, FR-019-45): port validation and one GET /health.

const VERSION = /^[0-9]+\.[0-9]+\.[0-9]+$/;
const DEFAULT_TIMEOUT_MS = 3000;

/** The port when `text` is exactly 1 to 5 ASCII digits denoting 1024..65535, else null. Never throws, whatever the length. */
export function validatePort(text: string): number | null {
  if (typeof text !== "string" || !/^[0-9]{1,5}$/.test(text)) return null;
  const port = Number(text);
  return port >= 1024 && port <= 65535 ? port : null;
}

export interface ConnectResult {
  connected: boolean;
  label: string;
  version?: string;
}

const NOT_CONNECTED: ConnectResult = { connected: false, label: "not connected" };

/** One request, a timeout that also ends the wait when the server ignores the abort signal, no second attempt, never throws. */
export async function connectLocal(
  port: number,
  options: { fetchImpl?: typeof fetch; timeoutMs?: number } = {},
): Promise<ConnectResult> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<ConnectResult>((resolve) => {
    timer = setTimeout(() => {
      controller.abort();
      resolve(NOT_CONNECTED);
    }, timeoutMs);
  });
  const attempt = (async (): Promise<ConnectResult> => {
    try {
      const response = await fetchImpl(`http://127.0.0.1:${port}/health`, {
        method: "GET",
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.ok) return NOT_CONNECTED;
      const body: unknown = JSON.parse(await response.text());
      if (typeof body !== "object" || body === null || Array.isArray(body)) return NOT_CONNECTED;
      const { status, console_version: version } = body as Record<string, unknown>;
      if (status !== "ok" || typeof version !== "string" || version.length > 64 || !VERSION.test(version))
        return NOT_CONNECTED;
      return { connected: true, version, label: `connected — console ${version}` };
    } catch {
      return NOT_CONNECTED;
    }
  })();
  try {
    return await Promise.race([attempt, timeout]);
  } finally {
    clearTimeout(timer);
  }
}
