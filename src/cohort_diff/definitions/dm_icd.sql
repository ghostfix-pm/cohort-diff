-- name: dm_icd
-- condition: diabetes
-- description: Any diabetes diagnosis code (ICD-10 E10-E14, ICD-9 250.*).
-- reference: Common administrative-data definition.
SELECT DISTINCT hadm_id
FROM diagnoses_icd
WHERE (icd_version = 10 AND substr(icd_code, 1, 3) IN ('E10', 'E11', 'E13', 'E14'))
   OR (icd_version = 9 AND icd_code LIKE '250%')
