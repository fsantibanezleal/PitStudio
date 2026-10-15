// FR-018-65: the lane gate of spec 001 (data-model 2.6), from measurements. Thresholds are the lane_gate keys of
// specs/000-foundation/thresholds.yaml (MB = 10^6 bytes).
export interface LaneMeasurements {
  web_drivable: boolean;
  max_asset_bytes: number;
  interaction_ms: number | null;
  run_ms_t2: number | null;
  trace_bytes: number | null;
}

export const LANE_GATE = {
  assetBytesMax: 25_000_000,
  interactionMsMax: 16,
  runMsMax: 1000,
  traceBytesMax: 10_000_000,
} as const;

const ok = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;

/** `live` iff the gate holds; every missing, negative or non-finite measurement fails its own condition. Never throws. */
export function deriveLane(m: LaneMeasurements): "live" | "replay" {
  if (m === null || typeof m !== "object") return "replay";
  const r = m as unknown as Record<string, unknown>;
  const asset = ok(r.max_asset_bytes) && r.max_asset_bytes <= LANE_GATE.assetBytesMax;
  const time =
    (ok(r.interaction_ms) && r.interaction_ms <= LANE_GATE.interactionMsMax) ||
    (ok(r.run_ms_t2) && r.run_ms_t2 <= LANE_GATE.runMsMax);
  const trace = r.trace_bytes === null || (ok(r.trace_bytes) && r.trace_bytes <= LANE_GATE.traceBytesMax);
  return r.web_drivable === true && asset && time && trace ? "live" : "replay";
}
