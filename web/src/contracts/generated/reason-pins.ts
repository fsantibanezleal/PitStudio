/* Generated from contracts/reason-pins.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "release_url".
 */
export type ReleaseUrl = string
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "archive_bytes".
 */
export type ArchiveBytes = number
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "cosmos_revision".
 */
export type CosmosRevision = string
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string

/**
 * Pins of the reason lane in studio/reason/pins.json: llama.cpp archives and executables, model repositories, revisions, file SHA-256 and prompt hashes (DC-015-03, spec 015-vlm).
 */
export interface ReasonLanePins {
$schema?: string
schema_version: SchemaVersion
llamacpp: {
build: "b11381"
archives: {
binaries: BinariesArchive
cudart: CudartArchive
}
executables: {
[k: string]: Sha256 | undefined
}
converter: {
source_tag: "b11381"
path: "convert_hf_to_gguf.py"
sha256: Sha256
}
}
models: {
cosmos: {
repository: "nvidia/Cosmos-Reason2-2B"
revision: CosmosRevision
files: ModelFiles
}
qwen: {
repository: "Qwen/Qwen3-VL-2B-Instruct"
revision: GitSha
files: ModelFiles
}
}
prompts: {
system: PromptPin
task_a_type_1: PromptPin
task_a_type_2: PromptPin
task_a_type_3: PromptPin
task_a_type_4: PromptPin
task_a_type_5: PromptPin
task_a_type_6: PromptPin
task_b_pair: PromptPin
task_b_single: PromptPin
task_c_caption: PromptPin
}
}
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "binaries_archive".
 */
export interface BinariesArchive {
name: "llama-b11381-bin-win-cuda-13.4-x64.zip"
url: ReleaseUrl
bytes: ArchiveBytes
sha256: Sha256
}
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "cudart_archive".
 */
export interface CudartArchive {
name: "cudart-llama-bin-win-cuda-13.4-x64.zip"
url: ReleaseUrl
bytes: ArchiveBytes
sha256: Sha256
}
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "model_files".
 */
export interface ModelFiles {
[k: string]: FilePin | undefined
}
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "file_pin".
 */
export interface FilePin {
sha256: Sha256
bytes: number
}
/**
 * This interface was referenced by `ReasonLanePins`'s JSON-Schema
 * via the `definition` "prompt_pin".
 */
export interface PromptPin {
path: string
sha256: Sha256
}
