import { sanitize } from "./SafeText";

/** A string clipped for inline use: unsafe characters replaced, at most 200 code points, an ellipsis when cut. */
export function clip(value: unknown): string {
  const { text, cut } = sanitize(String(value ?? ""), 200);
  return cut ? `${text}…` : text;
}

/** Memory in GiB, shown with a "GB" unit as the reference machine does (17,171,480,576 B reads 16). One decimal at most. */
export function gib(bytes: number): string {
  return String(Number((bytes / 2 ** 30).toFixed(1)));
}

/** A finite number as its shortest text, else null. Percentages and other products are normalised against float noise. */
export function num(value: unknown): string | null {
  return typeof value === "number" && Number.isFinite(value) ? String(Number(value.toPrecision(12))) : null;
}

export function percent(fraction: unknown): string | null {
  return typeof fraction === "number" && Number.isFinite(fraction) ? num(fraction * 100) : null;
}

/** UTC calendar date (YYYY-MM-DD) of an ISO timestamp, or null when it does not parse. */
export function utcDate(created: unknown): string | null {
  const time = Date.parse(String(created ?? ""));
  return Number.isNaN(time) ? null : new Date(time).toISOString().slice(0, 10);
}

/** The stage of a run card that made an artefact: same id and, when the artefact names a variant, the same variant. */
export function stageOf<S extends { key: { id: string; variant?: string } }>(
  run: { stages: S[] } | null | undefined,
  producerStage: { id: string; variant?: string },
): S | undefined {
  return run?.stages.find(
    (s) =>
      s.key.id === producerStage.id &&
      (producerStage.variant === undefined || s.key.variant === producerStage.variant),
  );
}

export const THROTTLE_REASONS = [
  "sw_power_cap",
  "sw_thermal",
  "hw_thermal",
  "hw_slowdown",
  "power_brake",
] as const;
