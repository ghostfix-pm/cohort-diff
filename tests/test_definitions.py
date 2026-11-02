from __future__ import annotations

import pandas as pd
import pytest

from cohort_diff import engine, registry


@pytest.fixture(scope="module")
def con(tables: dict[str, pd.DataFrame]):  # type: ignore[no-untyped-def]
    return engine.connect(tables)


def test_all_builtin_definitions_parse_and_run(con) -> None:  # type: ignore[no-untyped-def]
    defs = registry.builtin()
    assert {"aki_icd", "aki_kdigo_48h", "dm_meds", "readmit30_excl"} <= set(defs)
    for d in defs.values():
        assert isinstance(engine.run(con, d), set)


def test_icd_definition(con, tables) -> None:  # type: ignore[no-untyped-def]
    dx = tables["diagnoses_icd"]
    expected = set(dx[dx["icd_code"].str.startswith("N17")]["hadm_id"].astype(int))
    assert engine.run(con, registry.load("aki_icd")) == expected


def test_exclusions_shrink_readmissions(con) -> None:  # type: ignore[no-untyped-def]
    any_ = engine.run(con, registry.load("readmit30_any"))
    excl = engine.run(con, registry.load("readmit30_excl"))
    assert excl <= any_


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
