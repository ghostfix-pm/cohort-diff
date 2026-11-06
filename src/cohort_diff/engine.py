"""Run cohort definitions with DuckDB over MIMIC-IV-shaped tables.

DuckDB reads the demo's ``.csv.gz`` files in place, so nothing has to be
loaded into a server first.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from cohort_diff.registry import Definition

TABLES = (
    "patients",
    "admissions",
    "labevents",
    "d_labitems",
    "diagnoses_icd",
    "prescriptions",
    "icustays",
    "chartevents",
)
# Optional tables become empty views with these columns when the data lacks them.
OPTIONAL = {
    "prescriptions": "NULL::BIGINT AS subject_id, NULL::BIGINT AS hadm_id, "
    "NULL::TIMESTAMP AS starttime, NULL::TIMESTAMP AS stoptime, NULL::VARCHAR AS drug",
    "icustays": "NULL::BIGINT AS subject_id, NULL::BIGINT AS hadm_id, NULL::BIGINT AS stay_id, "
    "NULL::TIMESTAMP AS intime, NULL::TIMESTAMP AS outtime",
    "chartevents": "NULL::BIGINT AS subject_id, NULL::BIGINT AS hadm_id, NULL::BIGINT AS stay_id, "
    "NULL::TIMESTAMP AS charttime, NULL::BIGINT AS itemid, NULL::DOUBLE AS valuenum",
}


def _find(root: Path, table: str) -> Path | None:
    for candidate in (
        root / "hosp" / f"{table}.csv.gz",
        root / "hosp" / f"{table}.csv",
        root / "icu" / f"{table}.csv.gz",
        root / "icu" / f"{table}.csv",
        root / f"{table}.csv.gz",
        root / f"{table}.csv",
    ):
        if candidate.exists():
            return candidate
    return None


def connect(data: str | Path | dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection with one view per MIMIC table.

    ``data`` is a MIMIC-IV root (containing ``hosp/`` and optionally ``icu/``), a flat
    CSV directory, or a dict of DataFrames (used by the tests). Optional tables that
    are missing become empty views, so definitions that need them return no admissions.
    """
    con = duckdb.connect()
    if isinstance(data, dict):
        for name, frame in data.items():
            con.register(f"_{name}", frame)
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM _{name}")
        for name, columns in OPTIONAL.items():
            if name not in data:
                con.execute(f"CREATE VIEW {name} AS SELECT {columns} WHERE false")
        return con
    root = Path(data)
    for table in TABLES:
        path = _find(root, table)
        if path is None:
            if table in OPTIONAL:
                con.execute(f"CREATE VIEW {table} AS SELECT {OPTIONAL[table]} WHERE false")
                continue
            raise FileNotFoundError(f"{table}: expected {root}/hosp/{table}.csv.gz")
        # Views can't take bound parameters, so quote the path as an SQL literal.
        literal = str(path).replace("'", "''")
        con.execute(
            f"CREATE VIEW {table} AS SELECT * FROM read_csv_auto('{literal}', header = true)"
        )
    return con


def run(con: duckdb.DuckDBPyConnection, definition: Definition) -> set[int]:
    """The admissions (``hadm_id``) that meet a definition."""
    rows = con.execute(definition.sql).fetchall()
    return {int(r[0]) for r in rows if r[0] is not None}


def admissions_frame(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per admission with the fields used to describe cohorts."""
    return con.execute(
        """
        SELECT a.hadm_id, a.subject_id, a.hospital_expire_flag,
               date_diff('hour', a.admittime, a.dischtime) / 24.0 AS los_days,
               p.anchor_age + (year(a.admittime) - p.anchor_year) AS age,
               p.gender
        FROM admissions a JOIN patients p ON p.subject_id = a.subject_id
        """
    ).df()
