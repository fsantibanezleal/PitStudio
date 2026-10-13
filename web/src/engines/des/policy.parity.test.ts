// @vitest-environment node
//
// T-007-057 · the TypeScript twin runs the exported dispatch policies with ONNX Runtime Web (WASM) and agrees with the Python reference (ONNX Runtime CPU): FR-007-32, with the input and
// pin guards of FR-007-31, FR-007-33 and FR-007-44 on the TypeScript side.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-32 (when the twin runs a golden policy shift with ONNX Runtime Web (WASM), its trace equals the Python reference (ONNX Runtime CPU) up to the
// first decision whose top-2 logit margin in the reference is <= 2e-4; >= 99.5 % of golden policy shifts are identical end to end), section 7 "Policy near-ties" (the CPU and WASM backends differ by
// up to 1e-4 in fp32, which can flip an argmax at a near-tie), FR-007-31 (the DES applies the mask and the argmax, ties to the lowest target index, in Python and TypeScript), FR-007-33 (every
// target masked: `NoServiceableLoader`), FR-007-44 (a wrong shape, dtype or layout version, a non-finite feature or an ONNX file whose SHA-256 differs from its manifest stops the run with
// `InvalidPolicyInput` or `PolicyPinMismatch`, no partial result) and NFR-007-03 (each policy < 2 MB).
//
// Oracle: logits computed by the Python `onnxruntime` CPU provider (version recorded in each file) on 200 golden states, committed in tests/fixtures/haulage/policy/ (the generator is the throwaway
// script of the test author; the numbers do not come from the code under test); numpy-style masked argmax rewritten here (first maximum wins); the top-2 margin rule of FR-007-32 evaluated on those
// reference logits; `node:crypto` SHA-256 for the pin; the smoke scenario of the spec's contract examples for the shift checks.
//
// Fixture layout (tests/fixtures/haulage/policy/): states.json = {n: 200, truck_f32 [200,40,12], target_f32 [200,16,9], truck_mask_u8 [200,40], target_mask_u8 [200,16]} (base64, little-endian, row-major);
// <ppo|attention>/policy.onnx, <ppo|attention>/policy-io.json (a `dispatch-policy-io` document with the file's SHA-256), <ppo|attention>/logits-ort-cpu.json = {n: 200, logits_f32 [200,16]}.
//
// Expected API (module `~/engines/des/policy`; errors in `~/engines/des/errors`: InvalidPolicyInput, PolicyPinMismatch, NoServiceableLoader):
//   type PolicyInput = { truck: Float32Array /* 480 = [1,40,12] */; target: Float32Array /* 144 = [1,16,9] */; truckMask: Uint8Array /* 40 */; targetMask: Uint8Array /* 16 */ }
//   loadPolicy(onnx: Uint8Array, manifest: unknown): Promise<Policy>
//     the manifest is a parsed `policy-io.json`; checks layout_version === 1 (InvalidPolicyInput otherwise, also for a missing or non-object manifest) and the SHA-256 of `onnx` against
//     manifest.policy.onnx.sha256 (PolicyPinMismatch); creates an ONNX Runtime Web session on the WASM backend.
//   Policy: { id: "ppo" | "attention"; sha256: string; artefactId: string; logits(input: PolicyInput): Promise<Float32Array> /* 16 */; decide(input: PolicyInput): Promise<number>; dispose(): Promise<void> }
//     both validate lengths, element types and finiteness of every feature, padded slots included (InvalidPolicyInput); `decide` = maskedArgmax(logits, targetMask).
//   maskedArgmax(logits: ArrayLike<number>, mask: ArrayLike<number | boolean>): number    the lowest index among the maximal logits of the true entries; NoServiceableLoader when none is true;
//     InvalidPolicyInput for a non-finite logit on a true entry (a non-finite logit on a masked entry is ignored).
//   runShiftWithPolicy(bundle: unknown, seed: bigint | number, policy: { decide(input: PolicyInput): Promise<number> | number } & { sha256: string }): Promise<DesTrace>
//     the twin's `runShift` for a bundle whose dispatcher is `ppo` or `attention`; the bundle's dispatcher.policy.onnx_sha256 must equal `policy.sha256` (PolicyPinMismatch before any event); the policy is called
//     once per `dispatch` event with the layout above and must return a serviceable target slot (the DES falls back to nothing: a returned masked slot is an InvalidPolicyInput); the trace has the shape
//     of `runShift` and the same determinism (the same bundle, seed and policy give identical traces).

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { InvalidPolicyInput, NoServiceableLoader, PolicyPinMismatch } from "~/engines/des/errors";
import {
  loadPolicy,
  maskedArgmax,
  type Policy,
  type PolicyInput,
  runShiftWithPolicy,
} from "~/engines/des/policy";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
const FIX = resolve(REPO, "tests/fixtures/haulage/policy");
const EX = resolve(REPO, "specs/007-haulage-dispatch/contracts/examples");

const f32 = (b64: string): Float32Array => {
  const buf = Buffer.from(b64, "base64");
  return new Float32Array(new Uint8Array(buf).buffer);
};
const u8 = (b64: string): Uint8Array => new Uint8Array(Buffer.from(b64, "base64"));
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf-8"));

const S = readJson(resolve(FIX, "states.json"));
const N = S.n as number;
const TRUCK = f32(S.truck_f32);
const TARGET = f32(S.target_f32);
const TMASK = u8(S.truck_mask_u8);
const GMASK = u8(S.target_mask_u8);

const state = (i: number): PolicyInput => ({
  truck: TRUCK.slice(i * 480, (i + 1) * 480),
  target: TARGET.slice(i * 144, (i + 1) * 144),
  truckMask: TMASK.slice(i * 40, (i + 1) * 40),
  targetMask: GMASK.slice(i * 16, (i + 1) * 16),
});

function refMaskedArgmax(logits: Float32Array, mask: Uint8Array): number {
  let best = -1;
  for (let j = 0; j < 16; j++) if (mask[j] && (best < 0 || logits[j] > logits[best])) best = j;
  return best;
}
function refMargin(logits: Float32Array, mask: Uint8Array): number {
  const v: number[] = [];
  for (let j = 0; j < 16; j++) if (mask[j]) v.push(logits[j] as number);
  v.sort((a, b) => b - a);
  return v.length < 2 ? Number.POSITIVE_INFINITY : (v[0] as number) - (v[1] as number);
}

type Arch = "ppo" | "attention";
const ARCHS: Arch[] = ["ppo", "attention"];
const files = (a: Arch) => ({
  onnx: new Uint8Array(readFileSync(resolve(FIX, a, "policy.onnx"))),
  manifest: readJson(resolve(FIX, a, "policy-io.json")),
  ref: f32(readJson(resolve(FIX, a, "logits-ort-cpu.json")).logits_f32),
});

async function thrown(f: () => unknown): Promise<unknown> {
  try {
    await f();
  } catch (e) {
    return e;
  }
  return undefined;
}

describe("FR-007-44 · the fixture is what the spec says it is", () => {
  for (const a of ARCHS) {
    it(`NFR-007-03 · ${a}: the ONNX file is below 2 MB and its pin is the SHA-256 of the bytes`, () => {
      const { onnx, manifest } = files(a);
      expect(onnx.byteLength).toBeLessThan(2_000_000);
      expect(createHash("sha256").update(onnx).digest("hex")).toBe(manifest.policy.onnx.sha256);
      expect(manifest.layout_version).toBe(1);
    });
  }
});

describe("FR-007-31 · the masked argmax", () => {
  const table: [string, number[], number[], number][] = [
    ["a tie goes to the lowest index", [1, 3, 3, 2], [1, 1, 1, 1], 1],
    ["a masked maximum is ignored", [5, 3, 3, 2], [0, 1, 1, 1], 1],
    ["all equal: the lowest serviceable index", [0, 0, 0, 0], [0, 0, 1, 1], 2],
    ["negative logits", [-9, -8, -7], [1, 1, 1], 2],
    ["huge magnitudes", [1e30, -1e30, 0], [0, 1, 1], 2],
    ["a 1e-6 margin still decides", [2, 2 + 1e-6, 2], [1, 1, 1], 1],
  ];
  for (const [name, logits, mask, want] of table) {
    it(`FR-007-31 · ${name}`, () => {
      expect(maskedArgmax(Float32Array.from(logits), mask)).toBe(want);
    });
  }
  it("FR-007-31 · booleans work as the mask too", () => {
    expect(maskedArgmax([0, 1, 1], [false, true, true])).toBe(1);
  });
  it("FR-007-33 · every target masked is NoServiceableLoader", () => {
    expect(() => maskedArgmax(new Float32Array(16), new Uint8Array(16))).toThrow(NoServiceableLoader);
    expect(() => maskedArgmax([], [])).toThrow(NoServiceableLoader);
  });
  for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    it(`FR-007-44 · a non-finite logit (${String(bad)}) on a serviceable target is an input error, on a masked one it is ignored`, () => {
      expect(() => maskedArgmax([0, 0, bad, 0], [1, 1, 1, 0])).toThrow(InvalidPolicyInput);
      expect(maskedArgmax([0, 0, 0, bad], [1, 1, 1, 0])).toBe(0);
    });
  }
});

describe("FR-007-32 · ONNX Runtime Web (WASM) against ONNX Runtime CPU on 200 golden states", () => {
  for (const a of ARCHS) {
    describe(a, () => {
      let policy: Policy;
      const f = files(a);
      beforeAll(async () => {
        policy = await loadPolicy(f.onnx, f.manifest);
      });

      it("FR-007-32 · the loaded policy reports its identity and pin", () => {
        expect(policy.id).toBe(a);
        expect(policy.sha256).toBe(f.manifest.policy.onnx.sha256);
        expect(policy.artefactId).toBe(f.manifest.policy.artefact_id);
      });

      it("FR-007-32 · logits agree with the CPU reference to 1e-4 on every serviceable target of every state", async () => {
        let maxAbs = 0;
        for (let i = 0; i < N; i++) {
          const lg = await policy.logits(state(i));
          expect(lg).toBeInstanceOf(Float32Array);
          expect(lg.length).toBe(16);
          for (let j = 0; j < 16; j++) {
            if (!GMASK[i * 16 + j]) continue;
            const d = Math.abs((lg[j] as number) - (f.ref[i * 16 + j] as number));
            if (d > maxAbs) maxAbs = d;
            expect(d).toBeLessThanOrEqual(1e-5 + 1e-3 * Math.abs(f.ref[i * 16 + j] as number)); // SC-007-03 tolerances: rtol 1e-3, atol 1e-5
          }
        }
        expect(maxAbs).toBeLessThanOrEqual(1e-4);
      });

      it("FR-007-32 · decisions are identical wherever the reference top-2 margin exceeds 2e-4, and at least 99.5 % overall", async () => {
        let same = 0;
        let decided = 0;
        for (let i = 0; i < N; i++) {
          const ref = f.ref.slice(i * 16, (i + 1) * 16);
          const mask = GMASK.slice(i * 16, (i + 1) * 16);
          const want = refMaskedArgmax(ref, mask);
          const got = await policy.decide(state(i));
          if (refMargin(ref, mask) > 2e-4) {
            expect(got, `state ${i}`).toBe(want);
            decided++;
          }
          if (got === want) same++;
        }
        expect(decided).toBeGreaterThanOrEqual(Math.floor(0.995 * N));
        expect(same / N).toBeGreaterThanOrEqual(0.995);
      });

      it("FR-007-31 · a decision is always a serviceable target", async () => {
        for (let i = 0; i < N; i++) expect(GMASK[i * 16 + (await policy.decide(state(i)))]).toBe(1);
      });

      it("FR-007-33 · with every target masked the decision is NoServiceableLoader", async () => {
        const s = state(3);
        s.targetMask = new Uint8Array(16);
        expect(await thrown(() => policy.decide(s))).toBeInstanceOf(NoServiceableLoader);
      });

      const hostile = (): [string, () => PolicyInput][] => {
        const nan = (k: "truck" | "target", at: number) => () => {
          const s = state(5);
          s[k][at] = Number.NaN;
          return s;
        };
        const inf = (k: "truck" | "target", at: number, v: number) => () => {
          const s = state(5);
          s[k][at] = v;
          return s;
        };
        return [
          ["NaN in a real truck", nan("truck", 12 * 2 + 3)],
          ["NaN in a padded truck slot", nan("truck", 12 * 39 + 4)],
          ["+Infinity in a padded target slot", inf("target", 9 * 15 + 2, Number.POSITIVE_INFINITY)],
          ["-Infinity in a real target", inf("target", 1, Number.NEGATIVE_INFINITY)],
          ["short truck tensor", () => ({ ...state(5), truck: new Float32Array(479) })],
          ["long truck tensor", () => ({ ...state(5), truck: new Float32Array(481) })],
          ["short target tensor", () => ({ ...state(5), target: new Float32Array(143) })],
          [
            "empty tensors",
            () => ({
              truck: new Float32Array(0),
              target: new Float32Array(0),
              truckMask: new Uint8Array(0),
              targetMask: new Uint8Array(0),
            }),
          ],
          ["short truck mask", () => ({ ...state(5), truckMask: new Uint8Array(39) })],
          ["long target mask", () => ({ ...state(5), targetMask: new Uint8Array(17) })],
          [
            "float64 truck tensor",
            () => ({ ...state(5), truck: new Float64Array(480) as unknown as Float32Array }),
          ],
          [
            "plain array target tensor",
            () => ({ ...state(5), target: Array.from(state(5).target) as unknown as Float32Array }),
          ],
          ["float mask", () => ({ ...state(5), targetMask: new Float32Array(16) as unknown as Uint8Array })],
          ["null input", () => null as unknown as PolicyInput],
          ["missing field", () => ({ truck: state(5).truck }) as unknown as PolicyInput],
        ];
      };
      for (const [name, make] of hostile()) {
        it(`FR-007-44 · ${name} is InvalidPolicyInput, and the next valid call still works`, async () => {
          expect(await thrown(() => policy.decide(make()))).toBeInstanceOf(InvalidPolicyInput);
          expect(await thrown(() => policy.logits(make()))).toBeInstanceOf(InvalidPolicyInput);
          expect(GMASK[5 * 16 + (await policy.decide(state(5)))]).toBe(1);
        });
      }
    });
  }
});

describe("FR-007-44 · loading", () => {
  const f = files("ppo");
  it("FR-007-44 · a tampered ONNX file is a PolicyPinMismatch", async () => {
    const bad = f.onnx.slice();
    bad[Math.floor(bad.length / 2)] = (bad[Math.floor(bad.length / 2)] as number) ^ 1;
    expect(await thrown(() => loadPolicy(bad, f.manifest))).toBeInstanceOf(PolicyPinMismatch);
  });
  for (const digest of ["0".repeat(64), "f".repeat(64), "", "xyz", null, 7]) {
    it(`FR-007-44 · a manifest digest of ${JSON.stringify(digest)} is a pin mismatch or an input error`, async () => {
      const m = structuredClone(f.manifest);
      m.policy.onnx.sha256 = digest;
      const e = await thrown(() => loadPolicy(f.onnx, m));
      expect(e instanceof PolicyPinMismatch || e instanceof InvalidPolicyInput).toBe(true);
    });
  }
  for (const v of [0, 2, 99, "1", null, true]) {
    it(`FR-007-44 · layout_version ${JSON.stringify(v)} is InvalidPolicyInput`, async () => {
      const m = structuredClone(f.manifest);
      m.layout_version = v;
      expect(await thrown(() => loadPolicy(f.onnx, m))).toBeInstanceOf(InvalidPolicyInput);
    });
  }
  for (const m of [
    null,
    undefined,
    3,
    "x",
    [],
    {},
    { layout_version: 1 },
    { layout_version: 1, policy: {} },
  ]) {
    it(`FR-007-44 · a malformed manifest ${JSON.stringify(m)} is InvalidPolicyInput`, async () => {
      expect(await thrown(() => loadPolicy(f.onnx, m))).toBeInstanceOf(InvalidPolicyInput);
    });
  }
  it("FR-007-44 · empty or garbage bytes with a matching digest are rejected, not crashed on", async () => {
    const garbage = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
    const m = structuredClone(f.manifest);
    m.policy.onnx.sha256 = createHash("sha256").update(garbage).digest("hex");
    const e = await thrown(() => loadPolicy(garbage, m));
    expect(e).toBeInstanceOf(Error);
    expect(e instanceof PolicyPinMismatch).toBe(false); // the pin matches; the file is simply not a model
  });
});

describe("FR-007-32 · a policy shift in the twin", () => {
  // biome-ignore lint/suspicious/noExplicitAny: bundles are plain JSON here
  type B = Record<string, any>;
  const bundleFor = (a: Arch, sha256: string, artefact: string): B => {
    const b = readJson(resolve(EX, "haul-scenario.valid.json")) as B;
    b.horizon_s = 3600;
    b.dispatcher = { id: a, policy: { artefact_id: artefact, onnx_sha256: sha256, layout_version: 1 } };
    b.fleet = [1, 2, 3, 4, 5, 6].map((id) => ({
      id,
      truck_class: "CAT_793F",
      start_loader: id % 2 === 1 ? 1 : 2,
    }));
    for (const ld of b.loaders) ld.destination_dump = b.dumps[0];
    return b;
  };

  for (const a of ARCHS) {
    describe(a, () => {
      const f = files(a);
      let policy: Policy;
      beforeAll(async () => {
        policy = await loadPolicy(f.onnx, f.manifest);
      });

      it("FR-007-32 · the shift is deterministic, calls the policy once per dispatch event and only ever picks serviceable targets", async () => {
        const b = bundleFor(a, policy.sha256, policy.artefactId);
        const picks: { input: PolicyInput; slot: number }[] = [];
        const spy = {
          sha256: policy.sha256,
          decide: async (input: PolicyInput) => {
            const slot = await policy.decide(input);
            picks.push({ input, slot });
            return slot;
          },
        };
        const t1 = await runShiftWithPolicy(b, 7n, spy);
        const dispatches = t1.events.filter((e: { kind: string }) => e.kind === "dispatch").length;
        expect(dispatches).toBeGreaterThan(5);
        expect(picks.length).toBe(dispatches);
        for (const p of picks) expect(p.input.targetMask[p.slot]).toBe(1);
        const t2 = await runShiftWithPolicy(b, 7n, policy);
        expect(JSON.stringify(t2.events)).toBe(JSON.stringify(t1.events));
        expect(JSON.stringify(t2.cyclelog)).toBe(JSON.stringify(t1.cyclelog));
        expect(t2.results.tonnes_t).toBeGreaterThan(0);
      });

      it("FR-007-44 · a bundle pinned to another policy file is a PolicyPinMismatch before any event", async () => {
        const b = bundleFor(a, "0".repeat(64), policy.artefactId);
        let calls = 0;
        const counting = {
          sha256: policy.sha256,
          decide: (i: PolicyInput) => {
            calls += 1;
            return policy.decide(i);
          },
        };
        expect(await thrown(() => runShiftWithPolicy(b, 1n, counting))).toBeInstanceOf(PolicyPinMismatch);
        expect(calls).toBe(0);
      });

      it("FR-007-44 · a policy that returns a masked or out-of-range slot stops the run with InvalidPolicyInput and no partial trace", async () => {
        const b = bundleFor(a, policy.sha256, policy.artefactId);
        for (const slot of [-1, 16, 1.5, Number.NaN, 99]) {
          const rogue = { sha256: policy.sha256, decide: () => slot };
          expect(await thrown(() => runShiftWithPolicy(b, 1n, rogue))).toBeInstanceOf(InvalidPolicyInput);
        }
      });

      it("FR-007-31 · a classical dispatcher in the bundle is not run through a policy", async () => {
        const b = bundleFor(a, policy.sha256, policy.artefactId);
        b.dispatcher = { id: "sptf" };
        expect(await thrown(() => runShiftWithPolicy(b, 1n, policy))).toBeInstanceOf(InvalidPolicyInput);
      });
    });
  }
});
