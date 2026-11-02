-- name: dm_hba1c
-- condition: diabetes
-- description: Any HbA1c >= 6.5% during the admission.
-- reference: ADA diagnostic threshold for HbA1c (a single in-hospital value, so an approximation).
SELECT DISTINCT l.hadm_id
FROM labevents l
JOIN d_labitems d ON d.itemid = l.itemid
WHERE lower(d.label) IN ('% hemoglobin a1c', 'hemoglobin a1c')
  AND l.valuenum >= 6.5 AND l.hadm_id IS NOT NULL
