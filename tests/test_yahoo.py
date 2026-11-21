"""Carga de Yahoo sin red: fixture congelado con la estructura real de yfinance.

Cifras sintéticas (inventadas) en USD con cambio fijo 0,9 EUR/USD. Imita a Yahoo:
- cashflow y balance con 5 cierres; income_stmt con el más antiguo vacío (NaN);
- Capex y Repayment Of Debt negativos; sin fila Minority Interest.
"""

import dataclasses
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dcf.data.yahoo import YahooRawData, build_company, load_raw, normalize_price_currency, save_raw
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.wacc import compute_wacc
from dcf.valuation.fcff_cfo import value_company

REL = 1e-9
FX = 0.9
FETCHED = datetime(2026, 11, 18, 10, 30, tzinfo=UTC)
CLOSES = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31", "2021-12-31"])
REVENUE = [1331.0, 1210.0, 1100.0, 1000.0]  # 2025 → 2022, como ordena Yahoo


def _frame(rows: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=CLOSES).T


def _raw() -> YahooRawData:
    nan = math.nan
    income = _frame(
        {
            "Total Revenue": [*REVENUE, nan],
            "Net Income": [r * 0.10 for r in REVENUE] + [nan],
            "Interest Expense": [10.0] * 4 + [nan],
            "EBIT": [150.0] * 4 + [nan],
            "Pretax Income": [140.0] * 4 + [nan],
            "Tax Provision": [35.0] * 4 + [nan],
            "Diluted Average Shares": [100.0] * 4 + [nan],
        }
    )
    cashflow = _frame(
        {
            "Operating Cash Flow": [r * 0.15 for r in REVENUE] + [140.0],
            "Capital Expenditure": [-r * 0.05 for r in REVENUE] + [-45.0],
            "Issuance Of Debt": [20.0] * 5,
            "Repayment Of Debt": [-15.0] * 5,
        }
    )
    balance = _frame(
        {
            "Total Debt": [200.0] * 5,
            "Cash Cash Equivalents And Short Term Investments": [100.0] * 5,
            "Stockholders Equity": [610.0, 550.0, 500.0, 460.0, 420.0],
        }
    )
    estimates = pd.DataFrame(
        {
            "avg": [400.0, 410.0, 1500.0, 1600.0],
            "numberOfAnalysts": [5, 5, 5, 4],
            "currency": ["USD"] * 4,
        },
        index=pd.Index(["0q", "+1q", "0y", "+1y"], name="period"),
    )
    info = {
        "longName": "Empresa Sintética Inc.",
        "financialCurrency": "USD",
        "currency": "USD",
        "currentPrice": 11.0,
        "beta": 1.2,
        "sector": "Technology",
        "sectorKey": "technology",
        "industry": "Consumer Electronics",
        "industryKey": "consumer-electronics",
    }
    return YahooRawData("SYN", FETCHED, info, income, cashflow, balance, estimates, {"USD": FX})


def test_selecciona_los_4_ultimos_ejercicios_comunes() -> None:
    c = build_company(_raw())
    assert [h.fiscal_year for h in c.historicals] == [2022, 2023, 2024, 2025]
    assert [d.fiscal_year for d in c.debt_cost_data] == [2022, 2023, 2024, 2025]


def test_convierte_a_eur_y_normaliza_signos() -> None:
    c = build_company(_raw())
    first = c.historicals[0]
    assert first.revenue == pytest.approx(1000.0 * FX, rel=REL)
    assert first.net_income == pytest.approx(100.0 * FX, rel=REL)
    assert first.capital_expenditure == pytest.approx(50.0 * FX, rel=REL)  # Yahoo: −50
    assert first.debt_repayment == pytest.approx(15.0 * FX, rel=REL)  # Yahoo: −15
    assert first.interest_expense == pytest.approx(10.0 * FX, rel=REL)
    assert c.balance.total_debt == pytest.approx(200.0 * FX, rel=REL)
    assert c.balance.cash == pytest.approx(100.0 * FX, rel=REL)
    assert c.balance.share_price == pytest.approx(11.0 * FX, rel=REL)
    assert c.balance.diluted_shares == 100.0  # acciones: no se convierten
    assert c.balance.beta == 1.2
    assert c.balance.balance_date == datetime(2025, 12, 31, tzinfo=UTC)


def test_trazabilidad_de_moneda_y_fecha() -> None:
    info = build_company(_raw()).info
    assert info.source == "yahoo_finance"
    assert info.data_date == FETCHED
    assert info.original_currency == "USD"
    assert info.fx_rate_to_eur == FX
    assert info.fx_date == FETCHED
    assert info.price_currency == "USD"


def test_estimaciones_0y_y_1y() -> None:
    c = build_company(_raw())
    assert [(e.fiscal_year, e.num_analysts) for e in c.revenue_estimates] == [(2026, 5), (2027, 4)]
    assert c.revenue_estimates[0].revenue == pytest.approx(1500.0 * FX, rel=REL)


def test_minoritarios_ausentes_cero_con_aviso() -> None:
    c = build_company(_raw())
    assert c.balance.minority_interest == 0.0
    assert any("Minority Interest" in w for w in c.info.data_warnings)


def test_emision_ausente_cero_con_aviso() -> None:
    raw = _raw()
    raw = dataclasses.replace(raw, cashflow=raw.cashflow.drop(index="Issuance Of Debt"))
    c = build_company(raw)
    assert all(h.debt_issuance == 0.0 for h in c.historicals)
    assert sum("Issuance Of Debt" in w for w in c.info.data_warnings) == 4


@pytest.mark.parametrize(
    ("statement", "row"),
    [
        ("income_stmt", "Total Revenue"),
        ("income_stmt", "Diluted Average Shares"),
        ("income_stmt", "Interest Expense"),
        ("cashflow", "Operating Cash Flow"),
        ("balance_sheet", "Total Debt"),
        ("balance_sheet", "Cash Cash Equivalents And Short Term Investments"),
    ],
)
def test_error_si_falta_fila_obligatoria(statement: str, row: str) -> None:
    raw = _raw()
    raw = dataclasses.replace(raw, **{statement: getattr(raw, statement).drop(index=row)})
    with pytest.raises(ValueError, match=row):
        build_company(raw)


def test_error_si_falta_dato_de_un_ano() -> None:
    raw = _raw()
    income = raw.income_stmt.copy()
    income.loc["Tax Provision", CLOSES[2]] = np.nan
    with pytest.raises(ValueError, match="Tax Provision.*2023-12-31"):
        build_company(dataclasses.replace(raw, income_stmt=income))


@pytest.mark.parametrize("key", ["currentPrice", "financialCurrency"])
def test_error_si_falta_dato_de_info(key: str) -> None:
    raw = _raw()
    info = {k: v for k, v in raw.info.items() if k != key}
    with pytest.raises(ValueError, match=key):
        build_company(dataclasses.replace(raw, info=info))


# Sin beta en Yahoo la carga no falla: el modo de [beta] decide en el WACC.
def test_beta_ausente_queda_como_none() -> None:
    raw = _raw()
    info = {k: v for k, v in raw.info.items() if k != "beta"}
    assert build_company(dataclasses.replace(raw, info=info)).balance.beta is None


def test_beta_no_numerica_es_error() -> None:
    raw = _raw()
    with pytest.raises(ValueError, match="beta"):
        build_company(dataclasses.replace(raw, info={**raw.info, "beta": "alta"}))


def test_error_si_falta_tipo_de_cambio() -> None:
    with pytest.raises(ValueError, match="USD→EUR"):
        build_company(dataclasses.replace(_raw(), fx_to_eur={}))


def test_cotizacion_en_peniques() -> None:
    raw = _raw()
    info = {**raw.info, "currency": "GBp", "currentPrice": 250.0}
    c = build_company(dataclasses.replace(raw, info=info, fx_to_eur={"USD": FX, "GBP": 1.2}))
    assert c.info.price_currency == "GBP"
    assert c.balance.share_price == pytest.approx(2.5 * 1.2, rel=REL)


def test_normalize_price_currency() -> None:
    assert normalize_price_currency("GBp") == ("GBP", 0.01)
    assert normalize_price_currency("EUR") == ("EUR", 1.0)


def test_sin_estimaciones() -> None:
    c = build_company(dataclasses.replace(_raw(), revenue_estimate=pd.DataFrame()))
    assert c.revenue_estimates == ()
    assert any("0y" in w for w in c.info.data_warnings)


def test_sin_0y_no_usa_1y() -> None:
    raw = _raw()
    c = build_company(dataclasses.replace(raw, revenue_estimate=raw.revenue_estimate.drop("0y")))
    assert c.revenue_estimates == ()


def test_estimacion_sin_analistas_se_descarta() -> None:
    raw = _raw()
    est = raw.revenue_estimate.copy()
    est.loc["+1y", "numberOfAnalysts"] = 0
    c = build_company(dataclasses.replace(raw, revenue_estimate=est))
    assert [e.fiscal_year for e in c.revenue_estimates] == [2026]


def test_empresa_en_eur_sin_cambio() -> None:
    raw = _raw()
    info = {**raw.info, "financialCurrency": "EUR", "currency": "EUR"}
    est = raw.revenue_estimate.assign(currency="EUR")
    c = build_company(dataclasses.replace(raw, info=info, revenue_estimate=est, fx_to_eur={}))
    assert c.info.fx_date is None
    assert c.historicals[0].revenue == 1000.0


def test_cache_ida_y_vuelta(tmp_path: Path) -> None:
    raw = _raw()
    folder = save_raw(raw, tmp_path)
    assert folder == tmp_path / "SYN" / "20261118T103000Z"
    again = load_raw(folder)
    assert again.fetched_at == FETCHED
    assert build_company(again) == build_company(raw)


def test_valoracion_completa_desde_yahoo(market_inputs: MarketInputs) -> None:
    c = build_company(_raw())
    r = value_company(c, market_inputs, Assumptions(terminal_growth=0.02), FETCHED)
    assert r.ticker == "SYN"
    assert r.value_per_share > 0
    assert len(r.projections) == 5


KD_DEFAULT = MarketRate(0.04, "fixture Kd", FETCHED)


def _raw_without_interest(years: list[int]) -> YahooRawData:
    raw = _raw()
    income = raw.income_stmt.copy()
    for col in CLOSES:
        if col.year in years:
            income.loc["Interest Expense", col] = np.nan
    return dataclasses.replace(raw, income_stmt=income)


def test_intereses_ausentes_sin_kd_por_defecto_da_error() -> None:
    with pytest.raises(ValueError, match="default_cost_of_debt"):
        build_company(_raw_without_interest([2024, 2025]))


def test_intereses_ausentes_se_estiman_con_kd_por_defecto() -> None:
    # Deuda 200 USD × 0,9 = 180 EUR; intereses estimados = 4 % × 180 = 7,2 EUR
    c = build_company(_raw_without_interest([2024, 2025]), KD_DEFAULT)
    by_year = {h.fiscal_year: h.interest_expense for h in c.historicals}
    assert by_year[2024] == pytest.approx(0.04 * 180.0, rel=REL)
    assert by_year[2025] == pytest.approx(0.04 * 180.0, rel=REL)
    assert by_year[2023] == pytest.approx(10.0 * FX, rel=REL)  # publicado: no se toca
    debt = {d.fiscal_year: d.interest_expense for d in c.debt_cost_data}
    assert debt[2024] == by_year[2024]
    warnings = [w for w in c.info.data_warnings if "Interest Expense" in w]
    assert len(warnings) == 2 and "fixture Kd" in warnings[0]


def test_kd_del_ano_estimado_coincide_con_el_defecto(market_inputs: MarketInputs) -> None:
    c = build_company(_raw_without_interest([2024, 2025]), KD_DEFAULT)
    w = compute_wacc(c, market_inputs)
    assert w.cost_of_debt_by_year[2024] == pytest.approx(0.04, rel=REL)
    assert w.cost_of_debt_by_year[2022] == pytest.approx(0.05, rel=REL)  # 10 / 200
    assert w.cost_of_debt == pytest.approx((0.05 + 0.05 + 0.04 + 0.04) / 4, rel=REL)


def test_kd_por_defecto_no_se_usa_si_hay_intereses() -> None:
    c = build_company(_raw(), KD_DEFAULT)
    assert all(h.interest_expense == pytest.approx(10.0 * FX, rel=REL) for h in c.historicals)
    assert not any("Interest Expense" in w for w in c.info.data_warnings)
