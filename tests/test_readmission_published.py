"""Hand-made cases for readmit_gupta2022, readmit_prempeh2026 and readmit_shen2025.
Written before the SQL, as its specification.

Times are in days after 2150-01-01 (5.5 = noon on day 5). One patient per scenario unless
the test says otherwise. Each test also states what the other definitions give, so the
differences between the three papers are visible in one place."""

from __future__ import annotations

import pandas as pd

from cohort_diff import engine, registry

BASE = pd.Timestamp("2150-01-01")
MINUTE = 1 / 1440

# (subject_id, hadm_id, admit_day, disch_day, died_in_hospital)
Adm = tuple[int, int, float, float, int]


def _at(day: float) -> pd.Timestamp:
    return BASE + pd.to_timedelta(round(day * 86400), unit="s")


def _tables(adms: list[Adm], ages: dict[int, int] | None = None) -> dict[str, pd.DataFrame]:
    ages = ages or {}
    subjects = sorted({a[0] for a in adms})
    return {
        "admissions": pd.DataFrame(
            {
                "subject_id": [a[0] for a in adms],
                "hadm_id": [a[1] for a in adms],
                "admittime": [_at(a[2]) for a in adms],
                "dischtime": [_at(a[3]) for a in adms],
                "hospital_expire_flag": [a[4] for a in adms],
            }
        ),
        "patients": pd.DataFrame(
            {"subject_id": subjects, "anchor_age": [ages.get(s, 60) for s in subjects]}
        ),
    }


def _run(name: str, adms: list[Adm], ages: dict[int, int] | None = None) -> set[int]:
    return engine.run(engine.connect(_tables(adms, ages)), registry.load(name))


GUPTA, PREMPEH, SHEN = "readmit_gupta2022", "readmit_prempeh2026", "readmit_shen2025"


def test_readmission_within_30_days() -> None:
    adms = [(1, 1, 0, 5, 0), (1, 2, 20, 25, 0)]
    assert _run(GUPTA, adms) == {1}
    assert _run(PREMPEH, adms) == {1}
    assert _run(SHEN, adms) == {1}


def test_gupta_30_days_is_inclusive() -> None:
    adms = [
        (1, 1, 0, 5, 0), (1, 2, 35, 40, 0),  # readmitted exactly 30 days after discharge
        (2, 3, 0, 5, 0), (2, 4, 35 + MINUTE, 40, 0),  # 30 days and 1 minute
    ]  # fmt: skip
    assert _run(GUPTA, adms) == {1}


def test_prempeh_90_day_window() -> None:
    adms = [
        (1, 1, 0, 5, 0), (1, 2, 65, 70, 0),  # 60 days: Prempeh yes, Gupta (30 days) no
        (2, 3, 0, 5, 0), (2, 4, 95, 100, 0),  # exactly 90 days
        (3, 5, 0, 5, 0), (3, 6, 95 + MINUTE, 100, 0),  # 90 days and 1 minute
    ]  # fmt: skip
    assert _run(PREMPEH, adms) == {1, 3}
    assert _run(GUPTA, adms) == set()


def test_overlapping_admission_is_not_a_readmission() -> None:
    # The second admission starts before the first one ends (as in a transfer recorded twice).
    adms = [(1, 1, 0, 10, 0), (1, 2, 9, 12, 0)]
    assert _run(GUPTA, adms) == set()
    assert _run(PREMPEH, adms) == set()
    assert _run(SHEN, adms) == set()
    # The built-in rule only asks that the next admission starts within 30 days of discharge.
    assert _run("readmit30_any", adms) == {1}


def test_any_later_admission_counts_for_gupta_and_prempeh() -> None:
    # Admission 2 starts inside admission 1; admission 3 starts 10 days after admission 1 ends.
    adms = [(1, 1, 0, 40, 0), (1, 2, 2, 3, 0), (1, 3, 50, 55, 0)]
    assert _run(GUPTA, adms) == {1}  # 2 -> 3 is 47 days, beyond 30
    assert _run(PREMPEH, adms) == {1, 2}
    # Shen looks only at the NEXT admission: for admission 1 that is admission 2 (a gap
    # under 1 day), and admission 2 is shorter than 2 days.
    assert _run(SHEN, adms) == set()


def test_death_on_the_readmission() -> None:
    adms = [(1, 1, 0, 5, 0), (1, 2, 10, 15, 1)]
    # Gupta removes admissions ending in death before looking for readmissions.
    assert _run(GUPTA, adms) == set()
    assert _run(PREMPEH, adms) == {1}
    assert _run(SHEN, adms) == {1}


def test_death_on_the_index_admission() -> None:
    # Not possible in real data (the patient cannot be readmitted), but each rule says what
    # it would do.
    adms = [(1, 1, 0, 5, 1), (1, 2, 10, 15, 0)]
    assert _run(GUPTA, adms) == set()
    assert _run(PREMPEH, adms) == {1}  # Prempeh states no death exclusion
    assert _run(SHEN, adms) == set()


def test_gupta_adults_only() -> None:
    adms = [(1, 1, 0, 5, 0), (1, 2, 10, 15, 0)]
    assert _run(GUPTA, adms, ages={1: 17}) == set()
    assert _run(PREMPEH, adms, ages={1: 17}) == {1}


def test_shen_window_boundaries() -> None:
    adms = [
        (1, 1, 0, 5, 0), (1, 2, 95, 100, 0),  # exactly 90 days: in
        (2, 3, 0, 5, 0), (2, 4, 6, 8, 0),  # exactly 1 day: in
        (3, 5, 0, 5, 0), (3, 6, 5.5, 8, 0),  # 12 hours: under 1 day, out
    ]  # fmt: skip
    assert _run(SHEN, adms) == {1, 3}


def test_shen_short_gap_excludes_even_with_a_later_readmission() -> None:
    adms = [(1, 1, 0, 5, 0), (1, 2, 5.5, 6, 0), (1, 3, 30, 35, 0)]
    assert _run(SHEN, adms) == set()
    assert _run(GUPTA, adms) == {1, 2}
    assert _run(PREMPEH, adms) == {1, 2}


def test_shen_stay_of_at_least_2_days() -> None:
    adms = [
        (1, 1, 0, 1.5, 0), (1, 2, 10, 15, 0),  # 1.5-day stay: out
        (2, 3, 0, 2, 0), (2, 4, 10, 15, 0),  # exactly 2 days: in
    ]  # fmt: skip
    assert _run(SHEN, adms) == {3}
    assert _run(GUPTA, adms) == {1, 3}
