"""Planar DEM generator of the GNS reference rollouts (spec 011, FR-011-03, DC-011-01).

`space` (parameter space, split plan, contract metric), `packing` (column and funnel-hopper states), `measure` (rate,
repose, flow-aware rest test), `engine` (Warp batches), `generate` (resumable dataset run), `calibrate` (repose against
the 3-D DEM), `verify` (dataset checks and card), `gpujob` (machine lock and guard). Run `python -m
pitstudio_studio.physics.planar --help`.
"""
