"""Tests for the energy clamp running total."""

from custom_components.airzone_cloud.sensor import accumulate_energy
from homeassistant.util import dt as dt_util

END_1 = "2026-10-06T06:59:40.000Z"
END_2 = "2026-10-06T07:59:40.000Z"
END_3 = "2026-10-06T08:59:40.000Z"


def _dt(value: str):
    return dt_util.parse_datetime(value)


def test_first_value_starts_the_total() -> None:
    assert accumulate_energy(None, None, 0.181, END_1) == (0.181, _dt(END_1))


def test_same_period_is_not_counted_twice() -> None:
    total, end = accumulate_energy(None, None, 0.181, END_1)
    assert accumulate_energy(total, end, 0.181, END_1) == (0.181, _dt(END_1))


def test_each_new_period_is_added_once() -> None:
    total, end = accumulate_energy(None, None, 0.181, END_1)
    total, end = accumulate_energy(total, end, 0.05, END_2)
    total, end = accumulate_energy(total, end, 0.05, END_2)
    total, end = accumulate_energy(total, end, 0.12, END_3)
    assert (total, end) == (0.351, _dt(END_3))


def test_equal_values_in_different_periods_still_add() -> None:
    total, end = accumulate_energy(None, None, 0.08, END_1)
    assert accumulate_energy(total, end, 0.08, END_2)[0] == 0.16


def test_older_period_is_ignored() -> None:
    total, end = accumulate_energy(None, None, 0.1, END_2)
    assert accumulate_energy(total, end, 0.5, END_1) == (0.1, _dt(END_2))


def test_missing_data_changes_nothing() -> None:
    total, end = accumulate_energy(None, None, 0.1, END_1)
    assert accumulate_energy(total, end, None, END_2) == (total, end)
    assert accumulate_energy(total, end, 0.2, None) == (total, end)
    assert accumulate_energy(total, end, 0.2, "garbage") == (total, end)


def test_restored_total_without_period_is_only_a_baseline() -> None:
    assert accumulate_energy(12.5, None, 0.2, END_1) == (12.5, _dt(END_1))


def test_float_noise_is_rounded() -> None:
    total, end = accumulate_energy(None, None, 0.1, END_1)
    total, end = accumulate_energy(total, end, 0.2, END_2)
    assert total == 0.3
