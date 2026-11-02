-- name: aki_kdigo_7d
-- condition: aki
-- description: Serum creatinine >= 1.5 x the lowest value in the prior 7 days, within one admission.
-- reference: KDIGO 2012 AKI guideline, creatinine criterion 2 (baseline = in-admission minimum).
WITH cr AS (
    SELECT l.hadm_id, l.charttime, l.valuenum
    FROM labevents l
    JOIN d_labitems d ON d.itemid = l.itemid
    WHERE lower(d.label) = 'creatinine' AND d.fluid = 'Blood'
      AND l.valuenum IS NOT NULL AND l.hadm_id IS NOT NULL
),
flagged AS (
    SELECT later.hadm_id
    FROM cr AS later
    JOIN cr AS earlier
      ON earlier.hadm_id = later.hadm_id
     AND earlier.charttime < later.charttime
     AND earlier.charttime >= later.charttime - INTERVAL 7 DAY
    GROUP BY later.hadm_id, later.charttime, later.valuenum
    HAVING round(later.valuenum - 1.5 * min(earlier.valuenum), 6) >= 0
)
SELECT DISTINCT hadm_id FROM flagged
