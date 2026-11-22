// FR-018-72: what each case is built with, derived from the case registry (DC-018-01), the tool registry (DC-000-04), the method
// registry (DC-020-01) and the published runs of the case. A pure module: the components and the unit test both read it.
import { caseRegistry } from "./registry";
import type { CaseEntry, Lang } from "./types";

export type BuiltStatus = "used" | "planned";
export type BuiltGroupId = "omniverse" | "frameworks" | "methods" | "data";

export interface ToolInfo {
  id: string;
  name: string;
  version: string | null;
  licence: string | null;
  /** Case ids the studio tool registry names for the tool (`studio/tools.yaml`). */
  cases?: readonly string[];
  /** Registry status; a tool "evaluated-not-adopted" is not planned, so it is never listed. */
  status?: string;
}
export interface MethodInfo {
  id: string;
  name: { en: string; es: string };
  slug: string;
}
export interface BuiltItem {
  id: string;
  name: string;
  version: string | null;
  licence: string | null;
  href: string;
  nvidia: boolean;
  status: BuiltStatus;
}
export type BuiltGroups = Record<BuiltGroupId, BuiltItem[]>;

/** NVIDIA and Omniverse tools of the registry: the owner's list (Isaac Sim, Replicator, Isaac Lab, Newton, Warp, MuJoCo-Warp, ovrtx,
 *  USD Composer, Cosmos, TensorRT, USD) and the other NVIDIA tools the registry holds. */
export const NVIDIA_TOOL_IDS: readonly string[] = [
  "isaac-sim-replicator",
  "isaac-lab",
  "newton",
  "warp",
  "mujoco-warp",
  "ovrtx",
  "kit-usd-composer-explorer",
  "cosmos-reason-2",
  "cosmos-predict-transfer",
  "tensorrt",
  "openusd",
  "physx-ovphysx",
  "physicsnemo",
  "cuopt",
];

export interface BuiltWithInput {
  entry: CaseEntry;
  tools: readonly ToolInfo[];
  methods: readonly MethodInfo[];
  /** Tool ids that produced a published run of this case. */
  usedTools: ReadonlySet<string>;
  /** Method ids a published result of this case used. */
  usedMethods: ReadonlySet<string>;
  /** Tool ids of the published render shown on every case page (FR-018-73): used by the page, whatever the case lists. */
  renderTools?: readonly string[];
  lang: Lang;
  caseId?: string;
}

/** The id of the registry case an entry is, by its English title (unique per case); used when the caller does not pass the id. */
function caseIdOf(entry: CaseEntry): string | undefined {
  return Object.entries(caseRegistry.cases).find(([, c]) => c.title.en === entry.title.en)?.[0];
}

export function deriveBuiltWith(i: BuiltWithInput): BuiltGroups {
  const byId = new Map(i.tools.map((t) => [t.id, t]));
  const nvidia = new Set(NVIDIA_TOOL_IDS);
  const groups: BuiltGroups = { omniverse: [], frameworks: [], methods: [], data: [] };
  const render = new Set(i.renderTools ?? []);
  // the case registry first, then the tools the studio tool registry names for the case, then the tools of the published render
  const caseId = i.caseId ?? caseIdOf(i.entry);
  const named = i.tools
    .filter((t) => caseId !== undefined && t.cases?.includes(caseId) && t.status !== "evaluated-not-adopted")
    .map((t) => t.id);
  const toolIds = [...new Set([...Object.keys(i.entry.tools), ...named, ...render])];
  for (const id of toolIds) {
    const t = byId.get(id);
    if (!t) continue;
    const item: BuiltItem = {
      id,
      name: t.name,
      version: t.version,
      licence: t.licence,
      href: `/studio/tools/${id}/`,
      nvidia: nvidia.has(id),
      status: i.usedTools.has(id) || render.has(id) ? "used" : "planned",
    };
    groups[item.nvidia ? "omniverse" : "frameworks"].push(item);
  }
  for (const id of i.entry.methods) {
    const m = i.methods.find((x) => x.id === id);
    if (!m) continue;
    groups.methods.push({
      id,
      name: m.name[i.lang],
      version: null,
      licence: null,
      href: `/methods/${m.slug}/`,
      nvidia: false,
      status: i.usedMethods.has(id) ? "used" : "planned",
    });
  }
  const dataHref = `/cases/${caseId ?? ""}/?tab=context`;
  // no published summary names the data it used, so a data chip never claims more than "planned" (ADR-0040)
  const status: BuiltStatus = "planned";
  for (const s of i.entry.sources)
    groups.data.push({ id: s, name: s, version: null, licence: null, href: dataHref, nvidia: false, status });
  for (const s of i.entry.synthetic_data)
    groups.data.push({
      id: s.label.en,
      name: s.label[i.lang],
      version: null,
      licence: null,
      href: dataHref,
      nvidia: false,
      status,
    });
  return groups;
}

/** A tool name with the NVIDIA mark once: a registry name that already starts with the vendor is not prefixed again. */
export function vendorName(name: string, mark = "NVIDIA"): string {
  return name.toLowerCase().startsWith(mark.toLowerCase()) ? name : `${mark} ${name}`;
}

export interface StatusWords {
  used: string;
  planned: string;
}
const EN_WORDS: StatusWords = { used: "Used in the published result.", planned: "Planned, not yet run." };

/** "Forecast by PyTorch 2.14.1, Slope forecasting. Used in the published result." (tool, version, method, NVIDIA mark, status). */
export function attributionText(
  verb: string,
  tools: readonly BuiltItem[],
  methods: readonly BuiltItem[],
  words: StatusWords = EN_WORDS,
): string {
  const toolText = tools
    .map((t) => `${t.nvidia ? vendorName(t.name) : t.name}${t.version ? ` ${t.version}` : ""}`)
    .join(" + ");
  const parts = [toolText, ...methods.map((m) => m.name)].filter((p) => p.length > 0);
  const used = [...tools, ...methods].some((x) => x.status === "used");
  return `${verb} ${parts.join(", ")}. ${used ? words.used : words.planned}`;
}

/** Tool ids that may stand behind each kind of visual of a case page; the first two that the case lists are named. */
export const VISUAL_TOOLS: Record<string, readonly string[]> = {
  scene: ["threejs-r3f-3d-tiles", "openusd"],
  simulate: ["rapier-webgpu-pyodide", "minephys", "warp"],
  chart: ["pytorch", "onnx-runtime", "minephys", "warp"],
  kpi: ["minephys", "pytorch", "warp"],
};

export function toolsForVisual(kind: string, groups: BuiltGroups): BuiltItem[] {
  const all = [...groups.omniverse, ...groups.frameworks];
  const wanted = VISUAL_TOOLS[kind] ?? [];
  const hit = all.filter((i) => wanted.includes(i.id)).slice(0, 2);
  return hit.length > 0 ? hit : all.slice(0, 1);
}
