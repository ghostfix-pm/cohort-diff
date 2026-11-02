-- name: aki_kdigo_48h
-- condition: aki
-- description: Serum creatinine rises by >= 0.3 mg/dL within 48 hours, within one admission.
-- reference: KDIGO 2012 AKI guideline, creatinine criterion 1 (urine-output criterion not used).
WITH cr AS (
    SELECT l.hadm_id, l.charttime, l.valuenum
    FROM labevents l
    JOIN d_labitems d ON d.itemid = l.itemid
    WHERE lower(d.label) = 'creatinine' AND d.fluid = 'Blood'
      AND l.valuenum IS NOT NULL AND l.hadm_id IS NOT NULL
)
SELECT DISTINCT later.hadm_id
FROM cr AS later
JOIN cr AS earlier
  ON earlier.hadm_id = later.hadm_id
 AND earlier.charttime < later.charttime
 AND earlier.charttime >= later.charttime - INTERVAL 48 HOUR
-- Round the difference: in floating point 1.2 - 0.9 = 0.29999999999999993,
-- which would silently miss a true 0.3 mg/dL rise.
WHERE round(later.valuenum - earlier.valuenum, 6) >= 0.3