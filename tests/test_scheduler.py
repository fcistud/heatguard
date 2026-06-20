from __future__ import annotations

from heatguard.scheduler import build_conditions, decide, live_signal, schedule
from heatguard.types import MetabolicCategory as MC
from heatguard.types import Signal

from conftest import weather


def test_newcomer_never_less_strict_than_veteran(riyadh, veteran, newcomer):
    order = {Signal.WORK: 3, Signal.DRINK_NOW: 3, Signal.REST_IN_SHADE: 2, Signal.STOP: 1}
    for hour, tdb, rh, sw in [(7, 35, 40, 350), (9, 39, 30, 720), (11, 43, 22, 900)]:
        w = weather(hour, tdb, rh, sw=sw, direct=sw * 0.85)
        av = schedule(w, riyadh, veteran, MC.HEAVY)
        an = schedule(w, riyadh, newcomer, MC.HEAVY)
        # newcomer's signal is at least as restrictive, and work minutes <=
        assert order[an.signal] <= order[av.signal]
        assert an.cycle.work_min_per_hour <= av.cycle.work_min_per_hour


def test_stop_is_internally_consistent(riyadh, veteran):
    av = schedule(weather(13, 47, 16, sw=940, direct=820), riyadh, veteran, MC.HEAVY)
    assert av.signal is Signal.STOP
    assert av.cycle.work_min_per_hour == 0
    assert av.cycle.work_fraction == 0.0
    assert av.cycle.rest_min_per_hour == 60


def test_work_signal_has_positive_work(riyadh, veteran):
    av = schedule(weather(6, 31, 45, sw=120, direct=60), riyadh, veteran, MC.MODERATE)
    if av.signal is Signal.WORK:
        assert av.cycle.work_min_per_hour >= 30


def test_advisory_serialises(riyadh, veteran):
    av = schedule(weather(10, 40, 25, sw=800, direct=680), riyadh, veteran, MC.HEAVY)
    d = av.to_dict()
    assert d["signal"] in {s.value for s in Signal}
    assert "cycle" in d and "hydration" in d and "rationale" in d


def test_measured_overrides_estimate(riyadh, veteran):
    w = weather(12, 45, 18, sw=940, direct=820)
    est = schedule(w, riyadh, veteran, MC.HEAVY)
    meas = schedule(w, riyadh, veteran, MC.HEAVY, measured_wbgt_c=24.0)
    assert est.wbgt_source == "liljegren"
    assert meas.wbgt_source == "measured" and meas.wbgt_c == 24.0


def test_live_signal_sequence(riyadh, veteran):
    av = schedule(weather(8, 36, 35, sw=500, direct=380), riyadh, veteran, MC.MODERATE)
    signals = {live_signal(av, m) for m in range(60)}
    if av.signal is Signal.STOP:
        assert signals == {Signal.STOP}
    else:
        # a non-stopped hour broadcasts work and at least one drink prompt
        assert Signal.DRINK_NOW in signals
