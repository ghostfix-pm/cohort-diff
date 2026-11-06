-- name: dm_cheng2025
-- condition: diabetes
-- description: Type 2 diabetes = an ICD-10 E11 diagnosis code on the admission ("Diagnosis of type 2 diabetes (ICD-10: E11) ... documented during hospitalization").
-- reference: Cheng J, Cheng Q, Wu Y, Yin J, He F. Association between triglyceride-glucose-body mass index and adverse prognosis in elderly patients with severe heart failure and type 2 diabetes: a retrospective study based on the MIMIC-IV database. Cardiovasc Diabetol. 2025;24:299. doi:10.1186/s12933-025-02870-x. Methods, Inclusion criteria.
-- Only the paper's diabetes rule is implemented. Its other inclusion criteria (heart failure
--   ICD-10 I50, age > 65, first ICU admission, complete TyG-BMI data) define its study cohort,
--   not diabetes, and are not part of this definition.
-- As written, ICD-10 only: admissions coded in ICD-9 (before October 2015 in MIMIC-IV) never qualify.
-- Assumed: "E11" means any code beginning E11 with icd_version 10 (E11.0 to E11.9).
SELECT DISTINCT hadm_id
FROM diagnoses_icd
WHERE icd_version = 10
  AND icd_code LIKE 'E11%'