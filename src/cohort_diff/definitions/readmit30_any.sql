-- name: readmit30_any
-- condition: readmission
-- description: Index admissions followed by any admission of the same patient within 30 days of discharge.
-- reference: The simplest definition used in many MIMIC papers.
WITH ordered AS (
    SELECT hadm_id, dischtime,
           lead(admittime) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admit
    FROM admissions
)
SELECT hadm_id
FROM ordered
WHERE next_admit IS NOT NULL AND next_admit <= dischtime + INTERVAL 30 DAY