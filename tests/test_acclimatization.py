from __future__ import annotations

from heatguard import acclimatization as acc
from heatguard.types import Worker


def _new(day, experienced=False):
    return Worker("w", days_on_job=day, acclimatized=False, experienced_elsewhere=experienced)


def test_new_worker_ramp_sequence():
    fracs = [acc.allowed_fraction(_new(d)) for d in range(5)]
    assert fracs == [0.20, 0.40, 0.60, 0.80, 1.00]


def test_experienced_ramp_is_faster():
    assert acc.allowed_fraction(_new(0, experienced=True)) == 0.50
    assert acc.allowed_fraction(_new(1, experienced=True)) == 1.00


def test_acclimatized_always_full():
    assert acc.allowed_fraction(Worker("v", days_on_job=0, acclimatized=True)) == 1.0
    assert acc.allowed_fraction(Worker("v", days_on_job=200, acclimatized=True)) == 1.0


def test_thresholds_switch_after_ramp_completes():
    assert acc.use_unacclimatized_thresholds(_new(0)) is True
    assert acc.use_unacclimatized_thresholds(_new(4)) is True
    assert acc.use_unacclimatized_thresholds(_new(5)) is False  # ramp done -> TLV
    assert acc.is_ramping(_new(5)) is False


def test_ramp_past_end_is_full():
    assert acc.allowed_fraction(_new(10)) == 1.0
