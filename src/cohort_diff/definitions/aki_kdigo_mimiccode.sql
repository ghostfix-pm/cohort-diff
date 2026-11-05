-- name: aki_kdigo_mimiccode
-- condition: aki
-- description: KDIGO stage >= 1 by creatinine during an ICU stay, as in MIT-LCP mimic-code: creatinine >= lowest value in the prior 48 h + 0.3 mg/dL, or >= 1.5 x lowest value in the prior 7 days, using results from 7 days before ICU admission to ICU discharge.
-- reference: MIT-LCP mimic-code, mimic-iv/concepts/organfailure/kdigo_creatinine.sql and kdigo_stages.sql (https://github.com/MIT-LCP/mimic-code); Johnson AEW et al., JAMIA 2018;25(1):32-39, doi:10.1093/jamia/ocx084.
-- Implemented as the source states, including choices that differ from aki_kdigo_48h:
--   creatinine is itemid 50912, values above 150 are dropped, and results at the same
--   time are averaged per ICU stay; labs are matched to the stay by subject_id, so
--   pre-ICU results may come from another admission; baselines use strictly earlier
--   results from the same stay window; comparisons are not rounded (so 1.1 -> 1.4 is
--   missed: in floating point 1.1 + 0.3 = 1.4000000000000001).
-- Not used: urine output and renal replacement therapy (also part of mimic-code's KDIGO).
-- Assumed: an admission is in the cohort if any of its ICU stays meets the rule.
WITH cr AS (
    SELECT ie.hadm_id, ie.stay_id, le.charttime, avg(le.valuenum) AS creat
    FROM icustays ie
    JOIN labevents le
      ON le.subject_id = ie.subject_id
     AND le.itemid = 50912
     AND le.valuenum IS NOT NULL
     AND le.valuenum <= 150
     AND le.charttime >= ie.intime - INTERVAL 7 DAY
     AND le.charttime <= ie.outtime
    GROUP BY ie.hadm_id, ie.stay_id, le.charttime
)
SELECT DISTINCT cr.hadm_id
FROM cr
WHERE cr.creat >= (
        SELECT min(p.creat) FROM cr AS p
        WHERE p.stay_id = cr.stay_id
          AND p.charttime < cr.charttime
          AND p.charttime >= cr.charttime - INTERVAL 48 HOUR
    ) + 0.3
   OR cr.creat >= 1.5 * (
        SELECT min(p.creat) FROM cr AS p
        WHERE p.stay_id = cr.stay_id
          AND p.charttime < cr.charttime
          AND p.charttime >= cr.charttime - INTERVAL 7 DAY
    )