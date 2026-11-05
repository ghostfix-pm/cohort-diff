# AI log

What was delegated to an AI tool, what it got wrong, and how tests or review caught it.
One row per task. Keep failures: they are the point of the log.

| Date | Part | Task delegated | Tool | What it got wrong | Caught by | Kept / changed |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 1 | Assisted setup (repo, packaging, CI) | Claude | | four checks + CI | |
| 2026-11-05 | 6.2b | Implement aki_rahimi2023_b3 SQL and oracle from the spec and failing tests (prompt: docs/prompt/) | Claude Code | Nothing wrong in the code; it flagged 5 choices the header didn't state and a missing newline in my test file | Its own report; independent answer key gives identical cohorts on 4 synthetic datasets (273 on the reference run); exponent Break it | Kept; added its 5 choices as Assumed: lines; prompt committed with the result, not before |
| 2026-11-05 | 6.2c | Implement aki_rahimi2023_b1 and _b2 SQL and oracles from specs and failing tests (prompt: docs/prompt/aki_rahimi2023_b1_b2.txt) | Claude Code | Nothing wrong in the code; it found a contradiction in my b1 header (day-1 "rise" vs no time order) and an unhandled zero creatinine, and proposed two tests | Its own report; answer key gives identical cohorts (444 / 270 / 273); MDRD Break it | Kept its reading of day 1 (now an Assumed: line + test); added a <= 0 filter to all three baselines (spec, then code) and its two tests |