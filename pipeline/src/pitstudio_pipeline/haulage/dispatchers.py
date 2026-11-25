# ruff: noqa: E501
"""The classical dispatcher set (FR-007-14).

`fixed`, `nearest`, `sptf` (the engine's MinSaturationPolicy), `sq` (MinQueuePolicy) and `random` delegate to the reference
engine's own policies; `min-idle` is PitStudio's: the serviceable loader with the smallest backlog, where backlog is the time
until free plus (queued + inbound) times the loader's mean loading time, ties broken by ETA and then by the lowest node id.
Every dispatcher sends a loaded truck to its loader's declared destination dump, or to the first dump when none is declared.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from minehaulsim.des.dispatch import (
    FixedPolicy,
    LoaderView,
    MineView,
    MinQueuePolicy,
    MinSaturationPolicy,
    NearestPolicy,
    RandomPolicy,
    TruckView,
)

DISPATCHER_IDS = ("fixed", "nearest", "sptf", "sq", "random", "min-idle")
INF = float("inf")


def _serviceable(mine: MineView) -> list[LoaderView]:
    out = [lv for lv in mine.loaders if lv.diggable]
    if not out:
        raise RuntimeError("no diggable loader available (plan exhausted or all faces blocked)")
    return out


class Dispatcher:
    """A classical dispatcher: loader choice by an engine policy or `min-idle`, dump choice by the declared destination."""

    def __init__(self, name: str, policy: Any, destinations: Mapping[int, int | None] | None) -> None:
        self.name = name
        self._policy = policy
        self._destinations = dict(destinations or {})

    def next_loader(self, truck: TruckView, mine: MineView) -> int:
        return self._policy.next_loader(truck, mine)

    def next_dump(self, truck: TruckView, mine: MineView, *, from_loader: int | None = None) -> int:
        dest = self._destinations.get(from_loader) if from_loader is not None else None
        return dest if dest is not None else mine.dumps[0]


class MinIdlePolicy:
    """The serviceable loader with the smallest backlog; ties by ETA, then by the lowest node id (FR-007-14)."""

    name = "min-idle"

    def next_loader(self, truck: TruckView, mine: MineView) -> int:
        def key(lv: LoaderView) -> tuple[float, float, int]:
            backlog = lv.est_free_s + (lv.queue_len + lv.inbound) * lv.load_mean_s
            return (backlog, mine.eta_s.get((truck.truck_id, lv.node_id), INF), lv.node_id)

        return min(_serviceable(mine), key=key).node_id

    def next_dump(self, truck: TruckView, mine: MineView) -> int:
        return mine.dumps[0]


def make_dispatcher(
    dispatcher_id: str, *, destinations: Mapping[int, int | None] | None = None, rng: Any = None
) -> Dispatcher:
    """A classical dispatcher by id. `rng` (anything with `.integers(low, high)`) feeds `random` only."""
    if not isinstance(dispatcher_id, str) or dispatcher_id not in DISPATCHER_IDS:
        raise ValueError(f"unknown classical dispatcher {dispatcher_id!r}; the set is {', '.join(DISPATCHER_IDS)}")
    if dispatcher_id == "random":
        if rng is None:
            raise ValueError("the random dispatcher needs an rng")
        policy: Any = RandomPolicy(rng)
    else:
        policy = {
            "fixed": FixedPolicy,
            "nearest": NearestPolicy,
            "sptf": MinSaturationPolicy,
            "sq": MinQueuePolicy,
            "min-idle": MinIdlePolicy,
        }[dispatcher_id]()
    return Dispatcher(dispatcher_id, policy, destinations)
