"""Hand-made cases for dm_zhang2023_emerge (eMERGE T2DM, Zhang and Cao 2023), one per path of
Figure 1A and one per rule that could be implemented wrongly. Each patient has subject_id = s
and admissions 10*s + k. Written before the SQL, as its specification."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from cohort_diff import engine, registry

T0 = datetime(2150, 1, 1)


def _tables(
    admissions: list[tuple[int, int]],
    dx: list[tuple[int, str, int]] = (),  # type: ignore[assignment]
    rx: list[tuple[int, str, int]] = (),  # type: ignore[assignment]
    labs: list[tuple[int, int, float]] = (),  # type: ignore[assignment]
    charts: list[tuple[int, int, float]] = (),  # type: ignore[assignment]
) -> dict[str, pd.DataFrame]:
    """admissions: (subject_id, hadm_id). dx: (hadm_id, icd_code, icd_version).
    rx: (hadm_id, drug, day of starttime). labs and charts: (hadm_id, itemid, valuenum).
    Column types are set explicitly so that empty tables keep their MIMIC types."""
    subject = dict((h, s) for s, h in admissions)
    return {
        "admissions": pd.DataFrame(
            {"subject_id": [s for s, _ in admissions], "hadm_id": [h for _, h in admissions]}
        ),
        "diagnoses_icd": pd.DataFrame(
            {
                "subject_id": [subject[h] for h, _, _ in dx],
                "hadm_id": [h for h, _, _ in dx],
                "seq_num": 1,
                "icd_code": [c for _, c, _ in dx],
                "icd_version": [v for _, _, v in dx],
            },
            columns=["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"],
        ).astype(
            {"subject_id": "int64", "hadm_id": "int64", "icd_code": str, "icd_version": "int64"}
        ),
        "prescriptions": pd.DataFrame(
            {
                "subject_id": [subject[h] for h, _, _ in rx],
                "hadm_id": [h for h, _, _ in rx],
                "starttime": [T0 + timedelta(days=d) for _, _, d in rx],
                "stoptime": [T0 + timedelta(days=d + 1) for _, _, d in rx],
                "drug": [name for _, name, _ in rx],
            },
            columns=["subject_id", "hadm_id", "starttime", "stoptime", "drug"],
        ).astype(
            {
                "subject_id": "int64",
                "hadm_id": "int64",
                "starttime": "datetime64[us]",
                "stoptime": "datetime64[us]",
                "drug": str,
            }
        ),
        "labevents": pd.DataFrame(
            {
                "labevent_id": range(len(labs)),
                "subject_id": [subject[h] for h, _, _ in labs],
                "hadm_id": [h for h, _, _ in labs],
                "itemid": [i for _, i, _ in labs],
                "charttime": T0,
                "valuenum": [v for _, _, v in labs],
            },
            columns=["labevent_id", "subject_id", "hadm_id", "itemid", "charttime", "valuenum"],
        ).astype({"subject_id": "int64", "hadm_id": "int64", "itemid": "int64", "valuenum": float}),
        "chartevents": pd.DataFrame(
            {
                "subject_id": [subject[h] for h, _, _ in charts],
                "hadm_id": [h for h, _, _ in charts],
                "stay_id": [h for h, _, _ in charts],
                "charttime": T0,
                "itemid": [i for _, i, _ in charts],
                "valuenum": [v for _, _, v in charts],
            },
            columns=["subject_id", "hadm_id", "stay_id", "charttime", "itemid", "valuenum"],
        ).astype({"subject_id": "int64", "hadm_id": "int64", "itemid": "int64", "valuenum": float}),
    }


def _run(tables: dict[str, pd.DataFrame]) -> set[int]:
    return engine.run(engine.connect(tables), registry.load("dm_zhang2023_emerge"))


HBA1C, GLUCOSE_LAB, FINGERSTICK = 50852, 50931, 225664
T2DX, T1DX = ("25000", 9), ("25001", 9)


def test_path_1_t2_diagnosis_and_t2_medication() -> None:
    t = _tables([(1, 11)], dx=[(11, *T2DX)], rx=[(11, "Metformin XR (Glucophage XR)", 0)])
    assert _run(t) == {11}


def test_path_2_t2_diagnosis_no_medication_abnormal_hba1c() -> None:
    normal = _tables([(1, 11)], dx=[(11, *T2DX)], labs=[(11, HBA1C, 6.4)])
    abnormal = _tables([(1, 11)], dx=[(11, *T2DX)], labs=[(11, HBA1C, 6.5)])
    assert _run(normal) == set()
    assert _run(abnormal) == {11}


@pytest.mark.parametrize(
    ("t2_day", "t1_day", "is_case"), [(0, 5, True), (5, 0, False), (3, 3, False)]
)
def test_path_3_t2_medication_must_come_first(t2_day: int, t1_day: int, is_case: bool) -> None:
    t = _tables(
        [(1, 11)],
        dx=[(11, *T2DX)],
        rx=[(11, "glipizide", t2_day), (11, "Insulin Glargine", t1_day)],
    )
    assert (_run(t) == {11}) is is_case


def test_path_4_insulin_only_needs_two_coded_admissions() -> None:
    one = _tables([(1, 11)], dx=[(11, *T2DX)], rx=[(11, "Insulin", 0)])
    two = _tables([(1, 11), (1, 12)], dx=[(11, *T2DX), (12, "25002", 9)], rx=[(11, "Insulin", 0)])
    assert _run(one) == set()
    assert _run(two) == {11, 12}


def test_path_5_no_diagnosis_t2_medication_and_fingerstick_glucose() -> None:
    # Glucose from chartevents (fingerstick) counts; 125 is the threshold.
    high = _tables([(1, 11)], rx=[(11, "metformin", 0)], charts=[(11, FINGERSTICK, 125.0)])
    low = _tables([(1, 11)], rx=[(11, "metformin", 0)], charts=[(11, FINGERSTICK, 124.0)])
    assert _run(high) == {11}
    assert _run(low) == set()


def test_glucose_of_1000_or_more_is_an_outlier() -> None:
    t = _tables([(1, 11)], rx=[(11, "metformin", 0)], labs=[(11, GLUCOSE_LAB, 1000.0)])
    assert _run(t) == set()


def test_any_type_1_diagnosis_excludes_the_patient() -> None:
    # Every other path is met, but a type 1 code on another admission excludes the patient.
    t = _tables(
        [(1, 11), (1, 12)],
        dx=[(11, *T2DX), (12, *T1DX)],
        rx=[(11, "metformin", 0)],
        labs=[(11, HBA1C, 9.0)],
    )
    assert _run(t) == set()


def test_icd9_only_so_icd10_e11_does_not_count() -> None:
    # As written: E11.9 is not a type 2 diagnosis here, so without one, metformin needs an
    # abnormal lab (path 5), and this patient has none.
    t = _tables([(1, 11)], dx=[(11, "E119", 10)], rx=[(11, "metformin", 0)])
    assert _run(t) == set()


def test_250_10_and_250_12_are_not_type_2_diagnoses() -> None:
    t = _tables([(1, 11)], dx=[(11, "25010", 9)], labs=[(11, HBA1C, 9.0)])
    assert _run(t) == set()


def test_all_admissions_of_a_case_patient_are_returned() -> None:
    # Patient 1 is a case through admission 11; admission 12 has no diabetes data but is returned.
    # Patient 2 has nothing and is not a case.
    t = _tables(
        [(1, 11), (1, 12), (2, 21)],
        dx=[(11, *T2DX)],
        rx=[(11, "glyburide", 0)],
    )
    assert _run(t) == {11, 12}
