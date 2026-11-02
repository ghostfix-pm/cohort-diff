"""Run cohort definitions with DuckDB over MIMIC-IV-shaped tables.

DuckDB reads the demo's ``.csv.gz`` files in place, so nothing has to be
loaded into a server first.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from cohort_diff.registry import Definition

TABLES = ("patients", "admissions", "labevents", "d_labitems", "diagnoses_icd", "prescriptions")
OPTIONAL = {"prescriptions"}


def _find(root: Path, table: str) -> Path | None:
    for candidate in (
        root / "hosp" / f"{table}.csv.gz",
        root / "hosp" / f"{table}.csv",
        root / f"{table}.csv.gz",
        root / f"{table}.csv",
    ):
        if candidate.exists():
            return candidate
    return None


def connect(data: str | Path | dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection with one view per MIMIC table.

    ``data`` is a MIMIC-IV root (containing ``hosp/``), a flat CSV directory, or a
    dict of DataFrames (used by the tests).
    """
    con = duckdb.connect()
    if isinstance(data, dict):
        for name, frame in data.items():
            con.register(f"_{name}", frame)
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM _{name}")
        return con
    root = Path(data)
    for table in TABLES:
        path = _find(root, table)
        if path is None:
            if table in OPTIONAL:
                con.execute(
                    f"CREATE VIEW {table} AS SELECT NULL::BIGINT AS subject_id, "
                    "NULL::BIGINT AS hadm_id, NULL::TIMESTAMP AS starttime, "
                    "NULL::TIMESTAMP AS stoptime, NULL::VARCHAR AS drug WHERE false"
                )
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
