// Tool registry entries the matrices read (data-model 001 section 4.3: 20 `studio-tool` entries and the components).
// Display names follow docs/cases/tool-matrix.md. Replaced by the generated `studio/tools.yaml` types when the registry
// producer exists; the matrix itself keeps only the studio tools that at least one case lists.
import type { ToolEntry } from "./types";

const studio = (id: string, name: string, status = "not-yet-run"): ToolEntry => ({
  id,
  name,
  category: "studio-tool",
  status,
});
const component = (id: string, name: string): ToolEntry => ({
  id,
  name,
  category: "component",
  status: "not-yet-run",
});

export const toolRegistry: ToolEntry[] = [
  studio("openusd", "OpenUSD"),
  studio("warp", "Warp"),
  studio("newton", "Newton"),
  studio("mujoco-warp", "MuJoCo-Warp"),
  studio("physx-ovphysx", "PhysX / ovphysx"),
  studio("ovrtx", "ovrtx"),
  studio("isaac-sim-replicator", "Isaac Sim + Replicator"),
  studio("isaac-lab", "Isaac Lab"),
  studio("kit-usd-composer-explorer", "USD Composer / Explorer (Kit)"),
  studio("cosmos-reason-2", "Cosmos Reason 2"),
  studio("pytorch", "PyTorch"),
  studio("onnx-runtime", "ONNX Runtime (+Web)"),
  studio("tensorrt", "TensorRT"),
  studio("nvenc-ffmpeg", "NVENC / FFmpeg"),
  studio("nsight-nvml", "Nsight / NVML"),
  studio("threejs-r3f-3d-tiles", "three.js / R3F / 3D Tiles"),
  studio("rapier-webgpu-pyodide", "Rapier / WebGPU / Pyodide"),
  studio("cuopt", "cuOpt", "evaluated-not-adopted"),
  studio("physicsnemo", "PhysicsNeMo", "evaluated-not-adopted"),
  studio("cosmos-predict-transfer", "Cosmos Predict / Transfer", "evaluated-not-adopted"),
  component("pitstudio", "PitStudio"),
  component("minephys", "minephys"),
  component("minehaulsim", "minehaulsim"),
  component("oreblocks", "oreblocks"),
  component("colmap", "COLMAP"),
  component("brush", "Brush"),
];
