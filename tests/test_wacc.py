"""WACC sobre el fixture sintético, calculado a mano (tolerancia relativa 1e-9).

E = 10 € × 100 acciones = 1000; D = 200 → We = 5/6, Wd = 1/6.
Ke = 3 % + 1,2 × 5 % = 9 %. Kd = 10 / 200 = 5 % cada año. t = 35 / 140 = 25 %.
WACC = 5/6 × 9 % + 1/6 × 5 % × 0,75 = 7,5 % + 0,625 % = 8,125 %.
"""

import dataclasses
from datetime import UTC, datetime

import pytest

from dcf.company import Company
from dcf.model.cost_of_equity import MarketInputs, MarketRate, cost_of_equity
from dcf.model.wacc import compute_wacc, weighted_average_cost_of_capital

REL = 1e-9
NOW = datetime(2026, 11, 18, tzinfo=UTC)


def test_caso_referencia(company: Company, market_inputs: MarketInputs) -> None:
    w = compute_wacc(company, market_inputs)
    assert w.cost_of_equity == pytest.approx(0.09, rel=REL)
    assert w.cost_of_debt == pytest.approx(0.05, rel=REL)
    assert w.tax_rate == pytest.approx(0.25, rel=REL)
    assert w.equity_value == pytest.approx(1000.0, rel=REL)
    assert w.debt_value == pytest.approx(200.0, rel=REL)
    assert w.equity_weight == pytest.approx(5 / 6, rel=REL)
    assert w.debt_weight == pytest.approx(1 / 6, rel=REL)
    assert w.wacc == pytest.approx(0.08125, rel=REL)
    assert w.warnings == ()


def test_cost_of_equity() -> None:
    assert cost_of_equity(0.03, 1.2, 0.05) == pytest.approx(0.09, rel=REL)


@pytest.mark.parametrize(("we", "wd"), [(0.8, 0.3), (0.5, 0.4), (1.2, -0.2)])
def test_rechaza_pesos_invalidos(we: float, wd: float) -> None:
    with pytest.raises(ValueError, match="weight|sumar 1"):
        weighted_average_cost_of_capital(we, wd, 0.09, 0.05, 0.25)


def test_rechaza_kd_negativo() -> None:
    with pytest.raises(ValueError, match="cost_of_debt"):
        weighted_average_cost_of_capital(0.8, 0.2, 0.09, -0.01, 0.25)


@pytest.mark.parametrize("t", [-0.1, 1.1])
def test_rechaza_t_fuera_de_rango(t: float) -> None:
    with pytest.raises(ValueError, match="tax_rate"):
        weighted_average_cost_of_capital(0.8, 0.2, 0.09, 0.05, t)


def test_rechaza_wacc_no_positivo() -> None:
    with pytest.raises(ValueError, match="positivo"):
        weighted_average_cost_of_capital(1.0, 0.0, -0.01, 0.0, 0.25)


def test_sin_deuda_wacc_igual_a_ke(company: Company, market_inputs: MarketInputs) -> None:
    c = dataclasses.replace(
        company,
        balance=dataclasses.replace(company.balance, total_debt=0.0),
        debt_cost_data=tuple(
            dataclasses.replace(d, total_debt=0.0) for d in company.debt_cost_data
        ),
    )
    w = compute_wacc(c, market_inputs)
    assert w.cost_of_debt is None
    assert w.wacc == pytest.approx(0.09, rel=REL)
    assert len(w.warnings) == 4


def test_kd_excluye_anos_sin_deuda(company: Company, market_inputs: MarketInputs) -> None:
    debt = list(company.debt_cost_data)
    debt[0] = dataclasses.replace(debt[0], total_debt=0.0)
    debt[1] = dataclasses.replace(debt[1], interest_expense=20.0)  # Kd 2023 = 10 %
    w = compute_wacc(dataclasses.replace(company, debt_cost_data=tuple(debt)), market_inputs)
    assert 2022 not in w.cost_of_debt_by_year
    assert w.cost_of_debt == pytest.approx((0.10 + 0.05 + 0.05) / 3, rel=REL)


def test_error_si_hay_deuda_pero_ningun_kd(company: Company, market_inputs: MarketInputs) -> None:
    debt = tuple(dataclasses.replace(d, total_debt=0.0) for d in company.debt_cost_data)
    with pytest.raises(ValueError, match="Kd"):
        compute_wacc(dataclasses.replace(company, debt_cost_data=debt), market_inputs)


def test_error_si_ningun_t_valido(company: Company, market_inputs: MarketInputs) -> None:
    debt = tuple(dataclasses.replace(d, pretax_income=-1.0) for d in company.debt_cost_data)
    with pytest.raises(ValueError, match="tipo efectivo"):
        compute_wacc(dataclasses.replace(company, debt_cost_data=debt), market_inputs)


def test_market_rate_exige_fuente() -> None:
    with pytest.raises(ValueError, match="fuente"):
        MarketRate(0.03, " ", NOW)


def test_prima_debe_ser_positiva() -> None:
    with pytest.raises(ValueError, match="prima"):
        MarketInputs(MarketRate(0.03, "x", NOW), MarketRate(0.0, "x", NOW))


def test_kd_por_defecto_no_negativo() -> None:
    with pytest.raises(ValueError, match="deuda por defecto"):
        MarketInputs(
            MarketRate(0.03, "x", NOW), MarketRate(0.05, "x", NOW), MarketRate(-0.01, "x", NOW)
        )


def test_t_del_wacc_es_la_mediana(company: Company, market_inputs: MarketInputs) -> None:
    # t = 25 %, 91,64 %, 25 %, 25 % → media 41,6 %, mediana 25 %: el año anómalo no cuenta.
    debt = list(company.debt_cost_data)
    debt[1] = dataclasses.replace(debt[1], tax_provision=debt[1].pretax_income * 0.9164)
    w = compute_wacc(dataclasses.replace(company, debt_cost_data=tuple(debt)), market_inputs)
    assert w.tax_rate == pytest.approx(0.25, rel=REL)
    assert w.tax_rate_by_year[2023] == pytest.approx(0.9164, rel=REL)
