# cohort-diff

**Keywords:** EHR · MIMIC-IV · cohort definitions · phenotyping · acute kidney injury · diabetes · 30-day readmission · reproducibility · odds ratio · Jaccard index · bootstrap confidence intervals

**Skills:** Python · SQL · DuckDB · pandas · NumPy · patient-level bootstrap · uv packaging · PyPI (Trusted Publishing) · GitHub Actions CI · pytest · Hypothesis (property-based testing) · test oracles · mypy (strict) · ruff · AI-assisted engineering (Claude Code with CLAUDE.md, tests first, AI log)

How different are "the same" EHR cohorts? `cohort-diff` runs several definitions of one condition side by side on MIMIC-IV-shaped data and reports how much the cohorts, and the results built on them, disagree.

## Description

A cohort definition is a modelling decision, but papers usually report it in a sentence. Two studies that both say "AKI patients in MIMIC-IV" may share only a fraction of their admissions: one counts discharge diagnosis codes, another a creatinine rise within 48 hours, another a rise over 7 days. A finding such as "AKI is associated with higher in-hospital mortality" can change size with the definition. `cohort-diff` stores each definition as a versioned SQL file with its source, runs them on DuckDB directly over MIMIC's `.csv.gz` files, and reports overlap, who is in each cohort, and how a typical downstream association moves.

## Objective

1. Build a tested, pip-installable library that runs cohort definitions as reviewable SQL and checks each one against an independent implementation.
2. Measure how much definitions of the same condition (AKI, diabetes, 30-day readmission) disagree, in membership and in a downstream result (the odds ratio between membership and in-hospital mortality), with confidence intervals.
3. *(Extension, branch `cohort-diff-llm`.)* Measure how often a large language model, given a paper's methods text, drafts a cohort definition that passes the same oracle tests as the hand-written one.

## Hypotheses

- **H1.** Definitions of the same condition select substantially different admissions (pairwise Jaccard well below 1).
- **H2.** Code-based and lab-based definitions differ systematically: codes under-capture, and lab rules with fixed thresholds over-capture when measurements are frequent and noisy.
- **H3.** The mortality odds ratio reported for "the same" condition changes materially with the definition: for some pairs, the 95% interval of the ratio of their odds ratios excludes 1.
- **H4.** A definition limits which questions its cohort can answer (for example, readmission exclusions that remove every death).
- **H5.** *(Extension.)* LLM-drafted definitions often run without error but fail the oracle tests at clinically important details (thresholds, time windows, specimen type, boundary conditions), so tests, not inspection, decide whether a draft can be used.

## Samples

| Dataset | Access | Size | Role |
| --- | --- | --- | --- |
| Synthetic, MIMIC-shaped (`cohort-diff synth`, seed 0) | Generated | 2,000 patients, 2,738 admissions | Known-structure validation; numbers say nothing about real patients |
| MIMIC-IV Clinical Database Demo v2.2 | Open (ODbL) | 100 patients, 275 admissions | End-to-end run on real EHR data |

The demo shares the full MIMIC-IV schema, so the same definitions run on full MIMIC-IV (credentialed) unchanged.

## Methods

- **Definitions as data.** Each definition is one SQL file in `src/cohort_diff/definitions/` with a header (`name`, `condition`, `description`, `reference`) and returns one column, `hadm_id`. Adding a definition does not touch Python.
- **Built-in definitions.**

| Name | Condition | Rule |
| --- | --- | --- |
| `aki_icd` | AKI | ICD-10 N17.* or ICD-9 584.* on the admission |
| `aki_kdigo_48h` | AKI | Creatinine rises ≥ 0.3 mg/dL within 48 h (KDIGO 2012, criterion 1) |
| `aki_kdigo_7d` | AKI | Creatinine ≥ 1.5 × the lowest value in the prior 7 days (KDIGO 2012, criterion 2) |
| `aki_kdigo_mimiccode` | AKI | **Published:** KDIGO creatinine stage ≥ 1 as implemented in MIT-LCP mimic-code, ICU-anchored (results from 7 days before ICU admission to ICU discharge; ≥ lowest in 48 h + 0.3 or ≥ 1.5 × lowest in 7 days; itemid 50912, values ≤ 150, same-time results averaged, no rounding) |
| `aki_rahimi2023_b3` | AKI | **Published:** Kamel Rahimi et al. 2023, Baseline sCr 3: new AKI on ICU day 2 or 3 (≥ 0.3 mg/dL within 48 h or ≥ 1.5 × baseline), baseline = mean creatinine 180 to 7 days before ICU admission, else MDRD back-calculation (eGFR 75, exponent −0.887 as printed); first ICU stay of adults with creatinine on days 1–3; day-1 AKI excluded. Written by Claude Code from a spec and failing tests, checked against an independent answer key |
| `dm_icd` | Diabetes | ICD-10 E10/E11/E13/E14 or ICD-9 250.* |
| `dm_hba1c` | Diabetes | Any HbA1c ≥ 6.5% during the admission |
| `dm_meds` | Diabetes | Any glucose-lowering medication |
| `readmit30_any` | Readmission | Any admission within 30 days of discharge |
| `readmit30_excl` | Readmission | As above, excluding deaths, hospice, discharge against advice and elective readmissions (inspired by CMS HRRP, simplified) |

- **Engine.** DuckDB, in process, reads the MIMIC tables in place (demo folder layout or flat CSVs) as views. Lab items are found by label and fluid, not by itemid.
- **Correctness.** Every rule-based definition is compared with an independent, deliberately slow pandas implementation (a test oracle written with loops rather than joins), on the synthetic data and on hundreds of random creatinine series generated by Hypothesis. Hand-picked regression tests pin threshold edge cases that both implementations could get wrong together.
- **Comparison.** For every pair of definitions: admissions in both, in only one, and the Jaccard index |A ∩ B| / |A ∪ B|. For each cohort: size, prevalence, mean age, % female, in-hospital mortality.
- **Downstream result.** Unadjusted odds ratio between membership and in-hospital mortality, with a Woolf 95% CI (log OR ± 1.96·√(1/a + 1/b + 1/c + 1/d)); 0.5 is added to every cell when any cell is 0 (Haldane–Anscombe).
- **Uncertainty.** Patient-level bootstrap (1,000 resamples; a patient drawn k times contributes all their admissions k times) gives 95% percentile intervals for each pair's Jaccard index and for the ratio of their mortality odds ratios (OR of a / OR of b). An interval for the ratio that excludes 1 means the two definitions disagree about the association, beyond sampling noise. A test checks that patients, not admissions, are resampled.
- **Scale check.** Wall time of `compare` for each condition, on the demo and (once credentialed) on full MIMIC-IV, on one laptop.
- **Extension: LLM-drafted definitions** *(planned, branch `cohort-diff-llm`)*. An LLM receives a paper's methods text and the table and column names only (never patient data) and returns a definition through JSON-schema structured output. Each draft is graded by the same oracle and property tests, and by exact agreement with the hand-written definition on synthetic data. Pass rates for 3+ models on a 20-item labeled set, with 95% intervals; every failure is categorized.
- **Engineering.** Strict typing, lint and tests on Python 3.11–3.13 in CI; the wheel is built in CI; releases go to PyPI by Trusted Publishing from version tags.

## Results

### Synthetic data (2,000 patients, 2,738 admissions, seed 0)

| Definition | n | Prevalence | Mortality among members | Mortality OR [95% CI] |
| --- | --- | --- | --- | --- |
| aki_icd | 400 | 14.6% | 16.8% | 3.06 [2.24, 4.19] |
| aki_kdigo_48h | 2,139 | 78.2% | 9.2% | 4.23 [2.44, 7.33] |
| aki_kdigo_7d | 2,033 | 74.3% | 8.4% | 1.48 [1.04, 2.10] |
| dm_icd | 438 | 16.0% | 15.8% | 2.84 [2.09, 3.87] |
| dm_hba1c | 374 | 13.7% | 10.4% | 1.48 [1.03, 2.14] |
| dm_meds | 355 | 13.0% | 16.1% | 2.77 [2.00, 3.84] |
| readmit30_any | 296 | 10.8% | 0.0% | not meaningful (no deaths by construction) |
| readmit30_excl | 242 | 8.8% | 0.0% | not meaningful (no deaths by construction) |

Pairwise overlap and disagreement in the mortality association (patient-level bootstrap, 1,000 resamples, 95% intervals):

| Pair | Jaccard [95% CI] | Ratio of mortality ORs [95% CI] |
| --- | --- | --- |
| aki_icd vs aki_kdigo_48h | 0.160 [0.145, 0.176] | 0.72 [0.33, 1.26] |
| aki_icd vs aki_kdigo_7d | 0.142 [0.127, 0.157] | **2.08 [1.29, 3.37]** |
| aki_kdigo_48h vs aki_kdigo_7d | 0.883 [0.869, 0.896] | **2.87 [1.87, 5.15]** |
| dm_hba1c vs dm_icd | 0.099 [0.078, 0.121] | **0.52 [0.31, 0.83]** |
| dm_hba1c vs dm_meds | 0.093 [0.072, 0.116] | **0.54 [0.32, 0.86]** |
| dm_icd vs dm_meds | 0.811 [0.776, 0.847] | 1.03 [0.88, 1.21] |
| readmit30_any vs readmit30_excl | 0.818 [0.771, 0.860] | not meaningful (no deaths in either cohort) |

Bold: the interval excludes 1, so the two definitions disagree about the mortality association beyond sampling noise.

- **Code vs lab definitions barely overlap** (Jaccard 0.09–0.16), while two lab rules (KDIGO 48 h vs 7 d) or two code-like rules (ICD vs medications) overlap 81–88%.
- **High overlap does not mean the same answer.** The two KDIGO definitions share 88% of admissions, yet their mortality ORs differ about threefold (ratio 2.87 [1.87, 5.15]).
- **Different-looking ORs can be compatible.** `aki_icd` (3.06) and `aki_kdigo_48h` (4.23) look different, but the interval for their ratio includes 1.
- **KDIGO-48h flags 78% of synthetic admissions**: the generator draws creatinine about every 12 h with noise (SD 0.3 mg/dL), and a 0.3 mg/dL rule fires on noise when labs are frequent. Whether real data shows the same is what the demo and full MIMIC-IV can answer.
- **Readmission cohorts contain no deaths by construction** (an admission followed by another one cannot end in death), so their mortality ORs come only from the 0.5 zero-cell correction. The definition limits which questions the cohort can answer.

### MIMIC-IV demo (real data: 100 patients, 275 admissions)

| Definition | n | Prevalence | Mortality among members | Mortality OR [95% CI] |
| --- | --- | --- | --- | --- |
| aki_icd | 70 | 25.5% | 15.7% | 9.37 [2.88, 30.51] |
| aki_kdigo_48h | 69 | 25.1% | 15.9% | 9.58 [2.94, 31.20] |
| aki_kdigo_7d | 53 | 19.3% | 20.8% | 14.27 [4.34, 46.97] |
| aki_kdigo_mimiccode | 44 | 16.0% | 25.0% | 18.92 [5.69, 62.88] |
| aki_rahimi2023_b3 | 15 | 5.5% | 6.7% | 1.26 [0.15, 10.24] (1 death) |
| dm_icd | 111 | 40.4% | 4.5% | 0.73 [0.24, 2.19] |
| dm_hba1c | 17 | 6.2% | 0.0% | 0.45 [0.03, 7.82] (no deaths; zero-cell correction) |
| dm_meds | 135 | 49.1% | 5.9% | 1.20 [0.42, 3.40] |
| readmit30_any | 53 | 19.3% | 0.0% | not meaningful (no deaths by construction) |
| readmit30_excl | 49 | 17.8% | 0.0% | not meaningful (no deaths by construction) |

| Pair | Jaccard [95% CI] | Ratio of mortality ORs [95% CI] |
| --- | --- | --- |
| aki_icd vs aki_kdigo_48h | 0.376 [0.263, 0.494] | 0.98 [0.25, 3.23] |
| aki_icd vs aki_kdigo_7d | 0.309 [0.189, 0.440] | 0.66 [0.17, 2.48] |
| aki_kdigo_48h vs aki_kdigo_7d | 0.564 [0.447, 0.679] | 0.67 [0.20, 2.35] |
| aki_icd vs aki_kdigo_mimiccode | 0.326 [0.221, 0.449] | 0.50 [0.13, 1.80] |
| aki_kdigo_48h vs aki_kdigo_mimiccode | 0.614 [0.475, 0.759] | **0.51 [0.36, 0.71]** |
| aki_kdigo_7d vs aki_kdigo_mimiccode | 0.492 [0.387, 0.611] | 0.75 [0.22, 2.59] |
| aki_icd vs aki_rahimi2023_b3 | 0.062 [0.014, 0.126] | 7.46 [1.32, 56.25] |
| aki_kdigo_48h vs aki_rahimi2023_b3 | 0.217 [0.118, 0.345] | 7.63 [1.36, 57.58] |
| aki_kdigo_mimiccode vs aki_rahimi2023_b3 | 0.255 [0.139, 0.395] | 15.07 [2.98, 100.38] |
| dm_hba1c vs dm_icd | 0.113 [0.071, 0.171] | 0.62 [0.17, 5.56] (zero-cell) |
| dm_hba1c vs dm_meds | 0.126 [0.079, 0.176] | 0.38 [0.09, 1.91] (zero-cell) |
| dm_icd vs dm_meds | 0.608 [0.461, 0.715] | 0.61 [0.15, 1.51] |
| readmit30_any vs readmit30_excl | 0.925 [0.852, 1.000] | not meaningful |

- **Real definitions also select different patients.** The AKI definitions have similar prevalence (19–25%) but share only 31–56% of their combined admissions. Diabetes by HbA1c ≥ 6.5% (6% of admissions) overlaps the code and medication definitions at Jaccard 0.11–0.13.
- **The medication phenotype captures the most** (49% of admissions vs 40% by codes), consistent with insulin given for stress hyperglycemia; every HbA1c-defined admission is also in the medication cohort.
- **KDIGO-48h flags 25% of demo admissions, not the 78% seen on synthetic data**, so the synthetic over-capture came from the generator's frequent, noisy creatinine, not from the rule itself.
- **Anchoring to the ICU changes the cohort and the answer.** The published mimic-code KDIGO definition flags 44 admissions (16%) against 69 (25%) for the same creatinine rule over the whole hospital stay; 43 of its 44 are in the hospital-wide cohort. Its members are sicker (mortality 25% vs 16%), and the ratio of mortality ORs, 0.51 [0.36, 0.71], is the one demo interval that excludes 1. The cohorts are nested, which keeps the paired interval narrow; with 100 patients this shows how much the anchoring choice matters, not a real-world effect size.
- **A prediction-study definition selects a different population.** Kamel Rahimi et al.'s Baseline 3 keeps only new AKI on ICU day 2 or 3 in first ICU stays with creatinine on days 1–3, and excludes AKI on day 1. On the demo it flags 15 admissions (5.5%), all inside the hospital-wide KDIGO cohort but overlapping the code-based cohort at Jaccard 0.06. Its members have 6.7% mortality (1 death) against 16–25% for the other AKI definitions, and every ratio of mortality ORs against it excludes 1. With one death the intervals are very wide (up to about 100), and the comparison group includes the sicker patients the definition excludes (see Limitations).
- **Otherwise, no disagreement in the mortality association can be shown at this size.** The other AKI ORs range from 9.4 to 14.3 and the diabetes ORs from 0.45 to 1.20, and their ratio intervals include 1, some 20-fold wide.

With 100 patients, cohorts are small and intervals wide; these numbers show the tool runs on real data, not how much definitions disagree in practice.

### Scale check

Full MIMIC-IV (about 546,000 admissions) will be timed once credentialed.

| Data | Condition | Admissions | Wall time (s) | Machine |
| --- | --- | --- | --- | --- |
| MIMIC-IV demo | aki / diabetes / readmission | 275 | 1.6 / 1.5 / 1.3 (includes 1,000 bootstrap resamples and Python start-up) | Intel i7-12800HX, 64 GB RAM, Windows |

### Extension: LLM-drafted definitions (planned)

Not started. Planned on branch `cohort-diff-llm` after v0.1.0: pass rates of LLM-drafted definitions on the oracle tests for 3+ models on a 20-item labeled set, with 95% intervals and every failure categorized.

### Correctness

34 tests pass with 99% line coverage on Python 3.11–3.13 (CI). Two deliberate breaks show what each kind of test catches:

| Deliberate break | Caught by | Not caught by |
| --- | --- | --- |
| Remove the rounding from the KDIGO 0.3 mg/dL comparison in both the SQL and the oracle | The hand-picked boundary test (0.9 → 1.2 and 1.1 → 1.4 missed) | Every SQL-vs-oracle test, because both shared the bug |
| KDIGO window 48 h → 24 h | SQL vs oracle on synthetic data, and the Hypothesis property test (shrunk to creatinine 1.0 then 2.0 mg/dL, 25 hours apart) | (nothing missed) |
| mimic-code KDIGO without the ICU-discharge bound | SQL vs oracle on synthetic data, the hand-made ICU-window test, and the Hypothesis property test (shrunk to an ICU stay from hour 0 to 6, creatinine 0.5 then 1.0 at hour 7) | (nothing missed) |
| Kamel Rahimi 2023 Baseline 3 with the “corrected” MDRD exponent (−0.867 instead of the printed −0.887) | The hand-made exponent test: creatinine 1.605 in a 60-year-old man is wrongly flagged as AKI | (nothing missed) |

## Discussion

On synthetic data, where the structure is known, definitions of the same condition overlap little when they use different sources (codes vs labs, Jaccard 0.09–0.16; H1), and four of six pairs disagree about the mortality association beyond sampling noise (ratio intervals excluding 1; H3). High overlap does not guarantee agreement: the two KDIGO rules share 88% of admissions but their ORs differ about threefold.

The open demo shows the same pattern in membership on real data: AKI definitions with almost identical prevalence share at most 56% of their admissions, and diabetes by HbA1c overlaps the other definitions at about 0.12 (H1). The medication phenotype captures the most admissions, as expected (H2). For AKI, H2 was not supported on the demo: the lab rule flagged the same share as the codes (25%), and the synthetic data's 78% came from the generator. Whether the mortality association itself changes with the definition (H3) can mostly not be tested with 100 patients: every ratio interval among the textbook definitions includes 1. The exception is a published one: the mimic-code KDIGO definition, anchored to ICU stays, gives a mortality OR about half that of the hospital-wide rule (ratio 0.51 [0.36, 0.71]). Readmission definitions exclude deaths by construction, so they cannot answer a mortality question at all (H4).

**Strengths.** Definitions are versioned, cited SQL rather than prose; each is checked against an independent implementation and by property tests; known-structure validation on synthetic data; installable with `pip`; reproducible by anyone from open data, a lock file and CI on Python 3.11–3.13.

## Limitations

- **No real-world estimate of disagreement.** The demo has 100 patients; its cohorts and intervals are too small to say how much definitions disagree in practice.
- **Synthetic structure is planted.** Overlaps on synthetic data reflect the generator's assumptions, not real coding or lab practice.
- **KDIGO is creatinine-only** (no urine output) with an in-admission baseline; many studies use pre-admission baselines.
- **Readmission definitions are simplified**; the CMS planned-readmission algorithm is far more detailed.
- **The downstream comparison is members vs all other admissions.** For definitions with their own eligibility rules (such as Kamel Rahimi et al.'s first-ICU-stay, day-1-AKI-excluded cohort), the non-members include patients the paper excluded, so the odds ratio is not the comparison the paper made. Restricting the comparison to each definition's eligible population is a planned extension.
- **The odds ratio is unadjusted.** It shows how a reported association can move with the definition, not a causal effect.

## Trial and error

What went wrong while building this, and what changed as a result. Analysis problems come first because they affect results; engineering problems follow because they affect reproducibility.

### Analysis and data

| Problem | Why it matters | How it was handled |
| --- | --- | --- |
| A creatinine rise of exactly 0.3 mg/dL can be missed: in floating point, 1.2 − 0.9 = 0.29999999999999993 | KDIGO's 0.3 mg/dL threshold is clinically exact; a naive `>= 0.3` silently drops true AKI cases | The SQL and the oracle round the difference to 6 decimals. Removing the rounding from *both* left every SQL-vs-oracle test green (shared bug); only the hand-picked boundary test failed, on 0.9 → 1.2 and 1.1 → 1.4 (0.7 → 1.0 happens to round correctly) |
| KDIGO-48h flagged 78% of synthetic admissions but 25% of demo admissions | A planted generator artifact (creatinine every 12 h with SD 0.3 mg/dL noise) looked like a property of the rule | Reported both; the synthetic over-capture is attributed to the generator, and synthetic overlaps are used only to validate the tool |
| `dm_hba1c` has no deaths on the demo (17 admissions) | Its odds ratio and every ratio involving it come only from the 0.5 zero-cell correction | Flagged as zero-cell in the Results tables and not interpreted |
| mimic-code compares `creat >= baseline + 0.3` without rounding, so a true 0.3 mg/dL rise from 1.1 to 1.4 is missed (1.1 + 0.3 = 1.4000000000000001), while 0.9 → 1.2 is caught | A faithful reproduction of a published definition must keep its choices, including ones you'd make differently | Implemented as the source states and pinned by a test that expects the miss; the built-in `aki_kdigo_48h` rounds and catches all three cases. The difference is documented in the SQL header |
| A wrong time window (24 h instead of KDIGO's 48 h) still produces a plausible-looking cohort | Window edges are where cohort SQL is most often wrong, and a smaller cohort doesn't look broken | Deliberately changing the window to 24 h failed two tests: SQL vs oracle on synthetic data (admissions missing from the SQL cohort), and the Hypothesis property test, which shrank the failure to the minimal case: creatinine 1.0 then 2.0 mg/dL, 25 hours apart |

### Engineering

| Part | What went wrong | Cause | Fix and lesson |
| --- | --- | --- | --- |
| Setup | The parent lab repository saw the whole Level 1 folder (both projects and the MIMIC-IV demo data) as untracked files | The parent's `.gitignore` had no rule for that folder, although earlier notes said it did | Added the folder to the parent's `.gitignore` before any commit; nothing had been committed. Lesson: verify ignore rules with `git check-ignore -v` and `git status`, not from notes |
| CLI | The Part 5 commit had 2 files instead of 3: the CI workflow still lacked the release job | One of three files to replace was skipped; the commit itself succeeded, so nothing looked wrong | Caught by `git show --stat HEAD` before pushing; replaced the workflow and folded it in with `git commit --amend`. Lesson: compare the commit's file list with the list you expected before `git push` |
| Release | Every CI job warned that Node.js 20 is deprecated | `actions/checkout@v4` and `astral-sh/setup-uv@v5` target Node.js 20, which GitHub is retiring | Warnings only (the TestPyPI rehearsal published). Bumped to `checkout@v5` and `setup-uv@v7` in the release commit, as in ehr-asof. Lesson: read CI annotations even when jobs are green |

## Conclusions

"The same" cohort is often not the same patients: on real MIMIC-IV demo data, AKI definitions agree on at most 56% of their combined admissions and diabetes definitions on as little as 11%. `cohort-diff` makes that difference measurable, with each definition as tested, cited SQL and paired, patient-level intervals for overlap and for the downstream association. Whether those differences change published associations on real data is the question for full MIMIC-IV, where the same code runs unchanged.

## Repository layout

| Path | What it does |
| --- | --- |
| `src/cohort_diff/definitions/` | One SQL file per cohort definition, with a metadata header |
| `src/cohort_diff/registry.py` | Finds and parses definitions (built-in or a path) |
| `src/cohort_diff/engine.py` | DuckDB views over MIMIC tables (folder or DataFrames) |
| `src/cohort_diff/compare.py` | Jaccard, overlap table, cohort description, mortality odds ratio, patient-level bootstrap, markdown report |
| `src/cohort_diff/synth.py` | MIMIC-shaped synthetic data |
| `src/cohort_diff/cli.py` | `list`, `run`, `synth`, `compare` |
| `tests/` | Unit, oracle and property-based (Hypothesis) tests |
| `CLAUDE.md` | Project rules for AI coding agents (commands, testing, data safety) |
| `docs/AI_LOG.md` | What was delegated to AI tools, what they got wrong, and how it was caught |

## Reproduce

```bash
uv sync
uv run cohort-diff synth --out data/synth --patients 2000 --seed 0
uv run cohort-diff list
uv run cohort-diff compare --condition aki --data data/synth --out reports/aki.md
uv run cohort-diff compare --condition aki --data path/to/mimic-iv-clinical-database-demo-2.2
```

Development: `uv run ruff format --check src tests`, `uv run ruff check src tests`, `uv run mypy src` (strict), `uv run pytest`, `uv build`.

## Citations

- Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2023). MIMIC-IV Clinical Database Demo (version 2.2). PhysioNet. RRID:SCR_007345. https://doi.org/10.13026/dp1f-ex47
- Johnson, A. E. W., Bulgarelli, L., Shen, L., et al. (2023). MIMIC-IV, a freely accessible electronic health record dataset. *Scientific Data*, 10, 1. https://doi.org/10.1038/s41597-022-01899-x
- Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026). PhysioNet as a global platform for biomedical research. *Nature Health*. https://doi.org/10.1038/s44360-026-00096-z
- Kidney Disease: Improving Global Outcomes (KDIGO) Acute Kidney Injury Work Group (2012). KDIGO Clinical Practice Guideline for Acute Kidney Injury. *Kidney International Supplements*, 2(1), 1–138.

## License

Code: MIT. The MIMIC-IV demo data is distributed by PhysioNet under the Open Data Commons Open Database License v1.0 and is not included in this repository.
