"""Descuento, valor terminal, puente a fondos propios y sensibilidad (tolerancia relativa 1e-9).

Caso de libro calculado a mano: FCFF = 100, 100; WACC 10 %; g 2 %; rf 3 %.
  VA flujos = 100/1,1 + 100/1,21 = 173,5537
  VT = 100 · 1,02 / 0,08 = 1275; VA VT = 1275 / 1,21 = 1053,7190
  VE = (110 + 100 + 1275) / 1,21 = 1485 / 1,21 = 1227,2727
  Peso VT = 1275 / 1485 = 85,86 %
"""

import dataclasses
import math
from datetime import UTC, datetime

import pytest

import dcf
from dcf.company import BalanceSnapshot, Company
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.model.terminal_value import gordon_terminal_value
from dcf.valuation.discounting import discount_factors, value_per_share
from dcf.valuation.enterprise import compute_enterprise_value, equity_value, sensitivity_table
from dcf.valuation.fcff_cfo import value_company

REL = 1e-9
NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)


def test_discount_factors() -> None:
    assert list(discount_factors(0.10, 2)) == pytest.approx([1 / 1.1, 1 / 1.21], rel=REL)


def test_gordon() -> None:
    assert gordon_terminal_value(100.0, 0.10, 0.02, 0.03) == pytest.approx(1275.0, rel=REL)


@pytest.mark.parametrize(("g", "match"), [(0.10, "WACC"), (0.12, "WACC"), (0.03, "rf")])
def test_gordon_rechaza_g_invalido(g: float, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        gordon_terminal_value(100.0, 0.10, g, 0.03)


def test_caso_libro_valor_empresa() -> None:
    ev = compute_enterprise_value([100.0, 100.0], 0.10, 0.02, 0.03)
    assert sum(ev.present_values) == pytest.approx(100 / 1.1 + 100 / 1.21, rel=REL)
    assert ev.terminal_value == pytest.approx(1275.0, rel=REL)
    assert ev.terminal_value_present == pytest.approx(1275.0 / 1.21, rel=REL)
    assert ev.enterprise_value == pytest.approx(1485.0 / 1.21, rel=REL)
    assert ev.terminal_value_present / ev.enterprise_value == pytest.approx(1275 / 1485, rel=REL)


def test_puente_a_fondos_propios(balance: BalanceSnapshot) -> None:
    # 1500 − 200 + 100 − 50 = 1350 → 13,50 € por acción (100 acciones)
    b = dataclasses.replace(balance, minority_interest=50.0)
    equity = equity_value(1500.0, b)
    assert equity == pytest.approx(1350.0, rel=REL)
    assert value_per_share(equity, b.diluted_shares) == pytest.approx(13.50, rel=REL)


@pytest.mark.parametrize("shares", [0.0, -1.0])
def test_valor_por_accion_rechaza_acciones_no_positivas(shares: float) -> None:
    with pytest.raises(ValueError, match="diluted_shares"):
        value_per_share(1000.0, shares)


def test_sensibilidad_centro_y_celdas_invalidas(balance: BalanceSnapshot) -> None:
    table = sensitivity_table([100.0, 100.0], balance, 0.10, 0.02, 0.03)
    assert table.shape == (5, 5)
    assert list(table.index) == pytest.approx([0.09, 0.095, 0.10, 0.105, 0.11])
    assert list(table.columns) == pytest.approx([0.01, 0.015, 0.02, 0.025, 0.03])
    centro = (1485.0 / 1.21 - 200 + 100) / 100
    assert table.loc[0.10, 0.02] == pytest.approx(centro, rel=REL)
    # g = 3 % no es < rf = 3 %: columna vacía
    assert table[0.03].isna().all()
    # Más WACC → menos valor; más g → más valor
    assert table.loc[0.09, 0.02] > table.loc[0.10, 0.02] > table.loc[0.11, 0.02]
    assert table.loc[0.10, 0.01] < table.loc[0.10, 0.02] < table.loc[0.10, 0.025]


def test_sensibilidad_vacia_si_g_mayor_que_wacc(balance: BalanceSnapshot) -> None:
    table = sensitivity_table([100.0], balance, 0.02, 0.015, 0.05)
    # WACC 1 % con g ≥ 0,5 %: solo es válida g = 0,5 %
    assert math.isnan(table.loc[0.01, 0.01])
    assert not math.isnan(table.loc[0.01, 0.005])


def test_valoracion_completa_caso_referencia(company: Company, market_inputs: MarketInputs) -> None:
    # Fixture: WACC 8,125 %, g 2 %, rf 3 %. Valores calculados de forma independiente.
    r = value_company(company, market_inputs, Assumptions(terminal_growth=0.02), NOW)
    assert r.wacc.wacc == pytest.approx(0.08125, rel=REL)
    assert sum(p.present_value for p in r.projections) == pytest.approx(716.0882988496072, rel=REL)
    assert r.terminal_value == pytest.approx(3577.742402086519, rel=REL)
    assert r.terminal_value_present == pytest.approx(2420.909004246504, rel=REL)
    assert r.enterprise_value == pytest.approx(3136.9973030961114, rel=REL)
    assert r.equity_value == pytest.approx(3036.9973030961114, rel=REL)
    assert r.value_per_share == pytest.approx(30.369973030961113, rel=REL)
    assert r.terminal_value_weight == pytest.approx(0.7717281114195246, rel=REL)
    assert r.sensitivity.loc[0.08125, 0.02] == pytest.approx(r.value_per_share, rel=REL)


def test_valoracion_registra_trazabilidad(company: Company, market_inputs: MarketInputs) -> None:
    r = value_company(company, market_inputs, Assumptions(terminal_growth=0.02), NOW)
    assert r.ticker == "TEST"
    assert r.source == "fixture"
    assert r.data_date == company.info.data_date
    assert r.valuation_date == NOW
    assert r.code_version == dcf.__version__
    assert r.wacc.market_inputs.risk_free_rate.source == "fixture"
    assert len(r.projections) == 5


def test_valoracion_rechaza_g_mayor_que_rf(company: Company, market_inputs: MarketInputs) -> None:
    with pytest.raises(ValueError, match="rf"):
        value_company(company, market_inputs, Assumptions(terminal_growth=0.035), NOW)
