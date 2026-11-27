"""The fictional institution: calendar, jurisdictions, customer base and watch lists.

Every random draw comes from a generator keyed on (seed, purpose, period), so any period can be
regenerated on its own and gives the same result regardless of the order periods are built in.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.simulation import names as nm

# ---------------------------------------------------------------------------------------------
# Randomness and calendar
# ---------------------------------------------------------------------------------------------


def rng_for(seed: int, *keys) -> np.random.Generator:
    return np.random.default_rng([seed] + [zlib.crc32(str(k).encode()) for k in keys])


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def default_anchor(today: Optional[date] = None) -> date:
    t = today or date.today()
    return date(t.year, t.month, 1) - timedelta(days=1)


def period_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def period_bounds(period: str) -> Tuple[date, date]:
    y, m = (int(x) for x in period.split("-"))
    start = date(y, m, 1)
    return start, month_end(start)


def add_months(period: str, n: int) -> str:
    y, m = (int(x) for x in period.split("-"))
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def periods_ending(anchor: date, n: int) -> List[str]:
    last = period_of(anchor)
    return [add_months(last, -i) for i in range(n - 1, -1, -1)]


SCENARIO_INTENSITY = {"none": 0.0, "moderate": 0.5, "severe": 1.0}


@dataclass(frozen=True)
class WorldConfig:
    seed: int
    anchor: date
    history_months: int = 12
    reference_months: int = 6
    n_customers: int = 1200
    txn_scale: float = 0.85
    applications_per_month: int = 200
    articles_per_month: int = 520
    drift_scenario: str = "moderate"
    drift_periods: int = 3

    @property
    def periods(self) -> List[str]:
        return periods_ending(self.anchor, self.history_months)

    @property
    def reference_periods(self) -> List[str]:
        return self.periods[: self.reference_months]

    def intensity(self, period_index: int) -> float:
        """Drift intensity for the seeded history: ramps up over the last `drift_periods` periods."""
        s_max = SCENARIO_INTENSITY[self.drift_scenario]
        if s_max == 0 or self.drift_periods == 0:
            return 0.0
        first = self.history_months - self.drift_periods
        if period_index < first:
            return 0.0
        k = period_index - first + 1
        return round(s_max * k / self.drift_periods, 4)


# ---------------------------------------------------------------------------------------------
# Jurisdictions. Real ISO codes are used only for standard-risk locations. Elevated and high-risk
# jurisdictions use ISO 3166 user-assigned codes (Q*, X*) so no real country is labelled.
# ---------------------------------------------------------------------------------------------

JURISDICTIONS: Dict[str, Tuple[str, str]] = {
    "US": ("United States", "Standard"),
    "GB": ("United Kingdom", "Standard"),
    "DE": ("Germany", "Standard"),
    "IE": ("Ireland", "Standard"),
    "NL": ("Netherlands", "Standard"),
    "FR": ("France", "Standard"),
    "SG": ("Singapore", "Standard"),
    "CA": ("Canada", "Standard"),
    "JP": ("Japan", "Standard"),
    "CH": ("Switzerland", "Standard"),
    "QM": ("Jurisdiction M (fictional)", "Elevated"),
    "QN": ("Jurisdiction N (fictional)", "Elevated"),
    "QO": ("Jurisdiction O (fictional)", "Elevated"),
    "XA": ("Jurisdiction A (fictional)", "High"),
    "XB": ("Jurisdiction B (fictional)", "High"),
    "XC": ("Jurisdiction C (fictional)", "High"),
}
STANDARD = [k for k, v in JURISDICTIONS.items() if v[1] == "Standard"]
ELEVATED = [k for k, v in JURISDICTIONS.items() if v[1] == "Elevated"]
HIGH = [k for k, v in JURISDICTIONS.items() if v[1] == "High"]
RISK_LEVEL = {"Standard": 0, "Elevated": 1, "High": 2}


def jurisdiction_tier(code: Optional[str]) -> str:
    if code is None or (isinstance(code, float) and np.isnan(code)) or code == "":
        return "Missing"
    return JURISDICTIONS.get(code, ("Unknown", "Unknown"))[1]


BOOKING_COUNTRIES = ["US", "GB", "DE", "IE", "NL", "SG", "CH", "QM", "QN"]
BOOKING_WEIGHTS = [0.44, 0.16, 0.08, 0.04, 0.04, 0.12, 0.04, 0.05, 0.03]

SEGMENTS = ["Retail", "Small Business", "Corporate", "Private Banking", "Correspondent"]
SEGMENT_WEIGHTS = [0.55, 0.20, 0.12, 0.08, 0.05]
SEGMENT_TXN_RATE = {"Retail": 3.0, "Small Business": 6.0, "Corporate": 9.0, "Private Banking": 4.0,
                    "Correspondent": 12.0}
SEGMENT_AMOUNT_MULT = {"Retail": 1.0, "Small Business": 3.0, "Corporate": 12.0, "Private Banking": 8.0,
                       "Correspondent": 25.0}

INDUSTRY_RISK = {
    "Money services business": 2, "Virtual asset services": 2, "Real estate": 1, "Import / export": 2,
    "Gaming": 1, "Charity / non-profit": 1, "Professional services": 0, "Retail trade": 0,
    "Manufacturing": 0, "Restaurants and hospitality": 1, "Technology": 0, "Individual": 0,
}
BUSINESS_INDUSTRIES = [k for k in INDUSTRY_RISK if k != "Individual"]

REGION_WEIGHTS = [0.30, 0.22, 0.16, 0.10, 0.14, 0.08]

TYPOLOGIES = [
    "Structuring",
    "Rapid movement of funds",
    "High-risk jurisdiction exposure",
    "Funnel account",
    "Trade-based layering",
]


@dataclass
class World:
    config: WorldConfig
    customers: pd.DataFrame
    watchlists: pd.DataFrame
    meta: dict = field(default_factory=dict)


def build_customers(cfg: WorldConfig) -> pd.DataFrame:
    rng = rng_for(cfg.seed, "customers")
    n = cfg.n_customers
    seg = rng.choice(SEGMENTS, size=n, p=SEGMENT_WEIGHTS)
    region = rng.choice(nm.REGIONS, size=n, p=REGION_WEIGHTS)
    country = rng.choice(BOOKING_COUNTRIES, size=n, p=BOOKING_WEIGHTS)
    rows = []
    for i in range(n):
        s = seg[i]
        if s == "Retail" or s == "Private Banking":
            industry = "Individual"
            name = nm.person_name(rng, region[i])
        else:
            w = np.array([3 if INDUSTRY_RISK[k] == 0 else (2 if INDUSTRY_RISK[k] == 1 else 1) for k in BUSINESS_INDUSTRIES],
                         dtype=float)
            industry = rng.choice(BUSINESS_INDUSTRIES, p=w / w.sum())
            name = nm.company_name(rng)
        pep = bool(rng.random() < (0.05 if s == "Private Banking" else 0.012))
        onboard = cfg.anchor - timedelta(days=int(rng.integers(120, 365 * 9)))
        exp_vol = float(np.round(rng.lognormal(np.log(2500 * SEGMENT_AMOUNT_MULT[s]), 0.6), -1))
        # Latent propensity to launder: higher for risky industries, elevated jurisdictions and PEPs
        logit = -4.4 + 0.9 * INDUSTRY_RISK[industry] + 1.1 * RISK_LEVEL[JURISDICTIONS[country[i]][1]] + 1.0 * pep
        logit += {"Retail": 0.0, "Small Business": 0.6, "Corporate": 0.2, "Private Banking": 0.5, "Correspondent": 0.4}[s]
        p = 1 / (1 + np.exp(-logit))
        suspicious = bool(rng.random() < p)
        typology = None
        if suspicious:
            if s == "Retail":
                typology = rng.choice(["Structuring", "Funnel account", "Rapid movement of funds"], p=[0.5, 0.3, 0.2])
            elif s in ("Corporate", "Correspondent"):
                typology = rng.choice(["Trade-based layering", "High-risk jurisdiction exposure", "Rapid movement of funds"],
                                      p=[0.4, 0.35, 0.25])
            else:
                typology = rng.choice(TYPOLOGIES)
        rows.append({
            "customer_id": f"CUS-{i + 1:06d}",
            "name": name,
            "segment": s,
            "country": country[i],
            "nationality_region": region[i],
            "industry": industry,
            "onboarding_date": onboard,
            "pep_flag": pep,
            "expected_monthly_volume": exp_vol,
            "is_suspicious": suspicious,
            "typology": typology,
        })
    df = pd.DataFrame(rows)
    # Normal cash-intensive businesses that sit near reporting thresholds (a false-positive source)
    cash_heavy = (df["industry"].isin(["Restaurants and hospitality", "Retail trade"])) & (~df["is_suspicious"])
    df["cash_heavy_legit"] = cash_heavy & (rng.random(len(df)) < 0.45)
    # Legitimate pass-through activity: payroll processors, treasury sweeps
    df["pass_through_legit"] = (df["segment"].isin(["Corporate", "Correspondent", "Small Business"])) & (
        ~df["is_suspicious"]) & (rng.random(len(df)) < 0.12)
    # Legitimate customers with family or trade links to elevated or high-risk jurisdictions
    df["hr_corridor_legit"] = (~df["is_suspicious"]) & (rng.random(len(df)) < 0.045)
    return df


def build_watchlists(cfg: WorldConfig) -> pd.DataFrame:
    rng = rng_for(cfg.seed, "watchlists")
    rows = []
    counts = {"SANCTIONS": 320, "PEP": 420, "WATCHLIST": 160}
    k = 0
    for list_type, n in counts.items():
        for _ in range(n):
            k += 1
            region = rng.choice(nm.REGIONS, p=[0.08, 0.14, 0.18, 0.26, 0.20, 0.14])
            if list_type == "SANCTIONS" and rng.random() < 0.3:
                name = nm.company_name(rng)
            else:
                name = nm.person_name(rng, region, middle_initial_p=0.25)
            juris = rng.choice(HIGH + ELEVATED + STANDARD[:4], p=[0.2, 0.2, 0.15, 0.1, 0.1, 0.1, 0.05, 0.04, 0.03, 0.03])
            rows.append({"entry_id": f"WL-{k:05d}", "list_type": list_type, "name": name, "country": juris,
                         "region": region})
    return pd.DataFrame(rows)


def build_world(cfg: WorldConfig) -> World:
    return World(config=cfg, customers=build_customers(cfg), watchlists=build_watchlists(cfg))
