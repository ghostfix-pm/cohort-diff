"""Compare cohorts: overlap, who is in them, and how a downstream result moves.

The downstream result is deliberately simple and common in papers: the odds
ratio between cohort membership and in-hospital mortality. If that number
changes a lot between definitions of "the same" condition, so would the
conclusions of any study built on it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OddsRatio:
    estimate: float
    low: float
    high: float


def jaccard(a: set[int], b: set[int]) -> float:
    """Size of the intersection over size of the union; 1.0 when both are empty."""
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def overlap_table(cohorts: dict[str, set[int]]) -> pd.DataFrame:
    """One row per pair of definitions."""
    rows = []
    for (na, a), (nb, b) in combinations(cohorts.items(), 2):
        rows.append(
            {
                "a": na,
                "b": nb,
                "n_a": len(a),
                "n_b": len(b),
                "both": len(a & b),
                "only_a": len(a - b),
                "only_b": len(b - a),
                "jaccard": round(jaccard(a, b), 3),
            }
        )
    return pd.DataFrame(rows)


def odds_ratio(exposed: np.ndarray, outcome: np.ndarray) -> OddsRatio:
    """Woolf (log) 95% interval, with a 0.5 continuity correction if any cell is 0."""
    e, y = exposed.astype(bool), outcome.astype(bool)
    cells = np.array([(e & y).sum(), (e & ~y).sum(), (~e & y).sum(), (~e & ~y).sum()], dtype=float)
    if (cells == 0).any():
        cells = cells + 0.5
    a, b, c, d = cells
    log_or = math.log((a * d) / (b * c))
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return OddsRatio(math.exp(log_or), math.exp(log_or - 1.96 * se), math.exp(log_or + 1.96 * se))


def _weighted_or(weights: np.ndarray, exposed: np.ndarray, outcome: np.ndarray) -> float:
    """Odds ratio from a 2x2 table of summed weights (Haldane 0.5 if any cell is 0)."""
    cells = np.array(
        [
            weights @ (exposed & outcome),
            weights @ (exposed & ~outcome),
            weights @ (~exposed & outcome),
            weights @ (~exposed & ~outcome),
        ],
        dtype=float,
    )
    if (cells == 0).any():
        cells = cells + 0.5
    a, b, c, d = cells
    return float((a * d) / (b * c))


def bootstrap_pairs(
    cohorts: dict[str, set[int]],
    admissions: pd.DataFrame,
    n_boot: int = 1000,
    seed: int = 0,
) -> pd.DataFrame:
    """95% percentile intervals, per pair of definitions, for the Jaccard index and
    for the ratio of their mortality odds ratios (OR of a / OR of b).

    Patients are resampled, not admissions: one patient's admissions are not
    independent. A patient drawn k times contributes each of their admissions k times.
    A ratio of ORs whose interval excludes 1 means the two definitions give
    different answers to "is this condition associated with mortality, and how much".
    """
    patients, patient_idx = np.unique(admissions["subject_id"].to_numpy(), return_inverse=True)
    n_patients = len(patients)
    died = admissions["hospital_expire_flag"].to_numpy().astype(bool)
    member = {n: admissions["hadm_id"].isin(ids).to_numpy() for n, ids in cohorts.items()}
    pairs = list(combinations(member, 2))
    jac = np.empty((len(pairs), n_boot))
    ratio = np.empty((len(pairs), n_boot))
    rng = np.random.default_rng(seed)
    for r in range(n_boot):
        drawn = np.bincount(rng.integers(0, n_patients, n_patients), minlength=n_patients)
        weights = drawn[patient_idx].astype(float)
        for k, (na, nb) in enumerate(pairs):
            a, b = member[na], member[nb]
            union = weights @ (a | b)
            jac[k, r] = (weights @ (a & b)) / union if union > 0 else 1.0
            ratio[k, r] = _weighted_or(weights, a, died) / _weighted_or(weights, b, died)
    rows = []
    for k, (na, nb) in enumerate(pairs):
        a, b = member[na], member[nb]
        point = odds_ratio(a, died).estimate / odds_ratio(b, died).estimate
        j_low, j_high = np.percentile(jac[k], [2.5, 97.5])
        r_low, r_high = np.percentile(ratio[k], [2.5, 97.5])
        rows.append(
            {
                "a": na,
                "b": nb,
                "jaccard": round(jaccard(cohorts[na], cohorts[nb]), 3),
                "jaccard_low": round(float(j_low), 3),
                "jaccard_high": round(float(j_high), 3),
                "or_ratio": round(point, 2),
                "or_ratio_low": round(float(r_low), 2),
                "or_ratio_high": round(float(r_high), 2),
            }
        )
    return pd.DataFrame(rows)


def describe(cohorts: dict[str, set[int]], admissions: pd.DataFrame) -> pd.DataFrame:
    """Size, prevalence, demographics and the mortality odds ratio per definition."""
    rows = []
    n_total = len(admissions)
    for name, ids in cohorts.items():
        member = admissions["hadm_id"].isin(ids).to_numpy()
        sub = admissions[member]
        ratio = odds_ratio(member, admissions["hospital_expire_flag"].to_numpy())
        rows.append(
            {
                "definition": name,
                "n": int(member.sum()),
                "prevalence": round(member.mean(), 4) if n_total else float("nan"),
                "age_mean": round(float(sub["age"].mean()), 1) if len(sub) else float("nan"),
                "female_pct": round(float((sub["gender"] == "F").mean() * 100), 1)
                if len(sub)
                else float("nan"),
                "mortality_pct": round(float(sub["hospital_expire_flag"].mean() * 100), 1)
                if len(sub)
                else float("nan"),
                "mortality_or": round(ratio.estimate, 2),
                "or_low": round(ratio.low, 2),
                "or_high": round(ratio.high, 2),
            }
        )
    return pd.DataFrame(rows)


def to_markdown(
    overlap: pd.DataFrame,
    description: pd.DataFrame,
    title: str,
    uncertainty: pd.DataFrame | None = None,
) -> str:
    def table(frame: pd.DataFrame) -> str:
        header = "| " + " | ".join(frame.columns) + " |"
        sep = "| " + " | ".join("---" for _ in frame.columns) + " |"
        body = [
            "| " + " | ".join(str(v) for v in row) + " |" for row in frame.itertuples(index=False)
        ]
        return "\n".join([header, sep, *body])

    text = (
        f"# {title}\n\n## Cohorts\n\n{table(description)}\n\n"
        f"## Pairwise overlap\n\n{table(overlap)}\n\n"
        "Odds ratios: in-hospital mortality for members vs non-members, Woolf 95% CI.\n"
    )
    if uncertainty is not None:
        text += (
            f"\n## Uncertainty (patient-level bootstrap)\n\n{table(uncertainty)}\n\n"
            "95% percentile intervals. or_ratio = mortality OR of a / OR of b; "
            "an interval excluding 1 means the definitions disagree on the association.\n"
        )
    return text
