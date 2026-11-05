"""Count creatinine results (itemid 50912) <= 0 in a MIMIC-IV folder. Prints aggregates only."""

import sys
from pathlib import Path

import duckdb

path = Path(sys.argv[1]) / "hosp" / "labevents.csv.gz"
literal = str(path).replace("'", "''")
total, non_positive, minimum = duckdb.sql(
    "SELECT count(*), count(*) FILTER (WHERE valuenum <= 0), min(valuenum) "
    f"FROM read_csv_auto('{literal}') WHERE itemid = 50912"
).fetchall()[0]
print(f"creatinine results: {total}, <= 0: {non_positive}, minimum: {minimum}")