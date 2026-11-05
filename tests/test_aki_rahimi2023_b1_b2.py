"""Hand-made cases for aki_rahimi2023_b1 and _b2 (Kamel Rahimi et al. 2023, Baselines sCr 1
and 2). Same cohort rules as Baseline 3 (tested in test_aki_rahimi2023.py); these cases test
what differs: the baseline. Times are hours after INTIME. Written before the SQL."""

from __future__ import annotations

import pandas as pd
import pytest

from cohort_diff import engine, registry
from tests.test_aki_rahimi2023 import DAY, _tables


def _run(name: str, tables: dict[str, pd.DataFrame]) -> set[int]:
    return engine.run(engine.connect(tables), registry.load(name))


@pytest.mark.parametrize("name", ["aki_rahimi2023_b1", "aki_rahimi2023_b2"])
def test_rise_over_the_day_1_minimum(name: str) -> None:
    # Day 1: 1.0 and 1.1, so the day-1 minimum is 1.0; day 2: 1.6 >= 1.5 x 1.0.
    # (For Baseline 2, a man of 60 has an MDRD baseline of 1.0708, so day 1 is not AKI.)
    labs = [(1, 2, 1.0), (1, 12, 1.1), (1, 30, 1.6), (1, 50, 1.5)]
    assert _run(name, _tables(labs, [(1, "M", 60)])) == {1}


def test_baseline_1_ignores_pre_icu_results() -> None:
    # A pre-ICU 0.5 would make the Baseline 3 cohort exclude this as day-1 AKI;
    # Baseline 1 uses only day 1 (minimum 1.0), and 1.2 / 1.3 are not AKI. (The 1.3 is
    # at hour 55, more than 48 h after the 1.0: at hour 50 it would be a 0.3 rise.)
    labs = [(1, -30 * DAY, 0.5), (1, 2, 1.0), (1, 30, 1.2), (1, 55, 1.3)]
    assert _run("aki_rahimi2023_b1", _tables(labs, [(1, "M", 60)])) == set()


def test_baseline_1_does_not_depend_on_sex() -> None:
    # The Baseline 3 MDRD case: 1.4 / 1.45 / 1.62. With the day-1 minimum 1.4 as the
    # baseline, nobody reaches 2.1, and 1.62 - 1.4 = 0.22 < 0.3: no AKI for either sex.
    labs = [(s, h, v) for s in (1, 2) for h, v in ((2, 1.4), (30, 1.45), (50, 1.62))]
    assert _run("aki_rahimi2023_b1", _tables(labs, [(1, "M", 60), (2, "F", 60)])) == set()


@pytest.mark.parametrize("name", ["aki_rahimi2023_b1", "aki_rahimi2023_b2"])
def test_day_1_aki_by_the_48_hour_rule_is_excluded(name: str) -> None:
    # 1.0 then 1.4 on day 1 is a 0.4 rise within 48 h: AKI on day 1, so excluded.
    labs = [(1, 2, 1.0), (1, 20, 1.4), (1, 30, 2.0), (1, 50, 2.0)]
    assert _run(name, _tables(labs, [(1, "M", 60)])) == set()


def test_baseline_2_excludes_day_1_aki_against_mdrd() -> None:
    # A woman of 60: MDRD baseline 0.8218, so 1.5 x = 1.233. Her day-1 value of 1.3
    # is day-1 AKI under Baseline 2, so she is excluded. Baseline 1 has no MDRD step:
    # her day-1 minimum is 1.3, and 2.0 on day 2 (>= 1.95) is new AKI.
    labs = [(1, 2, 1.3), (1, 30, 2.0), (1, 50, 2.0)]
    tables = _tables(labs, [(1, "F", 60)])
    assert _run("aki_rahimi2023_b2", tables) == set()
    assert _run("aki_rahimi2023_b1", tables) == {1}


def test_baseline_2_uses_the_day_1_minimum_after_day_1() -> None:
    # Men of 60 (1.5 x MDRD = 1.606), neither with AKI on day 1 (1.2 < 1.606).
    # Patient 1: 1.4 on day 2, 1.62 on day 3. 1.62 would be AKI against MDRD, but after
    # day 1 the baseline is the day-1 minimum (1.5 x 1.2 = 1.8), and 1.62 - 1.4 = 0.22
    # within 48 h: no AKI. Patient 2: 1.75 on day 2 is 0.55 above 1.2 within 48 h: AKI.
    no_aki = [(1, 2, 1.2), (1, 30, 1.4), (1, 60, 1.62)]
    aki = [(2, 2, 1.2), (2, 30, 1.75), (2, 60, 1.75)]
    tables = _tables(no_aki + aki, [(1, "M", 60), (2, "M", 60)])
    assert _run("aki_rahimi2023_b2", tables) == {2}


def test_baseline_1_counts_a_falling_day_1_as_day_1_aki() -> None:
    # 2.0 then 1.0 on day 1: the 2.0 is >= 1.5 x the day-1 minimum (1.0), so this is AKI
    # already present on day 1 and the admission is excluded, even though 1.6 on day 2
    # would be new AKI. (Requiring the high value to come after the minimum would include it.)
    labs = [(1, 2, 2.0), (1, 12, 1.0), (1, 30, 1.6), (1, 50, 1.6)]
    assert _run("aki_rahimi2023_b1", _tables(labs, [(1, "M", 60)])) == set()


@pytest.mark.parametrize("name", ["aki_rahimi2023_b2", "aki_rahimi2023_b3"])
def test_non_positive_creatinine_is_ignored(name: str) -> None:
    # A 0.0 at hour 4 is impossible and is dropped. If it were kept, it would be the
    # day-1 minimum (Baseline 2) or the 48 h comparison value (Baseline 3), and 1.2 on
    # day 2 would count as AKI. Without it, 1.0 / 1.2 / 1.3 is not AKI for a man of 60.
    labs = [(1, 2, 1.0), (1, 4, 0.0), (1, 30, 1.2), (1, 55, 1.3)]
    assert _run(name, _tables(labs, [(1, "M", 60)])) == set()


def test_baseline_1_ignores_a_zero_on_day_1() -> None:
    # Kept, the 0.0 would be the day-1 minimum and make 1.0 on day 1 "AKI" (excluded).
    # Dropped, the day-1 minimum is 1.0 and 1.6 on day 2 is new AKI.
    labs = [(1, 2, 1.0), (1, 4, 0.0), (1, 30, 1.6), (1, 50, 1.6)]
    assert _run("aki_rahimi2023_b1", _tables(labs, [(1, "M", 60)])) == {1}


def test_baseline_3_ignores_a_zero_in_the_pre_icu_mean() -> None:
    # Kept, the pre-ICU mean would be 0.5 and 1.1 on day 1 "AKI" (excluded).
    # Dropped, the baseline is 1.0 and 1.6 on day 2 is new AKI.
    labs = [(1, -30 * DAY, 0.0), (1, -20 * DAY, 1.0), (1, 2, 1.1), (1, 30, 1.6), (1, 50, 1.5)]
    assert _run("aki_rahimi2023_b3", _tables(labs, [(1, "M", 60)])) == {1}
