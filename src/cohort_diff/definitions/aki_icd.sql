-- name: aki_icd
-- condition: aki
-- description: Any AKI diagnosis code on the admission (ICD-10 N17.*, ICD-9 584.*).
-- reference: Common administrative-data definition; codes are assigned after discharge.
SELECT DISTINCT hadm_id
FROM diagnoses_icd
WHERE (icd_version = 10 AND icd_code LIKE 'N17%')
   OR (icd_version = 9 AND icd_code LIKE '584%')
