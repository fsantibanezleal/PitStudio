// Shapes of the data the studio pages read. The contracts are the authority:
//   StudioTool  tool registry entry, specs/001-contracts data-model section 4 (DC-001-03)
//   InfoEntry   one tool of the studio index, specs/019-web-studio/contracts/studio-index.schema.json (DC-019-03)
//   RunCard     the published run manifest (DC-001-01) with the fields the studio pages read
import type { ArtefactRecord } from "~/cases/types";

export type ArtefactLike = ArtefactRecord;

export interface StudioTool {
  id: string;
  name: string;
  category: string;
  envs: string[];
  version?: Record<string, unknown>;
  spdx: string[];
  osi?: boolean;
  licence_class: string;
  ring: string;
  lane: string;
  performance: "public" | "local-only";
  role: string;
  cases: string[];
  produces?: string[];
  status: string;
  reason?: string;
  docs_page?: string;
  alternatives_rejected?: Array<{ name: string; reason: string }>;
  notice?: string;
}

export interface Probe {
  status: "pass" | "fail" | "skip" | "not-probed";
  name?: string;
  date?: string;
  gpu?: string;
  driver?: string;
  metrics?: Record<string, number> | string;
  error?: string;
}

export interface InfoEntry {
  id: string;
  position: { band: string; order: number; group: "map" | "not-adopted"; x_px: number; y_px: number };
  version: { value: string; release_date: string | null; from: string; lock?: string };
  probe: Probe;
  artefacts: string[];
}

export interface IndexEdgeJson {
  from: string;
  to: string;
  kind: string;
  state: "observed" | "planned";
  evidence?: { run_id: string; from_artefact: string; to_artefact: string };
}

export interface StudioIndex {
  schema_version: string;
  git_sha: string;
  tools: InfoEntry[];
  edges: IndexEdgeJson[];
  honesty: unknown;
}

export interface TelemetrySummary {
  sample_hz?: number | null;
  mem_used_peak_bytes?: number | null;
  energy_j?: number | null;
  power_at_limit_frac?: number | null;
  clocks_event_frac?: Record<string, number> | null;
  [k: string]: unknown;
}

export interface Attempt {
  n?: number;
  error_class?: string | null;
  duration_s?: number;
}

export interface Determinism {
  class: "bitwise" | "statistical" | "none";
  rerun_check?: string;
  rerun?: unknown;
}

export interface StageRecord {
  key: { id: string; variant?: string };
  tool: string;
  performance: "public" | "local-only" | string;
  status?: string;
  cache?: "hit" | "miss";
  wall_s?: number;
  exit_code?: number;
  error_class?: string | null;
  attempts?: Attempt[];
  inputs?: Array<{ id: string; sha256?: string; kind: string }>;
  telemetry?: TelemetrySummary | string | null;
  determinism?: Determinism;
  log_tail?: string;
  [k: string]: unknown;
}

export interface RunGpu {
  backend?: string;
  name: string;
  driver: string;
  vram_total_bytes: number;
  power_limit_enforced_w: number | null;
}

export interface RunCard {
  run_id: string;
  created: string;
  published?: boolean;
  stale?: boolean;
  fixture?: boolean;
  recipe?: { id?: string; path?: string; sha256?: string };
  profile?: string;
  git_sha?: string;
  gpu: RunGpu | null;
  stages: StageRecord[];
  artefacts: Array<
    | ArtefactRecord
    | (Omit<Partial<ArtefactRecord>, "producer"> & { id: string; producer: ArtefactRecord["producer"] })
  >;
  [k: string]: unknown;
}

export const NOT_PUBLISHED = "measured locally, not published (licence)";
