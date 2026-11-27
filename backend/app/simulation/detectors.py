"""The ten financial crime models the bank runs. These are the systems ModelGuard governs.

Each model is real code that scores synthetic records: a rules engine, gradient boosting, logistic
regression, TF-IDF text classification and character n-gram fuzzy matching. The two
LLM-based systems are the exception: AI-assisted investigations is a seeded simulation of triage
recommendations, and the LLM research assistant is evaluated only through recorded responses
(see app.analytics.llm_eval).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import normalize

from app.simulation.world import INDUSTRY_RISK, JURISDICTIONS, RISK_LEVEL, jurisdiction_tier

# ---------------------------------------------------------------------------------------------
# Shared transaction features
# ---------------------------------------------------------------------------------------------

CHANNEL_CODES = {"Card": 0, "ACH": 1, "Check": 2, "Cash deposit": 3, "Cash withdrawal": 4, "Domestic wire": 5,
                 "International wire": 6, "Instant payment": 7}
SEGMENT_CODES = {"Retail": 0, "Small Business": 1, "Corporate": 2, "Private Banking": 3, "Correspondent": 4}
SEGMENT_POINTS = {"Retail": 5, "Small Business": 15, "Corporate": 10, "Private Banking": 20, "Correspondent": 25}
JURIS_POINTS = {"Standard": 0, "Elevated": 12, "High": 25}

SAD_FEATURES = ["log_amt", "channel_code", "cp_risk", "cp_missing", "is_out", "near_ctr", "near_ctr_7d",
                "cash_dep_7d", "cash_dep_sum_7d", "txn_count_7d", "inflow_cover", "is_round", "static_risk",
                "segment_code"]


def static_risk_points(customers: pd.DataFrame) -> pd.Series:
    """Static part of the customer risk score: segment, industry, booking jurisdiction, PEP status."""
    seg = customers["segment"].map(SEGMENT_POINTS)
    ind = customers["industry"].map(INDUSTRY_RISK).fillna(0) * 10
    juris = customers["country"].map(lambda c: JURIS_POINTS.get(JURISDICTIONS[c][1], 0))
    pep = customers["pep_flag"].astype(int) * 20
    return (seg + ind + juris + pep).astype(float)


def transaction_features(txns: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Per-transaction features with 7-day and 4-day look-back windows per customer.

    `txns` may include a look-back tail from the previous period; callers filter afterwards.
    """
    d = txns.copy()
    d["booking_date"] = pd.to_datetime(d["booking_date"])
    d = d.sort_values(["customer_id", "booking_date", "txn_id"], kind="mergesort").reset_index(drop=True)
    amt = d["amount_usd"].fillna(0.0).astype(float)
    d["amt"] = amt
    d["log_amt"] = np.log1p(amt)
    d["channel_code"] = d["channel"].map(CHANNEL_CODES).astype(int)
    tier = d["counterparty_country"].map(jurisdiction_tier)
    d["cp_tier"] = tier
    d["cp_risk"] = tier.map(RISK_LEVEL).fillna(0).astype(int)
    d["cp_missing"] = (tier == "Missing").astype(int)
    d["is_out"] = (d["direction"] == "OUT").astype(int)
    is_cash_dep = d["channel"] == "Cash deposit"
    d["is_cash_dep"] = is_cash_dep.astype(int)
    d["near_ctr"] = (is_cash_dep & amt.between(8000, 9999.99)).astype(int)
    d["cash_dep_amt"] = np.where(is_cash_dep, amt, 0.0)
    d["in_amt"] = np.where(d["direction"] == "IN", amt, 0.0)
    d["one"] = 1

    idx = d.set_index("booking_date")
    g = idx.groupby("customer_id", sort=True)
    d["near_ctr_7d"] = g["near_ctr"].rolling("7D").sum().values
    d["cash_dep_7d"] = g["is_cash_dep"].rolling("7D").sum().values
    d["cash_dep_sum_7d"] = g["cash_dep_amt"].rolling("7D").sum().values
    d["txn_count_7d"] = g["one"].rolling("7D").sum().values
    inflow_4d = g["in_amt"].rolling("4D").sum().values - d["in_amt"].values
    with np.errstate(divide="ignore", invalid="ignore"):
        cover = np.where((d["is_out"] == 1) & (amt > 0), inflow_4d / amt.replace(0, np.nan), 0.0)
    d["inflow_cover"] = np.clip(np.nan_to_num(cover), 0, 3)
    d["is_round"] = ((amt >= 10000) & (np.mod(amt, 1000) == 0)).astype(int)

    cust = customers.set_index("customer_id")
    srp = static_risk_points(customers.reset_index(drop=True))
    srp.index = customers["customer_id"].values
    d["static_risk"] = d["customer_id"].map(srp).astype(float)
    d["segment"] = d["customer_id"].map(cust["segment"])
    d["segment_code"] = d["segment"].map(SEGMENT_CODES).astype(int)
    d["booking_date"] = d["booking_date"].dt.date
    return d


# ---------------------------------------------------------------------------------------------
# MDL-TM-001: rules-based transaction monitoring
# ---------------------------------------------------------------------------------------------

TM_RULES = [
    ("TM-R1", "Cash structuring: deposit of $8,000-$9,999 with 2+ such deposits in 7 days", 55),
    ("TM-R2", "Funnel activity: 4+ cash deposits totalling $15,000+ in 7 days", 50),
    ("TM-R3", "International wire of $5,000+ to a high-risk jurisdiction", 55),
    ("TM-R4", "Rapid movement: outgoing wire of $10,000+ covered 80%+ by inflows in the prior 4 days", 55),
    ("TM-R5", "Round-amount international wire of $25,000+", 35),
    ("TM-R6", "Velocity modifier: 8+ transactions in 7 days", 10),
    ("TM-R7", "Customer risk modifier: static risk score of 45+", 15),
]
TM_ALERT_THRESHOLD = 50


def tm_score(f: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    is_wire = f["channel"].isin(["International wire", "Domestic wire"])
    hits = {
        "TM-R1": (f["near_ctr"] == 1) & (f["near_ctr_7d"] >= 2),
        "TM-R2": (f["is_cash_dep"] == 1) & (f["cash_dep_7d"] >= 4) & (f["cash_dep_sum_7d"] >= 15000),
        "TM-R3": (f["channel"] == "International wire") & (f["cp_risk"] == 2) & (f["amt"] >= 5000),
        "TM-R4": is_wire & (f["is_out"] == 1) & (f["amt"] >= 10000) & (f["inflow_cover"] >= 0.8),
        "TM-R5": (f["channel"] == "International wire") & (f["is_round"] == 1) & (f["amt"] >= 25000),
        "TM-R6": f["txn_count_7d"] >= 8,
        "TM-R7": f["static_risk"] >= 45,
    }
    weights = {code: w for code, _, w in TM_RULES}
    score = np.zeros(len(f))
    for code, mask in hits.items():
        score += mask.values * weights[code]
    labels = []
    hit_frame = pd.DataFrame({k: v.values for k, v in hits.items()})
    for row in hit_frame.itertuples(index=False):
        labels.append(",".join(code for code, flag in zip(hit_frame.columns, row) if flag))
    return np.minimum(score, 100.0), labels


# ---------------------------------------------------------------------------------------------
# Name screening engine (MDL-SF-002, MDL-NS-003, MDL-PEP-005)
# ---------------------------------------------------------------------------------------------

_PUNCT = re.compile(r"[^A-Z ]")


def normalise_name(name: str) -> str:
    tokens = _PUNCT.sub(" ", str(name).upper()).split()
    tokens = [t for t in tokens if len(t) > 1 and t not in {"LLC", "LTD", "GMBH", "SA", "INC", "BV", "FZE", "PTE"}]
    return " ".join(sorted(tokens))


class Screener:
    """Character n-gram TF-IDF cosine similarity against a list, on token-sorted names."""

    def __init__(self, list_names: List[str]):
        self.names = list(list_names)
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), lowercase=False)
        self.matrix = normalize(self.vec.fit_transform([normalise_name(n) for n in self.names]))

    def score(self, names: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        if len(names) == 0:
            return np.zeros(0), np.zeros(0, dtype=int)
        q = normalize(self.vec.transform([normalise_name(n) for n in names]))
        sims = (q @ self.matrix.T).toarray()
        return sims.max(axis=1), sims.argmax(axis=1)


SF_THRESHOLD = 0.80
NS_THRESHOLD = 0.85
PEP_THRESHOLD = 0.86

# ---------------------------------------------------------------------------------------------
# MDL-CRS-004: customer risk scoring (points model, recalculated monthly)
# ---------------------------------------------------------------------------------------------

CRS_HIGH = 45.0
CRS_MEDIUM = 30.0


def crs_scores(customers: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Monthly customer risk score = static points + behavioural points from the month's activity."""
    static = static_risk_points(customers)
    static.index = customers["customer_id"].values
    f = feats.copy()
    f["out_amt"] = np.where(f["is_out"] == 1, f["amt"], 0.0)
    f["hr_out"] = np.where((f["is_out"] == 1) & (f["cp_risk"] >= 1), f["amt"], 0.0)
    agg = f.groupby("customer_id").agg(
        volume=("amt", "sum"), inflow=("in_amt", "sum"), cash_in=("cash_dep_amt", "sum"),
        out_amt=("out_amt", "sum"), hr_out=("hr_out", "sum"), near_ctr=("near_ctr", "sum"),
        dq=("dq_issue", lambda s: int(s.notna().sum())), n=("amt", "size"))
    out = pd.DataFrame({"customer_id": customers["customer_id"].values})
    out = out.merge(agg, left_on="customer_id", right_index=True, how="left").fillna(0)
    exp = customers.set_index("customer_id")["expected_monthly_volume"]
    cash_share = np.where(out["inflow"] > 0, out["cash_in"] / out["inflow"].replace(0, np.nan), 0)
    hr_share = np.where(out["out_amt"] > 0, out["hr_out"] / out["out_amt"].replace(0, np.nan), 0)
    vol_ratio = out["volume"] / out["customer_id"].map(exp)
    behaviour = (np.nan_to_num(cash_share) * 10 + np.nan_to_num(hr_share) * 20 + (vol_ratio >= 2) * 8
                 + (out["near_ctr"] >= 2) * 10)
    out["score"] = np.minimum(100.0, out["customer_id"].map(static).values + behaviour)
    out["rating"] = np.where(out["score"] >= CRS_HIGH, "High", np.where(out["score"] >= CRS_MEDIUM, "Medium", "Low"))
    out["dq_issue"] = np.where(out["dq"] > 0, "upstream_transaction_dq", None)
    out["monthly_volume"] = out["volume"]
    out["cash_share"] = np.nan_to_num(cash_share)
    return out


# ---------------------------------------------------------------------------------------------
# MDL-COR-010: onboarding risk classification (logistic regression)
# ---------------------------------------------------------------------------------------------

COR_SEGMENTS = ["Retail", "Small Business", "Corporate", "Private Banking"]
COR_THRESHOLD = 0.25


def application_features(apps: pd.DataFrame, screening_hits: pd.Series) -> np.ndarray:
    ind = apps["industry"].map(INDUSTRY_RISK).fillna(1).astype(float)
    country_lvl = apps["country"].map(lambda c: RISK_LEVEL[JURISDICTIONS[c][1]] if c in JURISDICTIONS else 1)
    seg = np.stack([(apps["segment"] == s).astype(float).values for s in COR_SEGMENTS], axis=1)
    X = np.column_stack([
        ind.values, country_lvl.astype(float).values, apps["ownership_layers"].astype(float).values,
        apps["cash_intensive"].astype(float).values, (~apps["source_of_funds_documented"].astype(bool)).astype(float).values,
        np.log1p(apps["expected_monthly_volume"].clip(lower=0).astype(float).values),
        screening_hits.reindex(apps["application_id"]).fillna(0).astype(float).values,
        seg,
    ])
    return X


# ---------------------------------------------------------------------------------------------
# MDL-AM-006: adverse media relevance classifier
# ---------------------------------------------------------------------------------------------

AM_THRESHOLD = 0.5


def article_text(articles: pd.DataFrame) -> List[str]:
    out = []
    for h, b, n in zip(articles["headline"], articles["body"].fillna(""), articles["subject_name"]):
        out.append(f"{h} {b}".replace(str(n), "SUBJECT").lower())
    return out


@dataclass
class ModelSuite:
    """Models that need fitting on the reference window."""

    sad: HistGradientBoostingClassifier = None
    sad_threshold: float = 0.5
    cor: LogisticRegression = None
    am_vec: TfidfVectorizer = None
    am_clf: LogisticRegression = None
    info: Dict[str, dict] = field(default_factory=dict)

    def fit(self, ref_txn_feats: pd.DataFrame, ref_apps: pd.DataFrame, ref_app_hits: pd.Series,
            ref_articles: pd.DataFrame, seed: int) -> "ModelSuite":
        X = ref_txn_feats[SAD_FEATURES].astype(float).values
        y = ref_txn_feats["is_suspicious"].astype(int).values
        self.sad = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_leaf_nodes=31,
                                                  l2_regularization=1.0, early_stopping=False,
                                                  random_state=seed % (2**31))
        self.sad.fit(X, y)
        ref_scores = self.sad.predict_proba(X)[:, 1]
        # Operating point: alert on the top 2.5% of reference-window scores
        self.sad_threshold = float(np.quantile(ref_scores, 0.975))
        self.info["MDL-SAD-007"] = {"algorithm": "HistGradientBoostingClassifier", "features": SAD_FEATURES,
                                    "training_rows": int(len(y)), "training_positive_rate": float(y.mean()),
                                    "operating_threshold": round(self.sad_threshold, 6),
                                    "threshold_rule": "97.5th percentile of reference-window scores"}

        Xa = application_features(ref_apps, ref_app_hits)
        ya = ref_apps["is_high_risk"].astype(int).values
        self.cor = LogisticRegression(max_iter=2000, C=1.0)
        self.cor.fit(Xa, ya)
        self.info["MDL-COR-010"] = {"algorithm": "LogisticRegression", "training_rows": int(len(ya)),
                                    "training_positive_rate": float(ya.mean()), "operating_threshold": COR_THRESHOLD}

        texts = article_text(ref_articles)
        self.am_vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
        Xt = self.am_vec.fit_transform(texts)
        yt = ref_articles["is_relevant"].astype(int).values
        self.am_clf = LogisticRegression(max_iter=3000, C=2.0, class_weight="balanced")
        self.am_clf.fit(Xt, yt)
        self.info["MDL-AM-006"] = {"algorithm": "TF-IDF (1-2 grams) + LogisticRegression",
                                   "vocabulary_size": int(len(self.am_vec.vocabulary_)),
                                   "training_rows": int(len(yt)), "operating_threshold": AM_THRESHOLD}
        return self

    def sad_scores(self, feats: pd.DataFrame) -> np.ndarray:
        return self.sad.predict_proba(feats[SAD_FEATURES].astype(float).values)[:, 1]

    def cor_scores(self, apps: pd.DataFrame, hits: pd.Series) -> np.ndarray:
        return self.cor.predict_proba(application_features(apps, hits))[:, 1]

    def am_scores(self, articles: pd.DataFrame) -> np.ndarray:
        return self.am_clf.predict_proba(self.am_vec.transform(article_text(articles)))[:, 1]
