import type { ResultsTabId } from "./tabs";

// The comparisons each tab will report, by id. Their titles, what they report and their pre-registered acceptance
// criteria are in the `results` locale files under `pending.<id>`, transcribed from the success-criterion rows of the
// owning model specs (SC-007-01, SC-007-02, SC-010-01, SC-010-02, SC-011-01, SC-012-03, SC-012-02, SC-012-04, SC-014-05,
// SC-010-03, SC-016-02, SC-018-01, SC-009-01, SC-009-02, SC-009-04, SC-014-01, SC-014-04, SC-014-06, SC-015-03,
// SC-015-05, SC-016-01, SC-016-03). A comparison whose results bundle is published leaves this list.
export const PENDING_BY_TAB: Record<ResultsTabId, readonly string[]> = {
  "learned-vs-classical": [
    "ppo-dispatch",
    "attention-dispatch",
    "slope-forecasters",
    "gns-granular",
    "unet-watershed",
  ],
  "sim-to-real": ["unet-tstr", "fragment-realism", "il1-sim-to-sim", "slope-real-event"],
  parity: ["onnx-parity", "web-engine-parity"],
  "dr-ablation": ["structured-dr", "detector-small", "detector-nano"],
  "isaac-lab": ["il1-route", "il1-vs-pid", "il2-fill"],
  cosmos: ["cosmos-vs-qwen", "cosmos-task-b"],
  acceleration: ["tensorrt-engines", "reduced-precision"],
};
