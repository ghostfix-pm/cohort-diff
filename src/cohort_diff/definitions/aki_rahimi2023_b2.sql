-- name: aki_rahimi2023_b2
-- condition: aki
-- description: New AKI on ICU day 2 or 3 (KDIGO creatinine: rise >= 0.3 mg/dL within 48 h, or >= 1.5 x baseline), where day-1 AKI is identified against an MDRD back-calculated baseline (eGFR 75) and excluded, and days 2-3 use the minimum creatinine on ICU day 1 as the baseline; first ICU stay of adults with creatinine on each of days 1-3.
-- reference: Kamel Rahimi A, et al. Machine learning clinical prediction models for acute kidney injury: the impact of baseline creatinine on prediction efficacy. BMC Med Inform Decis Mak. 2023;23:207. doi:10.1186/s12911-023-02306-0. Methods (Study design, Exclusion criteria), Baseline sCr 2.
-- As written: the MDRD baseline is used "to identify and exclude patients with AKI on day 1 of
--   admission. ... We then used the minimum creatine value on day 1 of admission as the baseline".
-- MDRD as printed in the paper: sCr = (75 / (186 * age^-0.203 * 0.742 if female))^-0.887
--   (inverting MDRD gives -1/1.154 = -0.867; kept as printed, as in aki_rahimi2023_b3).
-- Assumed: day-1 AKI = a day-1 result >= 1.5 x the MDRD baseline, or >= 0.3 above an earlier
--   result within 48 h; any gender other than 'F' uses the formula without the 0.742 factor.
-- Assumed: days 2-3 AKI = a result >= 1.5 x the day-1 minimum, or the 48 h rule.
-- Assumed: ICU day 1 = [intime, intime + 24 h), day 2 = [+24 h, +48 h), day 3 = [+48 h, +72 h),
--   counted from intime only (results after ICU discharge still count).
-- Assumed: age at ICU admission = anchor_age + (year(intime) - anchor_year); adults = age >= 18;
--   the first ICU stay is chosen before the adult check; tied intimes go to the lower stay_id.
-- Assumed: creatinine = labevents itemid 50912 with a value, matched to the stay by subject_id;
--   no upper plausibility limit.
-- Assumed: creatinine values <= 0 are dropped (physically impossible; the paper doesn't say).
-- Assumed: the 48 h rule compares a result with the lowest strictly earlier result since ICU intime
--   (a gap of exactly 48 h counts); the 1.5 x rule compares a result with the baseline.
-- Assumed: comparisons are rounded to 6 decimals (the paper doesn't say).
-- Assumed: the maintenance RRT exclusion is not applied (codes are in the paper's
--   Supplementary Material 2, not yet checked).
WITH first_stay AS (
    SELECT subject_id, hadm_id, intime
    FROM (
        SELECT subject_id, hadm_id, intime,
               row_number() OVER (PARTITION BY subject_id ORDER BY intime, stay_id) AS stay_order
        FROM icustays
    )
    WHERE stay_order = 1
),
adult_stay AS (
    SELECT s.subject_id, s.hadm_id, s.intime, p.gender,
           p.anchor_age + (year(s.intime) - p.anchor_year) AS age
    FROM first_stay s
    JOIN patients p ON p.subject_id = s.subject_id
    WHERE p.anchor_age + (year(s.intime) - p.anchor_year) >= 18
),
cr AS (
    SELECT subject_id, charttime, valuenum
    FROM labevents
    WHERE itemid = 50912 AND valuenum > 0
),
icu_result AS (
    SELECT s.subject_id, s.hadm_id, s.age, s.gender, c.charttime, c.valuenum,
           CASE
               WHEN c.charttime < s.intime + INTERVAL 24 HOUR THEN 1
               WHEN c.charttime < s.intime + INTERVAL 48 HOUR THEN 2
               ELSE 3
           END AS icu_day
    FROM adult_stay s
    JOIN cr c
      ON c.subject_id = s.subject_id
     AND c.charttime >= s.intime
     AND c.charttime < s.intime + INTERVAL 72 HOUR
),
day_1_min AS (
    SELECT subject_id, min(valuenum) AS min_creat
    FROM icu_result
    WHERE icu_day = 1
    GROUP BY subject_id
),
flagged AS (
    SELECT r.subject_id, r.hadm_id, r.icu_day,
           round(r.valuenum - 1.5 * CASE
               WHEN r.icu_day = 1 THEN power(
                   75 / (186 * power(r.age, -0.203)
                         * CASE WHEN r.gender = 'F' THEN 0.742 ELSE 1.0 END),
                   -0.887
               )
               ELSE m.min_creat
           END, 6) >= 0
           OR round(r.valuenum - (
                  SELECT min(p.valuenum) FROM icu_result p
                  WHERE p.subject_id = r.subject_id
                    AND p.charttime < r.charttime
                    AND p.charttime >= r.charttime - INTERVAL 48 HOUR
              ), 6) >= 0.3 AS is_aki
    FROM icu_result r
    JOIN day_1_min m ON m.subject_id = r.subject_id
)
SELECT hadm_id
FROM flagged
GROUP BY subject_id, hadm_id
HAVING count(DISTINCT icu_day) = 3
   AND count(*) FILTER (WHERE is_aki AND icu_day = 1) = 0
   AND count(*) FILTER (WHERE is_aki AND icu_day > 1) > 0