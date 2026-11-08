-- name: readmit_shen2025
-- condition: readmission
-- description: 90-day readmission after excluding index admissions that ended in death, lasted less than 2 days, or were followed by a readmission less than 1 day after discharge.
-- reference: Shen X, Yang J, Zhang X. Influencing factors of 90-day readmission of patients with heart failure based on the MIMIC-IV database. J Thorac Dis. 2025;17(3):1207-1216. doi:10.21037/jtd-24-1738. Methods, Inclusion and exclusion criteria; Definitions.
-- Only the paper's readmission rule is implemented. Its heart-failure inclusion (and the
--   exclusion of "patients with multiple records of HF", which depends on it) is not part of
--   this definition.
-- As written: exclude "patients who died in hospital", "patients whose readmission time was less
--   than 1 day" and "patients whose hospitalization time was less than 2 days"; "90-day
--   readmission: the patient was readmitted to the hospital within 90 days after discharge".
-- As written, and NOT implemented because it is about the comparison group, not the cases: the
--   paper also excludes "patients who lacked readmission time", and its control group "was
--   readmitted for more than 90 days", so patients never readmitted are in neither group.
-- Assumed: rules apply per admission; in-hospital death = hospital_expire_flag = 1;
--   hospitalization time = dischtime - admittime, kept if >= 2 days; the readmission is the NEXT
--   admission by admittime, and the gap is its admittime - index dischtime; a gap under 1 day
--   (including an overlapping next admission) excludes the index admission even if a later
--   admission falls within 90 days; case if 1 day <= gap <= 90 days.
WITH ordered AS (
    SELECT hadm_id, admittime, dischtime, hospital_expire_flag,
           lead(admittime) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admit
    FROM admissions
)
SELECT hadm_id
FROM ordered
WHERE hospital_expire_flag = 0
  AND dischtime >= admittime + INTERVAL 2 DAY
  AND next_admit >= dischtime + INTERVAL 1 DAY
  AND next_admit <= dischtime + INTERVAL 90 DAY