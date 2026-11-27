"""Data quality rules applied to model input feeds before scoring.

The generator injects defects without labelling them; these rules have to find them. Each row gets
the code of the first rule it fails, or None.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from app.simulation.world import JURISDICTIONS, period_bounds

VALID_CURRENCIES = {"USD", "GBP", "EUR", "SGD", "CHF", "CAD", "JPY"}

TRANSACTION_RULES = [
    ("missing_amount", "Amount is null"),
    ("non_positive_amount", "Amount is zero or negative"),
    ("invalid_currency", "Currency is not a valid ISO 4217 code used by the bank"),
    ("missing_counterparty_country", "Counterparty country missing on a non-cash payment"),
    ("unknown_counterparty_country", "Counterparty country not in the jurisdiction reference table"),
    ("booking_date_outside_period", "Booking date falls outside the reporting period"),
]
APPLICATION_RULES = [
    ("missing_country", "Applicant country missing"),
    ("missing_industry", "Industry missing for a business applicant"),
    ("non_positive_volume", "Expected monthly volume is zero or negative"),
]
ARTICLE_RULES = [("empty_body", "Article body empty or not parsed")]


def _first_issue(masks) -> pd.Series:
    out = pd.Series([None] * len(masks[0][1]), index=masks[0][1].index, dtype=object)
    for code, mask in reversed(masks):
        out = out.where(~mask, code)
    return out


def check_transactions(df: pd.DataFrame, period: Optional[str] = None) -> pd.Series:
    amt = df["amount_usd"]
    non_cash = ~df["channel"].isin(["Cash deposit", "Cash withdrawal"])
    cp = df["counterparty_country"]
    cp_missing = cp.isna() | (cp.astype(str).str.strip() == "")
    masks = [
        ("missing_amount", amt.isna()),
        ("non_positive_amount", amt.notna() & (amt <= 0)),
        ("invalid_currency", ~df["currency"].isin(VALID_CURRENCIES)),
        ("missing_counterparty_country", non_cash & cp_missing),
        ("unknown_counterparty_country", ~cp_missing & ~cp.isin(list(JURISDICTIONS.keys()))),
    ]
    if period:
        start, end = period_bounds(period)
        bd = pd.to_datetime(df["booking_date"]).dt.date
        masks.append(("booking_date_outside_period", (bd < start) | (bd > end)))
    else:
        masks.append(("booking_date_outside_period", pd.Series(False, index=df.index)))
    return _first_issue(masks)


def check_applications(df: pd.DataFrame) -> pd.Series:
    business = ~df["segment"].isin(["Retail", "Private Banking"])
    masks = [
        ("missing_country", df["country"].isna() | (df["country"].astype(str) == "")),
        ("missing_industry", business & ((df["industry"].isna()) | (df["industry"].astype(str) == ""))),
        ("non_positive_volume", ~(df["expected_monthly_volume"] > 0)),
    ]
    return _first_issue(masks)


def check_articles(df: pd.DataFrame) -> pd.Series:
    body = df["body"].fillna("").astype(str).str.strip()
    return _first_issue([("empty_body", body == "")])


def rule_catalogue():
    return {
        "transactions": [dict(code=c, description=d) for c, d in TRANSACTION_RULES],
        "applications": [dict(code=c, description=d) for c, d in APPLICATION_RULES],
        "articles": [dict(code=c, description=d) for c, d in ARTICLE_RULES],
    }


def none_if_nan(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    return v
