"""Hand-made cases for dm_charlson_mimiccode and dm_cheng2025. One admission per code
(hadm_id = position + 1). Written before the SQL, as its specification."""

from __future__ import annotations

import pandas as pd

from cohort_diff import engine, registry


def _dx(codes: list[tuple[str, int]]) -> dict[str, pd.DataFrame]:
    """codes: (icd_code as stored in MIMIC-IV, without dots; icd_version)."""
    return {
        "diagnoses_icd": pd.DataFrame(
            {
                "subject_id": range(1, len(codes) + 1),
                "hadm_id": range(1, len(codes) + 1),
                "seq_num": 1,
                "icd_code": [c for c, _ in codes],
                "icd_version": [v for _, v in codes],
            }
        )
    }


def _run(name: str, codes: list[tuple[str, int]]) -> set[int]:
    return engine.run(engine.connect(_dx(codes)), registry.load(name))


CODES = [
    ("25000", 9),  # 1  T2DM without complications (ICD-9)
    ("25013", 9),  # 2  T1DM with ketoacidosis (ICD-9)
    ("25060", 9),  # 3  diabetes with neurological manifestations (ICD-9, with complications)
    ("E119", 10),  # 4  T2DM without complications
    ("E1165", 10),  # 5  T2DM with hyperglycemia
    ("E1010", 10),  # 6  T1DM with ketoacidosis
    ("E0800", 10),  # 7  diabetes due to an underlying condition (secondary)
    ("O2410", 10),  # 8  pre-existing T2DM in pregnancy
    ("R7303", 10),  # 9  prediabetes
    ("24900", 9),  # 10 secondary diabetes (ICD-9)
    ("E119", 9),  # 11 an E11 code wrongly labelled ICD-9: the version decides
    ("4280", 9),  # 12 heart failure, not diabetes
]


def test_charlson_codes() -> None:
    # ICD-9 250.x and ICD-10 E10-E14, type 1 and type 2, with or without complications.
    assert _run("dm_charlson_mimiccode", CODES) == {1, 2, 3, 4, 5, 6}


def test_cheng_is_icd10_e11_only() -> None:
    # Only ICD-10 E11: no ICD-9 codes, no type 1 (E10), no secondary diabetes (E08).
    assert _run("dm_cheng2025", CODES) == {4, 5}


def test_icd9_only_admission_is_diabetes_for_charlson_but_not_for_cheng() -> None:
    codes = [("25000", 9)]
    assert _run("dm_charlson_mimiccode", codes) == {1}
    assert _run("dm_cheng2025", codes) == set()


def test_several_codes_on_one_admission_count_once() -> None:
    tables = _dx([("E119", 10), ("E1165", 10)])
    tables["diagnoses_icd"]["hadm_id"] = 7
    con = engine.connect(tables)
    assert engine.run(con, registry.load("dm_cheng2025")) == {7}
    assert engine.run(con, registry.load("dm_charlson_mimiccode")) == {7}
