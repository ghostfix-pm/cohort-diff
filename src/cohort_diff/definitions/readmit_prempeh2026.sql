-- name: readmit_prempeh2026
-- condition: readmission
-- description: All-cause 90-day hospital readmission: "any subsequent admission occurring within 90 days of the index hospital discharge", found by comparing later admission times of the same patient with the index discharge time.
-- reference: Prempeh AGA, Tenfelde A. Opioid Escalation in the ICU and 90-Day Readmission After Major Surgery: A Retrospective Cohort Study Using the MIMIC-IV Database. J Intensive Care Med. 2026;41(10):1008-1012. doi:10.1177/08850666261425613. Methods, Main Outcome and Measures.
-- Only the paper's readmission rule is implemented. Its study cohort (adults with a
--   postoperative ICU admission after major orthopedic, general or neurosurgical procedures)
--   is not part of this definition.
-- As written: no exclusions for death on the index admission or on the readmission.
-- Assumed: "subsequent" = admittime strictly after the index dischtime (an overlapping admission
--   is not a readmission); "within 90 days" = admittime - index dischtime <= 90 days (inclusive);
--   any later admission counts, not only the next one.
SELECT DISTINCT i.hadm_id
FROM admissions i JOIN admissions r ON r.subject_id = i.subject_id
WHERE r.admittime > i.dischtime
  AND r.admittime <= i.dischtime + INTERVAL 90 DAY