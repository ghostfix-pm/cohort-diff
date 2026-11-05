"""Independent pandas implementations of the SQL definitions.

If the SQL and these disagree on any dataset, one of them is wrong. They are
written the slow, obvious way on purpose.
"""

from __future__ import annotations

import itertools
from typing import Any

import pandas as pd


def creatinine(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    items = tables["d_labitems"]
    ids = items[(items["label"].str.lower() == "creatinine") & (items["fluid"] == "Blood")][
        "itemid"
    ]
    labs = tables["labevents"]
    labs = labs[labs["itemid"].isin(ids) & labs["valuenum"].notna() & labs["hadm_id"].notna()]
    return labs[["hadm_id", "charttime", "valuenum"]]


def aki_kdigo_48h(tables: dict[str, pd.DataFrame]) -> set[int]:
    out = set()
    for hadm, g in creatinine(tables).groupby("hadm_id"):
        rows = list(g.itertuples(index=False))
        for later in rows:
            for earlier in rows:
                gap = later.charttime - earlier.charttime
                if (
                    pd.Timedelta(0) < gap <= pd.Timedelta(hours=48)
                    and round(later.valuenum - earlier.valuenum, 6) >= 0.3
                ):
                    out.add(int(hadm))
    return out


def aki_kdigo_7d(tables: dict[str, pd.DataFrame]) -> set[int]:
    out = set()
    for hadm, g in creatinine(tables).groupby("hadm_id"):
        rows = list(g.itertuples(index=False))
        for later in rows:
            prior = [
                e.valuenum
                for e in rows
                if pd.Timedelta(0) < later.charttime - e.charttime <= pd.Timedelta(days=7)
            ]
            if prior and round(later.valuenum - 1.5 * min(prior), 6) >= 0:
                out.add(int(hadm))
    return out


def aki_kdigo_mimiccode(tables: dict[str, pd.DataFrame]) -> set[int]:
    """mimic-code's KDIGO creatinine rule, one ICU stay at a time, with plain loops."""
    labs = tables["labevents"]
    labs = labs[(labs["itemid"] == 50912) & labs["valuenum"].notna() & (labs["valuenum"] <= 150)]
    out = set()
    for stay in tables["icustays"].itertuples(index=False):
        window = labs[
            (labs["subject_id"] == stay.subject_id)
            & (labs["charttime"] >= stay.intime - pd.Timedelta(days=7))
            & (labs["charttime"] <= stay.outtime)
        ]
        series = window.groupby("charttime")["valuenum"].mean()
        for t, creat in series.items():
            low48 = [v for p, v in series.items() if t - pd.Timedelta(hours=48) <= p < t]
            low7 = [v for p, v in series.items() if t - pd.Timedelta(days=7) <= p < t]
            if (low48 and creat >= min(low48) + 0.3) or (low7 and creat >= 1.5 * min(low7)):
                out.add(int(stay.hadm_id))
    return out


Results = list[tuple[pd.Timestamp, float]]


def _rahimi_adult_first_stays(
    tables: dict[str, pd.DataFrame],
) -> list[tuple[Any, str, int, Results]]:
    """(first ICU stay, gender, age, all creatinine results) for each patient adult at that stay."""
    first_stay = {}
    for stay in tables["icustays"].itertuples(index=False):
        known = first_stay.get(int(stay.subject_id))
        if known is None or (stay.intime, stay.stay_id) < (known.intime, known.stay_id):
            first_stay[int(stay.subject_id)] = stay

    results_of: dict[int, Results] = {}
    for lab in tables["labevents"].itertuples(index=False):
        if lab.itemid == 50912 and not pd.isna(lab.valuenum) and lab.valuenum > 0:
            results_of.setdefault(int(lab.subject_id), []).append((lab.charttime, lab.valuenum))

    out = []
    for patient in tables["patients"].itertuples(index=False):
        stay = first_stay.get(int(patient.subject_id))
        if stay is None:
            continue
        age = patient.anchor_age + stay.intime.year - patient.anchor_year
        if age >= 18:
            results = results_of.get(int(patient.subject_id), [])
            out.append((stay, patient.gender, age, results))
    return out


def _rahimi_mdrd(age: int, gender: str) -> float:
    """The MDRD back-calculation at eGFR 75, with the exponent as printed in the paper."""
    egfr_at_scr_1 = 186 * float(age) ** -0.203
    if gender == "F":
        egfr_at_scr_1 *= 0.742
    return float((75 / egfr_at_scr_1) ** -0.887)


def _rahimi_icu_days(stay: Any, results: Results) -> dict[int, Results] | None:
    """Results by ICU day (1-3), or None unless every one of the three days has a result."""
    days: dict[int, Results] = {1: [], 2: [], 3: []}
    for time, value in results:
        hours = (time - stay.intime) / pd.Timedelta(hours=1)
        if 0 <= hours < 72:
            days[int(hours // 24) + 1].append((time, value))
    return days if all(days.values()) else None


def _rahimi_is_new_aki(days: dict[int, Results], baselines: dict[int, float]) -> bool:
    """AKI on day 2 or 3 and none on day 1; ``baselines`` gives the 1.5 x baseline per ICU day."""
    aki_days = set()
    for day, day_results in days.items():
        for time, value in day_results:
            if round(value - 1.5 * baselines[day], 6) >= 0:
                aki_days.add(day)
            for other_results in days.values():
                for earlier_time, earlier_value in other_results:
                    gap = time - earlier_time
                    if (
                        pd.Timedelta(0) < gap <= pd.Timedelta(hours=48)
                        and round(value - earlier_value, 6) >= 0.3
                    ):
                        aki_days.add(day)
    return 1 not in aki_days and bool(aki_days)


def aki_rahimi2023_b1(tables: dict[str, pd.DataFrame]) -> set[int]:
    """Kamel Rahimi et al. 2023, Baseline sCr 1: the day-1 minimum, on all three days."""
    out = set()
    for stay, _, _, results in _rahimi_adult_first_stays(tables):
        days = _rahimi_icu_days(stay, results)
        if days is None:
            continue
        day_1_min = min(value for _, value in days[1])
        if _rahimi_is_new_aki(days, {1: day_1_min, 2: day_1_min, 3: day_1_min}):
            out.add(int(stay.hadm_id))
    return out


def aki_rahimi2023_b2(tables: dict[str, pd.DataFrame]) -> set[int]:
    """Kamel Rahimi et al. 2023, Baseline sCr 2: MDRD on day 1, the day-1 minimum on days 2-3."""
    out = set()
    for stay, gender, age, results in _rahimi_adult_first_stays(tables):
        days = _rahimi_icu_days(stay, results)
        if days is None:
            continue
        day_1_min = min(value for _, value in days[1])
        if _rahimi_is_new_aki(days, {1: _rahimi_mdrd(age, gender), 2: day_1_min, 3: day_1_min}):
            out.add(int(stay.hadm_id))
    return out


def aki_rahimi2023_b3(tables: dict[str, pd.DataFrame]) -> set[int]:
    """Kamel Rahimi et al. 2023, Baseline sCr 3: each patient's first ICU stay, with plain loops."""
    out = set()
    for stay, gender, age, results in _rahimi_adult_first_stays(tables):
        earliest = stay.intime - pd.Timedelta(days=180)
        latest = stay.intime - pd.Timedelta(days=7)
        pre_icu = [value for time, value in results if earliest <= time <= latest]
        baseline = sum(pre_icu) / len(pre_icu) if pre_icu else _rahimi_mdrd(age, gender)

        days = _rahimi_icu_days(stay, results)
        if days is not None and _rahimi_is_new_aki(days, {1: baseline, 2: baseline, 3: baseline}):
            out.add(int(stay.hadm_id))
    return out


def readmit30(tables: dict[str, pd.DataFrame], exclusions: bool) -> set[int]:
    adm = tables["admissions"].sort_values(["subject_id", "admittime"])
    out = set()
    for _, g in adm.groupby("subject_id"):
        rows = list(g.itertuples(index=False))
        for cur, nxt in itertools.pairwise(rows):
            if nxt.admittime > cur.dischtime + pd.Timedelta(days=30):
                continue
            if exclusions and (
                cur.hospital_expire_flag == 1
                or cur.discharge_location in ("HOSPICE", "AGAINST ADVICE", "DIED")
                or "ELECTIVE" in str(nxt.admission_type).upper()
            ):
                continue
            out.add(int(cur.hadm_id))
    return out
