"""Explain the eMERGE (Zhang & Cao 2023) diabetes cohort against dm_icd.

For each patient: which eMERGE path made them a case, or why they were not one.
Prints counts of admissions and patients only.
"""

import sys

from cohort_diff import engine, registry

T1 = "insulin|pramlintide"
T2 = (
    "acetohexamide|tolazamide|chlorpropamide|glipizide|glyburide|glimepiride|repaglinide|"
    "nateglinide|metformin|rosiglitazone|pioglitazone|troglitazone|acarbose|miglitol|sitagliptin|"
    "exenatide|alogliptin|saxagliptin|linagliptin|ertugliflozin|dapagliflozin|empagliflozin|"
    "canagliflozin|dulaglutide|semaglutide|liraglutide|lixisenatide|colesevelam|bromocriptine"
)
FACTS = f"""
WITH dx AS (
  SELECT subject_id,
    bool_or(icd_version = 9 AND (icd_code LIKE '250_1' OR icd_code LIKE '250_3')) AS t1dx,
    count(DISTINCT CASE WHEN icd_version = 9 AND (icd_code LIKE '250_0' OR icd_code LIKE '250_2')
      AND icd_code NOT IN ('25010', '25012') THEN hadm_id END) AS t2n
  FROM diagnoses_icd GROUP BY subject_id),
rx AS (
  SELECT subject_id,
    bool_or(regexp_matches(lower(drug), '{T1}')) AS t1rx,
    bool_or(regexp_matches(lower(drug), '{T2}')) AS t2rx,
    min(CASE WHEN regexp_matches(lower(drug), '{T1}') THEN starttime END) AS t1_first,
    min(CASE WHEN regexp_matches(lower(drug), '{T2}') THEN starttime END) AS t2_first
  FROM prescriptions GROUP BY subject_id),
glu AS (
  SELECT subject_id, valuenum FROM labevents
  WHERE itemid IN (50809, 50931, 52569, 52027) AND valuenum < 1000
  UNION ALL
  SELECT subject_id, valuenum FROM chartevents
  WHERE itemid IN (220621, 225664, 226537) AND valuenum < 1000),
abn AS (
  SELECT subject_id FROM glu WHERE valuenum >= 125
  UNION SELECT subject_id FROM labevents WHERE itemid = 50852 AND valuenum >= 6.5)
SELECT a.subject_id,
  coalesce(t1dx, false) AS t1dx, coalesce(t2n, 0) AS t2n,
  coalesce(t1rx, false) AS t1rx, coalesce(t2rx, false) AS t2rx,
  coalesce(t2_first < t1_first, false) AS t2_before,
  abn.subject_id IS NOT NULL AS abn
FROM (SELECT DISTINCT subject_id FROM admissions) a
LEFT JOIN dx USING (subject_id) LEFT JOIN rx USING (subject_id) LEFT JOIN abn USING (subject_id)
"""
LABEL = """
CASE
  WHEN t1dx THEN 'not a case: has a type 1 code'
  WHEN t2n > 0 AND NOT t1rx AND t2rx THEN 'case, path 1: T2 code + T2 drug, no insulin'
  WHEN t2n > 0 AND NOT t1rx AND NOT t2rx AND abn THEN 'case, path 2: T2 code + abnormal lab'
  WHEN t2n > 0 AND t1rx AND t2rx AND t2_before THEN 'case, path 3: T2 drug before insulin'
  WHEN t2n > 0 AND t1rx AND NOT t2rx AND t2n >= 2 THEN 'case, path 4: insulin + T2 code x2'
  WHEN t2n = 0 AND t2rx AND abn THEN 'case, path 5: no ICD-9 T2 code, T2 drug + abnormal lab'
  WHEN t2n > 0 AND t1rx AND t2rx THEN 'not a case: T2 code, insulin not after T2 drug'
  WHEN t2n > 0 AND t1rx THEN 'not a case: T2 code once, insulin, no T2 drug'
  WHEN t2n > 0 THEN 'not a case: T2 code, no drugs, no abnormal lab'
  WHEN t2rx THEN 'not a case: no ICD-9 T2 code, T2 drug, no abnormal lab'
  ELSE 'not a case: no ICD-9 T2 code, no T2 drug'
END
"""

con = engine.connect(sys.argv[1])
icd = engine.run(con, registry.load("dm_icd"))
emerge = engine.run(con, registry.load("dm_zhang2023_emerge"))
con.execute(f"CREATE TEMP TABLE facts AS SELECT *, {LABEL} AS label FROM ({FACTS})")
con.execute("CREATE TEMP TABLE icd AS SELECT unnest(?::BIGINT[]) AS hadm_id", [sorted(icd)])
con.execute("CREATE TEMP TABLE em AS SELECT unnest(?::BIGINT[]) AS hadm_id", [sorted(emerge)])
labelled = con.execute(
    "SELECT hadm_id FROM admissions JOIN facts USING (subject_id) WHERE label LIKE 'case%'"
).fetchall()
assert {h for (h,) in labelled} == emerge, "the path labels disagree with the eMERGE SQL"


def table(title: str, sql: str) -> None:
    print(f"\n{title}")
    for label, adm, pts in con.execute(sql).fetchall():
        print(f"  {adm:4d} admissions, {pts:3d} patients  {label}")


print(f"dm_icd: {len(icd)} admissions; eMERGE: {len(emerge)}; both: {len(icd & emerge)}")
table(
    "eMERGE cases by path",
    """SELECT f.label, count(*), count(DISTINCT f.subject_id)
       FROM em JOIN admissions a USING (hadm_id) JOIN facts f USING (subject_id)
       GROUP BY 1 ORDER BY 1""",
)
table(
    "dm_icd admissions eMERGE misses, by reason",
    """SELECT f.label, count(*), count(DISTINCT f.subject_id)
       FROM icd JOIN admissions a USING (hadm_id) JOIN facts f USING (subject_id)
       WHERE hadm_id NOT IN (SELECT hadm_id FROM em)
       GROUP BY 1 ORDER BY 2 DESC""",
)
only = con.execute(
    """SELECT count(*), count(*) FILTER (WHERE a.subject_id IN (
                SELECT a2.subject_id FROM icd JOIN admissions a2 USING (hadm_id))),
              count(DISTINCT a.subject_id)
       FROM em JOIN admissions a USING (hadm_id)
       WHERE hadm_id NOT IN (SELECT hadm_id FROM icd)"""
).fetchall()[0]
print(
    f"\neMERGE-only admissions: {only[0]} ({only[2]} patients); {only[1]} belong to a patient"
    " with a diabetes code on another admission"
)
