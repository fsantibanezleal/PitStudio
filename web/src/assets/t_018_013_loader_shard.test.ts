// T-018-013 [red] · FR-018-43 (asset loader: SHA-256 and path rules), FR-018-45 (replay shard reader),
// P-018-68 (quantisation round trip), P-018-69 (decoding preserves order), P-018-70 (shifting the header minimum).
//
// Expected API
//   module `~/assets/loader` (web/src/assets/loader.ts):
//     INTEGRITY_FAILED = "integrity check failed"                       the text a card shows in place of the artefact
//     checkAssetPath(path: unknown): { ok: true } | { ok: false; reason: string }
//         rejects an absolute path, a URL scheme, `..` anywhere, a backslash, a percent-encoded separator (%2f, %5c, %2e, any
//         case), an empty or non-string path, a NUL, and a path longer than 2,000 characters (FR-018-43; FR-018-42 for the length)
//     verifySha256(bytes: ArrayBuffer | Uint8Array, expected: string): Promise<boolean>     lowercase 64-hex; malformed digest -> false
//     loadAsset(entry: { path: string; sha256: string; bytes: number }, opts: { baseUrl: string; fetch?: typeof fetch }):
//         Promise<{ ok: true; bytes: Uint8Array } | { ok: false; reason: "bad-path" | "integrity" | "unavailable"; message: string }>
//         requests `opts.baseUrl + entry.path` only after `checkAssetPath` passed (no request otherwise); `message` is exactly
//         INTEGRITY_FAILED for reason "integrity"; never throws.
//   module `~/assets/shard` (web/src/assets/shard.ts), header = DC-018-03 `$defs/shard_header`:
//     readShard(header: unknown, payload: ArrayBuffer | Uint8Array):
//         { ok: true; kind: string; fps: number; frames: number; items: number;
//           channels: Array<{ name: string; unit: string; min: number; max: number }>;
//           values: Float64Array }      decoded SI values, layout frame-major: index = (frame * items + item) * channels + channel
//       | { ok: false; code: "E_SCHEMA"; message: string }
//       Code words are little-endian 16-bit, signed for code_type "int16" and unsigned for "uint16" (raw16); Float32 tiles
//       (encoding "float32") are little-endian float32 with byte length frames x items x channels x 4. The WHOLE shard is rejected
//       (no partial data) when the header fails the schema, the payload byte length differs from frames x items x channels x 2
//       (x 4 for float32) or from `payload.bytes`, or a code lies outside the header's `code_range`. Never throws.
//     decodeCode(header: { code_type: "int16" | "uint16"; code_range: { min: number; max: number };
//                          channels: Array<{ min: number; max: number }> }, channel: number, code: number): number
//         affine: min + (code - code_range.min) * (max - min) / (code_range.max - code_range.min)
//
// Oracles: SHA-256 from node:crypto; the spec's hand-built shard corpus (contracts/examples/index.json, 14 hostile headers);
// the affine quantisation formula and half-quantum bound written in P-018-68; hand-built payloads below.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import fc from "fast-check";
import { describe, expect, it, vi } from "vitest";
import { checkAssetPath, INTEGRITY_FAILED, loadAsset, verifySha256 } from "~/assets/loader";
import { decodeCode, readShard } from "~/assets/shard";

const sha = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");

// ---------------------------------------------------------------------------------------------------------------------
// FR-018-43 · path rules
// ---------------------------------------------------------------------------------------------------------------------
describe("asset paths (FR-018-43)", () => {
  const good = [
    "artefacts/a1-queue-chart.json",
    "shards/fleet-000.bin",
    "a/b/c.png",
    "tiles/0/0/0.glb",
    "model_v1.onnx",
    "a.b/c-d_e.json",
  ];
  for (const p of good) {
    it(`FR-018-43 · accepts the manifest path ${p}`, () => {
      expect(checkAssetPath(p)).toEqual({ ok: true });
    });
  }

  const bad: Array<[string, unknown]> = [
    ["an absolute path", "/etc/passwd"],
    ["an absolute path under assets", "/assets/a.json"],
    ["a URL with a scheme", "https://example.org/a.json"],
    ["an http URL", "http://example.org/a.json"],
    ["a protocol-relative URL", "//example.org/a.json"],
    ["a data URL", "data:text/plain;base64,QQ=="],
    ["a javascript URL", "javascript:alert(1)"],
    ["a file URL", "file:///C:/Windows/win.ini"],
    ["a leading ..", "../x"],
    ["a middle ..", "a/../b"],
    ["an escaping ..", "a/../../x"],
    ["a trailing ..", "a/.."],
    ["a bare ..", ".."],
    ["a backslash", "a\\b"],
    ["a Windows drive path", "C:\\Windows\\win.ini"],
    ["a percent-encoded dot", "%2e%2e/x"],
    ["a percent-encoded dot, upper case", "%2E%2E/x"],
    ["a percent-encoded slash", "a%2fb"],
    ["a percent-encoded slash, upper case", "a%2Fb"],
    ["a percent-encoded backslash", "a%5cb"],
    ["a double dot inside a name", "a..b/c.json"],
    ["an empty string", ""],
    ["a NUL byte", "a\u0000b"],
    ["a 2,001-character path", `${"a/".repeat(1000)}b.json`],
    ["a non-string (number)", 42],
    ["a non-string (null)", null],
    ["a non-string (object)", { path: "a" }],
  ];
  for (const [name, p] of bad) {
    it(`FR-018-43 · rejects ${name}`, () => {
      const out = checkAssetPath(p);
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.reason.length).toBeGreaterThan(0);
    });
  }

  it("FR-018-43 · property: any path that starts with a slash, holds a backslash or `..`, or starts with a scheme is rejected", () => {
    const seg = fc.stringMatching(/^[a-z0-9._-]{1,8}$/);
    const tail = fc.array(seg, { maxLength: 4 }).map((s) => s.join("/"));
    fc.assert(
      fc.property(
        tail,
        fc.constantFrom("/", "\\", "../", "https://h/", "ftp://h/", "a:b/", "x/../"),
        (rest, prefix) => !checkAssetPath(`${prefix}${rest}`).ok,
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-43 · property: plain relative paths of safe segments are accepted", () => {
    const seg = fc.stringMatching(/^[a-z0-9_-][a-z0-9_.-]{0,7}$/).filter((s) => !s.includes(".."));
    fc.assert(
      fc.property(fc.array(seg, { minLength: 1, maxLength: 5 }), (segs) => checkAssetPath(segs.join("/")).ok),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// FR-018-43 · SHA-256 and the loader
// ---------------------------------------------------------------------------------------------------------------------
describe("integrity (FR-018-43)", () => {
  const body = new TextEncoder().encode('{"hello":"pit"}');
  const digest = sha(body);

  it("FR-018-43 · verifySha256 accepts the exact bytes and rejects every single-byte mutation", async () => {
    await expect(verifySha256(body, digest)).resolves.toBe(true);
    for (let i = 0; i < body.length; i++) {
      const mutated = body.slice();
      mutated[i] = (mutated[i] as number) ^ 0x01;
      await expect(verifySha256(mutated, digest)).resolves.toBe(false);
    }
  });

  it("FR-018-43 · verifySha256 takes an ArrayBuffer as well as a Uint8Array", async () => {
    await expect(verifySha256(body.slice().buffer as ArrayBuffer, digest)).resolves.toBe(true);
  });

  it("FR-018-43 · SHA-256 of the empty input is the FIPS 180-4 value e3b0c442…b855", async () => {
    await expect(
      verifySha256(new Uint8Array(0), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ).resolves.toBe(true);
  });

  for (const bad of [
    "",
    "abc",
    "g".repeat(64),
    digest.slice(1),
    `${digest}0`,
    digest.toUpperCase(),
    " ".repeat(64),
  ]) {
    it(`FR-018-43 · a malformed digest "${bad.slice(0, 12)}…" never verifies and never throws`, async () => {
      await expect(verifySha256(body, bad)).resolves.toBe(false);
    });
  }

  const entry = { path: "artefacts/a1.json", sha256: digest, bytes: body.length };
  const baseUrl = "https://example.org/PitStudio/assets/";
  const respond = (bytes: Uint8Array) => vi.fn(async () => new Response(bytes.slice(), { status: 200 }));

  it("FR-018-43 · loadAsset fetches baseUrl + path and returns the verified bytes", async () => {
    const fetchSpy = respond(body);
    const out = await loadAsset(entry, { baseUrl, fetch: fetchSpy as unknown as typeof fetch });
    expect(out.ok).toBe(true);
    if (out.ok) expect(Array.from(out.bytes)).toEqual(Array.from(body));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect((fetchSpy.mock.calls[0] as unknown[])[0]).toBe(`${baseUrl}artefacts/a1.json`);
  });

  it("FR-018-43 · served bytes that differ by one byte give 'integrity check failed' and no bytes", async () => {
    const mutated = body.slice();
    mutated[3] = (mutated[3] as number) ^ 0xff;
    const out = await loadAsset(entry, { baseUrl, fetch: respond(mutated) as unknown as typeof fetch });
    expect(out.ok).toBe(false);
    if (!out.ok) {
      expect(out.reason).toBe("integrity");
      expect(out.message).toBe(INTEGRITY_FAILED);
      expect(INTEGRITY_FAILED).toBe("integrity check failed");
    }
  });

  it("FR-018-43 · a truncated body gives 'integrity check failed'", async () => {
    const out = await loadAsset(entry, {
      baseUrl,
      fetch: respond(body.slice(0, body.length - 1)) as unknown as typeof fetch,
    });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.message).toBe(INTEGRITY_FAILED);
  });

  it("FR-018-43 · a hostile path is never requested and is reported as bad-path", async () => {
    for (const path of ["/x", "https://evil.example/x", "../x", "a\\b", "%2e%2e/x"]) {
      const fetchSpy = respond(body);
      const out = await loadAsset(
        { ...entry, path },
        { baseUrl, fetch: fetchSpy as unknown as typeof fetch },
      );
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.reason).toBe("bad-path");
      expect(fetchSpy).not.toHaveBeenCalled();
    }
  });

  it("FR-018-43 · an HTTP error or a network failure is reported, not thrown", async () => {
    const notFound = vi.fn(async () => new Response("nope", { status: 404 }));
    const a = await loadAsset(entry, { baseUrl, fetch: notFound as unknown as typeof fetch });
    expect(a.ok).toBe(false);
    const down = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const b = await loadAsset(entry, { baseUrl, fetch: down as unknown as typeof fetch });
    expect(b.ok).toBe(false);
    if (!b.ok) expect(b.reason).toBe("unavailable");
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// FR-018-45 · shard reader
// ---------------------------------------------------------------------------------------------------------------------
const EXAMPLES = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../specs/018-web-cases/contracts/examples",
);
interface ExampleHeader {
  payload: { bytes: number };
  [key: string]: unknown;
}
const readExample = (name: string) =>
  JSON.parse(readFileSync(resolve(EXAMPLES, name), "utf8")) as ExampleHeader;

type Header = Record<string, unknown>;

function poseHeader(over: Partial<Header> = {}): Header {
  // 2 frames x 3 items x 2 channels (x in [-100, 100] m, yaw in [-pi, pi] rad), uint16 codes 0..65535
  return {
    document: "replay-shard-header",
    schema_version: "1.0",
    kind: "pose",
    encoding: "raw16",
    code_type: "uint16",
    code_range: { min: 0, max: 65535 },
    fps: 10,
    frames: { start: 0, count: 2 },
    items: 3,
    channels: [
      { name: "x", unit: "m", min: -100, max: 100 },
      { name: "yaw", unit: "rad", min: -Math.PI, max: Math.PI },
    ],
    bbox_m: { min: [-100, -100, 0], max: [100, 100, 10] },
    payload: { path: "fleet-000.bin", bytes: 2 * 3 * 2 * 2, sha256: "0".repeat(64) },
    ...over,
  };
}

function u16(codes: number[], signed = false): Uint8Array {
  const buf = new ArrayBuffer(codes.length * 2);
  const dv = new DataView(buf);
  for (const [i, c] of codes.entries()) {
    if (signed) dv.setInt16(i * 2, c, true);
    else dv.setUint16(i * 2, c, true);
  }
  return new Uint8Array(buf);
}

describe("shard decoding by hand (FR-018-45, P-018-68)", () => {
  it("FR-018-45 · decodes uint16 codes affinely: code 0 -> min, 65535 -> max, 32768 -> min + 32768/65535 x span", () => {
    const codes = [0, 65535, 32768, 16384, 1, 65534, 0, 0, 65535, 65535, 49152, 8192];
    const out = readShard(poseHeader(), u16(codes));
    expect(out.ok).toBe(true);
    if (!out.ok) return;
    expect(out.frames).toBe(2);
    expect(out.items).toBe(3);
    expect(out.values.length).toBe(12);
    // index = (frame * items + item) * channels + channel
    expect(out.values[0]).toBe(-100); // frame 0, item 0, x, code 0
    expect(out.values[1]).toBeCloseTo(Math.PI, 12); // yaw, code 65535
    expect(out.values[2]).toBeCloseTo(-100 + (32768 * 200) / 65535, 9); // item 1, x
    expect(out.values[3]).toBeCloseTo(-Math.PI + (16384 * 2 * Math.PI) / 65535, 12);
    expect(out.values[4]).toBeCloseTo(-100 + 200 / 65535, 9);
    expect(out.values[10]).toBeCloseTo(-100 + (49152 * 200) / 65535, 9); // frame 1, item 2, x
    expect(out.values[11]).toBeCloseTo(-Math.PI + (8192 * 2 * Math.PI) / 65535, 12);
    expect(out.channels.map((c: { name: string }) => c.name)).toEqual(["x", "yaw"]);
    expect(out.fps).toBe(10);
  });

  it("FR-018-45 · decodes int16 codes: -32768 -> min, 32767 -> max, 0 -> min + 32768/65535 x span", () => {
    const header = poseHeader({
      code_type: "int16",
      code_range: { min: -32768, max: 32767 },
      channels: [
        { name: "x", unit: "m", min: 0, max: 65535 },
        { name: "y", unit: "m", min: -1, max: 1 },
      ],
      items: 1,
      frames: { start: 0, count: 2 },
      payload: { path: "p.bin", bytes: 8, sha256: "0".repeat(64) },
    });
    const out = readShard(header, u16([-32768, 32767, 0, -1], true));
    expect(out.ok).toBe(true);
    if (!out.ok) return;
    expect(out.values[0]).toBe(0);
    expect(out.values[1]).toBe(1);
    expect(out.values[2]).toBeCloseTo(32768, 9); // 0 + 32768 * 65535 / 65535
    expect(out.values[3]).toBeCloseTo(-1 + (32767 * 2) / 65535, 12);
  });

  it("FR-018-45 · a Float32 tile is read as little-endian float32 with 4 bytes per value", () => {
    const header = readExample("replay-shard.valid-field-float32.json");
    const payload = new Uint8Array(header.payload.bytes);
    const dv = new DataView(payload.buffer);
    dv.setFloat32(0, 12.5, true);
    dv.setFloat32(4, 3600, true);
    const out = readShard(header, payload);
    expect(out.ok).toBe(true);
    if (out.ok) {
      expect(out.values.length).toBe(65536);
      expect(out.values[0]).toBe(12.5);
      expect(out.values[1]).toBe(3600);
    }
  });

  it("FR-018-45 · the spec's valid particle and pose headers are accepted with zero-filled payloads", () => {
    for (const name of ["replay-shard.valid.json", "replay-shard.valid-pose.json"]) {
      const header = readExample(name);
      const out = readShard(header, new Uint8Array(header.payload.bytes));
      expect(out.ok, name).toBe(true);
    }
  });
});

describe("shard rejection (FR-018-45)", () => {
  it("FR-018-45 · a payload one byte too long or too short rejects the whole shard with E_SCHEMA", () => {
    for (const len of [23, 25, 0]) {
      const out = readShard(poseHeader(), new Uint8Array(len));
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.code).toBe("E_SCHEMA");
    }
  });

  it("FR-018-45 · a declared payload.bytes that disagrees with frames x items x channels x 2 rejects the shard", () => {
    const header = poseHeader({ payload: { path: "p.bin", bytes: 25, sha256: "0".repeat(64) } });
    const out = readShard(header, new Uint8Array(25));
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.code).toBe("E_SCHEMA");
  });

  it("FR-018-45 · a code outside the declared code range rejects the whole shard (no partial values)", () => {
    const header = poseHeader({ code_range: { min: 100, max: 60000 } });
    const codes = new Array(12).fill(1000);
    codes[7] = 99; // one code below the range
    const out = readShard(header, u16(codes));
    expect(out.ok).toBe(false);
    if (!out.ok) {
      expect(out.code).toBe("E_SCHEMA");
      expect("values" in out).toBe(false);
    }
    const high = new Array(12).fill(1000);
    high[11] = 60001;
    expect(readShard(header, u16(high)).ok).toBe(false);
  });

  it("FR-018-45 · codes at both ends of the declared range are accepted", () => {
    const header = poseHeader({ code_range: { min: 100, max: 60000 } });
    const codes = new Array(12).fill(100);
    codes[5] = 60000;
    expect(readShard(header, u16(codes)).ok).toBe(true);
  });

  it("FR-018-45 · an int16 shard whose code is below -32768 cannot exist, but one outside a narrowed range is rejected", () => {
    const header = poseHeader({
      code_type: "int16",
      code_range: { min: -1000, max: 1000 },
      items: 1,
      payload: { path: "p.bin", bytes: 8, sha256: "0".repeat(64) },
    });
    expect(readShard(header, u16([-1000, 1000, 0, 5], true)).ok).toBe(true);
    expect(readShard(header, u16([-1001, 1000, 0, 5], true)).ok).toBe(false);
    expect(readShard(header, u16([-1000, 1001, 0, 5], true)).ok).toBe(false);
  });

  const headerCorpus = [
    "replay-shard.hostile-code-range-outside-dtype.json",
    "replay-shard.hostile-code-range-negative-uint16.json",
    "replay-shard.hostile-oversized.json",
    "replay-shard.hostile-unknown-enum.json",
    "replay-shard.hostile-unknown-code-type.json",
    "replay-shard.hostile-malformed-digest.json",
    "replay-shard.hostile-path-traversal.json",
    "replay-shard.hostile-absolute-path.json",
    "replay-shard.hostile-unknown-field.json",
    "replay-shard.hostile-wrong-unit.json",
    "replay-shard.hostile-wrong-unit-position.json",
    "replay-shard.hostile-conditional-float32-codes.json",
    "replay-shard.hostile-conditional-png16-int16.json",
    "replay-shard.hostile-conditional-missing-code-type.json",
    "replay-shard.hostile-conditional-field-grid.json",
    "replay-shard.hostile-conditional-particle-encoding.json",
    "replay-shard.hostile-out-of-range-fps.json",
    "replay-shard.hostile-wrong-shape-bbox.json",
    "replay-shard.hostile-missing-required.json",
    "replay-shard.hostile-empty-channels.json",
    "replay-shard.hostile-unknown-document.json",
  ];
  for (const name of headerCorpus) {
    it(`FR-018-45 · the spec's hostile header ${name} is rejected with E_SCHEMA`, () => {
      const header = readExample(name);
      const declared =
        typeof header.payload?.bytes === "number" ? Math.min(header.payload.bytes, 12_000_000) : 16;
      const out = readShard(header, new Uint8Array(declared));
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.code).toBe("E_SCHEMA");
    });
  }

  const hostileValues: Array<[string, unknown, unknown]> = [
    ["a null header", null, new Uint8Array(4)],
    ["a string header", "header", new Uint8Array(4)],
    ["an array header", [], new Uint8Array(4)],
    ["an empty header", {}, new Uint8Array(4)],
    ["a valid header and a null payload", poseHeader(), null],
    ["a valid header and a string payload", poseHeader(), "bytes"],
  ];
  for (const [name, header, payload] of hostileValues) {
    it(`FR-018-45 · ${name} gives E_SCHEMA and no exception`, () => {
      let out: ReturnType<typeof readShard> | undefined;
      expect(() => {
        out = readShard(header, payload as Uint8Array);
      }).not.toThrow();
      expect(out?.ok).toBe(false);
    });
  }

  it("FR-018-45 · property: random bytes against a valid header are either decoded inside the header's bounds or rejected, never thrown", () => {
    fc.assert(
      fc.property(fc.uint8Array({ minLength: 0, maxLength: 40 }), (bytes) => {
        const out = readShard(poseHeader({ code_range: { min: 1000, max: 50000 } }), bytes);
        if (!out.ok) return out.code === "E_SCHEMA";
        return Array.from(out.values as Float64Array).every((v: number, i: number) => {
          const ch = out.channels[i % 2] as { min: number; max: number };
          return v >= ch.min - 1e-9 && v <= ch.max + 1e-9;
        });
      }),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// P-018-68 / P-018-69 / P-018-70
// ---------------------------------------------------------------------------------------------------------------------
type CodeType = "int16" | "uint16";
const RANGE: Record<CodeType, { min: number; max: number }> = {
  uint16: { min: 0, max: 65535 },
  int16: { min: -32768, max: 32767 },
};

function head(codeType: CodeType, min: number, max: number) {
  return { code_type: codeType, code_range: RANGE[codeType], channels: [{ min, max }] };
}

describe("quantisation properties (P-018-68, P-018-69, P-018-70)", () => {
  it("P-018-68 · quantising any value of the channel range and decoding it errs by at most half a quantum (both code types)", () => {
    fc.assert(
      fc.property(
        fc.constantFrom<CodeType>("int16", "uint16"),
        fc.double({ min: -2000, max: 2000, noNaN: true }),
        fc.double({ min: 1, max: 4000, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        (codeType, min, span, u) => {
          const max = min + span;
          const v = min + u * span;
          const r = RANGE[codeType];
          const code = Math.round(((v - min) / (max - min)) * (r.max - r.min)) + r.min;
          const decoded = decodeCode(head(codeType, min, max), 0, code);
          const halfQuantum = (max - min) / 65535 / 2;
          return Math.abs(decoded - v) <= halfQuantum * (1 + 1e-9) + 1e-12 * (Math.abs(min) + span);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-68 · the end codes decode to the channel limits", () => {
    for (const codeType of ["int16", "uint16"] as const) {
      const r = RANGE[codeType];
      expect(decodeCode(head(codeType, -3.5, 12.25), 0, r.min)).toBe(-3.5);
      expect(decodeCode(head(codeType, -3.5, 12.25), 0, r.max)).toBeCloseTo(12.25, 12);
    }
  });

  it("P-018-69 · decoding is strictly increasing over all 65,536 codes of each code type", () => {
    for (const codeType of ["int16", "uint16"] as const) {
      const h = head(codeType, -1650, 1650);
      const r = RANGE[codeType];
      let prev = Number.NEGATIVE_INFINITY;
      for (let code = r.min; code <= r.max; code++) {
        const v = decodeCode(h, 0, code);
        expect(v > prev, `${codeType} code ${code}`).toBe(true);
        prev = v;
      }
    }
  });

  it("P-018-70 · shifting the header minimum and maximum by a dyadic delta shifts every decoded value by that delta, exactly", () => {
    fc.assert(
      fc.property(
        fc.constantFrom<CodeType>("int16", "uint16"),
        fc.integer({ min: 0, max: 10 }),
        fc.integer({ min: -256, max: 256 }),
        fc.integer({ min: -256, max: 256 }),
        fc.integer({ min: 0, max: 65535 }),
        (codeType, k, m, d, offset) => {
          const q = 2 ** -k;
          const min = m * q;
          const max = min + 65535 * q;
          const delta = d * q;
          const r = RANGE[codeType];
          const code = r.min + offset;
          const base = decodeCode(head(codeType, min, max), 0, code);
          const shifted = decodeCode(head(codeType, min + delta, max + delta), 0, code);
          return shifted === base + delta;
        },
      ),
      { numRuns: 200 },
    );
  });
});
