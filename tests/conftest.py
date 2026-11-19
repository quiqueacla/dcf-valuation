"""Fixtures con cifras sintéticas (inventadas, redondas). No representan ninguna empresa real."""

from datetime import UTC, datetime

import pytest

from dcf.company import (
    BalanceSnapshot,
    Company,
    CompanyInfo,
    DebtCostYear,
    HistoricalYear,
    RevenueEstimate,
)
from dcf.model.cost_of_equity import MarketInputs, MarketRate

DATA_DATE = datetime(2026, 11, 18, tzinfo=UTC)


@pytest.fixture
def market_inputs() -> MarketInputs:
    # Tasas sintéticas redondas para tests: no son datos de mercado reales.
    return MarketInputs(
        risk_free_rate=MarketRate(0.03, "fixture", DATA_DATE),
        market_risk_premium=MarketRate(0.05, "fixture", DATA_DATE),
    )


@pytest.fixture
def info() -> CompanyInfo:
    return CompanyInfo(
        ticker="TEST",
        name="Empresa Sintética S.A.",
        source="fixture",
        data_date=DATA_DATE,
        original_currency="EUR",
        fx_rate_to_eur=1.0,
        fx_date=None,
    )


@pytest.fixture
def historicals() -> tuple[HistoricalYear, ...]:
    return tuple(
        HistoricalYear(
            fiscal_year=year,
            revenue=revenue,
            net_income=revenue * 0.10,
            operating_cash_flow=revenue * 0.15,
            capital_expenditure=revenue * 0.05,
            interest_expense=10.0,
            debt_issuance=20.0,
            debt_repayment=15.0,
        )
        for year, revenue in [(2022, 1000.0), (2023, 1100.0), (2024, 1210.0), (2025, 1331.0)]
    )


@pytest.fixture
def debt_cost_data() -> tuple[DebtCostYear, ...]:
    return tuple(
        DebtCostYear(
            fiscal_year=year,
            total_debt=200.0,
            interest_expense=10.0,
            ebit=150.0,
            pretax_income=140.0,
            tax_provision=35.0,
        )
        for year in range(2022, 2026)
    )


@pytest.fixture
def balance() -> BalanceSnapshot:
    return BalanceSnapshot(
        balance_date=datetime(2025, 12, 31, tzinfo=UTC),
        cash=100.0,
        total_debt=200.0,
        minority_interest=0.0,
        diluted_shares=100.0,
        share_price=10.0,
        beta=1.2,
    )


@pytest.fixture
def company(
    info: CompanyInfo,
    historicals: tuple[HistoricalYear, ...],
    debt_cost_data: tuple[DebtCostYear, ...],
    balance: BalanceSnapshot,
) -> Company:
    return Company(
        info=info,
        historicals=historicals,
        debt_cost_data=debt_cost_data,
        balance=balance,
        revenue_estimates=(
            RevenueEstimate(fiscal_year=2026, revenue=1450.0, num_analysts=5),
            RevenueEstimate(fiscal_year=2027, revenue=1550.0, num_analysts=4),
        ),
    )
