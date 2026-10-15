import type { PublishedBundle } from "~/results/bundles";
import { criterionStatus } from "~/results/criteria";
import type { MethodEntry, MethodStatus } from "./registry";

/** The computed status of every method that records a criterion; the others have none and read "Not yet run". */
export function methodStatuses(
  methods: readonly MethodEntry[],
  bundles: ReadonlyArray<Pick<PublishedBundle, "criteria">>,
): Record<string, MethodStatus> {
  const out: Record<string, MethodStatus> = {};
  for (const m of methods) {
    if (m.criterion) out[m.id] = criterionStatus([m.criterion.requirement], bundles);
  }
  return out;
}
