// Availability of a published surrogate (FR-011-09, FR-011-38): the descriptor `models/<model_id>.surrogate-io.json` (DC-011-02)
// beside the ONNX file. No descriptor, or one that is not a descriptor of that model, means "not published": the scenes then show
// the declared state "not yet trained" and compute nothing. Never throws.
import { useEffect, useState } from "react";

export type Availability = "checking" | "published" | "not-published";

export function descriptorUrl(baseUrl: string, modelId: string): string {
  return `${baseUrl}models/${modelId}.surrogate-io.json`;
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

export async function fetchAvailability(
  baseUrl: string,
  modelId: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<Exclude<Availability, "checking">> {
  try {
    const res = await fetcher(descriptorUrl(baseUrl, modelId), { signal });
    if (!res.ok) return "not-published";
    return isDescriptorOf(await res.json(), modelId) ? "published" : "not-published";
  } catch {
    return "not-published"; // a missing, aborted or unparsable descriptor publishes nothing
  }
}

export function useModelAvailability(modelId: string): Availability {
  const [state, setState] = useState<Availability>("checking");
  useEffect(() => {
    const controller = new AbortController();
    setState("checking");
    fetchAvailability(import.meta.env.BASE_URL, modelId, controller.signal).then((next) => {
      if (!controller.signal.aborted) setState(next);
    });
    return () => controller.abort();
  }, [modelId]);
  return state;
}
