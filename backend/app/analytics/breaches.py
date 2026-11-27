"""Threshold evaluation and breach severity.

Each monitored metric has a warning limit and a breach limit. For 'min' metrics (recall, precision)
lower values are adverse; for 'max' metrics (PSI, data quality exceptions) higher values are adverse.

Severity:
    Low        value is past the warning limit but within the breach limit
    Medium     value is past the breach limit by less than one warning-to-breach band
    High       value is past the breach limit by one band or more
    Escalation one level up (Medium to High, High to Critical) when the breach has persisted for
               2+ consecutive periods on a High-risk model, or 3+ consecutive periods on any model.
"""
from __future__ import annotations

from typing import Optional, Tuple

ORDER = ["Low", "Medium", "High", "Critical"]


def adverse_excess(value: float, limit: float, direction: str) -> float:
    """How far past the limit the value is in the adverse direction (negative when not past it)."""
    return (limit - value) if direction == "min" else (value - limit)


def evaluate(value: Optional[float], direction: str, warning: float, breach: float) -> str:
    if value is None:
        return "Not available"
    if adverse_excess(value, breach, direction) > 0:
        return "Breach"
    if adverse_excess(value, warning, direction) > 0:
        return "Warning"
    return "Within limits"


def severity(value: float, direction: str, warning: float, breach: float, consecutive: int,
             model_risk: str) -> Tuple[str, str]:
    status = evaluate(value, direction, warning, breach)
    if status == "Within limits" or status == "Not available":
        raise ValueError("severity only applies to warnings and breaches")
    if status == "Warning":
        return "Low", "Past the warning limit, within the breach limit"
    band = abs(breach - warning) or abs(breach) * 0.1 or 1e-9
    r = adverse_excess(value, breach, direction) / band
    level = "Medium" if r < 1 else "High"
    why = f"Past the breach limit by {r:.2f} warning-to-breach bands"
    escalate = (consecutive >= 2 and model_risk == "High") or consecutive >= 3
    if escalate:
        level = ORDER[min(ORDER.index(level) + 1, len(ORDER) - 1)]
        why += f"; escalated after {consecutive} consecutive periods in breach on a {model_risk}-risk model"
    return level, why


def validate_limits(direction: str, warning: float, breach: float) -> None:
    if direction == "min" and warning < breach:
        raise ValueError("For 'min' metrics the warning limit must be at or above the breach limit")
    if direction == "max" and warning > breach:
        raise ValueError("For 'max' metrics the warning limit must be at or below the breach limit")
