"""Hand-made cases for aki_rahimi2023_b3 (Kamel Rahimi et al. 2023, Baseline sCr 3).

Each case is one patient with one ICU stay starting at INTIME. Times are hours after
INTIME (negative = before ICU admission). Written before the SQL, as its specification.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from cohort_diff import engine, registry

INTIME = datetime(2150, 6, 1)
DAY = 24


def _tables(
    labs: list[tuple[int, float, float]],
    patients: list[tuple[int, str, int]],
    stays: list[tuple[int, int, float]] | None = None,
) -> dict[str, pd.DataFrame]:
    """labs: (subject_id, hours after INTIME, creatinine).
    patients: (subject_id, gender, anchor_age in 2150).
    stays: (subject_id, hadm_id, intime in hours after INTIME); default one per patient,
    with hadm_id = subject_id, starting at INTIME and lasting 5 days."""
    stays = stays or [(s, s, 0.0) for s, _, _ in patients]
    return {
        "patients": pd.DataFrame(
            {
                "subject_id": [s for s, _, _ in patients],
                "gender": [g for _, g, _ in patients],
                "anchor_age": [a for _, _, a in patients],
                "anchor_year": 2150,
            }
        ),
        "icustays": pd.DataFrame(
            {
                "subject_id": [s for s, _, _ in stays],
                "hadm_id": [h for _, h, _ in stays],
                "stay_id": [1000 + i for i in range(len(stays))],
                "intime": [INTIME + timedelta(hours=t) for _, _, t in stays],
                "outtime": [INTIME + timedelta(hours=t + 5 * DAY) for _, _, t in stays],
            }
        ),
        "labevents": pd.DataFrame(
            {
                "labevent_id": range(len(labs)),
                "subject_id": [s for s, _, _ in labs],
                "hadm_id": [s for s, _, _ in labs],
                "itemid": 50912,
                "charttime": [INTIME + timedelta(hours=h) for _, h, _ in labs],
                "valuenum": [v for _, _, v in labs],
            }
        ),
    }


def _run(tables: dict[str, pd.DataFrame]) -> set[int]:
    return engine.run(engine.connect(tables), registry.load("aki_rahimi2023_b3"))


def test_new_aki_on_day_2_with_pre_icu_baseline() -> None:
    # Baseline = mean(1.0, 1.0) = 1.0; day 1 1.1 (no AKI); day 2 1.6 >= 1.5 x 1.0.
    labs = [(1, -30 * DAY, 1.0), (1, -20 * DAY, 1.0), (1, 2, 1.1), (1, 30, 1.6), (1, 50, 1.5)]
    assert _run(_tables(labs, [(1, "M", 60)])) == {1}


def test_aki_on_day_1_is_excluded() -> None:
    # Same baseline; 1.6 already on day 1, so this is not a *new* AKI on day 2 or 3.
    labs = [(1, -30 * DAY, 1.0), (1, 2, 1.6), (1, 30, 1.7), (1, 50, 1.8)]
    assert _run(_tables(labs, [(1, "M", 60)])) == set()


def test_needs_creatinine_on_each_of_days_1_to_3() -> None:
    # Would be AKI on day 2, but there is no result on day 3.
    labs = [(1, -30 * DAY, 1.0), (1, 2, 1.1), (1, 30, 1.6)]
    assert _run(_tables(labs, [(1, "M", 60)])) == set()


def test_baseline_window_ignores_the_last_7_days_before_icu() -> None:
    # The 0.5 at -3 days is inside the 7-day gap, so the baseline stays 1.0 and
    # 1.1 / 1.2 / 1.3 is not AKI. Using the 0.5 would make the baseline 0.75 and
    # flag 1.2 on day 2.
    labs = [(1, -10 * DAY, 1.0), (1, -3 * DAY, 0.5), (1, 2, 1.1), (1, 30, 1.2), (1, 50, 1.3)]
    assert _run(_tables(labs, [(1, "M", 60)])) == set()


def test_mdrd_fallback_depends_on_sex() -> None:
    # No pre-ICU creatinine, so the baseline is the MDRD estimate at age 60:
    # male 1.0708 (1.5 x = 1.606), female 0.8218 (1.5 x = 1.233).
    # Same results for both: 1.4 / 1.45 / 1.62. The man has new AKI on day 3;
    # the woman already meets 1.5 x baseline on day 1, so she is excluded.
    labs = [(s, h, v) for s in (1, 2) for h, v in ((2, 1.4), (30, 1.45), (50, 1.62))]
    assert _run(_tables(labs, [(1, "M", 60), (2, "F", 60)])) == {1}


@pytest.mark.parametrize(("value", "flagged"), [(1.607, True), (1.605, False)])
def test_mdrd_uses_the_printed_exponent(value: float, flagged: bool) -> None:
    # With the printed exponent -0.887, 1.5 x baseline is 1.6062 for a man of 60;
    # with -1/1.154 it would be 1.6036, and 1.605 would count as AKI.
    labs = [(1, 2, 1.4), (1, 30, 1.45), (1, 50, value)]
    assert (_run(_tables(labs, [(1, "M", 60)])) == {1}) is flagged


def test_only_the_first_icu_stay_counts() -> None:
    # Patient 1 has two ICU stays (admissions 11 and 12). Only the first counts:
    # it has no AKI, and the second stay's AKI is ignored.
    first = [(1, -30 * DAY, 1.0), (1, 2, 1.0), (1, 30, 1.0), (1, 50, 1.0)]
    later = 30 * DAY
    second = [(1, later + 2, 1.0), (1, later + 30, 1.6), (1, later + 50, 1.6)]
    stays = [(1, 11, 0.0), (1, 12, float(later))]
    assert _run(_tables(first + second, [(1, "M", 60)], stays)) == set()


def test_adults_only() -> None:
    labs = [(1, -30 * DAY, 1.0), (1, 2, 1.1), (1, 30, 1.6), (1, 50, 1.5)]
    assert _run(_tables(labs, [(1, "M", 17)])) == set()
