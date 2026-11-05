-- name: aki_rahimi2023_b3
-- condition: aki
-- description: New AKI on ICU day 2 or 3 (KDIGO creatinine: rise >= 0.3 mg/dL within 48 h, or >= 1.5 x baseline), baseline = mean creatinine 180 to 7 days before ICU admission, else MDRD back-calculation (eGFR 75); first ICU stay of adults with creatinine on each of days 1-3; admissions with AKI on day 1 excluded.
-- reference: Kamel Rahimi A, et al. Machine learning clinical prediction models for acute kidney injury: the impact of baseline creatinine on prediction efficacy. BMC Med Inform Decis Mak. 2023;23:207. doi:10.1186/s12911-023-02306-0. Methods (Study design, Exclusion criteria), Baseline sCr 3.
-- MDRD as printed in the paper: sCr = (75 / (186 * age^-0.203 * 0.742 if female))^-0.887.
--   Inverting MDRD gives an exponent of -1/1.154 = -0.867; -0.887 looks like a typo, but is kept.
-- Assumed: ICU day 1 = [intime, intime + 24 h), day 2 = [+24 h, +48 h), day 3 = [+48 h, +72 h).
-- Assumed: age at ICU admission = anchor_age + (year(intime) - anchor_year); adults = age >= 18.
-- Assumed: creatinine = labevents itemid 50912 with a value, matched to the stay by subject_id.
-- Assumed: the 48 h rule compares a result with the lowest strictly earlier result since ICU intime;
--   the 1.5 x rule compares any result on days 1-3 with the baseline (no 7-day limit).
-- Assumed: comparisons are rounded to 6 decimals (the paper doesn't say).
-- Assumed: the maintenance RRT exclusion is not applied (codes are in the paper's
--   Supplementary Material 2, not yet checked).
-- Assumed: ICU days are counted from intime only, so results after ICU discharge (outtime)
--   still count towards days 1-3.
-- Assumed: the first ICU stay is chosen before the adult check, so a patient under 18 at their
--   first stay is excluded even if a later stay is at 18 or over; tied intimes go to the lower stay_id.
-- Assumed: window edges are inclusive: the baseline window includes exactly 180 and exactly 7 days
--   before intime, and a gap of exactly 48 h counts for the 48 h rule.
-- Assumed: creatinine values have no upper plausibility limit.
-- Assumed: creatinine values <= 0 are dropped (physically impossible; the paper doesn't say).
-- Assumed: any gender other than 'F' uses the MDRD formula without the 0.742 factor.
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
pre_icu AS (
    SELECT s.subject_id, avg(c.valuenum) AS mean_creat
    FROM adult_stay s
    JOIN cr c
      ON c.subject_id = s.subject_id
     AND c.charttime >= s.intime - INTERVAL 180 DAY
     AND c.charttime <= s.intime - INTERVAL 7 DAY
    GROUP BY s.subject_id
),
baseline AS (
    SELECT s.subject_id, s.hadm_id, s.intime,
           coalesce(
               b.mean_creat,
               power(
                   75 / (186 * power(s.age, -0.203)
                         * CASE WHEN s.gender = 'F' THEN 0.742 ELSE 1.0 END),
                   -0.887
               )
           ) AS baseline_creat
    FROM adult_stay s
    LEFT JOIN pre_icu b ON b.subject_id = s.subject_id
),
icu_result AS (
    SELECT b.subject_id, b.hadm_id, b.baseline_creat, c.charttime, c.valuenum,
           CASE
               WHEN c.charttime < b.intime + INTERVAL 24 HOUR THEN 1
               WHEN c.charttime < b.intime + INTERVAL 48 HOUR THEN 2
               ELSE 3
           END AS icu_day
    FROM baseline b
    JOIN cr c
      ON c.subject_id = b.subject_id
     AND c.charttime >= b.intime
     AND c.charttime < b.intime + INTERVAL 72 HOUR
),
flagged AS (
    SELECT r.subject_id, r.hadm_id, r.icu_day,
           round(r.valuenum - 1.5 * r.baseline_creat, 6) >= 0
           OR round(r.valuenum - (
                  SELECT min(p.valuenum) FROM icu_result p
                  WHERE p.subject_id = r.subject_id
                    AND p.charttime < r.charttime
                    AND p.charttime >= r.charttime - INTERVAL 48 HOUR
              ), 6) >= 0.3 AS is_aki
    FROM icu_result r
)
SELECT hadm_id
FROM flagged
GROUP BY subject_id, hadm_id
HAVING count(DISTINCT icu_day) = 3
   AND count(*) FILTER (WHERE is_aki AND icu_day = 1) = 0
   AND count(*) FILTER (WHERE is_aki AND icu_day > 1) > 0