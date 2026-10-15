// T-018-012 [red] · FR-018-38 (typed message protocol), FR-018-39 (hostile requests, answered in 50 ms, nothing computed),
// FR-018-40 (size caps -> E_SIZE naming the cap) and FR-018-46 (timeout -> terminate, E_TIMEOUT, fallback).
//
// Expected API
//   module `~/engines/host/protocol` (web/src/engines/host/protocol.ts), validators generated from contracts/engines/*.schema.json:
//     type ErrorCode = "E_SCHEMA" | "E_RANGE" | "E_NONFINITE" | "E_SIZE" | "E_UNKNOWN_ENGINE" | "E_TIMEOUT" | "E_RUNTIME"
//     ENGINE_ERROR_CODES: readonly ErrorCode[]                       exactly those seven
//     interface EngineError { kind: "error"; code: ErrorCode; message: string;
//                             detail?: { pointer?: string; cap?: number | string; name?: string } }
//     validateRequest(raw: unknown, opts?: { loaded?: Record<string, string> }):
//         { ok: true; request: EngineRequest } | { ok: false; error: EngineError }
//         `raw` is a DC-018-02 `input` document ({ kind: "input", engine, engine_version, function, args }); it is never mutated,
//         never throws, and checks NaN and +-Infinity before the schema (-> E_NONFINITE); a version different from
//         `loaded[engine]` is rejected; an unknown engine id gives E_UNKNOWN_ENGINE.
//     validateResult(raw: unknown): { ok: true; result: EngineResult } | { ok: false; error: EngineError }   (an `output` document)
//   module `~/engines/host/host` (web/src/engines/host/host.ts):
//     createEngineHost(opts: {
//        loaded: Record<string, string>;                       engine id -> loaded engine version
//        engines: Record<string, EngineBackend>;
//        timeoutMs?: Partial<Record<string, number>>;           override of the per-engine timeout of spec 018 section 7.1
//        onFailure?: (engineId: string, f: { runtime: string; kind: "timeout" | "throw" | "init" }) => void;
//        ready?: Promise<unknown>;                              no backend is called before it has settled (FR-018-29)
//     }): { request(raw: unknown): Promise<EngineResponse> }
//     EngineBackend = { runtime: string; run(request: EngineRequest, ctx: { signal: AbortSignal }): Promise<unknown>; terminate(): void }
//     EngineResponse = a validated `output` document, or an EngineError. `request` never rejects.
//     Per-engine default timeouts are those of section 7.1 (10 s unless the table says otherwise, e.g. haulage 2 s).
//     A backend that throws gives E_RUNTIME with `detail.name` = the error's name (spec 018 section 7.1: the engine-specific
//     errors of specs 007, 013 and 014 travel in `detail.name`) and calls `onFailure` with kind "throw".
//
// Oracles: the spec's own corpus of 298 hand-built examples (74 valid, 193 hostile requests, 31 hostile results) (contracts/examples/index-engines.json: valid ones accepted,
// hostile ones rejected, with the defect class) via web/src/test-support/engine-examples.ts; the EARS text of FR-018-38..40, 46.
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createEngineHost } from "~/engines/host/host";
import { ENGINE_ERROR_CODES, validateRequest, validateResult } from "~/engines/host/protocol";
import {
  ENGINE_IDS,
  type EngineExample,
  expectedCodes,
  loadEngineExamples,
  numericPaths,
  withValueAt,
} from "~/test-support/engine-examples";

const examples = loadEngineExamples();
const validInputs = examples.filter((e) => e.valid && e.direction === "input");
const validOutputs = examples.filter((e) => e.valid && e.direction === "output");
const hostileInputs = examples.filter((e) => !e.valid && e.direction === "input");
const hostileOutputs = examples.filter((e) => !e.valid && e.direction === "output");
const LOADED = Object.fromEntries(ENGINE_IDS.map((id) => [id, "0.1.0"]));

function backendFor(result: Record<string, unknown> | ((req: Record<string, unknown>) => unknown)) {
  return {
    runtime: "test",
    run: vi.fn(async (req: unknown) =>
      typeof result === "function" ? result(req as Record<string, unknown>) : result,
    ),
    terminate: vi.fn(),
  };
}

describe("the corpus itself (guards the oracle)", () => {
  it("FR-018-38 · covers all 25 engines with valid requests and valid results, and many hostile ones", () => {
    expect(new Set(validInputs.map((e) => e.engine))).toEqual(new Set(ENGINE_IDS));
    expect(new Set(validOutputs.map((e) => e.engine))).toEqual(new Set(ENGINE_IDS));
    expect(hostileInputs.length).toBeGreaterThanOrEqual(190);
    expect(hostileOutputs.length).toBeGreaterThanOrEqual(25);
  });

  it("FR-018-38 · the error codes are exactly the seven of the spec", () => {
    expect([...ENGINE_ERROR_CODES].sort()).toEqual(
      ["E_NONFINITE", "E_RANGE", "E_RUNTIME", "E_SCHEMA", "E_SIZE", "E_TIMEOUT", "E_UNKNOWN_ENGINE"].sort(),
    );
  });
});

describe("valid documents (FR-018-38)", () => {
  for (const ex of validInputs) {
    it(`FR-018-38 · accepts the valid request ${ex.file}`, () => {
      const before = structuredClone(ex.doc);
      const out = validateRequest(ex.doc, { loaded: LOADED });
      expect(out.ok).toBe(true);
      expect(ex.doc).toEqual(before);
    });
  }
  for (const ex of validOutputs) {
    it(`FR-018-38 · accepts the valid result ${ex.file}`, () => {
      expect(validateResult(ex.doc).ok).toBe(true);
    });
  }
});

describe("hostile requests (FR-018-39, FR-018-40)", () => {
  for (const ex of hostileInputs) {
    it(`FR-018-39 · rejects ${ex.file} (${ex.klass}) with ${expectedCodes(ex).join(" or ")}`, () => {
      const out = validateRequest(ex.doc, { loaded: LOADED });
      expect(out.ok).toBe(false);
      if (!out.ok) {
        expect(out.error.kind).toBe("error");
        expect(expectedCodes(ex)).toContain(out.error.code);
        expect(typeof out.error.message).toBe("string");
        expect(out.error.message.length).toBeGreaterThan(0);
      }
    });
  }

  for (const ex of hostileInputs.filter((e) => /^oversized/.test(e.klass ?? ""))) {
    it(`FR-018-40 · ${ex.file}: E_SIZE names the cap (detail.cap, repeated in the message)`, () => {
      const out = validateRequest(ex.doc, { loaded: LOADED });
      expect(out.ok).toBe(false);
      if (!out.ok) {
        expect(out.error.code).toBe("E_SIZE");
        const cap = out.error.detail?.cap;
        expect(cap).toBeDefined();
        expect(out.error.message).toContain(String(cap));
      }
    });
  }

  for (const ex of hostileOutputs) {
    it(`FR-018-38 · rejects the invalid result ${ex.file} (${ex.klass})`, () => {
      const out = validateResult(ex.doc);
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.error.kind).toBe("error");
    });
  }
});

describe("non-finite numbers and malformed envelopes (FR-018-39)", () => {
  const base = validInputs.find((e) => e.file === "engines/geotech.valid.json") as EngineExample;

  for (const [name, bad] of [
    ["NaN", Number.NaN],
    ["+Infinity", Number.POSITIVE_INFINITY],
    ["-Infinity", Number.NEGATIVE_INFINITY],
  ] as const) {
    it(`FR-018-39 · a ${name} in an argument gives E_NONFINITE`, () => {
      const doc = withValueAt(base.doc, ["args", "cohesion_pa"], bad);
      const out = validateRequest(doc, { loaded: LOADED });
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.error.code).toBe("E_NONFINITE");
    });
  }

  it("FR-018-39 · a non-finite number nested in an array of records gives E_NONFINITE", () => {
    const doc = withValueAt(base.doc, ["args", "slices", 1, "weight_n_per_m"], Number.NaN);
    const out = validateRequest(doc, { loaded: LOADED });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.error.code).toBe("E_NONFINITE");
  });

  it("FR-018-39 · property: any numeric leaf of any valid request replaced by NaN or an infinity gives E_NONFINITE", () => {
    const sample = validInputs.filter((e) => numericPaths(e.doc).length > 0);
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: sample.length - 1 }),
        fc.nat(),
        fc.constantFrom(Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY),
        (i, k, bad) => {
          const ex = sample[i] as EngineExample;
          const paths = numericPaths(ex.doc);
          const path = paths[k % paths.length] as Array<string | number>;
          const out = validateRequest(withValueAt(ex.doc, path, bad), { loaded: LOADED });
          return !out.ok && out.error.code === "E_NONFINITE";
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-39 · an unknown engine id gives E_UNKNOWN_ENGINE", () => {
    const out = validateRequest({ ...base.doc, engine: "no-such-engine" }, { loaded: LOADED });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.error.code).toBe("E_UNKNOWN_ENGINE");
  });

  it("FR-018-39 · a version other than the loaded one is rejected (E_UNKNOWN_ENGINE or E_SCHEMA) and a well-formed other version too", () => {
    for (const version of ["0.2.0", "9.9.9", "0.1.1"]) {
      const out = validateRequest({ ...base.doc, engine_version: version }, { loaded: LOADED });
      expect(out.ok).toBe(false);
      if (!out.ok) expect(["E_UNKNOWN_ENGINE", "E_SCHEMA"]).toContain(out.error.code);
    }
  });

  const malformed: Array<[string, unknown]> = [
    ["null", null],
    ["undefined", undefined],
    ["a number", 42],
    ["a string", "geotech"],
    ["an array", [1, 2, 3]],
    ["an empty object", {}],
    ["a function", () => 1],
    ["a 1 MB string", "x".repeat(1_000_000)],
    ["kind output sent as a request", { ...base.doc, kind: "output" }],
    ["prototype pollution", JSON.parse('{"__proto__": {"polluted": true}, "kind": "input"}')],
    ["a symbol key payload", { ...base.doc, args: { [Symbol("s")]: 1 } }],
  ];
  for (const [name, raw] of malformed) {
    it(`FR-018-39 · ${name} is rejected with a typed error and no exception`, () => {
      let out: ReturnType<typeof validateRequest> | undefined;
      expect(() => {
        out = validateRequest(raw, { loaded: LOADED });
      }).not.toThrow();
      expect(out?.ok).toBe(false);
      if (out && !out.ok) expect(ENGINE_ERROR_CODES).toContain(out.error.code);
      expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    });
  }

  it("FR-018-39 · unicode and control characters in an enum field are rejected, not echoed unescaped", () => {
    const doc = { ...base.doc, function: "bishop\u0000\u202e<script>" };
    const out = validateRequest(doc, { loaded: LOADED });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.error.message).not.toContain("<script>");
  });
});

describe("the host (FR-018-38, FR-018-39, FR-018-46)", () => {
  const bishop = validInputs.find((e) => e.file === "engines/geotech.valid.json") as EngineExample;
  const bishopOut = validOutputs.find((e) => e.file === "engines/geotech.valid-output.json") as EngineExample;

  it("FR-018-38 · a valid request reaches the backend once and its validated result comes back", async () => {
    const backend = backendFor(bishopOut.doc);
    const host = createEngineHost({ loaded: LOADED, engines: { geotech: backend } });
    const res = await host.request(bishop.doc);
    expect(backend.run).toHaveBeenCalledTimes(1);
    expect(res).toEqual(bishopOut.doc);
  });

  it("FR-018-39 · every hostile request is answered in under 50 ms with a typed error and the backend is never called", async () => {
    const backend = backendFor(bishopOut.doc);
    const engines = Object.fromEntries(ENGINE_IDS.map((id) => [id, backend]));
    const host = createEngineHost({ loaded: LOADED, engines });
    await host.request(bishop.doc); // warm-up: validator compilation is not part of the 50 ms
    backend.run.mockClear();
    for (const ex of hostileInputs) {
      const t0 = performance.now();
      const res = (await host.request(ex.doc)) as { kind: string; code?: string };
      const dt = performance.now() - t0;
      expect(res.kind, ex.file).toBe("error");
      expect(ENGINE_ERROR_CODES, ex.file).toContain(res.code);
      expect(dt, ex.file).toBeLessThan(50);
    }
    expect(backend.run).not.toHaveBeenCalled();
  });

  it("FR-018-39 · an unknown engine id is answered E_UNKNOWN_ENGINE without calling any backend", async () => {
    const backend = backendFor(bishopOut.doc);
    const host = createEngineHost({ loaded: LOADED, engines: { geotech: backend } });
    const res = (await host.request({ ...bishop.doc, engine: "nope" })) as { code: string };
    expect(res.code).toBe("E_UNKNOWN_ENGINE");
    expect(backend.run).not.toHaveBeenCalled();
  });

  it("FR-018-38 · a backend error becomes E_RUNTIME with the engine's own error name in detail.name and onFailure is told", async () => {
    const err = Object.assign(new Error("scenario has no loader"), { name: "InvalidScenario" });
    const backend = {
      runtime: "des-worker",
      run: vi.fn(async () => Promise.reject(err)),
      terminate: vi.fn(),
    };
    const onFailure = vi.fn();
    const host = createEngineHost({ loaded: LOADED, engines: { geotech: backend }, onFailure });
    const res = (await host.request(bishop.doc)) as { code: string; detail?: { name?: string } };
    expect(res.code).toBe("E_RUNTIME");
    expect(res.detail?.name).toBe("InvalidScenario");
    expect(onFailure).toHaveBeenCalledWith(
      "geotech",
      expect.objectContaining({ kind: "throw", runtime: "des-worker" }),
    );
  });

  it("FR-018-38 · a result that violates the output schema is never returned as a result", async () => {
    const bad = hostileOutputs.find((e) => e.engine === "geotech") as EngineExample;
    const backend = backendFor(bad.doc);
    const host = createEngineHost({ loaded: LOADED, engines: { geotech: backend } });
    const res = (await host.request(bishop.doc)) as { kind: string; code?: string };
    expect(res.kind).toBe("error");
    expect(["E_SCHEMA", "E_RUNTIME", "E_RANGE"]).toContain(res.code);
  });

  it("FR-018-29 · no backend is called before the `ready` promise (capability probe) has settled", async () => {
    let release: () => void = () => undefined;
    const ready = new Promise<void>((r) => {
      release = r;
    });
    const backend = backendFor(bishopOut.doc);
    const host = createEngineHost({ loaded: LOADED, engines: { geotech: backend }, ready });
    const pending = host.request(bishop.doc);
    await Promise.resolve();
    await Promise.resolve();
    expect(backend.run).not.toHaveBeenCalled();
    release();
    await pending;
    expect(backend.run).toHaveBeenCalledTimes(1);
  });

  it("FR-018-38 · two requests in flight are answered independently", async () => {
    const a = backendFor(bishopOut.doc);
    const host = createEngineHost({ loaded: LOADED, engines: { geotech: a } });
    const [r1, r2] = await Promise.all([
      host.request(bishop.doc),
      host.request({ ...bishop.doc, engine: "nope" }),
    ]);
    expect((r1 as { kind: string }).kind).toBe("output");
    expect((r2 as { kind: string }).kind).toBe("error");
  });
});

describe("timeouts (FR-018-46)", () => {
  const bishop = validInputs.find((e) => e.file === "engines/geotech.valid.json") as EngineExample;

  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function hangingBackend() {
    let signal: AbortSignal | undefined;
    return {
      runtime: "geotech-worker",
      run: vi.fn((_req: unknown, ctx: { signal: AbortSignal }) => {
        signal = ctx.signal;
        return new Promise(() => undefined);
      }),
      terminate: vi.fn(),
      aborted: () => signal?.aborted ?? false,
    };
  }

  it("FR-018-46 · a run that exceeds its timeout is terminated, answered E_TIMEOUT and reported to the fallback chain", async () => {
    const backend = hangingBackend();
    const onFailure = vi.fn();
    const host = createEngineHost({
      loaded: LOADED,
      engines: { geotech: backend },
      timeoutMs: { geotech: 100 },
      onFailure,
    });
    const pending = host.request(bishop.doc) as Promise<{ code?: string; kind: string }>;
    await vi.advanceTimersByTimeAsync(99);
    expect(backend.terminate).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    const res = await pending;
    expect(res.kind).toBe("error");
    expect(res.code).toBe("E_TIMEOUT");
    expect(backend.terminate).toHaveBeenCalledTimes(1);
    expect(backend.aborted()).toBe(true);
    expect(onFailure).toHaveBeenCalledWith(
      "geotech",
      expect.objectContaining({ kind: "timeout", runtime: "geotech-worker" }),
    );
  });

  it("FR-018-46 · geotech uses its 5 s timeout of section 7.1 by default", async () => {
    const backend = hangingBackend();
    const host = createEngineHost({ loaded: LOADED, engines: { geotech: backend } });
    const pending = host.request(bishop.doc) as Promise<{ code?: string }>;
    await vi.advanceTimersByTimeAsync(4999);
    expect(backend.terminate).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect((await pending).code).toBe("E_TIMEOUT");
  });

  it("FR-018-46 · the default is 10 s for des and 2 s for haulage, as in the engine table", async () => {
    const haulage = validInputs.find((e) => e.file === "engines/haulage.valid.json") as EngineExample;
    const des = validInputs.find((e) => e.file === "engines/des.valid.json") as EngineExample;
    const hb = hangingBackend();
    const db = hangingBackend();
    const host = createEngineHost({ loaded: LOADED, engines: { haulage: hb, des: db } });
    const h = host.request(haulage.doc) as Promise<{ code?: string }>;
    const d = host.request(des.doc) as Promise<{ code?: string }>;
    await vi.advanceTimersByTimeAsync(2000);
    expect((await h).code).toBe("E_TIMEOUT");
    expect(db.terminate).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(8000);
    expect((await d).code).toBe("E_TIMEOUT");
  });

  it("FR-018-46 · a run that finishes in time is not terminated and its timer does not fire later", async () => {
    const backend = backendFor(
      validOutputs.find((e) => e.file === "engines/geotech.valid-output.json")?.doc as Record<
        string,
        unknown
      >,
    );
    const onFailure = vi.fn();
    const host = createEngineHost({
      loaded: LOADED,
      engines: { geotech: backend },
      timeoutMs: { geotech: 100 },
      onFailure,
    });
    const res = (await host.request(bishop.doc)) as { kind: string };
    expect(res.kind).toBe("output");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(backend.terminate).not.toHaveBeenCalled();
    expect(onFailure).not.toHaveBeenCalled();
  });
});
