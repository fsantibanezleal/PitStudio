/* Generated from contracts/pit-shells.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "licence".
 */
export type Licence = {
spdx: SpdxId
licence_class: LicenceClass
attribution?: string
}
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "lambda".
 */
export type Lambda = number
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "shell".
 */
export type Shell = {
lambda: Lambda
blocks: Bitset
block_count: number
ore_t: Tonnes
waste_t: Tonnes
value_cents: Cents
strip_ratio: StripRatio
}
/**
 * Block set: bit b of byte b // 8 (least significant bit first) is block index b in the block-model blocks order; standard base64 with padding.
 * 
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "bitset".
 */
export type Bitset = string
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "tonnes".
 */
export type Tonnes = number
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "cents".
 */
export type Cents = number
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "strip_ratio".
 */
export type StripRatio = (number | null)
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "schedule".
 */
export type Schedule = {
solver: {
name: ("highs" | "scipy-milp")
version: Version
}
status: ("optimal" | "time-limit" | "infeasible" | "unbounded" | "error")
binaries: number
gap: (number | null)
npv_usd: (number | null)
/**
 * @minItems 0
 * @maxItems 50
 */
periods: Period[]
}
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string

/**
 * Nested pit shells, pushbacks, bench-phase units and the MILP schedule written by the planner (DC-017-03, spec 017-planning-survey).
 */
export interface E1ShellsPushbacksAndSchedule {
$schema?: string
schema_version: string
block_model: {
id: Slug
sha256: Sha256
n_blocks: number
}
licence: Licence
block_set_encoding: "bitset-lsb0-base64"
config: Config
/**
 * @minItems 1
 * @maxItems 200
 */
shells: [Shell, ...(Shell)[]]
ultimate_pit: {
shell: number
value_cents: Cents
strip_ratio: StripRatio
}
/**
 * @minItems 1
 * @maxItems 200
 */
pushbacks: [Pushback, ...(Pushback)[]]
/**
 * @minItems 0
 * @maxItems 200000
 */
units: Unit[]
schedule: Schedule
}
/**
 * Shell and schedule configuration validated before solving (FR-017-28).
 * 
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "config".
 */
export interface Config {
/**
 * @minItems 1
 * @maxItems 200
 */
lambdas: [Lambda, ...(Lambda)[]]
t_min_t: number
periods: number
/**
 * @minItems 1
 * @maxItems 50
 */
mining_capacity_t: [number, ...(number)[]]
/**
 * @minItems 1
 * @maxItems 50
 */
processing_capacity_t: [number, ...(number)[]]
discount_rate: number
time_limit_s: number
mip_rel_gap: number
}
/**
 * Incremental block set closed at the cumulative shell `shell` (FR-017-17).
 * 
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "pushback".
 */
export interface Pushback {
shell: number
blocks: Bitset
ore_t: Tonnes
waste_t: Tonnes
strip_ratio_incremental: StripRatio
strip_ratio_cumulative: StripRatio
}
/**
 * Bench-phase unit: the blocks of one pushback on one bench (FR-017-18).
 * 
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "unit".
 */
export interface Unit {
id: number
pushback: number
bench: number
ore_t: Tonnes
waste_t: Tonnes
value_cents: Cents
}
/**
 * This interface was referenced by `E1ShellsPushbacksAndSchedule`'s JSON-Schema
 * via the `definition` "period".
 */
export interface Period {
t: number
/**
 * @minItems 0
 * @maxItems 200000
 */
units: number[]
mined_t: Tonnes
ore_t: Tonnes
cash_flow_usd: number
strip_ratio: StripRatio
}
