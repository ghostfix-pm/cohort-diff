-- name: dm_zhang2023_emerge
-- condition: diabetes
-- description: eMERGE type 2 diabetes case algorithm as adapted to MIMIC-IV by Zhang and Cao: patients with no type 1 diabetes code who meet one of five paths combining ICD-9 type 2 diabetes codes, type 1 and type 2 diabetes medications (and their order), at least 2 coded admissions, and an abnormal glucose or HbA1c; all admissions of case patients.
-- reference: Zhang W, Cao T. Automated Type 2 Diabetes Case and Control Identification from the MIMIC-IV Database. AMIA Jt Summits Transl Sci Proc. 2023;2023:602-611. Methods (Data extraction and pre-processing), Figure 1A, Tables 3-5. Algorithm: eMERGE (Kho AN, et al. JAMIA 2012;19(2):212-8).
-- As written (Table 3, ICD-9 only; the paper states ICD-10 T2DM codes "were not found in MIMIC-IV"):
--   type 1 diagnosis = ICD-9 250.x1 or 250.x3; type 2 diagnosis = ICD-9 250.x0 or 250.x2,
--   excluding 250.10 and 250.12. Codes are stored without dots (250.x0 = '250' + digit + '0').
-- As written (Table 4): type 1 medication = insulin, pramlintide. Type 2 medication = acetohexamide,
--   tolazamide, chlorpropamide, glipizide, glyburide, glimepiride, repaglinide, nateglinide,
--   metformin, rosiglitazone, pioglitazone, troglitazone, acarbose, miglitol, sitagliptin, exenatide,
--   alogliptin, saxagliptin, linagliptin, ertugliflozin, dapagliflozin, empagliflozin,
--   canagliflozin, dulaglutide, semaglutide, liraglutide, lixisenatide, colesevelam, bromocriptine.
-- As written (Table 5 and text): abnormal lab = maximum HbA1c (labevents itemid 50852) >= 6.5, or
--   maximum glucose >= 125 mg/dL, all glucose treated as fasting: labevents itemids 50809, 50931,
--   52569, 52027 and chartevents itemids 220621, 225664, 226537; glucose values >= 1000 removed.
-- As written (Figure 1A), with no type 1 diagnosis, a patient is a case if:
--   (1) type 2 diagnosis, no type 1 medication, type 2 medication;
--   (2) type 2 diagnosis, no medication of either type, abnormal lab;
--   (3) type 2 diagnosis, type 1 and type 2 medication, the first type 2 medication before the first
--       type 1 medication;
--   (4) type 2 diagnosis, type 1 medication, no type 2 medication, type 2 diagnosis on >= 2 admissions;
--   (5) no type 2 diagnosis, type 2 medication, abnormal lab.
-- The flowchart's patient counts do not add up (for example, 382,278 patients enter and 253,006 leave
--   "no type 1 diagnosis"); only its structure and the final 12,735 cases are used.
-- Assumed: the phenotype is per patient (subject_id); the cohort is every admission of a case
--   patient (the paper's Table 7 counts all 53,038 admissions of its cases).
-- Assumed: a medication is a prescriptions row whose drug name contains a listed name, ignoring case;
--   its date is starttime. "Before" is strictly earlier; equal first dates are not "before".
-- Assumed: ">= 2 diagnoses" (the paper's adaptation of eMERGE's ">= 2 physician diagnoses") counts
--   distinct admissions with a type 2 code, since diagnoses_icd has no dates.
-- Assumed: lab values must be present (valuenum not null); glucose and HbA1c are taken over all of a
--   patient's records, from any admission or ICU stay.
WITH dx AS (
    SELECT subject_id, hadm_id,
           regexp_full_match(icd_code, '250[0-9][13]') AS is_t1,
           regexp_full_match(icd_code, '250[0-9][02]') AND icd_code NOT IN ('25010', '25012')
               AS is_t2
    FROM diagnoses_icd
    WHERE icd_version = 9
),
dx_patient AS (
    SELECT subject_id,
           bool_or(is_t1) AS t1_dx,
           bool_or(is_t2) AS t2_dx,
           count(DISTINCT hadm_id) FILTER (WHERE is_t2) AS t2_dx_admissions
    FROM dx
    GROUP BY subject_id
),
rx AS (
    SELECT subject_id, starttime,
           regexp_matches(lower(drug), 'insulin|pramlintide') AS is_t1,
           regexp_matches(
               lower(drug),
               'acetohexamide|tolazamide|chlorpropamide|glipizide|glyburide|glimepiride|'
               || 'repaglinide|nateglinide|metformin|rosiglitazone|pioglitazone|troglitazone|'
               || 'acarbose|miglitol|sitagliptin|exenatide|alogliptin|saxagliptin|linagliptin|'
               || 'ertugliflozin|dapagliflozin|empagliflozin|canagliflozin|dulaglutide|'
               || 'semaglutide|liraglutide|lixisenatide|colesevelam|bromocriptine'
           ) AS is_t2
    FROM prescriptions
    WHERE drug IS NOT NULL
),
rx_patient AS (
    SELECT subject_id,
           bool_or(is_t1) AS t1_med,
           bool_or(is_t2) AS t2_med,
           min(starttime) FILTER (WHERE is_t1) AS first_t1,
           min(starttime) FILTER (WHERE is_t2) AS first_t2
    FROM rx
    GROUP BY subject_id
),
lab AS (
    SELECT subject_id FROM labevents
    WHERE itemid = 50852 AND valuenum IS NOT NULL
    GROUP BY subject_id
    HAVING max(valuenum) >= 6.5
    UNION
    SELECT subject_id FROM (
        SELECT subject_id, valuenum FROM labevents
        WHERE itemid IN (50809, 50931, 52569, 52027)
        UNION ALL
        SELECT subject_id, valuenum FROM chartevents
        WHERE itemid IN (220621, 225664, 226537)
    ) AS glucose
    WHERE valuenum IS NOT NULL AND valuenum < 1000
    GROUP BY subject_id
    HAVING max(valuenum) >= 125
),
patient AS (
    SELECT p.subject_id,
           coalesce(d.t1_dx, false) AS t1_dx,
           coalesce(d.t2_dx, false) AS t2_dx,
           coalesce(d.t2_dx_admissions, 0) AS t2_dx_admissions,
           coalesce(r.t1_med, false) AS t1_med,
           coalesce(r.t2_med, false) AS t2_med,
           coalesce(r.first_t2 < r.first_t1, false) AS t2_med_first,
           l.subject_id IS NOT NULL AS abnormal_lab
    FROM (SELECT DISTINCT subject_id FROM admissions) AS p
    LEFT JOIN dx_patient AS d USING (subject_id)
    LEFT JOIN rx_patient AS r USING (subject_id)
    LEFT JOIN lab AS l USING (subject_id)
),
cases AS (
    SELECT subject_id
    FROM patient
    WHERE NOT t1_dx
      AND (
          (t2_dx AND NOT t1_med AND t2_med)                                   -- path 1
          OR (t2_dx AND NOT t1_med AND NOT t2_med AND abnormal_lab)           -- path 2
          OR (t2_dx AND t1_med AND t2_med AND t2_med_first)                   -- path 3
          OR (t2_dx AND t1_med AND NOT t2_med AND t2_dx_admissions >= 2)      -- path 4
          OR (NOT t2_dx AND t2_med AND abnormal_lab)                          -- path 5
      )
)
SELECT DISTINCT a.hadm_id
FROM admissions AS a
JOIN cases AS c USING (subject_id)