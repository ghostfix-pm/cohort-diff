-- name: readmit30_excl
-- condition: readmission
-- description: As readmit30_any, but excludes index admissions ending in death, hospice or discharge against advice, and planned (elective) readmissions.
-- reference: Inspired by the CMS Hospital Readmissions Reduction Program exclusions (simplified).
WITH ordered AS (
    SELECT hadm_id, dischtime, hospital_expire_flag, discharge_location,
           lead(admittime) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admit,
           lead(admission_type) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_type
    FROM admissions
)
SELECT hadm_id
FROM ordered
WHERE next_admit IS NOT NULL
  AND next_admit <= dischtime + INTERVAL 30 DAY
  AND hospital_expire_flag = 0
  AND coalesce(discharge_location, '') NOT IN ('HOSPICE', 'AGAINST ADVICE', 'DIED')
  AND upper(coalesce(next_type, '')) NOT LIKE '%ELECTIVE%'