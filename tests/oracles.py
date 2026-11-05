"""Independent pandas implementations of the SQL definitions.

If the SQL and these disagree on any dataset, one of them is wrong. They are
written the slow, obvious way on purpose.
"""

from __future__ import annotations

import itertools

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


def aki_rahimi2023_b3(tables: dict[str, pd.DataFrame]) -> set[int]:
    """Kamel Rahimi et al. 2023, Baseline sCr 3: each patient's first ICU stay, with plain loops."""
    first_stay = {}
    for stay in tables["icustays"].itertuples(index=False):
        known = first_stay.get(int(stay.subject_id))
        if known is None or (stay.intime, stay.stay_id) < (known.intime, known.stay_id):
            first_stay[int(stay.subject_id)] = stay

    results_of: dict[int, list[tuple[pd.Timestamp, float]]] = {}
    for lab in tables["labevents"].itertuples(index=False):
        if lab.itemid == 50912 and not pd.isna(lab.valuenum):
            results_of.setdefault(int(lab.subject_id), []).append((lab.charttime, lab.valuenum))

    out = set()
    for patient in tables["patients"].itertuples(index=False):
        stay = first_stay.get(int(patient.subject_id))
        if stay is None:
            continue
        age = patient.anchor_age + stay.intime.year - patient.anchor_year
        if age < 18:
            continue
        results = results_of.get(int(patient.subject_id), [])

        earliest = stay.intime - pd.Timedelta(days=180)
        latest = stay.intime - pd.Timedelta(days=7)
        pre_icu = [value for time, value in results if earliest <= time <= latest]
        if pre_icu:
            baseline = sum(pre_icu) / len(pre_icu)
        else:
            egfr_at_scr_1 = 186 * float(age) ** -0.203
            if patient.gender == "F":
                egfr_at_scr_1 *= 0.742
            baseline = (75 / egfr_at_scr_1) ** -0.887

        days: dict[int, list[tuple[pd.Timestamp, float]]] = {1: [], 2: [], 3: []}
        for time, value in results:
            hours = (time - stay.intime) / pd.Timedelta(hours=1)
            if 0 <= hours < 72:
                days[int(hours // 24) + 1].append((time, value))
        if not all(days.values()):
            continue

        aki_days = set()
        for day, day_results in days.items():
            for time, value in day_results:
                if round(value - 1.5 * baseline, 6) >= 0:
                    aki_days.add(day)
                for other_results in days.values():
                    for earlier_time, earlier_value in other_results:
                        gap = time - earlier_time
                        if (
                            pd.Timedelta(0) < gap <= pd.Timedelta(hours=48)
                            and round(value - earlier_value, 6) >= 0.3
                        ):
                            aki_days.add(day)
        if 1 not in aki_days and aki_days:
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
