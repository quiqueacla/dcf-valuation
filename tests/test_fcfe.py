"""Modelo FCFE sobre un banco sintético, calculado a mano (tolerancia relativa 1e-9).

Cifras inventadas y redondas (no son de ninguna entidad real):

- Históricos: 2024 ventas 1000, NI 100, FP 900; 2025 ventas 1100, NI 110, FP 1000.
  Crecimiento histórico 10 %, margen neto 10 %. Sin estimaciones: g_t = 10 %.
- 2026e: ventas 1210, NI 121, reinversión 0,10 × 1000 = 100, FCFE 21, FP 1100.
- 2027e: ventas 1331, NI 133,1, reinversión 0,10 × 1100 = 110, FCFE 23,1, FP 1210.
- Ke = 3 % + 1,2 × 5 % = 9 %; g = 2 %.
- FCFE 2028 = 133,1 × 1,02 − 0,02 × 1210 = 111,562; VT = 111,562 / 0,07.
- Fondos propios = 21 / 1,09 + 23,1 / 1,09² + VT / 1,09² = 1380,1305… → 13,80 € por acción
  (100 acciones).
"""

import dataclasses
from datetime import UTC, datetime

import pytest

from dcf.company import (
    BalanceSnapshot,
    Company,
    CompanyInfo,
    CompanyType,
    HistoricalYear,
    ValuationModel,
)
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.model.fcfe_projection import compute_fcfe_ratios, project_fcfe, terminal_fcfe
from dcf.reports.markdown import render_report
from dcf.valuation.fcfe import value_company
from dcf.valuation.fcfe_result import FcfeValuationResult
from dcf.valuation.fcff_result import ValuationResult
from dcf.valuation.run import run_valuation
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode, ScenarioName

REL = 1e-9
NOW = datetime(2026, 11, 19, tzinfo=UTC)
KE, G = 0.09, 0.02
TV = (133.1 * 1.02 - 0.02 * 1210) / (KE - G)
EQUITY = 21 / 1.09 + 23.1 / 1.09**2 + TV / 1.09**2
COST = ScenarioConfig(frozenset({ScenarioMode.COST}), 0.01, 0.005)


# Ejercicio de un banco: sin datos de caja (el FCFE no los usa).
def _year(fiscal_year: int, revenue: float, net_income: float, equity: float) -> HistoricalYear:
    return HistoricalYear(fiscal_year, revenue, net_income, None, None, None, None, None, equity)


@pytest.fixture
def bank() -> Company:
    info = CompanyInfo(
        ticker="BANK",
        name="Banco Sintético S.A.",
        source="fixture",
        data_date=NOW,
        original_currency="EUR",
        fx_rate_to_eur=1.0,
        fx_date=None,
        company_type=CompanyType.BANK,
        valuation_model=ValuationModel.FCFE,
    )
    balance = BalanceSnapshot(
        balance_date=datetime(2025, 12, 31, tzinfo=UTC),
        cash=None,
        total_debt=None,
        minority_interest=0.0,
        diluted_shares=100.0,
        share_price=10.0,
        beta=1.2,
    )
    return Company(
        info=info,
        historicals=(_year(2024, 1000.0, 100.0, 900.0), _year(2025, 1100.0, 110.0, 1000.0)),
        debt_cost_data=(),
        balance=balance,
    )


# Valoración FCFE del banco con horizonte de 2 años.
def _value(
    bank: Company,
    market: MarketInputs,
    g: float = G,
    scenario_config: ScenarioConfig | None = None,
) -> FcfeValuationResult:
    return value_company(bank, market, Assumptions(g, projection_years=2), NOW, scenario_config)


def test_ratios(bank: Company) -> None:
    r = compute_fcfe_ratios(bank)
    assert r.average_revenue_growth == pytest.approx(0.10, rel=REL)
    assert r.average_net_margin == pytest.approx(0.10, rel=REL)
    assert r.last_equity == 1000.0
    assert r.return_on_equity_by_year == {2025: pytest.approx(110 / 900, rel=REL)}


def test_proyeccion_calculada_a_mano(bank: Company) -> None:
    flows = project_fcfe(bank, compute_fcfe_ratios(bank), 2).flows
    assert [f.fiscal_year for f in flows] == [2026, 2027]
    assert [f.net_income for f in flows] == pytest.approx([121.0, 133.1], rel=REL)
    assert [f.equity_reinvestment for f in flows] == pytest.approx([100.0, 110.0], rel=REL)
    assert [f.fcfe for f in flows] == pytest.approx([21.0, 23.1], rel=REL)
    assert [f.equity_end for f in flows] == pytest.approx([1100.0, 1210.0], rel=REL)
    assert flows[0].implied_roe == pytest.approx(0.121, rel=REL)
    assert terminal_fcfe(flows[-1], G) == pytest.approx(111.562, rel=REL)


def test_caso_referencia(bank: Company, market_inputs: MarketInputs) -> None:
    r = _value(bank, market_inputs)
    assert r.cost_of_equity.cost_of_equity == pytest.approx(KE, rel=REL)
    assert r.terminal_fcfe == pytest.approx(111.562, rel=REL)
    assert r.terminal_value == pytest.approx(TV, rel=REL)
    assert r.equity_value == pytest.approx(EQUITY, rel=REL)
    assert r.equity_value == pytest.approx(1380.1305, rel=1e-6)
    assert r.value_per_share == pytest.approx(EQUITY / 100, rel=REL)
    assert r.terminal_value_weight == pytest.approx((TV / 1.09**2) / EQUITY, rel=REL)
    assert r.sensitivity.loc[KE, G] == pytest.approx(r.value_per_share, rel=REL)


def test_sensibilidad_ke_por_g(bank: Company, market_inputs: MarketInputs) -> None:
    s = _value(bank, market_inputs).sensitivity
    assert s.index.name == "discount_rate" and s.shape == (5, 5)
    # Mayor Ke → menor valor; g ≥ rf (3 %) → celda vacía.
    assert s.loc[0.08, G] > s.loc[KE, G] > s.loc[0.10, G]
    assert s[0.03].isna().all()


def test_escenarios_coste_desplazan_ke(bank: Company, market_inputs: MarketInputs) -> None:
    scenarios = {s.name: s for s in _value(bank, market_inputs, scenario_config=COST).scenarios}
    bear, neutral = scenarios[ScenarioName.BEARISH], scenarios[ScenarioName.NEUTRAL]
    assert bear.discount_rate == pytest.approx(0.10, rel=REL)
    assert bear.terminal_growth == pytest.approx(0.015, rel=REL)
    assert neutral.value_per_share == pytest.approx(EQUITY / 100, rel=REL)
    bear_tv = (133.1 * 1.015 - 0.015 * 1210) / (0.10 - 0.015)
    bear_equity = 21 / 1.10 + 23.1 / 1.10**2 + bear_tv / 1.10**2
    assert bear.value_per_share == pytest.approx(bear_equity / 100, rel=REL)
    # Alcista: g = 2,5 % < rf = 3 %, Ke = 8 %.
    assert scenarios[ScenarioName.BULLISH].value_per_share is not None


def test_rechaza_g_mayor_o_igual_que_ke(bank: Company, market_inputs: MarketInputs) -> None:
    with pytest.raises(ValueError, match="Ke"):
        _value(bank, market_inputs, g=0.09)


def test_rechaza_g_mayor_o_igual_que_rf(bank: Company, market_inputs: MarketInputs) -> None:
    with pytest.raises(ValueError, match="rf"):
        _value(bank, market_inputs, g=0.03)


def test_error_si_faltan_fondos_propios(bank: Company, market_inputs: MarketInputs) -> None:
    years = (
        bank.historicals[0],
        dataclasses.replace(bank.historicals[1], stockholders_equity=None),
    )
    with pytest.raises(ValueError, match="fondos propios de 2025.*fcfe"):
        _value(dataclasses.replace(bank, historicals=years), market_inputs)


def test_error_si_fondos_propios_no_positivos(bank: Company, market_inputs: MarketInputs) -> None:
    years = (bank.historicals[0], dataclasses.replace(bank.historicals[1], stockholders_equity=0.0))
    with pytest.raises(ValueError, match="positivos"):
        _value(dataclasses.replace(bank, historicals=years), market_inputs)


def test_error_si_el_valor_no_es_positivo(bank: Company, market_inputs: MarketInputs) -> None:
    # Pérdidas: NI negativo → FCFE y valor negativos.
    years = tuple(dataclasses.replace(h, net_income=-h.net_income) for h in bank.historicals)
    with pytest.raises(ValueError, match="equity_value"):
        _value(dataclasses.replace(bank, historicals=years), market_inputs)


def test_run_valuation_elige_el_modelo(
    bank: Company, company: Company, market_inputs: MarketInputs
) -> None:
    a = Assumptions(G, projection_years=2)
    assert isinstance(run_valuation(bank, market_inputs, a, NOW), FcfeValuationResult)
    assert isinstance(run_valuation(company, market_inputs, a, NOW), ValuationResult)


def test_fcff_sobre_un_banco_falla_con_dato_ausente(
    bank: Company, market_inputs: MarketInputs
) -> None:
    forced = dataclasses.replace(
        bank, info=dataclasses.replace(bank.info, valuation_model=ValuationModel.FCFF)
    )
    with pytest.raises(ValueError, match="impuestos"):
        run_valuation(forced, market_inputs, Assumptions(G, projection_years=2), NOW)


def test_informe_fcfe(bank: Company, market_inputs: MarketInputs) -> None:
    md = render_report(bank, _value(bank, market_inputs, scenario_config=COST), scale=1.0, unit="€")
    for title in (
        "# Valoración DCF (FCFE): Banco Sintético S.A. (BANK)",
        "## 2. Coste de los fondos propios (Ke)",
        "## 3. Históricos y proyecciones",
        "### 4.1 Del FCFE al valor por acción",
        "### 4.2 Escenarios",
        "### 4.3 Sensibilidad del valor por acción (Ke × g terminal)",
    ):
        assert title in md
    assert "**9,00 %**" in md  # Ke
    assert "**13,80 €**" in md  # valor por acción del caso de referencia
    assert "| Modelo de valoración | fcfe |" in md
    assert "WACC \\ g" not in md and "Coste de la deuda (Kd)" not in md
    assert "Aviso de modelo" not in md  # FCFE es adecuado para un banco
