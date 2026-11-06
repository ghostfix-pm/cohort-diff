-- name: dm_charlson_mimiccode
-- condition: diabetes
-- description: Charlson comorbidity "diabetes" (without or with chronic complications) on the admission, as in MIT-LCP mimic-code: ICD-9 250.0-250.9 or ICD-10 E10-E14 (first four characters).
-- reference: MIT-LCP mimic-code, mimic-iv/concepts/comorbidity/charlson.sql (https://github.com/MIT-LCP/mimic-code, read 2026-11-05), flags diabetes_without_cc and diabetes_with_cc, citing Quan H, et al. Coding algorithms for defining comorbidities in ICD-9-CM and ICD-10 administrative data. Med Care. 2005;43(11):1130-9.
-- As in the source: codes are compared on their first four characters, ICD-9 and ICD-10 are
--   separated by icd_version, and flags are computed per admission (hadm_id).
--   diabetes_without_cc: ICD-9 2500 2501 2502 2503 2508 2509;
--     ICD-10 E100 E101 E106 E108 E109 E110 E111 E116 E118 E119 E120 E121 E126 E128 E129
--     E130 E131 E136 E138 E139 E140 E141 E146 E148 E149.
--   diabetes_with_cc: ICD-9 2504 2505 2506 2507;
--     ICD-10 E102 E103 E104 E105 E107 E112 E113 E114 E115 E117 E122 E123 E124 E125 E127
--     E132 E133 E134 E135 E137 E142 E143 E144 E145 E147.
-- Assumed: the cohort is admissions with either flag (type 1 and type 2 both count).
-- Not included, as in the source: secondary diabetes (ICD-9 249, ICD-10 E08, E09),
--   diabetes in pregnancy (ICD-9 648.0, ICD-10 O24) and prediabetes (ICD-10 R73.0x).
SELECT DISTINCT hadm_id
FROM diagnoses_icd
WHERE (icd_version = 9 AND substr(icd_code, 1, 4) IN (
          '2500', '2501', '2502', '2503', '2504',
          '2505', '2506', '2507', '2508', '2509'))
   OR (icd_version = 10 AND substr(icd_code, 1, 4) IN (
          'E100', 'E101', 'E102', 'E103', 'E104', 'E105', 'E106', 'E107', 'E108', 'E109',
          'E110', 'E111', 'E112', 'E113', 'E114', 'E115', 'E116', 'E117', 'E118', 'E119',
          'E120', 'E121', 'E122', 'E123', 'E124', 'E125', 'E126', 'E127', 'E128', 'E129',
          'E130', 'E131', 'E132', 'E133', 'E134', 'E135', 'E136', 'E137', 'E138', 'E139',
          'E140', 'E141', 'E142', 'E143', 'E144', 'E145', 'E146', 'E147', 'E148', 'E149'))