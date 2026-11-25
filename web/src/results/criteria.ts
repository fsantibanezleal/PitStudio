export type CriterionStatus = "pass" | "fail" | "not-yet-run";

export interface ModelRow {
  id: string;
  /** Method-registry ids (M1..M23) whose pre-registered criterion is shown. */
  methods: string[];
  /** Success-criterion ids (SC-nnn-nn) whose status is computed from the results bundles. */
  requirements: string[];
}

/**
 * The 13 model rows of plan section 7 (FR-020-24), in order. Requirements are the success criteria of the owning model
 * specs (009, 011, 012, 007, 014, 010, 017, 015, 016); methods are the registry entries that carry the criterion text.
 */
export const MODEL_ROWS: readonly ModelRow[] = [
  { id: "dfine", methods: ["M10"], requirements: ["SC-009-01", "SC-009-02"] },
  { id: "rfdetr-seg", methods: ["M10"], requirements: ["SC-009-05"] },
  { id: "unet", methods: ["M11"], requirements: ["SC-012-01"] },
  { id: "gns", methods: ["M8"], requirements: ["SC-011-01"] },
  { id: "fno", methods: ["M15"], requirements: ["SC-011-03"] },
  { id: "dispatch", methods: ["M4", "M5"], requirements: ["SC-007-01", "SC-007-02"] },
  { id: "il1", methods: ["M21"], requirements: ["SC-014-01"] },
  { id: "il2", methods: ["M21"], requirements: ["SC-014-06"] },
  { id: "slope-forecasters", methods: ["M14"], requirements: ["SC-010-01"] },
  { id: "meta-model", methods: ["M17"], requirements: ["SC-017-01"] },
  { id: "dem-calibration", methods: ["M9"], requirements: ["SC-011-02"] },
  { id: "cosmos", methods: ["M22"], requirements: ["SC-015-03"] },
  { id: "tensorrt-engines", methods: ["M4", "M8", "M10", "M11", "M15"], requirements: ["SC-016-01"] },
];

/** fail beats pass beats not-yet-run; an empty list, or a requirement no bundle records as pass, is not-yet-run. */
export function criterionStatus(
  requirements: readonly string[],
  bundles: ReadonlyArray<{ criteria?: ReadonlyArray<{ requirement: string; status: string }> }>,
): CriterionStatus {
  if (requirements.length === 0) return "not-yet-run";
  const seen = new Map<string, "pass" | "fail">();
  for (const bundle of bundles) {
    const list = Array.isArray(bundle?.criteria) ? bundle.criteria : [];
    for (const c of list) {
      if (typeof c !== "object" || c === null) continue;
      if (c.status !== "pass" && c.status !== "fail") continue;
      if (seen.get(c.requirement) !== "fail") seen.set(c.requirement, c.status);
    }
  }
  if (requirements.some((r) => seen.get(r) === "fail")) return "fail";
  return requirements.every((r) => seen.get(r) === "pass") ? "pass" : "not-yet-run";
}
