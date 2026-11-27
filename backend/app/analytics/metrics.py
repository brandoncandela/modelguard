"""Classification and operational metrics. Pure functions over arrays; no database access.

Definitions (also served by GET /monitoring/methodology and documented in VALIDATION_METHODOLOGY.md):
  precision                TP / (TP + FP)          share of alerts that were truly suspicious / true matches
  recall                   TP / (TP + FN)          share of truly suspicious records that were alerted
  f1                       2PR / (P + R)
  false_positive_rate      FP / (FP + TN)          share of non-suspicious records that were alerted
  alert_false_positive_share  FP / (TP + FP)       what AML teams often call the "false positive rate"
  alert_rate               (TP + FP) / N
  alert_conversion_rate    escalated alerts / alerts
  override_rate            decisions differing from the model's recommendation / decisions
  dq_exception_rate        records failing an input data quality rule / records
Undefined ratios (zero denominator) are returned as None, never as 0.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Confusion:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn


def safe_div(num: float, den: float) -> Optional[float]:
    return None if den == 0 else float(num) / float(den)


def confusion(predicted, actual) -> Confusion:
    p = np.asarray(predicted, dtype=bool)
    a = np.asarray(actual, dtype=bool)
    if p.shape != a.shape:
        raise ValueError("predicted and actual must have the same length")
    return Confusion(tp=int((p & a).sum()), fp=int((p & ~a).sum()), fn=int((~p & a).sum()), tn=int((~p & ~a).sum()))


def classification_metrics(predicted, actual) -> Dict[str, Dict[str, Optional[float]]]:
    c = confusion(predicted, actual)
    precision = safe_div(c.tp, c.tp + c.fp)
    recall = safe_div(c.tp, c.tp + c.fn)
    f1 = None if precision is None or recall is None or (precision + recall) == 0 else \
        2 * precision * recall / (precision + recall)
    return {
        "precision": {"value": precision, "numerator": c.tp, "denominator": c.tp + c.fp},
        "recall": {"value": recall, "numerator": c.tp, "denominator": c.tp + c.fn},
        "f1": {"value": f1, "numerator": None, "denominator": None},
        "false_positive_rate": {"value": safe_div(c.fp, c.fp + c.tn), "numerator": c.fp, "denominator": c.fp + c.tn},
        "alert_false_positive_share": {"value": safe_div(c.fp, c.tp + c.fp), "numerator": c.fp,
                                       "denominator": c.tp + c.fp},
        "alert_rate": {"value": safe_div(c.tp + c.fp, c.n), "numerator": c.tp + c.fp, "denominator": c.n},
        "_confusion": asdict(c),
    }


def _bools(values) -> np.ndarray:
    """Booleans from a column that may hold None/NaN for records that were never alerted."""
    return np.array([bool(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else False
                     for v in values], dtype=bool)


def alert_conversion_rate(predicted, escalated) -> Dict[str, Optional[float]]:
    p = np.asarray(predicted, dtype=bool)
    e = _bools(escalated)
    alerts = int(p.sum())
    conv = int((p & e).sum())
    return {"value": safe_div(conv, alerts), "numerator": conv, "denominator": alerts}


def override_rate(recommended, decided) -> Dict[str, Optional[float]]:
    r = np.asarray(recommended, dtype=bool)
    d = _bools(decided)
    diff = int((r != d).sum())
    return {"value": safe_div(diff, len(r)), "numerator": diff, "denominator": len(r)}


def dq_exception_rate(dq_issue) -> Dict[str, object]:
    s = pd.Series(dq_issue, dtype=object)
    bad = s.notna() & (s.astype(str) != "")
    counts = s[bad].value_counts().to_dict()
    return {"value": safe_div(int(bad.sum()), len(s)), "numerator": int(bad.sum()), "denominator": len(s),
            "by_rule": {str(k): int(v) for k, v in sorted(counts.items())}}
