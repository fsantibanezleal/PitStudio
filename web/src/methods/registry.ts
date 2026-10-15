// The method registry the pages read (DC-020-01). `studio/methods.yaml` is the source; the contract example below holds the
// same 23 entries (tests/contract/test_t_020_001_methods_registry.py checks the registry against the schema) and is what the
// web build embeds until the registry is generated into the build, as `~/cases/registry` does for the case registry.

import type { Text2 } from "~/cases/types";
import registryJson from "../../../specs/020-web-knowledge/contracts/examples/methods.valid.json";

export interface MethodEntry {
  id: string;
  name: Text2;
  tiers: string[];
  implementation: string;
  spdx: string[];
  lanes: string[];
  learned: boolean;
  cases: string[];
  docs_page: string;
  comparison?: {
    baseline: Text2;
    metric: { name: Text2; unit: string; orientation: string };
    pairing_unit: Text2;
    n: number;
  };
  criterion?: { text: Text2; requirement: string; spec: string };
}

export type MethodStatus = "pass" | "fail" | "not-yet-run";

export const methodRegistry = (registryJson as unknown as { methods: MethodEntry[] }).methods;

/** `M2` to `m02`: the id of a method page (lower case, number padded to two digits). */
export function methodSlug(id: string): string {
  const n = /^M([1-9]|1\d|2[0-3])$/.exec(id)?.[1];
  return n === undefined ? "" : `m${n.padStart(2, "0")}`;
}

/** The registry entry of a page slug (`m02`), only for the 23 canonical slugs. */
export function methodBySlug(slug: string | undefined): MethodEntry | undefined {
  if (slug === undefined || !/^m(0[1-9]|1\d|2[0-3])$/.test(slug)) return undefined;
  return methodRegistry.find((m) => methodSlug(m.id) === slug);
}

export const REPO_URL = "https://github.com/fsantibanezleal/PitStudio";
