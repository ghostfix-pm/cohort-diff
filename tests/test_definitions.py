from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cohort_diff import engine, registry
from tests import oracles


@pytest.fixture(scope="module")
def con(tables: dict[str, pd.DataFrame]):  # type: ignore[no-untyped-def]
    return engine.connect(tables)


def test_all_builtin_definitions_parse_and_run(con) -> None:  # type: ignore[no-untyped-def]
    defs = registry.builtin()
    assert {"aki_icd", "aki_kdigo_48h", "dm_meds", "readmit30_excl"} <= set(defs)
    for d in defs.values():
        assert isinstance(engine.run(con, d), set)


@pytest.mark.parametrize(
    ("name", "oracle"),
    [
        ("aki_kdigo_48h", oracles.aki_kdigo_48h),
        ("aki_kdigo_7d", oracles.aki_kdigo_7d),
        ("aki_kdigo_mimiccode", oracles.aki_kdigo_mimiccode),
        ("readmit30_any", lambda t: oracles.readmit30(t, exclusions=False)),
        ("readmit30_excl", lambda t: oracles.readmit30(t, exclusions=True)),
    ],
)
def test_sql_matches_independent_implementation(con, tables, name, oracle) -> None:  # type: ignore[no-untyped-def]
    assert engine.run(con, registry.load(name)) == oracle(tables)


def test_icd_definition(con, tables) -> None:  # type: ignore[no-untyped-def]
    dx = tables["diagnoses_icd"]
    expected = set(dx[dx["icd_code"].str.startswith("N17")]["hadm_id"].astype(int))
    assert engine.run(con, registry.load("aki_icd")) == expected


def test_exclusions_shrink_readmissions(con) -> None:  # type: ignore[no-untyped-def]
    any_ = engine.run(con, registry.load("readmit30_any"))
    excl = engine.run(con, registry.load("readmit30_excl"))
    assert excl <= any_


BASE = datetime(2150, 1, 1)


@settings(max_examples=150, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 24 * 10), st.floats(0.3, 6.0, allow_nan=False)),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x[0],
    )
)
def test_kdigo_on_random_creatinine_series(series: list[tuple[int, float]]) -> None:
    labs = pd.DataFrame(
        {
            "labevent_id": range(len(series)),
            "subject_id": 1,
            "hadm_id": 1,
            "itemid": 50912,
            "charttime": [BASE + timedelta(hours=h) for h, _ in series],
            "valuenum": [round(v, 2) for _, v in series],
        }
    )
    tables = {
        "labevents": labs,
        "d_labitems": pd.DataFrame(
            {
                "itemid": [50912],
                "label": ["Creatinine"],
                "fluid": ["Blood"],
                "category": ["Chemistry"],
            }
        ),
    }
    con = engine.connect(tables)
    for name, oracle in (
        ("aki_kdigo_48h", oracles.aki_kdigo_48h),
        ("aki_kdigo_7d", oracles.aki_kdigo_7d),
    ):
        assert engine.run(con, registry.load(name)) == oracle(tables)


def test_parse_rejects_missing_header() -> None:
    with pytest.raises(ValueError, match="missing"):
        registry.parse("-- name: x\nSELECT 1")


def test_unknown_definition() -> None:
    with pytest.raises(KeyError):
        registry.load("nope")


def test_user_sql_file(tmp_path, con) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "mine.sql"
    f.write_text(
        "-- name: mine\n-- condition: test\n-- description: d\n-- reference: r\n"
        "SELECT hadm_id FROM admissions WHERE hospital_expire_flag = 1"
    )
    assert len(engine.run(con, registry.load(str(f)))) > 0


@pytest.mark.parametrize(("first", "second"), [(0.9, 1.2), (0.7, 1.0), (1.1, 1.4)])
def test_kdigo_catches_exact_threshold_rise(first: float, second: float) -> None:
    """A rise of exactly 0.3 mg/dL is AKI. Floating point makes some of these
    differences 0.29999999999999993; the definition must still flag them."""
    labs = pd.DataFrame(
        {
            "labevent_id": [1, 2],
            "subject_id": 1,
            "hadm_id": 1,
            "itemid": 50912,
            "charttime": [BASE, BASE + timedelta(hours=24)],
            "valuenum": [first, second],
        }
    )
    items = pd.DataFrame(
        {"itemid": [50912], "label": ["Creatinine"], "fluid": ["Blood"], "category": ["Chemistry"]}
    )
    con = engine.connect({"labevents": labs, "d_labitems": items})
    assert engine.run(con, registry.load("aki_kdigo_48h")) == {1}


def _labs(rows: list[tuple[int, int, float]]) -> pd.DataFrame:
    """Creatinine results as (subject_id, hours after BASE, value)."""
    return pd.DataFrame(
        {
            "labevent_id": range(len(rows)),
            "subject_id": [s for s, _, _ in rows],
            "hadm_id": [s for s, _, _ in rows],
            "itemid": 50912,
            "charttime": [BASE + timedelta(hours=h) for _, h, _ in rows],
            "valuenum": [v for _, _, v in rows],
        }
    )


ITEMS = pd.DataFrame(
    {"itemid": [50912], "label": ["Creatinine"], "fluid": ["Blood"], "category": ["Chemistry"]}
)


def _stays(rows: list[tuple[int, int, int]]) -> pd.DataFrame:
    """ICU stays as (subject_id = hadm_id, intime hours, outtime hours after BASE)."""
    return pd.DataFrame(
        {
            "subject_id": [s for s, _, _ in rows],
            "hadm_id": [s for s, _, _ in rows],
            "stay_id": [100 + s for s, _, _ in rows],
            "intime": [BASE + timedelta(hours=i) for _, i, _ in rows],
            "outtime": [BASE + timedelta(hours=o) for _, _, o in rows],
        }
    )


def test_mimiccode_counts_only_rises_during_the_icu_window() -> None:
    """Both patients are in the ICU from hour 24 to 96 and have a 0.4 mg/dL rise within
    48 h. Patient 1's rise is in the ICU; patient 2's comes after ICU discharge, so
    mimic-code leaves it out while the hospital-wide aki_kdigo_48h counts it."""
    tables = {
        "labevents": _labs([(1, 30, 1.0), (1, 50, 1.4), (2, 100, 1.0), (2, 120, 1.4)]),
        "d_labitems": ITEMS,
        "icustays": _stays([(1, 24, 96), (2, 24, 96)]),
    }
    con = engine.connect(tables)
    assert engine.run(con, registry.load("aki_kdigo_mimiccode")) == {1}
    assert engine.run(con, registry.load("aki_kdigo_48h")) == {1, 2}


def test_mimiccode_drops_implausible_values() -> None:
    tables = {
        "labevents": _labs([(1, 30, 1.0), (1, 40, 200.0)]),
        "d_labitems": ITEMS,
        "icustays": _stays([(1, 24, 96)]),
    }
    con = engine.connect(tables)
    assert engine.run(con, registry.load("aki_kdigo_mimiccode")) == set()


@pytest.mark.parametrize(
    ("first", "second", "flagged"), [(0.9, 1.2, True), (0.7, 1.0, True), (1.1, 1.4, False)]
)
def test_mimiccode_keeps_the_source_float_behaviour(
    first: float, second: float, flagged: bool
) -> None:
    """mimic-code compares creat >= baseline + 0.3 without rounding. 1.1 + 0.3 is
    1.4000000000000001 in floating point, so a true 0.3 mg/dL rise from 1.1 is missed.
    The faithful implementation keeps that; aki_kdigo_48h (which rounds) does not."""
    tables = {
        "labevents": _labs([(1, 30, first), (1, 54, second)]),
        "d_labitems": ITEMS,
        "icustays": _stays([(1, 24, 96)]),
    }
    con = engine.connect(tables)
    assert (engine.run(con, registry.load("aki_kdigo_mimiccode")) == {1}) is flagged
    assert engine.run(con, registry.load("aki_kdigo_48h")) == {1}


@settings(max_examples=150, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 24 * 12), st.floats(0.3, 6.0, allow_nan=False)),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x[0],
    ),
    st.integers(0, 24 * 10),
    st.integers(6, 24 * 5),
)
def test_mimiccode_on_random_icu_stays(
    series: list[tuple[int, float]], intime: int, length: int
) -> None:
    tables = {
        "labevents": _labs([(1, h, round(v, 2)) for h, v in series]),
        "d_labitems": ITEMS,
        "icustays": _stays([(1, intime, intime + length)]),
    }
    con = engine.connect(tables)
    assert engine.run(con, registry.load("aki_kdigo_mimiccode")) == oracles.aki_kdigo_mimiccode(
        tables
    )
