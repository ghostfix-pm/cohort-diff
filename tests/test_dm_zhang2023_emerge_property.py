"""Random small sets of patients for dm_zhang2023_emerge: the SQL must agree with the oracle.

The synthetic data only reaches path 5 of Figure 1A (ICD-10 codes, no glucose), so these cover
the rest: ICD-9 type 1 and type 2 codes (with the excluded 250.10 and 250.12), ICD-10 E11 codes,
drug names in mixed case with start dates that often tie, and HbA1c and glucose values at the
thresholds, at or above the 1000 cut-off and missing, from labevents and chartevents."""

from __future__ import annotations

import math
from typing import TypeVar

from hypothesis import given, settings
from hypothesis import strategies as st

from cohort_diff import engine, registry
from tests import oracles
from tests.test_dm_zhang2023_emerge import _tables

CODES = [
    # ICD-9 type 1 (250.x1, 250.x3)
    ("25001", 9),
    ("25093", 9),
    # ICD-9 type 2 (250.x0, 250.x2), and the two excluded codes
    ("25000", 9),
    ("25002", 9),
    ("25040", 9),
    ("25092", 9),
    ("25010", 9),
    ("25012", 9),
    # ICD-10 E11 (not type 2 here), ICD-10 E10, an ICD-9 code read as ICD-10, and non-diabetes
    ("E119", 10),
    ("E1165", 10),
    ("E109", 10),
    ("25000", 10),
    ("4019", 9),
    ("2500", 9),
]
DRUGS = [
    "insulin",
    "Insulin Glargine",
    "pramlintide",
    "metformin",
    "Metformin XR (Glucophage XR)",
    "glipizide",
    "glyburide",
    "sitagliptin",
    "semaglutide",
    "bromocriptine",
    "lisinopril",
    "Sodium Chloride 0.9%",
]
LAB_ITEMS = [50852, 50809, 50931, 52569, 52027, 50912]  # HbA1c, 4 glucose, creatinine
CHART_ITEMS = [220621, 225664, 226537, 220045, 50931]  # 3 glucose, heart rate, a lab itemid
VALUES = [6.4, 6.5, 6.6, 9.0, 124.0, 124.9, 125.0, 126.0, 999.9, 1000.0, 1500.0, math.nan]


T = TypeVar("T")


def _pool(options: list[T]) -> st.SearchStrategy[list[T]]:
    """A few of the options; drawing events from a small pool makes paths such as "insulin and
    no type 2 drug" (path 4) common instead of rare."""
    return st.lists(st.sampled_from(options), min_size=1, max_size=4, unique=True)


@st.composite
def mixed_case(draw: st.DrawFn, names: list[str]) -> str:
    name = draw(st.sampled_from(names))
    upper = draw(st.lists(st.booleans(), min_size=len(name), max_size=len(name)))
    return "".join(c.upper() if u else c.lower() for c, u in zip(name, upper, strict=True))


@st.composite
def patients(draw: st.DrawFn) -> dict[str, object]:
    admissions = [
        (s, 10 * s + k)
        for s in range(1, draw(st.integers(1, 4)) + 1)
        for k in range(draw(st.integers(1, 3)))
    ]
    hadm = st.sampled_from([h for _, h in admissions])
    code = st.sampled_from(draw(_pool(CODES)))
    drugs = draw(_pool(DRUGS))
    # Pooled too, so that an example whose only abnormal value is exactly 6.5 or 125 is common.
    value = st.sampled_from(draw(_pool(VALUES)))
    lab_item = st.sampled_from(draw(_pool(LAB_ITEMS)))
    chart_item = st.sampled_from(draw(_pool(CHART_ITEMS)))
    return {
        "admissions": admissions,
        "dx": draw(st.lists(st.tuples(hadm, code).map(lambda t: (t[0], *t[1])), max_size=6)),
        "rx": draw(st.lists(st.tuples(hadm, mixed_case(drugs), st.integers(0, 3)), max_size=6)),
        "labs": draw(st.lists(st.tuples(hadm, lab_item, value), max_size=6)),
        "charts": draw(st.lists(st.tuples(hadm, chart_item, value), max_size=6)),
    }


@settings(max_examples=400, deadline=None)
@given(patients())
def test_sql_matches_oracle_on_random_patients(data: dict[str, object]) -> None:
    tables = _tables(**data)  # type: ignore[arg-type]  # values are the helper's argument types
    con = engine.connect(tables)
    assert engine.run(con, registry.load("dm_zhang2023_emerge")) == oracles.dm_zhang2023_emerge(
        tables
    )
