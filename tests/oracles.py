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
