"""Milestone 3: metric, PSI, drift and breach calculations checked against hand-computed values."""
from __future__ import annotations

import math

import numpy as np
import pytest

from app.analytics import breaches as br
from app.analytics import drift as dr
from app.analytics import metrics as mt
from app.analytics import psi


def test_confusion_and_classification_metrics():
    pred = [1, 1, 1, 0, 0, 0, 0, 1]
    act = [1, 0, 1, 1, 0, 0, 0, 0]
    c = mt.confusion(pred, act)
    assert (c.tp, c.fp, c.fn, c.tn) == (2, 2, 1, 3)
    m = mt.classification_metrics(pred, act)
    assert m["precision"]["value"] == pytest.approx(2 / 4)
    assert m["recall"]["value"] == pytest.approx(2 / 3)
    assert m["f1"]["value"] == pytest.approx(2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))
    assert m["false_positive_rate"]["value"] == pytest.approx(2 / 5)
    assert m["alert_false_positive_share"]["value"] == pytest.approx(2 / 4)
    assert m["alert_rate"]["value"] == pytest.approx(4 / 8)


def test_undefined_ratios_are_none_not_zero():
    m = mt.classification_metrics([0, 0, 0], [0, 0, 0])
    assert m["precision"]["value"] is None and m["recall"]["value"] is None and m["f1"]["value"] is None
    assert m["false_positive_rate"]["value"] == 0.0


def test_conversion_override_and_dq():
    assert mt.alert_conversion_rate([1, 1, 1, 0], [True, False, None, None])["value"] == pytest.approx(1 / 3)
    assert mt.override_rate([1, 0, 1, 0], [True, True, False, False])["value"] == pytest.approx(0.5)
    dq = mt.dq_exception_rate([None, "missing_amount", None, "invalid_currency", "missing_amount"])
    assert dq["value"] == pytest.approx(3 / 5)
    assert dq["by_rule"] == {"invalid_currency": 1, "missing_amount": 2}


def test_psi_categorical_hand_computed():
    ref = ["a"] * 50 + ["b"] * 50
    cur = ["a"] * 70 + ["b"] * 30
    value, table = psi.psi_categorical(ref, cur)
    expected = 0.2 * math.log(0.7 / 0.5) + (-0.2) * math.log(0.3 / 0.5)
    assert value == pytest.approx(expected, abs=1e-9)
    assert sum(r["contribution"] for r in table) == pytest.approx(value)


def test_psi_numeric_identical_is_zero_and_bins_are_deciles():
    rng = np.random.default_rng(1)
    ref = rng.normal(size=10_000)
    value, table = psi.psi_numeric(ref, ref.copy())
    assert value == pytest.approx(0.0, abs=1e-12)
    assert len(table) == 10
    assert all(abs(r["expected_share"] - 0.1) < 0.002 for r in table)


def test_psi_numeric_shift_matches_manual_computation():
    rng = np.random.default_rng(2)
    ref = rng.normal(size=20_000)
    cur = rng.normal(loc=0.5, size=20_000)
    value, table = psi.psi_numeric(ref, cur)
    e = np.array([r["expected_share"] for r in table])
    a = np.array([r["actual_share"] for r in table])
    assert value == pytest.approx(float(np.sum((a - e) * np.log(a / e))), rel=1e-9)
    assert 0.2 < value < 0.35  # half a standard deviation shift is a large population change
    assert psi.psi_band(value) in ("Moderate shift", "Significant shift")


def test_psi_empty_bin_uses_floor():
    value, table = psi.psi_categorical(["a", "b"], ["a", "a"])
    assert math.isfinite(value) and value > 1


def test_drift_effect_size_floor():
    rng = np.random.default_rng(3)
    big_ref = rng.normal(size=200_000)
    tiny_shift = rng.normal(loc=0.02, size=200_000)
    r = dr.numeric_drift("x", big_ref, tiny_shift)
    assert r.p_value < 0.01            # statistically significant because n is huge
    assert r.level == "Stable" and not r.flag  # but not material
    shifted = rng.normal(loc=0.6, size=5_000)
    r2 = dr.numeric_drift("x", big_ref[:5000], shifted)
    assert r2.flag and r2.level == "Significant"


def test_categorical_drift_chi_square():
    ref = ["wire"] * 600 + ["ach"] * 300 + ["instant"] * 100
    same = ["wire"] * 590 + ["ach"] * 310 + ["instant"] * 100
    moved = ["wire"] * 450 + ["ach"] * 250 + ["instant"] * 300
    assert dr.categorical_drift("channel", ref, same).level == "Stable"
    r = dr.categorical_drift("channel", ref, moved)
    assert r.flag and r.test_name == "Chi-square" and r.effect_size > 0.2


def test_breach_evaluation_both_directions():
    assert br.evaluate(0.60, "min", 0.55, 0.50) == "Within limits"
    assert br.evaluate(0.52, "min", 0.55, 0.50) == "Warning"
    assert br.evaluate(0.49, "min", 0.55, 0.50) == "Breach"
    assert br.evaluate(0.05, "max", 0.10, 0.25) == "Within limits"
    assert br.evaluate(0.12, "max", 0.10, 0.25) == "Warning"
    assert br.evaluate(0.30, "max", 0.10, 0.25) == "Breach"
    assert br.evaluate(None, "max", 0.10, 0.25) == "Not available"


def test_breach_severity_rules():
    assert br.severity(0.52, "min", 0.55, 0.50, 1, "High")[0] == "Low"
    assert br.severity(0.48, "min", 0.55, 0.50, 1, "Medium")[0] == "Medium"   # 0.4 bands past
    assert br.severity(0.44, "min", 0.55, 0.50, 1, "Medium")[0] == "High"     # 1.2 bands past
    assert br.severity(0.48, "min", 0.55, 0.50, 2, "High")[0] == "High"       # escalated, high-risk model
    assert br.severity(0.44, "min", 0.55, 0.50, 2, "High")[0] == "Critical"
    assert br.severity(0.48, "min", 0.55, 0.50, 2, "Low")[0] == "Medium"      # not escalated yet
    assert br.severity(0.48, "min", 0.55, 0.50, 3, "Low")[0] == "High"        # 3 periods: any model
    with pytest.raises(ValueError):
        br.validate_limits("min", 0.40, 0.50)
    with pytest.raises(ValueError):
        br.validate_limits("max", 0.30, 0.25)
