"""Escenarios sobre el fixture sintético (tolerancia relativa 1e-9).

Fixture: WACC 8,125 %, g 2 %, rf 3 %. Estimaciones +1/+2: media 1450/1550,
baja 1400/1480, alta 1500/1620 (cifras inventadas).
"""

import dataclasses
from datetime import UTC, datetime

import pytest

from dcf.company import Company, RevenueEstimate
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.model.fcff_cfo_projection import project_cash_flows
from dcf.model.fcff_cfo_ratios import compute_historical_ratios
from dcf.model.revenue_projection import EstimateCase
from dcf.valuation.enterprise import compute_enterprise_value, equity_value
from dcf.valuation.fcff_cfo import value_company
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode, ScenarioName

REL = 1e-9
NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)
SALES = ScenarioConfig(frozenset({ScenarioMode.SALES}), 0.01, 0.005)
COST = ScenarioConfig(frozenset({ScenarioMode.COST}), 0.01, 0.005)
BOTH = ScenarioConfig(frozenset({ScenarioMode.SALES, ScenarioMode.COST}), 0.01, 0.005)
NONE = ScenarioConfig(frozenset(), 0.01, 0.005)


@pytest.fixture
def ranged(company: Company) -> Company:
    estimates = (
        RevenueEstimate(2026, 1450.0, 5, revenue_low=1400.0, revenue_high=1500.0),
        RevenueEstimate(2027, 1550.0, 4, revenue_low=1480.0, revenue_high=1620.0),
    )
    return dataclasses.replace(company, revenue_estimates=estimates)


def _vps(c: Company, case: EstimateCase, wacc: float, g: float) -> float:
    ratios = compute_historical_ratios(c)
    flows = [f.fcff for f in project_cash_flows(c, ratios, 5, case).flows]
    ev = compute_enterprise_value(flows, wacc, g, 0.03)
    return equity_value(ev.enterprise_value, c.balance) / c.balance.diluted_shares


def _by_name(c: Company, mi: MarketInputs, cfg: ScenarioConfig, g: float = 0.02) -> dict:
    r = value_company(c, mi, Assumptions(terminal_growth=g), NOW, cfg)
    return {s.name: s for s in r.scenarios}


def test_proyeccion_con_estimacion_baja_y_alta(ranged: Company) -> None:
    ratios = compute_historical_ratios(ranged)
    low = project_cash_flows(ranged, ratios, 5, EstimateCase.LOW)
    high = project_cash_flows(ranged, ratios, 5, EstimateCase.HIGH)
    assert [f.revenue for f in low.flows[:2]] == [1400.0, 1480.0]
    assert [f.revenue for f in high.flows[:2]] == [1500.0, 1620.0]
    g1, g2 = 1400 / 1331 - 1, 1480 / 1400 - 1
    assert low.projection_growth == pytest.approx(0.10, rel=REL)  # mediana de {10 % × 3, g1, g2}
    assert g1 < 0.10 and g2 < 0.10


def test_falta_estimacion_alta_usa_la_media(company: Company) -> None:
    p = project_cash_flows(company, compute_historical_ratios(company), 5, EstimateCase.HIGH)
    assert [f.revenue for f in p.flows[:2]] == [1450.0, 1550.0]
    assert len(p.warnings) == 2 and "media" in p.warnings[0]


def test_modo_ventas(ranged: Company, market_inputs: MarketInputs) -> None:
    s = _by_name(ranged, market_inputs, SALES)
    assert s[ScenarioName.BEARISH].estimate_case is EstimateCase.LOW
    assert s[ScenarioName.BEARISH].discount_rate == pytest.approx(0.08125, rel=REL)
    assert s[ScenarioName.BEARISH].value_per_share == pytest.approx(
        _vps(ranged, EstimateCase.LOW, 0.08125, 0.02), rel=REL
    )
    assert s[ScenarioName.BULLISH].value_per_share == pytest.approx(
        _vps(ranged, EstimateCase.HIGH, 0.08125, 0.02), rel=REL
    )
    bear, neutral, bull = (s[n].value_per_share for n in ScenarioName)
    assert bear is not None and neutral is not None and bull is not None
    assert bear < neutral < bull


def test_neutro_coincide_con_la_valoracion(ranged: Company, market_inputs: MarketInputs) -> None:
    r = value_company(ranged, market_inputs, Assumptions(terminal_growth=0.02), NOW, BOTH)
    neutral = next(s for s in r.scenarios if s.name is ScenarioName.NEUTRAL)
    assert neutral.value_per_share == pytest.approx(r.value_per_share, rel=REL)


def test_modo_coste_alcista_invalido_si_g_alcanza_rf(
    ranged: Company, market_inputs: MarketInputs
) -> None:
    # g 2,5 %: bajista g = 2 % y WACC 9,125 %; alcista g = 3 % = rf → no válido
    s = _by_name(ranged, market_inputs, COST, g=0.025)
    bear, bull = s[ScenarioName.BEARISH], s[ScenarioName.BULLISH]
    assert bear.discount_rate == pytest.approx(0.09125, rel=REL)
    assert bear.terminal_growth == pytest.approx(0.02, rel=REL)
    assert bear.estimate_case is EstimateCase.AVERAGE
    assert bear.value_per_share == pytest.approx(
        _vps(ranged, EstimateCase.AVERAGE, 0.09125, 0.02), rel=REL
    )
    assert bull.value_per_share is None
    assert bull.error is not None and "rf" in bull.error


def test_modos_combinados(ranged: Company, market_inputs: MarketInputs) -> None:
    s = _by_name(ranged, market_inputs, BOTH, g=0.015)
    bull = s[ScenarioName.BULLISH]
    assert bull.estimate_case is EstimateCase.HIGH
    assert bull.discount_rate == pytest.approx(0.07125, rel=REL)
    assert bull.terminal_growth == pytest.approx(0.02, rel=REL)
    assert bull.value_per_share == pytest.approx(
        _vps(ranged, EstimateCase.HIGH, 0.07125, 0.02), rel=REL
    )


def test_sin_modos_los_tres_iguales(ranged: Company, market_inputs: MarketInputs) -> None:
    values = {s.value_per_share for s in _by_name(ranged, market_inputs, NONE).values()}
    assert len(values) == 1


def test_sin_config_no_hay_escenarios(ranged: Company, market_inputs: MarketInputs) -> None:
    r = value_company(ranged, market_inputs, Assumptions(terminal_growth=0.02), NOW)
    assert r.scenarios == ()


def test_config_rechaza_desplazamiento_negativo() -> None:
    with pytest.raises(ValueError, match="wacc_shift"):
        ScenarioConfig(frozenset(), -0.01, 0.005)
