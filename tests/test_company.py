import dataclasses
import math
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


def test_company_valida(company: Company) -> None:
    assert company.last_fiscal_year == 2025
    assert len(company.historicals) == 4
    assert len(company.revenue_estimates) == 2


def test_company_es_inmutable(company: Company) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        company.historicals = ()  # type: ignore[misc]


def test_info_rechaza_fecha_sin_zona(info: CompanyInfo) -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        dataclasses.replace(info, data_date=datetime(2026, 1, 1))


def test_info_eur_exige_fx_uno(info: CompanyInfo) -> None:
    with pytest.raises(ValueError, match="1.0"):
        dataclasses.replace(info, fx_rate_to_eur=1.1)


def test_info_otra_moneda_exige_fecha_fx(info: CompanyInfo) -> None:
    with pytest.raises(ValueError, match="fx_date"):
        dataclasses.replace(info, original_currency="USD", fx_rate_to_eur=0.9, fx_date=None)


def test_info_otra_moneda_valida(info: CompanyInfo) -> None:
    converted = dataclasses.replace(
        info,
        original_currency="USD",
        fx_rate_to_eur=0.9,
        fx_date=datetime(2026, 11, 18, tzinfo=UTC),
    )
    assert converted.fx_rate_to_eur == 0.9


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("revenue", 0.0),
        ("revenue", -1.0),
        ("capital_expenditure", -5.0),
        ("interest_expense", -1.0),
        ("debt_issuance", -1.0),
        ("debt_repayment", -1.0),
        ("net_income", math.nan),
        ("operating_cash_flow", math.inf),
    ],
)
def test_historical_rechaza_valores_invalidos(
    historicals: tuple[HistoricalYear, ...], field: str, value: float
) -> None:
    with pytest.raises(ValueError, match=field):
        dataclasses.replace(historicals[0], **{field: value})


def test_historical_admite_perdidas(historicals: tuple[HistoricalYear, ...]) -> None:
    year = dataclasses.replace(historicals[0], net_income=-50.0, operating_cash_flow=-10.0)
    assert year.net_income == -50.0


def test_debt_cost_rechaza_deuda_negativa(debt_cost_data: tuple[DebtCostYear, ...]) -> None:
    with pytest.raises(ValueError, match="total_debt"):
        dataclasses.replace(debt_cost_data[0], total_debt=-1.0)


@pytest.mark.parametrize("shares", [0.0, -100.0])
def test_balance_rechaza_acciones_no_positivas(balance: BalanceSnapshot, shares: float) -> None:
    with pytest.raises(ValueError, match="diluted_shares"):
        dataclasses.replace(balance, diluted_shares=shares)


def test_estimate_rechaza_ventas_no_positivas() -> None:
    with pytest.raises(ValueError, match="revenue"):
        RevenueEstimate(fiscal_year=2026, revenue=0.0)


def test_company_exige_minimo_historicos(company: Company) -> None:
    with pytest.raises(ValueError, match="al menos 2"):
        dataclasses.replace(company, historicals=company.historicals[:1])


def test_company_rechaza_historicos_no_consecutivos(company: Company) -> None:
    gap = (company.historicals[0], company.historicals[2])
    with pytest.raises(ValueError, match="consecutivos"):
        dataclasses.replace(company, historicals=gap)


def test_company_rechaza_historicos_desordenados(company: Company) -> None:
    with pytest.raises(ValueError, match="consecutivos"):
        dataclasses.replace(company, historicals=tuple(reversed(company.historicals)))


def test_company_estimaciones_deben_seguir_al_ultimo_historico(company: Company) -> None:
    with pytest.raises(ValueError, match="2026"):
        dataclasses.replace(
            company, revenue_estimates=(RevenueEstimate(fiscal_year=2027, revenue=1500.0),)
        )


def test_company_sin_estimaciones_es_valida(company: Company) -> None:
    assert dataclasses.replace(company, revenue_estimates=()).revenue_estimates == ()
