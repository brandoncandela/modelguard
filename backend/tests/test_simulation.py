"""Milestone 1: synthetic data generation is reproducible, meets volume targets and responds to drift."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.simulation import dq
from app.simulation.pipeline import generate_raw, list_names
from app.simulation.world import WorldConfig, build_world, periods_ending

CFG = WorldConfig(seed=20261031, anchor=date(2026, 10, 31))


@pytest.fixture(scope="module")
def world():
    return build_world(CFG)


def test_calendar():
    assert periods_ending(date(2026, 10, 31), 3) == ["2026-08", "2026-09", "2026-10"]
    assert CFG.periods[0] == "2025-11" and CFG.periods[-1] == "2026-10"
    assert CFG.reference_periods == CFG.periods[:6]
    # drift ramps over the last three periods only
    assert [CFG.intensity(i) for i in range(12)][:9] == [0.0] * 9
    assert CFG.intensity(11) == 0.5 and CFG.intensity(9) < CFG.intensity(10) < CFG.intensity(11)


def test_world_is_reproducible(world):
    again = build_world(CFG)
    pd.testing.assert_frame_equal(world.customers, again.customers)
    pd.testing.assert_frame_equal(world.watchlists, again.watchlists)
    other = build_world(WorldConfig(seed=7, anchor=date(2026, 10, 31)))
    assert not other.customers["name"].equals(world.customers["name"])


def test_period_generation_is_order_independent(world):
    lists = list_names(world)
    a = generate_raw(world, lists, "2026-03", 0.0)
    generate_raw(world, lists, "2026-01", 0.0)  # generating another period first must not matter
    b = generate_raw(world, lists, "2026-03", 0.0)
    pd.testing.assert_frame_equal(a.transactions, b.transactions)
    pd.testing.assert_frame_equal(a.applications, b.applications)


def test_customer_profiles(world):
    c = world.customers
    assert len(c) >= 1000
    assert c["customer_id"].is_unique
    assert 0.015 < c["is_suspicious"].mean() < 0.06
    assert set(c["segment"]) == {"Retail", "Small Business", "Corporate", "Private Banking", "Correspondent"}


def test_volumes_meet_specification(db):
    from sqlalchemy import func, select

    import app.models as m

    count = lambda model: db.execute(select(func.count()).select_from(model)).scalar()  # noqa: E731
    assert count(m.Transaction) >= 50_000
    assert count(m.Alert) >= 5_000
    assert count(m.Customer) >= 1_000
    assert count(m.InventoryModel) >= 10
    assert db.execute(select(func.count(func.distinct(m.ScoredRecord.period)))).scalar() == 12


def test_drift_shifts_channel_mix_and_amounts(world):
    lists = list_names(world)
    base = generate_raw(world, lists, "2026-05", 0.0).transactions
    severe = generate_raw(world, lists, "2026-05", 1.0).transactions
    share = lambda df: (df["channel"] == "Instant payment").mean()  # noqa: E731
    assert share(severe) > share(base) + 0.15
    # within a channel, amounts inflate (the overall median falls because cheap instant payments grow)
    ach = lambda df: df[(df.channel == "ACH") & df.typology.isna()]["amount_usd"].median()  # noqa: E731
    assert ach(severe) > ach(base) * 1.05
    # launderers adapt: structuring moves below the $8,000 band the rules watch
    s_base = base[(base.typology == "Structuring")]["amount_usd"]
    s_sev = severe[(severe.typology == "Structuring")]["amount_usd"]
    assert (s_base >= 8000).mean() > 0.9
    assert (s_sev < 8000).mean() > 0.9


def test_data_quality_rules_find_injected_defects(world):
    lists = list_names(world)
    base = generate_raw(world, lists, "2026-05", 0.0).transactions
    severe = generate_raw(world, lists, "2026-05", 1.0).transactions
    assert severe["dq_issue"].notna().mean() > base["dq_issue"].notna().mean() * 4
    assert set(severe["dq_issue"].dropna()) <= {c for c, _ in dq.TRANSACTION_RULES}


def test_dq_rules_unit():
    df = pd.DataFrame({
        "amount_usd": [100.0, np.nan, -5.0, 50.0, 70.0, 80.0],
        "currency": ["USD", "USD", "USD", "US$", "EUR", "EUR"],
        "channel": ["ACH", "ACH", "ACH", "ACH", "International wire", "Cash deposit"],
        "counterparty_country": ["US", "US", "US", "US", None, None],
        "booking_date": [date(2026, 5, 3)] * 6,
    })
    issues = dq.check_transactions(df, "2026-05").tolist()
    assert issues == [None, "missing_amount", "non_positive_amount", "invalid_currency",
                      "missing_counterparty_country", None]
