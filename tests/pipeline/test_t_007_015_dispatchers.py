# ruff: noqa: E501
"""T-007-015: the classical dispatcher set: delegation to the engine policies, `min-idle`, the declared-destination dump rule, tie rules; hand-calculated
MineView cases.

Requirements: FR-007-14.

Spec: specs/007-haulage-dispatch/spec.md FR-007-14 (the classical set is `fixed`, `nearest`, `sptf`, `sq`, `random` and `min-idle`; the first five delegate to the
reference engine's policies: FixedPolicy, NearestPolicy, MinSaturationPolicy (earliest expected start of loading, max(ETA, backlog)), MinQueuePolicy (fewest queued +
inbound, then ETA) and RandomPolicy; `min-idle` is PitStudio's own: the serviceable loader with the smallest backlog, backlog = time until free + (queued + inbound) x mean
loading time, ties broken by ETA; every dispatcher breaks the remaining ties by the lowest node id; every dispatcher, including LP and learned ones, sends a loaded truck to
its loader's declared destination dump, or to the first dump when none is declared) and section 8 item 3 (SPTF = MinSaturationPolicy, shortest queue = MinQueuePolicy).

Oracle: the reference engine's own policy classes (`minehaulsim.des.dispatch`), called directly on the same views (reference implementation); hand calculation of every
numeric case below (ETA, backlog and cost written out in the comments).

Expected API (module `pitstudio_pipeline.haulage.dispatchers`):
    DISPATCHER_IDS = ("fixed", "nearest", "sptf", "sq", "random", "min-idle")
    make_dispatcher(dispatcher_id: str, *, destinations: Mapping[int, int | None] | None = None, rng=None) -> Dispatcher
        `destinations` maps a loader node to its declared destination dump (None or absent: none declared); `rng` is the object `random` draws from: anything with
        `.integers(low, high)` returning an int in [low, high) (the adapter passes the variate source's "policy" stream); `random` without `rng` raises ValueError;
        an unknown id raises ValueError.
    Dispatcher: attribute `name` (the id); `next_loader(truck: TruckView, mine: MineView) -> int` and `next_dump(truck, mine, *, from_loader: int | None = None) -> int` using the
        engine's dataclasses; `next_dump` returns `destinations[from_loader]` when declared, else `mine.dumps[0]`. When no loader is serviceable (`diggable`), `next_loader`
        raises a RuntimeError (the engine parks the truck on a RuntimeError, like its own policies).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit  # noqa: F401
from pitstudio_pipeline.haulage.dispatchers import DISPATCHER_IDS, make_dispatcher

SETTINGS = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
ENGINE = {
    "fixed": lambda rng: FixedPolicy(),
    "nearest": lambda rng: NearestPolicy(),
    "sptf": lambda rng: MinSaturationPolicy(),
    "sq": lambda rng: MinQueuePolicy(),
    "random": lambda rng: RandomPolicy(rng),
}


class ScriptedRng:
    """An rng whose `.integers(low, high)` replays a list of indexes (the same object feeds the engine policy and ours)."""

    def __init__(self, picks):
        self.picks, self.i = list(picks), 0

    def integers(self, low, high):
        v = self.picks[self.i % len(self.picks)]
        self.i += 1
        return low + (v % (high - low))


def lv(node, queue=0, inbound=0, free=0.0, mean=100.0, diggable=True, in_service=False):
    return LoaderView(
        node_id=node,
        queue_len=queue,
        inbound=inbound,
        in_service=in_service,
        est_free_s=free,
        load_mean_s=mean,
        diggable=diggable,
    )


def mine(loaders, etas, dumps=(9, 8), now=0.0, truck=1):
    return MineView(
        now=now, loaders=tuple(loaders), dumps=tuple(dumps), eta_s={(truck, node): eta for node, eta in etas.items()}
    )


def tv(home=1, tid=1):
    return TruckView(truck_id=tid, unit_name="CAT_793F", home_loader=home)


@st.composite
def views(draw):
    nodes = draw(st.lists(st.integers(1, 30), min_size=1, max_size=6, unique=True))
    loaders = [
        lv(
            n,
            queue=draw(st.integers(0, 5)),
            inbound=draw(st.integers(0, 4)),
            free=float(draw(st.integers(0, 600))),
            mean=float(draw(st.integers(30, 400))),
            diggable=draw(st.booleans()),
            in_service=draw(st.booleans()),
        )
        for n in nodes
    ]
    etas = {n: float(draw(st.integers(10, 900))) for n in nodes}
    home = draw(st.sampled_from([*nodes, 99]))
    return mine(loaders, etas), tv(home=home)


# ---------------------------------------------------------------------------------------------------------------------
# the set and delegation
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-14")
def test_the_classical_set_is_exactly_the_six_ids_and_names_follow_the_ids():
    assert DISPATCHER_IDS == ("fixed", "nearest", "sptf", "sq", "random", "min-idle")
    for i in DISPATCHER_IDS:
        d = make_dispatcher(i, rng=ScriptedRng([0]))
        assert d.name == i


@pytest.mark.req("FR-007-14")
@pytest.mark.parametrize("bad", ["minsat", "minqueue", "SPTF", "", "lp", "ppo", "attention", "teleport", None, 3])
def test_unknown_and_non_classical_ids_are_rejected(bad):
    with pytest.raises(ValueError):  # noqa: PT011
        make_dispatcher(bad, rng=ScriptedRng([0]))


@pytest.mark.req("FR-007-14")
def test_random_needs_an_rng():
    with pytest.raises(ValueError):  # noqa: PT011
        make_dispatcher("random")


@pytest.mark.req("FR-007-14")
@pytest.mark.parametrize("did", ["fixed", "nearest", "sptf", "sq", "random"])
@SETTINGS
@given(views(), st.lists(st.integers(0, 50), min_size=1, max_size=5))
def test_the_first_five_choose_exactly_what_the_engine_policy_chooses(did, view, picks):
    m, t = view
    ours = make_dispatcher(did, rng=ScriptedRng(picks))
    engine = ENGINE[did](ScriptedRng(picks))
    try:
        expected = engine.next_loader(t, m)
    except RuntimeError:
        with pytest.raises(RuntimeError):
            ours.next_loader(t, m)
        return
    assert ours.next_loader(t, m) == expected


# ---------------------------------------------------------------------------------------------------------------------
# hand-calculated cases
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-14")
def test_sptf_picks_the_earliest_expected_start_of_loading():
    # L1: ETA 50 s, backlog = 30 + (1 + 0) x 100 = 130 s -> cost max(50, 130) = 130.  L2: ETA 120 s, backlog = 0 + (0 + 0) x 100 = 0 -> cost max(120, 0) = 120.
    m = mine([lv(1, queue=1, free=30.0), lv(2)], {1: 50.0, 2: 120.0})
    assert make_dispatcher("sptf").next_loader(tv(), m) == 2  # the farther loader starts loading earlier
    assert make_dispatcher("nearest").next_loader(tv(), m) == 1  # while `nearest` looks at the ETA only


@pytest.mark.req("FR-007-14")
def test_sq_picks_the_fewest_queued_plus_inbound_then_the_eta():
    # L1: queue 1 + inbound 0 = 1; L2: 0 + 2 = 2; L3: 1 + 0 = 1 with a shorter ETA than L1
    m = mine([lv(1, queue=1), lv(2, inbound=2), lv(3, queue=1)], {1: 200.0, 2: 10.0, 3: 90.0})
    assert make_dispatcher("sq").next_loader(tv(), m) == 3


@pytest.mark.req("FR-007-14")
def test_min_idle_picks_the_smallest_backlog():
    # backlog = time until free + (queued + inbound) x mean loading time
    # L1: 30 + (1 + 0) x 100 = 130 s;  L2: 0 + (0 + 1) x 100 = 100 s;  L3: 60 + 0 = 60 s with mean 250 -> 60 + (0) x 250 = 60 s
    m = mine([lv(1, queue=1, free=30.0), lv(2, inbound=1), lv(3, free=60.0, mean=250.0)], {1: 10.0, 2: 10.0, 3: 900.0})
    assert (
        make_dispatcher("min-idle").next_loader(tv(), m) == 3
    )  # the far loader has the smallest backlog; ETA only breaks ties


@pytest.mark.req("FR-007-14")
def test_min_idle_uses_the_mean_loading_time_of_each_loader():
    # L1: 0 + 2 x 50 = 100 s;  L2: 0 + 1 x 120 = 120 s -> L1 although it has the longer queue
    m = mine([lv(1, queue=2, mean=50.0), lv(2, queue=1, mean=120.0)], {1: 300.0, 2: 10.0})
    assert make_dispatcher("min-idle").next_loader(tv(), m) == 1


@pytest.mark.req("FR-007-14")
def test_min_idle_breaks_equal_backlogs_by_eta_then_by_node_id():
    m = mine(
        [lv(5, queue=1), lv(3, queue=1), lv(4, queue=1)], {5: 20.0, 3: 30.0, 4: 20.0}
    )  # backlogs all 100 s; ETAs 20, 30, 20
    assert (
        make_dispatcher("min-idle").next_loader(tv(), m) == 4
    )  # ETA 20 ties between nodes 4 and 5 -> the lowest node id
    m2 = mine([lv(5), lv(3), lv(4)], {5: 20.0, 3: 20.0, 4: 20.0})
    assert make_dispatcher("min-idle").next_loader(tv(), m2) == 3


@pytest.mark.req("FR-007-14")
def test_min_idle_skips_loaders_that_are_not_serviceable():
    m = mine([lv(1, diggable=False), lv(2, queue=3), lv(3, queue=1, diggable=False)], {1: 10.0, 2: 10.0, 3: 10.0})
    assert make_dispatcher("min-idle").next_loader(tv(), m) == 2  # the only diggable loader, however long its queue


@pytest.mark.req("FR-007-14")
@pytest.mark.parametrize("did", DISPATCHER_IDS)
def test_when_no_loader_is_serviceable_every_classical_dispatcher_raises_a_runtime_error(did):
    m = mine([lv(1, diggable=False), lv(2, diggable=False)], {1: 10.0, 2: 10.0})
    with pytest.raises(RuntimeError):
        make_dispatcher(did, rng=ScriptedRng([0])).next_loader(tv(), m)


@pytest.mark.req("FR-007-14")
def test_fixed_sends_a_truck_to_its_home_loader_or_the_lowest_node_id():
    m = mine([lv(4), lv(2), lv(7)], {4: 10.0, 2: 99.0, 7: 5.0})
    assert make_dispatcher("fixed").next_loader(tv(home=7), m) == 7
    assert make_dispatcher("fixed").next_loader(tv(home=99), m) == 2  # home is not a loader here: the lowest node id
    m2 = mine([lv(4), lv(2, diggable=False), lv(7)], {4: 10.0, 2: 99.0, 7: 5.0})
    assert make_dispatcher("fixed").next_loader(tv(home=2), m2) == 4  # home is not serviceable


# ---------------------------------------------------------------------------------------------------------------------
# ties by the lowest node id (every dispatcher)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-14")
@pytest.mark.parametrize("did", ["nearest", "sptf", "sq", "min-idle"])
def test_identical_loaders_are_broken_by_the_lowest_node_id(did):
    m = mine([lv(7), lv(3), lv(5)], {7: 60.0, 3: 60.0, 5: 60.0})
    assert make_dispatcher(did).next_loader(tv(), m) == 3


@pytest.mark.req("FR-007-14")
def test_random_chooses_among_the_serviceable_loaders_sorted_by_node_id():
    m = mine([lv(7), lv(3), lv(5), lv(2, diggable=False)], {7: 1.0, 3: 1.0, 5: 1.0, 2: 1.0})
    sorted_nodes = [3, 5, 7]
    for k in range(3):
        assert make_dispatcher("random", rng=ScriptedRng([k])).next_loader(tv(), m) == sorted_nodes[k]


# ---------------------------------------------------------------------------------------------------------------------
# the declared destination dump (every dispatcher)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-14")
@pytest.mark.parametrize("did", DISPATCHER_IDS)
def test_a_loaded_truck_goes_to_its_loaders_declared_dump(did):
    d = make_dispatcher(did, destinations={1: 8, 2: 9}, rng=ScriptedRng([0]))
    m = mine([lv(1), lv(2)], {1: 1.0, 2: 1.0}, dumps=(9, 8))
    assert d.next_dump(tv(), m, from_loader=1) == 8
    assert d.next_dump(tv(), m, from_loader=2) == 9


@pytest.mark.req("FR-007-14")
@pytest.mark.parametrize("did", DISPATCHER_IDS)
@pytest.mark.parametrize("destinations", [None, {}, {1: None}, {2: 9}])
def test_without_a_declared_destination_the_first_dump_is_used(did, destinations):
    d = make_dispatcher(did, destinations=destinations, rng=ScriptedRng([0]))
    m = mine([lv(1), lv(2)], {1: 1.0, 2: 1.0}, dumps=(8, 9))
    assert d.next_dump(tv(), m, from_loader=1) == 8
    assert d.next_dump(tv(), m) == 8  # no loader context given: the first dump
