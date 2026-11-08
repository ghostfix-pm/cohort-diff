-- name: readmit_gupta2022
-- condition: readmission
-- description: 30-day readmission as labelled by the MIMIC-IV Data Pipeline (Gupta et al. 2022): index admissions of adults, ending alive, followed by another surviving adult admission of the same patient that starts after the index discharge and within 30 days of it.
-- reference: Gupta M, Gallamoza B, Cutrona N, Dhakal P, Poulain R, Beheshti R. An Extensive Data Processing Pipeline for MIMIC-IV. Proc Mach Learn Res. 2022;193:311-325. Logic from the code: github.com/healthylaife/MIMIC-IV-Data-Pipeline, preprocessing/day_intervals_preproc/day_intervals_cohort_v3.py (get_visit_pts, partition_by_readmit), commit afcd8a3, read 2026-11-06.
-- As written (paper): readmission "after user-defined (between 10 to 150) days from the previous
--   admission discharge time"; the pipeline's default and the paper's example task use 30 days.
-- As written (code, non-ICU hospital admissions):
--   1. Admissions with hospital_expire_flag = 1 are removed BEFORE readmissions are looked for,
--      so an admission ending in death is neither an index nor a readmission.
--   2. Only adults: patients.anchor_age >= 18 (applies to every admission of the patient).
--   3. An index admission is a case if ANY remaining admission of the same patient has
--      admittime > index dischtime and admittime - index dischtime <= 30 days.
--      Any later admission counts, not only the next one by admission time; an admission that
--      starts before the index discharge (overlapping) never counts.
-- Assumed: the pipeline also drops patients with no anchor_year_group; MIMIC-IV has none, so
--   this is not implemented.
WITH visits AS (
    SELECT a.subject_id, a.hadm_id, a.admittime, a.dischtime
    FROM admissions a JOIN patients p USING (subject_id)
    WHERE a.hospital_expire_flag = 0 AND p.anchor_age >= 18
)
SELECT DISTINCT i.hadm_id
FROM visits i JOIN visits r ON r.subject_id = i.subject_id
WHERE r.admittime > i.dischtime
  AND r.admittime <= i.dischtime + INTERVAL 30 DAY