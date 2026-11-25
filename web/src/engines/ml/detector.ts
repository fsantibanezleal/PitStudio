// Feed and display of the `detector` engine (FR-018-58, spec 009 FR-009-35). The ORT-web session lives in ort.ts; this module is the part
// that does not need it: the u8 -> float32 lookup, the HWC -> CHW tensor, the `orig_target_sizes` input and the display threshold.
// The post-processor (score, labels, boxes in pixels) is inside the exported graph, so there is no non-maximum suppression here.

/** float32(i) / float32(255) for every byte: the spec 009 preprocessing (values in [0, 1]). */
export const U8_TO_F32: Float32Array = Float32Array.from({ length: 256 }, (_, i) => i / 255);

/** The int64 [1, 2] input `orig_target_sizes`: PitStudio always letterboxes to 640 x 640 (spec 009). */
export const ORIG_TARGET_SIZES: BigInt64Array = BigInt64Array.from([640n, 640n]);

/** Label index order of the exported graph. */
export const DETECTOR_CLASSES: readonly string[] = [
  "haul_truck",
  "shovel",
  "light_vehicle",
  "person",
  "boulder",
];

/** HWC uint8 -> CHW float32 `images` data (one frame): out[c * rows * cols + y * cols + x]. */
export function frameToTensor(frame: Uint8Array, rows: number, cols: number): Float32Array {
  if (!Number.isInteger(rows) || rows < 1 || !Number.isInteger(cols) || cols < 1)
    throw new RangeError("rows and cols must be positive integers");
  if (frame.length !== rows * cols * 3)
    throw new RangeError(
      `the frame holds ${frame.length} bytes, ${rows} x ${cols} x 3 = ${rows * cols * 3} expected`,
    );
  const plane = rows * cols;
  const out = new Float32Array(3 * plane);
  for (let i = 0; i < plane; i++) {
    const p = 3 * i;
    out[i] = U8_TO_F32[frame[p] as number] as number;
    out[plane + i] = U8_TO_F32[frame[p + 1] as number] as number;
    out[2 * plane + i] = U8_TO_F32[frame[p + 2] as number] as number;
  }
  return out;
}

export interface DetectorOutput {
  boxes: Float32Array;
  labels: BigInt64Array | number[];
  scores: Float32Array;
}

export interface Detection {
  label: string;
  score: number;
  box_xyxy_px: [number, number, number, number];
}

/** The rows whose score is strictly above `threshold`, with the class name, in the graph's order; no suppression. */
export function showDetections(output: DetectorOutput, threshold: number): Detection[] {
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1)
    throw new RangeError("the display threshold must lie in [0, 1]");
  const n = output.scores.length;
  if (output.labels.length !== n || output.boxes.length !== 4 * n)
    throw new RangeError("boxes, labels and scores have inconsistent lengths");
  const shown: Detection[] = [];
  for (let i = 0; i < n; i++) {
    const label = Number(output.labels[i]);
    if (!Number.isInteger(label) || label < 0 || label >= DETECTOR_CLASSES.length)
      throw new RangeError(
        `label index ${String(output.labels[i])} is outside 0..${DETECTOR_CLASSES.length - 1}`,
      );
    const score = output.scores[i] as number;
    if (!(score > threshold)) continue;
    const b = 4 * i;
    shown.push({
      label: DETECTOR_CLASSES[label] as string,
      score,
      box_xyxy_px: [
        output.boxes[b] as number,
        output.boxes[b + 1] as number,
        output.boxes[b + 2] as number,
        output.boxes[b + 3] as number,
      ],
    });
  }
  return shown;
}
