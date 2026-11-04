from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import given
from hypothesis import strategies as st

from cohort_diff.compare import (
    bootstrap_pairs,
    describe,
    jaccard,
    odds_ratio,
    overlap_table,
    to_markdown,
)
from cohort_diff.engine import admissions_frame, connect
from cohort_diff.registry import builtin

sets = st.sets(st.integers(0, 50), max_size=30)


@given(sets, sets)
def test_jaccard_properties(a: set[int], b: set[int]) -> None:
    j = jaccard(a, b)
    assert 0.0 <= j <= 1.0
    assert j == jaccard(b, a)
    assert jaccard(a, a) == 1.0


def test_overlap_counts() -> None:
    t = overlap_table({"x": {1, 2, 3}, "y": {3, 4}})
    row = t.iloc[0]
    assert (row["both"], row["only_a"], row["only_b"]) == (1, 2, 1)
    assert row["jaccard"] == 0.25


def test_odds_ratio_known_table() -> None:
    # a=20, b=80, c=10, d=90 -> OR = (20*90)/(80*10) = 2.25
    exposed = np.r_[np.ones(100), np.zeros(100)]
    outcome = np.r_[np.ones(20), np.zeros(80), np.ones(10), np.zeros(90)]
    r = odds_ratio(exposed, outcome)
    assert abs(r.estimate - 2.25) < 1e-9
    assert r.low < 2.25 < r.high


def test_odds_ratio_zero_cell_is_finite() -> None:
    r = odds_ratio(np.array([1, 1, 0, 0]), np.array([0, 0, 1, 0]))
    assert np.isfinite(r.estimate)


def test_describe_and_markdown() -> None:
    adm = pd.DataFrame(
        {
            "hadm_id": [1, 2, 3, 4],
            "hospital_expire_flag": [1, 0, 0, 1],
            "age": [60, 70, 80, 90],
            "gender": ["F", "M", "F", "M"],
        }
    )
    d = describe({"x": {1, 2}, "y": set()}, adm)
    assert d.loc[0, "n"] == 2 and d.loc[0, "mortality_pct"] == 50.0
    md = to_markdown(overlap_table({"x": {1, 2}, "y": set()}), d, "t")
    assert md.startswith("# t") and "| definition |" in md


def test_bootstrap_identical_cohorts_has_no_spread() -> None:
    adm = pd.DataFrame(
        {
            "hadm_id": [1, 2, 3, 4, 5, 6],
            "subject_id": [1, 1, 2, 3, 4, 5],
            "hospital_expire_flag": [1, 0, 0, 1, 0, 0],
        }
    )
    t = bootstrap_pairs({"x": {1, 3, 5}, "y": {1, 3, 5}}, adm, n_boot=200)
    row = t.iloc[0]
    assert (row["jaccard_low"], row["jaccard_high"]) == (1.0, 1.0)
    assert (row["or_ratio_low"], row["or_ratio_high"]) == (1.0, 1.0)


def test_bootstrap_resamples_patients_not_admissions() -> None:
    # Patient 1: 10 admissions in both cohorts. Patient 2: 10 admissions only in x.
    # Resampling 2 patients, Jaccard can only be 0, 0.5 or 1, and both extremes
    # happen a quarter of the time, so the 95% interval is [0, 1]. Resampling
    # admissions instead would give a narrow interval around 0.5.
    adm = pd.DataFrame(
        {
            "hadm_id": range(20),
            "subject_id": [1] * 10 + [2] * 10,
            "hospital_expire_flag": [0, 1] * 10,
        }
    )
    t = bootstrap_pairs({"x": set(range(20)), "y": set(range(10))}, adm, n_boot=1000)
    assert (t.loc[0, "jaccard_low"], t.loc[0, "jaccard_high"]) == (0.0, 1.0)


def test_bootstrap_on_synthetic(tables: dict[str, pd.DataFrame]) -> None:
    con = connect(tables)
    defs = builtin()
    cohorts = {
        n: set(con.execute(defs[n].sql).fetchnumpy()["hadm_id"].tolist())
        for n in ("aki_icd", "aki_kdigo_48h", "aki_kdigo_7d")
    }
    t = bootstrap_pairs(cohorts, admissions_frame(con), n_boot=100, seed=1)
    assert len(t) == 3
    assert (t["jaccard_low"] <= t["jaccard"]).all() and (t["jaccard"] <= t["jaccard_high"]).all()
    assert (t["or_ratio_low"] < t["or_ratio_high"]).all()
    again = bootstrap_pairs(cohorts, admissions_frame(con), n_boot=100, seed=1)
    pd.testing.assert_frame_equal(t, again)
