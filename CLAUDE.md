# cohort-diff: rules for AI coding agents

## Project
A Python library and CLI that runs EHR cohort definitions (SQL on DuckDB) side by side and diffs them.
Layout: src/cohort_diff/ (package), src/cohort_diff/definitions/*.sql (one definition per file), tests/.

## Commands (all must pass before any commit)
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv run pytest
uv build

## Rules
- Write or update a failing test before changing behaviour; show it failing first.
- Every new definition: a .sql file with name / condition / description / reference header,
  a hand-made in/out test, and an oracle in tests/oracles.py if it is rule-based.
- Keep thresholds and windows exactly as the cited source states. Write anything the source
  leaves open as "Assumed: ..." in the SQL header.
- mypy strict: annotate everything; no "# type: ignore" without a reason on the same line.
- Don't add dependencies without asking.
- Development is on Windows PowerShell 5.1: one command per line, no "&&".

## Data safety
- Never open, print or paste MIMIC files or row-level output (demo or full) into a prompt,
  a test fixture, a commit or a log. Use synthetic data (cohort-diff synth) for examples and tests.
- Only aggregate results (counts, rates, intervals) go in README, reports or docs.
- data/, reports/ and dist/ stay ignored.