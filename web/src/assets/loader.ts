// Asset loader (FR-018-43): a manifest path is requested only after it passed the path rules, and the served bytes are used
// only if their SHA-256 equals the manifest entry. Nothing here throws.

export const INTEGRITY_FAILED = "integrity check failed";

const MAX_PATH = 2000;

export type PathCheck = { ok: true } | { ok: false; reason: string };

/** Rejects an absolute path, a URL scheme, `..`, a backslash, a percent-encoded separator or dot, a NUL and an over-long path. */
export function checkAssetPath(path: unknown): PathCheck {
  if (typeof path !== "string" || path.length === 0)
    return { ok: false, reason: "the path is empty or not a string" };
  if (path.length > MAX_PATH) return { ok: false, reason: "the path is longer than 2,000 characters" };
  if (path.includes("\u0000")) return { ok: false, reason: "the path holds a NUL character" };
  if (path.startsWith("/")) return { ok: false, reason: "the path is absolute" };
  if (path.includes("\\")) return { ok: false, reason: "the path holds a backslash" };
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(path)) return { ok: false, reason: "the path has a URL scheme" };
  if (/%(2f|5c|2e|00)/i.test(path))
    return { ok: false, reason: "the path holds a percent-encoded separator" };
  if (path.includes("..")) return { ok: false, reason: "the path holds .." };
  return { ok: true };
}

const HEX64 = /^[0-9a-f]{64}$/;

function toHex(buffer: ArrayBuffer): string {
  let out = "";
  for (const byte of new Uint8Array(buffer)) out += byte.toString(16).padStart(2, "0");
  return out;
}

/** True iff SHA-256(bytes) equals `expected` (lowercase 64 hex). A malformed digest never verifies. */
export async function verifySha256(bytes: ArrayBuffer | Uint8Array, expected: string): Promise<boolean> {
  if (typeof expected !== "string" || !HEX64.test(expected)) return false;
  try {
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const copy = new Uint8Array(view.byteLength);
    copy.set(view);
    return toHex(await crypto.subtle.digest("SHA-256", copy)) === expected;
  } catch {
    return false;
  }
}

export interface AssetEntry {
  path: string;
  sha256: string;
  bytes: number;
}

export type AssetResult =
  | { ok: true; bytes: Uint8Array }
  | { ok: false; reason: "bad-path" | "integrity" | "unavailable"; message: string };

export async function loadAsset(
  entry: AssetEntry,
  opts: { baseUrl: string; fetch?: typeof fetch },
): Promise<AssetResult> {
  const check = checkAssetPath(entry?.path);
  if (!check.ok) return { ok: false, reason: "bad-path", message: check.reason };
  const doFetch = opts.fetch ?? globalThis.fetch.bind(globalThis);
  let body: Uint8Array;
  try {
    const response = await doFetch(`${opts.baseUrl}${entry.path}`);
    if (!response.ok) return { ok: false, reason: "unavailable", message: `HTTP ${response.status}` };
    body = new Uint8Array(await response.arrayBuffer());
  } catch (error) {
    return {
      ok: false,
      reason: "unavailable",
      message: error instanceof Error ? error.message : "request failed",
    };
  }
  if (!(await verifySha256(body, entry.sha256)))
    return { ok: false, reason: "integrity", message: INTEGRITY_FAILED };
  return { ok: true, bytes: body };
}
