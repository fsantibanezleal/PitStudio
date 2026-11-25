/* Generated from contracts/people-asset-record.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Provenance record of one person character for the SDG scenes, either a MakeHuman 1.3.0 export or a procedural mannequin, read by the st30_assets handoff and the dataset card (DC-009-04, spec 009-perception).
 */
export type PeopleAssetRecord = (Makehuman | Mannequin)
export type ArtefactId = string
export type Sha256 = string
export type SettingId = string
export type Seed = number
export type Relpath = string
export type UtcTimestamp = string
export type Semver = string
export type GitSha = string

export interface Makehuman {
$schema?: string
source: "makehuman"
character_id: ArtefactId
application: "MakeHuman"
application_version: "1.3.0"
build: "official-unmodified"
zip_sha256: Sha256
/**
 * @minItems 1
 * @maxItems 256
 */
assets: [Asset, ...(Asset)[]]
export_settings: ExportSettings
seed: Seed
export_path: Relpath
export_sha256: Sha256
exported_utc?: UtcTimestamp
licence: {
spdx: "CC0-1.0"
licence_class: "open-no-attribution"
}
}
export interface Asset {
kind: ("skin" | "clothes" | "hair" | "eyebrows" | "eyelashes" | "eyes" | "teeth" | "tongue" | "proxy" | "material")
name: string
origin: "system"
}
export interface ExportSettings {
format: ("fbx" | "dae" | "obj")
scale_unit: ("m" | "dm" | "cm" | "mm")
skeleton: SettingId
pose?: SettingId
feet_on_ground?: boolean
subdivide?: boolean
hide_faces_under_clothes?: boolean
}
export interface Mannequin {
$schema?: string
source: "mannequin"
character_id: ArtefactId
generator: "procedural-mannequin"
generator_version: Semver
git_sha: GitSha
seed: Seed
export_path: Relpath
export_sha256: Sha256
exported_utc?: UtcTimestamp
licence: {
spdx: "CC-BY-4.0"
licence_class: "own"
}
}
