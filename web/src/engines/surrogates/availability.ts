// Availability of a published surrogate (FR-011-09, FR-011-38): the descriptor `models/<model_id>.surrogate-io.json` (DC-011-02) and the
// published evaluation `models/<model_id>.evaluation.json` beside the ONNX file. The scene shows the real state of the model:
//   not-published       no descriptor: "not yet trained", nothing is computed;
//   unevaluated         a descriptor without an evaluation report: no live rollout is offered for a model nobody has evaluated;
//   evaluation-failed   the evaluation report does not pass (sc_011_01 is not "pass"): no live rollout is offered;
//   ready               descriptor and a passing evaluation.
// A missing, aborted, unparsable or foreign document publishes nothing. Never throws.
import { useEffect, useState } from "react";

export type AvailabilityState = "not-published" | "unevaluated" | "evaluation-failed" | "ready";

export interface Availability {
  state: AvailabilityState | "checking";
  /** Test geometries that passed and the number evaluated, when an evaluation is published. */
  passed?: number;
  total?: number;
}

export const CHECKING: Availability = { state: "checking" };

export function descriptorUrl(baseUrl: string, modelId: string): string {
  return `${baseUrl}models/${modelId}.surrogate-io.json`;
}

export function evaluationUrl(baseUrl: string, modelId: string): string {
  return `${baseUrl}models/${modelId}.evaluation.json`;
}

/** True when `doc` is a descriptor of `modelId` (an object whose `model_id` is that id). */
export function isDescriptorOf(doc: unknown, modelId: string): boolean {
  return (
    doc !== null &&
    typeof doc === "object" &&
    !Array.isArray(doc) &&
    (doc as { model_id?: unknown }).model_id === modelId
  );
}

/** The verdict of an evaluation report: pass only when `sc_011_01` is "pass"; counts from its per-geometry `pass` flags. */
export function readEvaluation(doc: unknown): { pass: boolean; passed: number; total: number } | null {
  if (doc === null || typeof doc !== "object" || Array.isArray(doc)) return null;
  const { sc_011_01: verdict, geometries } = doc as { sc_011_01?: unknown; geometries?: unknown };
  if (typeof verdict !== "string" || !Array.isArray(geometries)) return null;
  const flags = geometries.map((g) => (g as { pass?: unknown } | null)?.pass === true);
  return {
    pass: verdict === "pass" && flags.every(Boolean),
    passed: flags.filter(Boolean).length,
    total: flags.length,
  };
}

async function json(fetcher: typeof fetch, url: string, signal?: AbortSignal): Promise<unknown> {
  try {
    const res = await fetcher(url, { signal });
    return res.ok ? await res.json() : undefined;
  } catch {
    return undefined;
  }
}

export async function fetchAvailability(
  baseUrl: string,
  modelId: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<Availability> {
  if (!isDescriptorOf(await json(fetcher, descriptorUrl(baseUrl, modelId), signal), modelId))
    return { state: "not-published" };
  const evaluation = readEvaluation(await json(fetcher, evaluationUrl(baseUrl, modelId), signal));
  if (evaluation === null) return { state: "unevaluated" };
  return {
    state: evaluation.pass ? "ready" : "evaluation-failed",
    passed: evaluation.passed,
    total: evaluation.total,
  };
}

export function useModelAvailability(modelId: string): Availability {
  const [state, setState] = useState<Availability>(CHECKING);
  useEffect(() => {
    const controller = new AbortController();
    setState(CHECKING);
    fetchAvailability(import.meta.env.BASE_URL, modelId, controller.signal).then((next) => {
      if (!controller.signal.aborted) setState(next);
    });
    return () => controller.abort();
  }, [modelId]);
  return state;
}

/** The locale key of the notice of a state (surrogates namespace); null while checking. */
export function noticeKey(state: Availability["state"]): string | null {
  switch (state) {
    case "checking":
      return null;
    case "not-published":
      return "notTrained";
    case "unevaluated":
      return "notEvaluated";
    case "evaluation-failed":
      return "evaluationFailed";
    case "ready":
      return "runtimeMissing";
  }
}
