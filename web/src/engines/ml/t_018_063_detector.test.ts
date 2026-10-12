// T-018-063 [red] · FR-018-58 (detector feed: the u8 -> float32 lookup, the `orig_target_sizes` input, the display threshold, no NMS) and P-018-27
// (display monotonicity and permutation invariance). Browser half (boxes within 0.5 px, labels top-1 agreement >= 0.995 on every golden image):
// web/e2e/parity/t_018_063_detector.spec.ts.
//
// Expected API (module `~/engines/ml/detector`, file web/src/engines/ml/detector.ts; the ORT-web session lives in ort.ts)
//     U8_TO_F32: Float32Array                      256 entries; entry i is float32(i) / float32(255) (the spec 009 preprocessing: values in [0, 1])
//     frameToTensor(frame: Uint8Array, rows: number, cols: number): Float32Array
//         HWC uint8 -> CHW float32 `images` data: out[c * rows * cols + y * cols + x] = U8_TO_F32[frame[(y * cols + x) * 3 + c]]; RangeError when the frame length
//         is not rows x cols x 3 or rows or cols is not a positive integer
//     ORIG_TARGET_SIZES: BigInt64Array             the int64 [1, 2] input `orig_target_sizes` = [[640, 640]] (PitStudio always letterboxes to 640 x 640; spec 009)
//     DETECTOR_CLASSES: readonly string[]          ["haul_truck", "shovel", "light_vehicle", "person", "boulder"], the label index order of the exported graph
//     showDetections(output: { boxes: Float32Array; labels: BigInt64Array | number[]; scores: Float32Array }, threshold: number):
//         Array<{ label: string; score: number; box_xyxy_px: [number, number, number, number] }>
//         `boxes` is n x 4 row-major xyxy in pixels (n = 300 for the graph, any n here), the graph's own order is kept; a row is shown iff its score is
//         strictly above `threshold`; there is NO non-maximum suppression and no box conversion (FR-009-35: the post-processor is inside the graph)
//         RangeError for a threshold outside [0, 1] or non-finite, a label index outside 0..4, or arrays of inconsistent length
//
// Oracles (independent of the code under test): numpy 2.5.3 `np.arange(256, dtype=np.float32) / np.float32(255)` (the table's SHA-256 and spot values);
// the CHW layout written out by hand on a 2 x 3 image; the model I/O of FR-009-35 (float32 [N, 3, 640, 640] in [0, 1], int64 [N, 2]); the metamorphic
// relations of P-018-27 (thresholding is a filter; set semantics).
import { createHash } from "node:crypto";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import {
  DETECTOR_CLASSES,
  frameToTensor,
  ORIG_TARGET_SIZES,
  showDetections,
  U8_TO_F32,
} from "~/engines/ml/detector";

describe("u8 -> float32 lookup (FR-018-58)", () => {
  it("FR-018-58 · the table has 256 float32 entries whose bytes hash to numpy's float32(i) / float32(255): 010413ef…1fc8", () => {
    expect(U8_TO_F32).toBeInstanceOf(Float32Array);
    expect(U8_TO_F32).toHaveLength(256);
    const bytes = new Uint8Array(U8_TO_F32.buffer, U8_TO_F32.byteOffset, U8_TO_F32.byteLength);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      "010413efe9fc4438fee48de66c4d09f377b28af6a9fe2522201e8c1dbb831fc8",
    );
  });

  it("FR-018-58 · spot values equal numpy's, bit for bit: 0, 1/255, 2/255, 0.2 (51), 127, 128, 254 and 1 (255)", () => {
    const want: Array<[number, number]> = [
      [0, 0],
      [1, 0.003921568859368563],
      [2, 0.007843137718737125],
      [51, 0.20000000298023224],
      [127, 0.49803921580314636],
      [128, 0.501960813999176],
      [254, 0.9960784316062927],
      [255, 1],
    ];
    for (const [i, v] of want) expect(U8_TO_F32[i], `entry ${i}`).toBe(v);
  });

  it("FR-018-58 · every entry equals Math.fround(i / 255) and the table is strictly increasing inside [0, 1]", () => {
    for (let i = 0; i < 256; i++) expect(U8_TO_F32[i]).toBe(Math.fround(i / 255));
    for (let i = 1; i < 256; i++) expect((U8_TO_F32[i] as number) > (U8_TO_F32[i - 1] as number)).toBe(true);
    expect(U8_TO_F32[0]).toBe(0);
    expect(U8_TO_F32[255]).toBe(1);
  });
});

describe("the model input (FR-018-58)", () => {
  it("FR-018-58 · HWC uint8 becomes CHW float32: a 2 x 3 image written out by hand", () => {
    // pixels (y, x): R, G, B
    const frame = Uint8Array.from([
      0, 10, 20, /* (0,0) */ 1, 11, 21, /* (0,1) */ 2, 12, 22 /* (0,2) */, 3, 13, 23, /* (1,0) */ 4, 14, 24,
      /* (1,1) */ 255, 15, 25 /* (1,2) */,
    ]);
    const t = frameToTensor(frame, 2, 3);
    expect(t).toBeInstanceOf(Float32Array);
    expect(t).toHaveLength(18);
    const want = [
      // channel R over (y, x) row-major, then G, then B
      0, 1, 2, 3, 4, 255, 10, 11, 12, 13, 14, 15, 20, 21, 22, 23, 24, 25,
    ].map((v) => Math.fround(v / 255));
    expect(Array.from(t)).toEqual(want);
  });

  it("FR-018-58 · the shipped 640 x 640 frame gives 3 x 640 x 640 values in [0, 1] and every value is the table entry of its byte", () => {
    const frame = new Uint8Array(640 * 640 * 3);
    for (let i = 0; i < frame.length; i++) frame[i] = (i * 7 + 3) & 255;
    const t = frameToTensor(frame, 640, 640);
    expect(t).toHaveLength(3 * 640 * 640);
    for (const i of [0, 1, 2, 3, 640 * 3, 640 * 640 * 3 - 1, 123456]) {
      const pixel = Math.floor(i / 3);
      const c = i % 3;
      expect(t[c * 640 * 640 + pixel], `byte ${i}`).toBe(U8_TO_F32[frame[i] as number]);
    }
    expect(Math.min(...t.slice(0, 4096))).toBeGreaterThanOrEqual(0);
    expect(Math.max(...t.slice(0, 4096))).toBeLessThanOrEqual(1);
  });

  it("FR-018-58 · the second input is the int64 [[640, 640]]", () => {
    expect(ORIG_TARGET_SIZES).toBeInstanceOf(BigInt64Array);
    expect(Array.from(ORIG_TARGET_SIZES)).toEqual([640n, 640n]);
  });

  it("FR-018-58 · the frame is not modified and a wrong length or non-positive size is a RangeError", () => {
    const frame = new Uint8Array(2 * 3 * 3).fill(7);
    const copy = Uint8Array.from(frame);
    frameToTensor(frame, 2, 3);
    expect(frame).toEqual(copy);
    expect(() => frameToTensor(new Uint8Array(17), 2, 3)).toThrow(RangeError);
    expect(() => frameToTensor(frame, 0, 3)).toThrow(RangeError);
    expect(() => frameToTensor(frame, 2, -3)).toThrow(RangeError);
    expect(() => frameToTensor(frame, 1.5, 4)).toThrow(RangeError);
  });
});

describe("display threshold, no NMS (FR-018-58, P-018-27)", () => {
  const out = {
    boxes: Float32Array.from([
      10, 20, 110, 220, /* */ 12, 22, 112, 222, /* */ 300, 300, 340, 360, /* */ 5, 5, 6, 6,
    ]),
    labels: BigInt64Array.from([0n, 0n, 3n, 4n]),
    scores: Float32Array.from([0.9, 0.85, 0.5, 0.1]),
  };

  it("FR-018-58 · the classes are the five of the exported graph, in label order", () => {
    expect([...DETECTOR_CLASSES]).toEqual(["haul_truck", "shovel", "light_vehicle", "person", "boulder"]);
  });

  it("FR-018-58 · rows with a score above the threshold are shown with their class name, score and box, in the graph's order", () => {
    const shown = showDetections(out, 0.4);
    expect(shown).toHaveLength(3);
    expect(shown[0]).toEqual({
      label: "haul_truck",
      score: Math.fround(0.9),
      box_xyxy_px: [10, 20, 110, 220],
    });
    expect(shown[2]).toEqual({ label: "person", score: Math.fround(0.5), box_xyxy_px: [300, 300, 340, 360] });
  });

  it("FR-018-58 · no non-maximum suppression: two almost identical boxes of the same class (IoU about 0.9) are both shown", () => {
    const shown = showDetections(out, 0.4);
    expect(shown.filter((d: { label: string }) => d.label === "haul_truck")).toHaveLength(2);
  });

  it("FR-018-58 · a threshold of 0 shows every row with a positive score, a threshold of 1 shows none, and an empty output shows nothing", () => {
    expect(showDetections(out, 0)).toHaveLength(4);
    expect(showDetections(out, 1)).toHaveLength(0);
    expect(
      showDetections(
        { boxes: new Float32Array(0), labels: new BigInt64Array(0), scores: new Float32Array(0) },
        0.3,
      ),
    ).toEqual([]);
  });

  it("FR-018-58 · labels given as plain numbers are accepted as well", () => {
    const shown = showDetections({ ...out, labels: [0, 0, 3, 4] }, 0.4);
    expect(shown.map((d: { label: string }) => d.label)).toEqual(["haul_truck", "haul_truck", "person"]);
  });

  it("FR-018-58 · a threshold outside [0, 1] or non-finite, a label index outside 0..4 and inconsistent array lengths are a RangeError", () => {
    for (const t of [-0.1, 1.1, Number.NaN, Number.POSITIVE_INFINITY])
      expect(() => showDetections(out, t)).toThrow(RangeError);
    expect(() => showDetections({ ...out, labels: BigInt64Array.from([0n, 0n, 7n, 4n]) }, 0.4)).toThrow(
      RangeError,
    );
    expect(() => showDetections({ ...out, scores: Float32Array.from([0.9, 0.85, 0.5]) }, 0.4)).toThrow(
      RangeError,
    );
    expect(() => showDetections({ ...out, boxes: Float32Array.from([1, 2, 3]) }, 0.4)).toThrow(RangeError);
  });

  const outputArb = fc.integer({ min: 1, max: 300 }).chain((n) =>
    fc.record({
      boxes: fc
        .array(fc.float({ min: 0, max: 640, noNaN: true }), { minLength: 4 * n, maxLength: 4 * n })
        .map((a) => Float32Array.from(a)),
      labels: fc.array(fc.integer({ min: 0, max: 4 }), { minLength: n, maxLength: n }),
      scores: fc
        .array(fc.float({ min: 0, max: 1, noNaN: true }), { minLength: n, maxLength: n })
        .map((a) => Float32Array.from(a)),
    }),
  );
  type Det = { label: string; score: number; box_xyxy_px: number[] };
  const key = (d: Det) => `${d.label}|${d.score}|${d.box_xyxy_px.join(",")}`;

  it("P-018-27 · raising the score threshold shows a subset of the detections shown before", () => {
    fc.assert(
      fc.property(
        outputArb,
        fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        (o, a, b) => {
          const lo = Math.min(a, b);
          const hi = Math.max(a, b);
          const before = new Set(showDetections(o, lo).map(key));
          return showDetections(o, hi).every((d: Det) => before.has(key(d)));
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-27 · permuting the graph's output rows leaves the shown set unchanged", () => {
    fc.assert(
      fc.property(outputArb, fc.double({ min: 0, max: 1, noNaN: true }), fc.nat(), (o, threshold, seed) => {
        const n = o.scores.length;
        const order = Array.from({ length: n }, (_, i) => i).sort(
          (p, q) => ((p * 7919 + seed) % 1013) - ((q * 7919 + seed) % 1013) || p - q,
        );
        const permuted = {
          boxes: Float32Array.from(
            order.flatMap((i) => [0, 1, 2, 3].map((k) => o.boxes[4 * i + k] as number)),
          ),
          labels: order.map((i) => o.labels[i] as number),
          scores: Float32Array.from(order.map((i) => o.scores[i] as number)),
        };
        const a = showDetections(o, threshold).map(key).sort();
        const b = showDetections(permuted, threshold).map(key).sort();
        return JSON.stringify(a) === JSON.stringify(b);
      }),
      { numRuns: 200 },
    );
  });
});
