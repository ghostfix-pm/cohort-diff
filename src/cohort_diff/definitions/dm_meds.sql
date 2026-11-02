-- name: dm_meds
-- condition: diabetes
-- description: Any glucose-lowering medication ordered (insulin, metformin, sulfonylureas, DPP-4 inhibitors, SGLT2 inhibitors, GLP-1 agonists).
-- reference: Medication-based phenotype; insulin for stress hyperglycemia will over-capture.
SELECT DISTINCT hadm_id
FROM prescriptions
WHERE hadm_id IS NOT NULL AND regexp_matches(
    lower(drug),
    'insulin|metformin|glipizide|glyburide|glimepiride|sitagliptin|linagliptin|empagliflozin|dapagliflozin|canagliflozin|liraglutide|semaglutide|dulaglutide'
)