"""Split diabetes admissions (Charlson codes) by why Cheng 2025's ICD-10 E11 rule misses them.

Prints counts of admissions only.
"""

import sys

from cohort_diff import engine, registry

con = engine.connect(sys.argv[1])
charlson = engine.run(con, registry.load("dm_charlson_mimiccode"))
cheng = engine.run(con, registry.load("dm_cheng2025"))
missed = sorted(charlson - cheng)
con.execute("CREATE TEMP TABLE missed AS SELECT unnest(?::BIGINT[]) AS hadm_id", [missed])
icd9_only, icd10_not_e11 = con.execute(
    """
    SELECT
      count(*) FILTER (WHERE n10 = 0),
      count(*) FILTER (WHERE n10 > 0)
    FROM (
      SELECT m.hadm_id, count(*) FILTER (WHERE d.icd_version = 10) AS n10
      FROM missed m JOIN diagnoses_icd d USING (hadm_id)
      GROUP BY m.hadm_id
    )
    """
).fetchall()[0]
print(f"Charlson diabetes admissions: {len(charlson)}, also in Cheng: {len(charlson & cheng)}")
print(f"missed by Cheng: {len(missed)} = {icd9_only} coded in ICD-9 only"
      f" + {icd10_not_e11} with ICD-10 codes but no E11 (e.g. type 1, E10)")