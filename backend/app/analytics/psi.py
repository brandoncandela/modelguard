"""Population Stability Index.

    PSI = sum over bins of (a_i - e_i) * ln(a_i / e_i)

e_i is the share of the reference (expected) population in bin i and a_i the share of the current
(actual) population. Numeric variables use bins cut at the reference deciles, so each reference bin
holds about 10% of records; outer bins are open-ended so no current value falls outside. Categorical
variables use one bin per category seen in either population. Empty bins are floored at 0.0001 so the
logarithm is defined (a standard convention; it caps the contribution of a bin that empties out).

Interpretation used by the bank (industry convention, not a regulatory standard):
    < 0.10 stable, 0.10 - 0.25 moderate shift, >= 0.25 significant shift.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

EPS = 1e-4


def _contrib(e: np.ndarray, a: np.ndarray) -> np.ndarray:
    e = np.maximum(e, EPS)
    a = np.maximum(a, EPS)
    return (a - e) * np.log(a / e)


def quantile_edges(reference, bins: int = 10) -> np.ndarray:
    ref = np.asarray(reference, dtype=float)
    ref = ref[~np.isnan(ref)]
    if ref.size == 0:
        raise ValueError("reference sample is empty")
    qs = np.quantile(ref, np.linspace(0, 1, bins + 1)[1:-1])
    inner = np.unique(qs)
    return np.concatenate(([-np.inf], inner, [np.inf]))


def psi_numeric(reference, current, bins: int = 10) -> Tuple[float, List[Dict[str, float]]]:
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref = ref[~np.isnan(ref)]
    cur = cur[~np.isnan(cur)]
    if ref.size == 0 or cur.size == 0:
        raise ValueError("PSI needs non-empty reference and current samples")
    edges = quantile_edges(ref, bins)
    # right-closed bins: (edge_i, edge_i+1]; the first bin includes -inf
    e_counts = np.histogram(ref, bins=edges)[0]
    a_counts = np.histogram(cur, bins=edges)[0]
    e = e_counts / e_counts.sum()
    a = a_counts / a_counts.sum()
    c = _contrib(e, a)
    table = []
    for i in range(len(e)):
        table.append({"bin": i + 1, "lower": None if np.isinf(edges[i]) else float(edges[i]),
                      "upper": None if np.isinf(edges[i + 1]) else float(edges[i + 1]),
                      "expected_share": float(e[i]), "actual_share": float(a[i]),
                      "expected_count": int(e_counts[i]), "actual_count": int(a_counts[i]),
                      "contribution": float(c[i])})
    return float(c.sum()), table


def psi_categorical(reference, current) -> Tuple[float, List[Dict[str, float]]]:
    ref = pd.Series(reference, dtype=object).fillna("Missing").astype(str)
    cur = pd.Series(current, dtype=object).fillna("Missing").astype(str)
    if len(ref) == 0 or len(cur) == 0:
        raise ValueError("PSI needs non-empty reference and current samples")
    cats = sorted(set(ref.unique()) | set(cur.unique()))
    e_counts = ref.value_counts().reindex(cats, fill_value=0).values
    a_counts = cur.value_counts().reindex(cats, fill_value=0).values
    e = e_counts / e_counts.sum()
    a = a_counts / a_counts.sum()
    c = _contrib(e, a)
    table = [{"bin": cat, "expected_share": float(e[i]), "actual_share": float(a[i]),
              "expected_count": int(e_counts[i]), "actual_count": int(a_counts[i]), "contribution": float(c[i])}
             for i, cat in enumerate(cats)]
    return float(c.sum()), table


def psi_band(value: float) -> str:
    if value < 0.10:
        return "Stable"
    if value < 0.25:
        return "Moderate shift"
    return "Significant shift"
