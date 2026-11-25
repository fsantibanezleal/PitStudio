"""The scenario dust field of the structured SDG arm: haul-road plumes from `minephys.environment` (FR-009-05).

Every road edge is cut into pieces of at most `PIECE_M` metres; each piece is a finite crosswind line source in the
frame of the wind (ISC3 finite line source, `minephys.environment.finite_line_source_plume`) with the AP-42 unpaved-road
emission (`ap42_unpaved_emission_factor`, `line_emission_rate`) and the Pasquill-Gifford dispersion coefficients at the
downwind distance of the piece (`pasquill_sigmas`). The concentration at a point is the sum over the pieces upwind.

Approximations, all stated in the dataset card of the job: a piece that is oblique to the wind is replaced by its
projection on the crosswind axis with the emission rescaled to conserve mass (the crosswind extent is floored at
`MIN_EXTENT_M`); the release height is a design assumption (`SOURCE_HEIGHT_M`); the scenario draws (silt, vehicle
weight, traffic, wind, stability class) are design assumptions inside the ranges of AP-42 Table 13.2.2-3 and are
recorded with every dust value in the parameter table.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from minephys import environment

from pitstudio_studio.sdg.scene_inputs import SceneInputs

PIECE_M = 10.0
MIN_EXTENT_M = 1.0
SOURCE_HEIGHT_M = 1.0  # release height of the haul-road dust (design assumption)
MIN_DOWNWIND_M = 5.0  # nearer pieces are skipped (the Gaussian plume is not defined at the source)
STABILITY_CLASSES = ("B", "C", "D")
PARTICLE_DIAMETER_M = 5.0e-6  # optical particle size of the extinction coefficient (design assumption)
PARTICLE_DENSITY_KG_M3 = 2650.0


@dataclass(frozen=True)
class DustScenario:
    """The scenario draw behind a field: all recorded in the parameter table."""

    silt_fraction: float  # AP-42 Table 13.2.2-3 range 0.018 .. 0.252
    mean_weight_kg: float  # fleet mean vehicle weight
    vehicles_per_s: float  # trucks per second on every edge
    wind_speed_m_s: float
    wind_from_deg: float  # meteorological: direction the wind blows FROM, clockwise from north
    stability_class: str

    def as_dict(self) -> dict[str, float | str]:
        return {
            "silt_fraction": self.silt_fraction,
            "mean_weight_kg": self.mean_weight_kg,
            "vehicles_per_s": self.vehicles_per_s,
            "wind_speed_m_s": self.wind_speed_m_s,
            "wind_from_deg": self.wind_from_deg,
            "stability_class": self.stability_class,
        }


def draw_scenario(rng: np.random.Generator) -> DustScenario:
    """One dust scenario drawn from its assumption ranges."""
    return DustScenario(
        silt_fraction=float(rng.uniform(0.02, 0.15)),
        mean_weight_kg=float(rng.uniform(162_000.0, 250_000.0)),
        vehicles_per_s=float(rng.uniform(0.002, 0.03)),
        wind_speed_m_s=float(rng.uniform(1.5, 8.0)),
        wind_from_deg=float(rng.uniform(0.0, 360.0)),
        stability_class=str(rng.choice(STABILITY_CLASSES)),
    )


class RoadPlumeField:
    """`DustField` (dust_wet.py) of the haul roads of a scene under one `DustScenario`."""

    def __init__(self, scene: SceneInputs, scenario: DustScenario, *, ground: Callable[[float, float], float]) -> None:
        self.scenario = scenario
        self._ground = ground
        factor = float(
            environment.ap42_unpaved_emission_factor(scenario.silt_fraction, scenario.mean_weight_kg, "PM10")
        )
        self._q_line = float(environment.line_emission_rate(factor, scenario.vehicles_per_s))
        starts, ends = [], []
        for edge in scene.edges:
            xy = edge.xyz[:, :2]
            n = max(1, math.ceil(edge.length_m / PIECE_M))
            cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
            s = np.linspace(0.0, cum[-1], n + 1)
            pts = np.column_stack([np.interp(s, cum, xy[:, 0]), np.interp(s, cum, xy[:, 1])])
            starts.append(pts[:-1])
            ends.append(pts[1:])
        self._a = np.vstack(starts)
        self._b = np.vstack(ends)
        theta = math.radians(scenario.wind_from_deg + 180.0)  # direction the wind blows TO, clockwise from north
        self._w = np.array([math.sin(theta), math.cos(theta)])  # downwind unit vector (x east, y north)
        self._c = np.array([-self._w[1], self._w[0]])  # crosswind unit vector
        self._length = np.hypot(*(self._b - self._a).T)
        mid = 0.5 * (self._a + self._b)
        self._mid_down = mid @ self._w
        ya, yb = self._a @ self._c, self._b @ self._c
        self._y1 = np.minimum(ya, yb)
        self._y2 = np.maximum(ya, yb)
        extent = np.maximum(self._y2 - self._y1, MIN_EXTENT_M)
        centre = 0.5 * (self._y1 + self._y2)
        self._y1, self._y2 = centre - extent / 2.0, centre + extent / 2.0
        self._q_eff = self._q_line * self._length / extent  # mass-conserving emission per crosswind metre

    def concentration_kg_m3(self, x_m: float, y_m: float, z_m: float) -> float:
        """Dust mass concentration at a point of the stage frame (z above the design surface of the point's ground)."""
        r = np.array([x_m, y_m], dtype=np.float64)
        downwind = float(r @ self._w) - self._mid_down  # distance of the receptor downwind of each piece
        keep = downwind > MIN_DOWNWIND_M
        if not keep.any():
            return 0.0
        height = max(float(z_m) - float(self._ground(x_m, y_m)), 0.0)
        sy, sz = environment.pasquill_sigmas(downwind[keep], self.scenario.stability_class)
        total = environment.finite_line_source_plume(
            self._q_eff[keep],
            self.scenario.wind_speed_m_s,
            float(r @ self._c),
            height,
            SOURCE_HEIGHT_M,
            self._y1[keep],
            self._y2[keep],
            sy,
            sz,
        )
        return float(np.sum(total))
