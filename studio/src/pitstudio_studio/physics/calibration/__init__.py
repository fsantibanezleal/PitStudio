"""DEM calibration arms and driver on the studio solvers (spec 011, FR-011-17 ... FR-011-31).

`cmaes` (gradient-free arm), `tape` (differentiable DEM and the gradient arm), `driver` (requests, DC-011-04 documents,
interval and
gradient checks, OOM fallback, literature targets) and `simulator` (the Warp heap simulator the driver runs on a GPU).
The numpy
protocol cores (interval, gradient gate, coverage study) are in `pitstudio.calibration`.
"""
