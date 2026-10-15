"""The detector + geometric rule baseline (FR-015-29, FR-015-47, P-015-09).

Detections with score >= 0.5 and the known camera calibration answer task-A types 1, 3 and 5 without any language model:
the bottom-centre of a pixel box is back-projected onto the ground plane (a level plane at `ground_z`; the site terrain
model is reduced to the height under the camera by the caller), then

- type 1: a person and a haul truck within 30 m of each other (ground distance between their back-projected points);
- type 3: the number of haul-truck boxes, in {0, 1, 2, 3+};
- type 5: a light vehicle whose point, in the body frame of the (single) truck, lies inside the blind-zone polygon.

Types 2, 4 and 6 have no detector evidence: "not applicable". Anything the rule cannot answer from valid inputs (a
missing or degenerate calibration, a non-finite box, a box outside the image, a ray that never reaches the ground) is
also "not applicable": the rule never guesses.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio.reason.truth import NEAR_M, point_in_polygon, quat_to_matrix

NOT_APPLICABLE = "not applicable"
SCORE_MIN = 0.5
UNSUPPORTED_TYPES = (2, 4, 6)
SUPPORTED_TYPES = (1, 3, 5)
_COUNT_LABELS = ("0", "1", "2", "3+")


class BadDetectorInput(ValueError):
    """The calibration or a detection is missing or invalid; the rule refuses to answer."""


def _finite(*values: Any) -> bool:
    return all(isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def _camera(camera: Any) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float, float]]:
    try:
        k = camera["intrinsics"]
        fx, fy, cx, cy = k["fx_px"], k["fy_px"], k["cx_px"], k["cy_px"]
        t = list(camera["pose"]["translation_m"])
        q = list(camera["pose"]["rotation_xyzw"])
    except (KeyError, TypeError) as exc:
        raise BadDetectorInput("camera calibration is missing or incomplete") from exc
    if not (_finite(fx, fy, cx, cy) and fx > 0 and fy > 0 and len(t) == 3 and len(q) == 4 and _finite(*t, *q)):
        raise BadDetectorInput("camera calibration holds a non-finite or non-positive value")
    if not math.isclose(math.sqrt(sum(c * c for c in q)), 1.0, abs_tol=1e-6):
        raise BadDetectorInput("camera rotation is not a unit quaternion")
    return np.asarray(t, dtype=float), quat_to_matrix(q), (fx, fy, cx, cy)


def backproject(camera: Mapping[str, Any], uv: Sequence[float], *, ground_z: float) -> tuple[float, float]:
    """Pixel (u, v) to the horizontal plane z = `ground_z` (Z-up world, OpenGL camera): the world point (x, y).

    Raises ValueError when the ray does not reach the plane (parallel to it, or pointing away from it).
    """
    origin, rot, (fx, fy, cx, cy) = _camera(camera)
    if not _finite(ground_z, *uv):
        raise ValueError("pixel or ground height is not finite")
    d = rot @ np.array([(uv[0] - cx) / fx, -(uv[1] - cy) / fy, -1.0])
    dz = float(d[2])
    if dz == 0.0:
        raise ValueError("the ray is parallel to the ground plane")
    t = (ground_z - float(origin[2])) / dz
    if not t > 0:
        raise ValueError("the ray does not reach the ground plane")
    hit = origin + t * d
    return float(hit[0]), float(hit[1])


def _valid_detections(detections: Any, image_size: Sequence[int]) -> list[dict[str, Any]]:
    if not isinstance(detections, Sequence) or isinstance(detections, str | bytes):
        raise BadDetectorInput("detections are missing")
    width, height = image_size
    out: list[dict[str, Any]] = []
    for det in detections:
        try:
            cls, score, box = det["class"], det["score"], list(det["box"])
        except (KeyError, TypeError) as exc:
            raise BadDetectorInput("a detection lacks class, score or box") from exc
        if not _finite(score) or len(box) != 4 or not _finite(*box):
            raise BadDetectorInput("a detection holds a non-finite score or box")
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise BadDetectorInput("a detection box is empty, inverted or outside the image")
        out.append({"class": cls, "score": float(score), "box": box})
    return out


def _ground_points(
    dets: Sequence[Mapping[str, Any]], cls: str, camera: Any, ground_z: float
) -> list[tuple[float, float]]:
    points = []
    for det in dets:
        if det["class"] == cls and det["score"] >= SCORE_MIN:
            x1, _, x2, y2 = det["box"]
            try:
                points.append(backproject(camera, ((x1 + x2) / 2, y2), ground_z=ground_z))
            except ValueError as exc:
                raise BadDetectorInput(str(exc)) from exc
    return points


def _answer(
    qtype: int,
    detections: Any,
    camera: Any,
    *,
    image_size: Sequence[int],
    ground_z: float,
    blind_zone: Sequence[Sequence[float]] | None,
    truck_heading_deg: float | None,
) -> str:
    """The answer for a supported type; raises `BadDetectorInput` when the inputs cannot support one."""
    _camera(camera)
    dets = _valid_detections(detections, image_size)
    if not _finite(ground_z):
        raise BadDetectorInput("ground height is not finite")
    if qtype == 3:
        n = sum(1 for d in dets if d["class"] == "haul_truck" and d["score"] >= SCORE_MIN)
        return _COUNT_LABELS[min(n, 3)]
    trucks = _ground_points(dets, "haul_truck", camera, ground_z)
    if qtype == 1:
        persons = _ground_points(dets, "person", camera, ground_z)
        near = any(math.hypot(p[0] - t[0], p[1] - t[1]) <= NEAR_M for p in persons for t in trucks)
        return "yes" if near else "no"
    if blind_zone is None or truck_heading_deg is None or not _finite(truck_heading_deg) or len(trucks) != 1:
        raise BadDetectorInput("type 5 needs one truck, its heading and its blind-zone polygon")
    h = math.radians(truck_heading_deg)
    tx, ty = trucks[0]
    for x, y in _ground_points(dets, "light_vehicle", camera, ground_z):
        dx, dy = x - tx, y - ty
        if point_in_polygon((math.cos(h) * dx + math.sin(h) * dy, -math.sin(h) * dx + math.cos(h) * dy), blind_zone):
            return "yes"
    return "no"


def detector_answer(
    qtype: int,
    detections: Any,
    camera: Any,
    *,
    image_size: Sequence[int],
    ground_z: float,
    blind_zone: Sequence[Sequence[float]] | None = None,
    truck_heading_deg: float | None = None,
) -> str:
    """The rule's label for one query, or `NOT_APPLICABLE`."""
    if qtype not in SUPPORTED_TYPES:
        return NOT_APPLICABLE
    try:
        return _answer(
            qtype,
            detections,
            camera,
            image_size=image_size,
            ground_z=ground_z,
            blind_zone=blind_zone,
            truck_heading_deg=truck_heading_deg,
        )
    except BadDetectorInput:
        return NOT_APPLICABLE


def run_detector_rule(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Answer a batch. Each item holds `query_id`, `qtype` and the keywords of `detector_answer` (any may be invalid).

    Returns `{"answers": {query_id: label}, "not_applicable_bad_input": n}`; a type the rule does not cover is
    "not applicable" by design and is not counted as bad input.
    """
    answers: dict[str, str] = {}
    bad = 0
    for item in items:
        qid, qtype = item["query_id"], item["qtype"]
        if qtype not in SUPPORTED_TYPES:
            answers[qid] = NOT_APPLICABLE
            continue
        try:
            answers[qid] = _answer(
                qtype,
                item.get("detections"),
                item.get("camera"),
                image_size=item["image_size"],
                ground_z=item["ground_z"],
                blind_zone=item.get("blind_zone"),
                truck_heading_deg=item.get("truck_heading_deg"),
            )
        except BadDetectorInput, KeyError, TypeError, ValueError:
            answers[qid] = NOT_APPLICABLE
            bad += 1
    return {"answers": answers, "not_applicable_bad_input": bad}
