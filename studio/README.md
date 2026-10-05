# studio/

The local simulation studio. Each tool family lives in its own uv environment, because their Python versions and
pinned runtimes conflict. Environments exchange schema-validated files, never imports. Nothing here runs GPU work in
CI.

| Folder | Python | Holds | Status |
|---|---|---|---|
| `studio/` | 3.14 | OpenUSD (`usd-core`), Warp, Newton, USD validators, PyNvVideoCodec, NVML | locked |
| `studio/isaac/` | 3.12 (uv-managed) | Isaac Sim + Replicator, its pinned torch | locked; not installed by default (tens of GB) |
| `studio/rtx/` | 3.12 (uv-managed) | ovrtx / ovstage / ovphysx (Kit-less RTX sensors) | locked |
| `studio/isaaclab/` | 3.12 (uv-managed) | Isaac Lab 3.0 kit-less on Newton | locked |
| `studio/bench/` | (runs in each env) | capability probes + `run_bench.py` → `studio/capabilities.json` | code merged; GPU runs pending |

NVIDIA software is installed from NVIDIA's package index at sync time. It is **never redistributed**: no binaries,
engines, caches or assets are committed. Performance data of Isaac Sim, Kit, Replicator and ovrtx stay on the machine
that measured them, as their licences require.

## The capability bench

`studio/bench/run_bench.py` runs the probes one at a time:
- under a machine-wide GPU lock (`$GPU_LOCK_DIR/gpu0.compute`);
- refusing to start while `$GPU_LOCK_DIR/gpu0.hold` exists;
- with NVML telemetry.

```bash run deferred=P6
uv run --extra runner python studio/bench/run_bench.py            # default probe set
uv run --extra runner python studio/bench/run_bench.py stress     # opt-in: supervised GPU stability test
```

The command already exists. It is tagged deferred because no GPU run has been recorded yet on the reference machine.
It writes the committed `studio/capabilities.json` (publishable fields only) and a full local report under
`$PITSTUDIO_TMP/bench/`. See `docs/studio/capabilities-probe.md`.
