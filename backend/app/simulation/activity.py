"""Monthly activity generators: transactions, onboarding applications and media articles.

`intensity` (0 to 1) is the drift dial. At 0 behaviour matches the reference window. As it rises:
  population drift  more instant payments, higher amounts, more cross-border activity
  concept drift     launderers adapt: structuring below the band the rules watch, pass-through via
                    instant payments, routing through elevated jurisdictions, new crime vocabulary
  data quality      a payment platform migration drops counterparty country and currency codes
"""
from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from app.simulation import names as nm
from app.simulation.world import (
    ELEVATED,
    HIGH,
    INDUSTRY_RISK,
    JURISDICTIONS,
    RISK_LEVEL,
    SEGMENT_AMOUNT_MULT,
    SEGMENT_TXN_RATE,
    STANDARD,
    World,
    period_bounds,
    rng_for,
)

CHANNELS = ["Card", "ACH", "Check", "Cash deposit", "Cash withdrawal", "Domestic wire", "International wire",
            "Instant payment"]
CHANNEL_MIX = {
    "Retail": [0.42, 0.20, 0.05, 0.08, 0.10, 0.03, 0.04, 0.08],
    "Small Business": [0.15, 0.25, 0.12, 0.15, 0.05, 0.10, 0.10, 0.08],
    "Corporate": [0.05, 0.30, 0.05, 0.00, 0.00, 0.25, 0.27, 0.08],
    "Private Banking": [0.15, 0.15, 0.05, 0.02, 0.03, 0.25, 0.30, 0.05],
    "Correspondent": [0.00, 0.00, 0.00, 0.00, 0.00, 0.30, 0.62, 0.08],
}
MEDIAN_AMOUNT = {"Card": 85, "ACH": 900, "Check": 1200, "Cash deposit": 1400, "Cash withdrawal": 600,
                 "Domestic wire": 6000, "International wire": 9000, "Instant payment": 450}
INBOUND_P = {"Card": 0.0, "ACH": 0.5, "Check": 0.6, "Cash deposit": 1.0, "Cash withdrawal": 0.0,
             "Domestic wire": 0.5, "International wire": 0.45, "Instant payment": 0.5}
CURRENCY = {"US": "USD", "GB": "GBP", "DE": "EUR", "IE": "EUR", "NL": "EUR", "FR": "EUR", "SG": "SGD",
            "CH": "CHF", "CA": "CAD", "JP": "JPY", "QM": "USD", "QN": "USD", "QO": "USD"}


def _foreign_country(rng: np.random.Generator, home: str, hr_bias: float = 0.0) -> str:
    p_high = 0.03 + 0.25 * hr_bias
    p_elev = 0.12 + 0.35 * hr_bias
    u = rng.random()
    if u < p_high:
        return str(rng.choice(HIGH))
    if u < p_high + p_elev:
        return str(rng.choice(ELEVATED))
    choices = [c for c in STANDARD if c != home]
    return str(rng.choice(choices))


def generate_transactions(world: World, period: str, intensity: float, list_names: Dict[str, List[str]]
                          ) -> pd.DataFrame:
    """Generate one month of transactions with typology injection and data quality defects."""
    cfg = world.config
    rng = rng_for(cfg.seed, "txn", period)
    start, end = period_bounds(period)
    days = (end - start).days + 1
    s = intensity
    rows: List[dict] = []

    def add(cust, day, amount, channel, direction, cp_country, cp_name=None, suspicious=False, typology=None):
        day = int(min(max(day, 0), days - 1))
        rows.append({
            "customer_id": cust["customer_id"],
            "booking_date": start + timedelta(days=day),
            "amount_usd": float(round(amount, 2)),
            "currency": CURRENCY.get(cust["country"], "USD"),
            "channel": channel,
            "direction": direction,
            "counterparty_country": cp_country,
            "counterparty_name": cp_name,
            "is_suspicious": suspicious,
            "typology": typology,
        })

    instant_boost = 0.30 * s
    inflation = 1 + 0.15 * s
    for cust in world.customers.to_dict("records"):
        seg = cust["segment"]
        lam = SEGMENT_TXN_RATE[seg] * cfg.txn_scale * (1 + 0.20 * s)
        n = int(rng.poisson(lam))
        mix = np.array(CHANNEL_MIX[seg], dtype=float)
        mix = (1 - instant_boost) * mix
        mix[CHANNELS.index("Instant payment")] += instant_boost
        mix = mix / mix.sum()
        hr_bias = 0.6 if cust["hr_corridor_legit"] else 0.0
        for _ in range(n):
            ch = str(rng.choice(CHANNELS, p=mix))
            amt = rng.lognormal(np.log(MEDIAN_AMOUNT[ch] * SEGMENT_AMOUNT_MULT[seg] ** 0.6), 0.95) * inflation
            direction = "IN" if rng.random() < INBOUND_P[ch] else "OUT"
            if ch == "International wire" or (ch == "Instant payment" and rng.random() < 0.12 + 0.25 * s):
                cp = _foreign_country(rng, cust["country"], hr_bias + 0.1 * s)
            else:
                cp = cust["country"]
            if ch == "International wire" and seg in ("Corporate", "Correspondent") and rng.random() < 0.18:
                amt = float(rng.choice([25000, 50000, 100000, 250000]))  # treasury round amounts
            add(cust, rng.integers(0, days), max(amt, 1.0), ch, direction, cp)

        if cust["cash_heavy_legit"]:
            for _ in range(int(rng.integers(3, 8))):
                amt = rng.uniform(7600, 9900) if rng.random() < 0.40 else rng.uniform(2500, 7500)
                add(cust, rng.integers(0, days), amt, "Cash deposit", "IN", cust["country"])
        if cust["pass_through_legit"] and rng.random() < 0.7:
            amt = rng.lognormal(np.log(45000), 0.6)
            d0 = int(rng.integers(0, days - 3))
            add(cust, d0, amt, "Domestic wire", "IN", cust["country"])
            ch_out = "International wire" if rng.random() < 0.4 else "Domestic wire"
            cp = _foreign_country(rng, cust["country"]) if ch_out == "International wire" else cust["country"]
            add(cust, d0 + int(rng.integers(0, 3)), amt * rng.uniform(0.9, 0.99), ch_out, "OUT", cp)

        if cust["is_suspicious"] and rng.random() < 0.65:
            _inject_typology(rng, cust, add, days, s)

    df = pd.DataFrame(rows)
    df = df.sort_values(["booking_date", "customer_id"], kind="mergesort").reset_index(drop=True)
    df.insert(0, "txn_id", [f"TXN-{period.replace('-', '')}-{i + 1:06d}" for i in range(len(df))])
    df["period"] = period

    # Counterparty names, with sanctions list matches and near misses in cross-border payments
    cross = (df["counterparty_country"] != df["customer_id"].map(world.customers.set_index("customer_id")["country"]))
    df["cp_list_match"] = False
    names_out = []
    sanctions = list_names["SANCTIONS"]
    region_of = list_names["_region"]
    for i, row in enumerate(df.itertuples(index=False)):
        if row.channel in ("Cash deposit", "Cash withdrawal"):
            names_out.append(f"Branch {int(rng.integers(100, 999))}")
            continue
        if cross.iloc[i]:
            u = rng.random()
            if u < 0.015:
                target = sanctions[int(rng.integers(0, len(sanctions)))]
                names_out.append(nm.variant(rng, target, aggressiveness=0.15 + 0.85 * s))
                df.at[i, "cp_list_match"] = True
                continue
            if u < 0.055:
                target = sanctions[int(rng.integers(0, len(sanctions)))]
                if len(target.split()) <= 3 and not target.endswith(("LLC", "Ltd", "GmbH", "SA", "Inc", "BV", "FZE")):
                    names_out.append(nm.near_miss(rng, target, region_of[target]))
                    continue
        if row.channel == "Card" or rng.random() < 0.5:
            names_out.append(nm.company_name(rng))
        else:
            names_out.append(nm.person_name(rng, str(rng.choice(nm.REGIONS))))
    df["counterparty_name"] = names_out

    # Data quality defects: baseline noise plus a migration that drops fields under drift
    n = len(df)
    u = rng.random((n, 3))
    df.loc[u[:, 0] < 0.003, "amount_usd"] = np.nan
    df.loc[u[:, 1] < 0.002 + 0.015 * s, "currency"] = "US$"
    miss_cp = cross.values & (u[:, 2] < 0.004 + 0.07 * s)
    df.loc[miss_cp, "counterparty_country"] = None
    return df


def _inject_typology(rng, cust, add, days, s):
    t = cust["typology"]
    evade = rng.random() < s  # launderer adapts to the bank's detection logic
    home = cust["country"]
    if t == "Structuring":
        k = int(rng.integers(3, 7))
        d0 = int(rng.integers(0, days - 8))
        span = 20 if evade else 7
        for _ in range(k):
            amt = rng.uniform(5500, 7900) if evade else rng.uniform(8000, 9900)
            add(cust, d0 + int(rng.integers(0, span)), amt, "Cash deposit", "IN", home, suspicious=True, typology=t)
    elif t == "Rapid movement of funds":
        x = rng.lognormal(np.log(60000), 0.7)
        d0 = int(rng.integers(0, days - 4))
        if evade:
            add(cust, d0, x, "Instant payment", "IN", home, suspicious=True, typology=t)
            for part in (0.55, 0.42):
                add(cust, d0 + int(rng.integers(0, 2)), x * part, "Instant payment", "OUT", str(rng.choice(ELEVATED)),
                    suspicious=True, typology=t)
        else:
            add(cust, d0, x, str(rng.choice(["Domestic wire", "International wire"])), "IN", home, suspicious=True,
                typology=t)
            add(cust, d0 + int(rng.integers(1, 4)), x * rng.uniform(0.9, 0.98), "International wire", "OUT",
                str(rng.choice(ELEVATED + HIGH)), suspicious=True, typology=t)
    elif t == "High-risk jurisdiction exposure":
        if evade:
            for _ in range(int(rng.integers(5, 9))):
                add(cust, rng.integers(0, days), rng.uniform(2000, 4900), "International wire", "OUT",
                    str(rng.choice(ELEVATED)), suspicious=True, typology=t)
        else:
            for _ in range(int(rng.integers(2, 5))):
                add(cust, rng.integers(0, days), rng.uniform(8000, 90000), "International wire", "OUT",
                    str(rng.choice(HIGH)), suspicious=True, typology=t)
    elif t == "Funnel account":
        k = int(rng.integers(5, 11))
        total = 0.0
        d0 = int(rng.integers(0, days - 12))
        for _ in range(k):
            amt = rng.uniform(2000, 6000)
            total += amt
            add(cust, d0 + int(rng.integers(0, 9)), amt, "Cash deposit", "IN", home, suspicious=True, typology=t)
        ch = "Instant payment" if evade else "International wire"
        add(cust, d0 + 10, total * 0.95, ch, "OUT", str(rng.choice(ELEVATED)), suspicious=True, typology=t)
    elif t == "Trade-based layering":
        for _ in range(int(rng.integers(2, 4))):
            amt = float(rng.choice([25000, 50000, 75000, 100000, 150000]))
            if evade:
                amt = amt * rng.uniform(0.93, 1.07)
            add(cust, rng.integers(0, days), amt, "International wire", "OUT", str(rng.choice(ELEVATED)),
                suspicious=True, typology=t)


# ---------------------------------------------------------------------------------------------
# Onboarding applications and the names screened for each
# ---------------------------------------------------------------------------------------------


def generate_applications(world: World, period: str, intensity: float, list_names: Dict[str, List[str]]
                          ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    cfg = world.config
    rng = rng_for(cfg.seed, "applications", period)
    s = intensity
    n = int(round(cfg.applications_per_month * (1 + 0.3 * s)))
    region_of = list_names["_region"]
    apps, screen = [], []
    industries = list(INDUSTRY_RISK.keys())
    for i in range(n):
        app_id = f"APP-{period.replace('-', '')}-{i + 1:04d}"
        seg = str(rng.choice(["Retail", "Small Business", "Corporate", "Private Banking"], p=[0.5, 0.28, 0.14, 0.08]))
        region = str(rng.choice(nm.REGIONS, p=[0.30, 0.22, 0.16, 0.10, 0.14, 0.08]))
        if seg in ("Retail", "Private Banking"):
            industry = "Individual"
            applicant = nm.person_name(rng, region)
            n_rel = int(rng.integers(0, 2))
            layers = 1
        else:
            w = np.array([1.0 if k != "Individual" else 0.0 for k in industries])
            w[industries.index("Virtual asset services")] += 2.5 * s
            industry = str(rng.choice(industries, p=w / w.sum()))
            applicant = nm.company_name(rng)
            n_rel = int(rng.integers(1, 4))
            layers = int(min(6, 1 + rng.poisson(0.8 + 0.8 * s)))
        country = str(rng.choice(["US", "GB", "DE", "SG", "CH", "QM", "QN", "QO", "XA"],
                                 p=[0.36, 0.14, 0.08, 0.10, 0.04, 0.12, 0.08, 0.05, 0.03]))
        cash = bool(rng.random() < (0.35 if industry in ("Restaurants and hospitality", "Retail trade",
                                                           "Money services business", "Gaming") else 0.05))
        sof = bool(rng.random() < 0.85)
        exp_vol = float(np.round(rng.lognormal(np.log(3000 * SEGMENT_AMOUNT_MULT[seg]), 0.7), -1))

        names = [("Applicant", applicant)] + [("Related party", nm.person_name(rng, region)) for _ in range(n_rel)]
        sanc_any = pep_any = False
        for k, (role, name) in enumerate(names):
            ref = f"{app_id}-{k}"
            u = rng.random()
            sanc_truth = pep_truth = False
            if u < 0.025:
                target = list_names["SANCTIONS_WL"][int(rng.integers(0, len(list_names["SANCTIONS_WL"])))]
                name = nm.variant(rng, target, aggressiveness=0.1 + 0.6 * s)
                sanc_truth = True
            elif u < 0.065:
                target = list_names["PEP"][int(rng.integers(0, len(list_names["PEP"])))]
                name = nm.variant(rng, target, aggressiveness=0.1 + 0.6 * s)
                pep_truth = True
            elif u < 0.110:
                pool = list_names["PEP"] if rng.random() < 0.6 else list_names["SANCTIONS_WL"]
                target = pool[int(rng.integers(0, len(pool)))]
                if target in region_of and len(target.split()) <= 3:
                    name = nm.near_miss(rng, target, region_of[target])
            sanc_any |= sanc_truth
            pep_any |= pep_truth
            screen.append({"screen_ref": ref, "application_id": app_id, "period": period, "role": role,
                           "name": name, "sanctions_truth": sanc_truth, "pep_truth": pep_truth})
            if k == 0:
                applicant = name

        logit = (-3.9 + 1.0 * INDUSTRY_RISK[industry] + 1.1 * RISK_LEVEL[JURISDICTIONS[country][1]]
                 + 0.45 * (layers - 1) + 0.9 * cash + 1.4 * (not sof) + 1.6 * pep_any + 2.5 * sanc_any
                 + rng.normal(0, 0.6))
        high_risk = bool(rng.random() < 1 / (1 + np.exp(-logit)))
        apps.append({
            "application_id": app_id, "period": period, "applicant_name": applicant,
            "related_parties": [nme for role, nme in names[1:]], "segment": seg, "country": country,
            "nationality_region": region, "industry": industry, "ownership_layers": layers,
            "expected_monthly_volume": exp_vol, "cash_intensive": cash, "source_of_funds_documented": sof,
            "is_high_risk": high_risk,
        })
    apps_df = pd.DataFrame(apps)
    screen_df = pd.DataFrame(screen)
    # Data quality defects in onboarding feeds
    u = rng.random((len(apps_df), 2))
    apps_df.loc[u[:, 0] < 0.004 + 0.03 * s, "country"] = None
    apps_df.loc[u[:, 1] < 0.003, "industry"] = ""
    return apps_df, screen_df


# ---------------------------------------------------------------------------------------------
# Adverse media articles
# ---------------------------------------------------------------------------------------------

CRIME_TERMS = ["money laundering", "bribery", "embezzlement", "wire fraud", "sanctions evasion", "tax evasion",
               "a Ponzi scheme", "securities fraud", "corruption", "smuggling"]
NEW_CRIME_TERMS = ["a pig butchering scam", "a money mule network", "a crypto mixing service", "a romance scam ring",
                   "deepfake impersonation", "an account takeover ring"]
PLACES = ["Rotterdam", "Lagos", "Miami", "Singapore", "Frankfurt", "Panama City", "Dubai", "Toronto", "Lyon",
          "Cape Town", "Osaka", "Bogota"]
REL_HEADLINES = [
    "{name} charged with {crime} in {place} probe",
    "Prosecutors indict {name} over {crime}",
    "{name} arrested in connection with {crime}",
    "Regulator fines firm linked to {name} for {crime}",
    "{name} convicted of {crime} after lengthy trial",
    "Court freezes assets of {name} amid {crime} investigation",
    "{name} pleads guilty to {crime} charges",
]
REL_BODY = [
    "Authorities in {place} said the investigation into {crime} had been running for two years.",
    "Court filings allege that funds were moved through several shell companies.",
    "Investigators traced transfers to accounts held in multiple jurisdictions.",
    "The indictment describes a pattern of cash deposits and offshore transfers.",
    "A spokesperson for the prosecutor's office declined to comment on further arrests.",
    "Asset seizures included property, vehicles and bank balances.",
]
NEW_REL_HEADLINES = [
    "{name} named in report on {crime}",
    "Police link {name} to {crime} targeting retirees",
    "Victims say {name} ran {crime} through messaging apps",
    "{name} exposed in investigation into {crime}",
]
NEW_REL_BODY = [
    "Victims described being contacted on social platforms and persuaded to transfer savings.",
    "Funds were routed through instant payments and converted to stablecoins within hours.",
    "Consumer advocates in {place} warned of copycat schemes.",
    "Platform operators removed accounts linked to the operation.",
]
IRR_HEADLINES = [
    "{name} named to board of {company}",
    "{name} opens new office in {place}",
    "{name} wins regional entrepreneur award",
    "Charity gala hosted by {name} raises record funds",
    "{company} appoints {name} as chief financial officer",
    "{name} speaks at {place} payments conference",
    "{name} involved in minor traffic accident in {place}",
    "{name} settles contract dispute with supplier",
    "{name} completes marathon for children's hospital",
    "{company} reports strong quarter under {name}",
]
IRR_BODY = [
    "The appointment takes effect next month, the company said in a statement.",
    "Attendees at the event in {place} included local business leaders.",
    "The firm plans to hire forty staff over the coming year.",
    "No injuries were reported and the matter was resolved the same day.",
    "Both parties said they were satisfied with the outcome.",
    "Analysts expect continued growth in the region.",
]
COLLISION_HEADLINES = [
    "{name}, a {age}-year-old resident of {place}, charged with {crime}",
    "Local man {name} arrested in {place} on {crime} allegations",
]


def generate_articles(world: World, period: str, intensity: float, subject_pool: List[str]) -> pd.DataFrame:
    cfg = world.config
    rng = rng_for(cfg.seed, "articles", period)
    s = intensity
    rows = []
    p_rel = 0.13 + 0.06 * s
    for i in range(cfg.articles_per_month):
        name = subject_pool[int(rng.integers(0, len(subject_pool)))] if subject_pool else nm.person_name(rng, "Europe")
        place = str(rng.choice(PLACES))
        company = nm.company_name(rng)
        u = rng.random()
        body_empty = False
        if u < p_rel:
            relevant = True
            if rng.random() < s:
                crime = str(rng.choice(NEW_CRIME_TERMS))
                head = str(rng.choice(NEW_REL_HEADLINES))
                body = list(rng.choice(NEW_REL_BODY, size=2, replace=False))
            else:
                crime = str(rng.choice(CRIME_TERMS))
                head = str(rng.choice(REL_HEADLINES))
                body = list(rng.choice(REL_BODY, size=2, replace=False))
        elif u < p_rel + 0.035:
            # Same name, different person. The text reads exactly like a true hit, which is the known
            # limitation of name-based media screening and the main source of false positives.
            relevant = False
            crime = str(rng.choice(CRIME_TERMS))
            head = str(rng.choice(REL_HEADLINES + COLLISION_HEADLINES))
            body = list(rng.choice(REL_BODY, size=2, replace=False))
        else:
            relevant = False
            crime = ""
            head = str(rng.choice(IRR_HEADLINES))
            body = list(rng.choice(IRR_BODY, size=2, replace=False))
        fmt = dict(name=name, crime=crime, place=place, company=company, age=int(rng.integers(24, 71)))
        headline = head.format(**fmt)
        text = " ".join(b.format(**fmt) for b in body)
        if rng.random() < 0.003:
            text = ""
            body_empty = True
        rows.append({"article_id": f"ART-{period.replace('-', '')}-{i + 1:05d}", "period": period,
                     "subject_name": name, "headline": headline, "body": text, "is_relevant": relevant,
                     "_body_empty": body_empty})
    df = pd.DataFrame(rows).drop(columns=["_body_empty"])
    return df
