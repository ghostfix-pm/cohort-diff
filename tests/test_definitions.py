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
