"""Input drift tests: PSI plus a hypothesis test with an effect-size floor.

With thousands of records a hypothesis test flags trivially small shifts, so drift is only flagged
when the test is significant AND the effect is material:
    numeric      two-sample Kolmogorov-Smirnov test; effect size = KS statistic D
    categorical  chi-square test of homogeneity on the reference/current contingency table;
                 effect size = Cramer's V
Levels:
    Significant  PSI >= 0.25, or p < 0.01 with effect >= 0.20
    Moderate     PSI >= 0.10, or p < 0.01 with effect >= 0.10
    Stable       otherwise
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from app.analytics.psi import psi_categorical, psi_numeric

ALPHA = 0.01


@dataclass
class DriftResult:
    feature: str
    feature_type: str
    psi: float
    test_name: str
    statistic: float
    p_value: float
    effect_size: float
    level: str
    flag: bool
    table: List[Dict] = field(default_factory=list)


def _level(psi: float, p: float, effect: float) -> str:
    if psi >= 0.25 or (p < ALPHA and effect >= 0.20):
        return "Significant"
    if psi >= 0.10 or (p < ALPHA and effect >= 0.10):
        return "Moderate"
    return "Stable"


def numeric_drift(name: str, reference, current) -> DriftResult:
    ref = pd.to_numeric(pd.Series(reference), errors="coerce").dropna().values
    cur = pd.to_numeric(pd.Series(current), errors="coerce").dropna().values
    psi, table = psi_numeric(ref, cur)
    ks = stats.ks_2samp(ref, cur, alternative="two-sided", method="asymp")
    level = _level(psi, float(ks.pvalue), float(ks.statistic))
    return DriftResult(name, "numeric", psi, "Kolmogorov-Smirnov", float(ks.statistic), float(ks.pvalue),
                       float(ks.statistic), level, level != "Stable", table)


def cramers_v(chi2: float, n: int, r: int, k: int) -> float:
    denom = n * (min(r, k) - 1)
    return float(np.sqrt(chi2 / denom)) if denom > 0 else 0.0


def categorical_drift(name: str, reference, current) -> DriftResult:
    ref = pd.Series(reference, dtype=object).fillna("Missing").astype(str)
    cur = pd.Series(current, dtype=object).fillna("Missing").astype(str)
    psi, table = psi_categorical(ref, cur)
    cats = sorted(set(ref) | set(cur))
    obs = np.array([ref.value_counts().reindex(cats, fill_value=0).values,
                    cur.value_counts().reindex(cats, fill_value=0).values])
    obs = obs[:, obs.sum(axis=0) > 0]
    if obs.shape[1] < 2:
        chi2, p = 0.0, 1.0
    else:
        chi2, p, _, _ = stats.chi2_contingency(obs, correction=False)
    v = cramers_v(float(chi2), int(obs.sum()), obs.shape[0], obs.shape[1])
    level = _level(psi, float(p), v)
    return DriftResult(name, "categorical", psi, "Chi-square", float(chi2), float(p), v, level, level != "Stable",
                       table)
