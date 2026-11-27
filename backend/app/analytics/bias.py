"""Outcome disparity testing for models that act on people.

For each group the test reports:
  adverse rate        share of the group receiving the adverse outcome (e.g. referred to EDD, rated High)
  favourable rate     1 - adverse rate
  impact ratio        group favourable rate / highest group favourable rate
  false positive rate adverse outcomes among people whose ground truth is negative
  FPR ratio           lowest group FPR / group FPR (1.0 means no excess false positives)

A group is flagged when a ratio is below 0.80 (the "four-fifths" screening heuristic) AND the difference
from the comparison group is statistically significant (two-proportion z-test, p < 0.05). Requiring both
keeps small-sample noise from raising flags. The heuristic is a screening convention borrowed from US
employment practice, not a legal test for AML models; a flag triggers review, not a conclusion of unfair
treatment. Records from the same customer are not independent, so p-values for transaction-level
models are optimistic. Groups with fewer than `min_n` records are reported but not tested.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd
from scipy.stats import norm

THRESHOLD = 0.80
ALPHA = 0.05


def two_proportion_p(x1: int, n1: int, x2: int, n2: int) -> float:
    if n1 == 0 or n2 == 0:
        return 1.0
    p = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (x1 / n1 - x2 / n2) / se
    return float(2 * (1 - norm.cdf(abs(z))))


def disparity(df: pd.DataFrame, group_col: str, adverse_col: str, truth_col: str, min_n: int = 100) -> Dict:
    rows: List[Dict] = []
    for g, part in df.groupby(group_col):
        n = len(part)
        adverse = part[adverse_col].astype(bool)
        truth = part[truth_col].astype(bool)
        neg = ~truth
        fpr = float((adverse & neg).sum() / neg.sum()) if neg.sum() else None
        rows.append({"group": str(g), "n": int(n), "adverse_rate": float(adverse.mean()),
                     "favourable_rate": float(1 - adverse.mean()), "base_rate": float(truth.mean()),
                     "false_positive_rate": fpr, "tested": n >= min_n, "_adv": int(adverse.sum()),
                     "_fp": int((adverse & neg).sum()), "_neg": int(neg.sum())})
    tested = [r for r in rows if r["tested"]]
    if not tested:
        return {"groups": rows, "min_impact_ratio": None, "min_fpr_ratio": None, "passed": None,
                "reference_group": None}
    best = max(tested, key=lambda r: r["favourable_rate"])
    best_fav = best["favourable_rate"]
    ref = best["group"]
    fpr_rows = [r for r in tested if r["false_positive_rate"]]
    low = min(fpr_rows, key=lambda r: r["false_positive_rate"]) if fpr_rows else None
    for r in rows:
        r["impact_ratio"] = r["favourable_rate"] / best_fav if best_fav else None
        r["impact_p_value"] = two_proportion_p(r["_adv"], r["n"], best["_adv"], best["n"])
        r["fpr_ratio"] = (low["false_positive_rate"] / r["false_positive_rate"]) if (
            low and r["false_positive_rate"]) else None
        r["fpr_p_value"] = two_proportion_p(r["_fp"], r["_neg"], low["_fp"], low["_neg"]) if low else 1.0
        ir_flag = r["impact_ratio"] is not None and r["impact_ratio"] < THRESHOLD and r["impact_p_value"] < ALPHA
        fpr_flag = r["fpr_ratio"] is not None and r["fpr_ratio"] < THRESHOLD and r["fpr_p_value"] < ALPHA
        r["flag"] = bool(r["tested"] and (ir_flag or fpr_flag))
    for r in rows:
        for k in ("_adv", "_fp", "_neg"):
            r.pop(k)
    min_ir = min(r["impact_ratio"] for r in tested)
    min_fr = min([r["fpr_ratio"] for r in tested if r["fpr_ratio"] is not None], default=None)
    return {"groups": sorted(rows, key=lambda r: r["group"]), "reference_group": ref,
            "min_impact_ratio": float(np.round(min_ir, 6)),
            "min_fpr_ratio": None if min_fr is None else float(np.round(min_fr, 6)),
            "passed": not any(r["flag"] for r in rows)}
