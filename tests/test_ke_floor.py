"""Beta bottom-up, ajuste de Blume, suelo de Ke por riesgo país y exclusión de escenarios.

Casos calculados a mano sobre el fixture sintético (conftest: deuda 200, 100 acciones a 10 €
→ E = 1000, D/E = 0,2; t = 25 %; beta de Yahoo 1,2; rf 3 %, PRM 5 %). Tolerancia 1e-9.

- Bottom-up con βu = 1: β = 1 · (1 + 0,75 · 0,2) = 1,15; Ke = 3 % + 1,15 · 5 % = 8,75 %.
- Blume: β = 0,67 · 1,2 + 0,33 = 1,134; Ke = 3 % + 1,134 · 5 % = 8,67 %.
- Suelo: rf + PRM + prima país = 3 % + 5 % + 0 % = 8 %; con prima 1 %, 9 %. Con β = 0,5 el
  CAPM da 5,5 % y Ke = suelo.
"""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf.company import Company, TerminalMethod, ValuationModel
from dcf.data.market_inputs import load_market_inputs
from dcf.model.assumptions import Assumptions
from dcf.model.checks import WarningThresholds
from dcf.model.cost_of_equity import (
    BetaMode,
    BetaSettings,
    MarketInputs,
    MarketRate,
    compute_cost_of_equity,
)
from dcf.model.terminal_methods import TerminalOptions
from dcf.reports.markdown import render_report
from dcf.settings import load_thresholds
from dcf.valuation import fcff
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode, ScenarioName, growth_gap_error
from tests.test_fcff import industrial  # noqa: F401 (fixture)
from tests.test_market_inputs import VALID

REL = 1e-9
NOW = datetime(2026, 11, 24, tzinfo=UTC)


def _rate(value: float) -> MarketRate:
    return MarketRate(value, "prueba", NOW)


# Compañía del fixture con claves de clasificación, beta y modelo.
def _company(
    company: Company,
    beta: float | None = 1.2,
    model: ValuationModel = ValuationModel.FCFF_CFO,
) -> Company:
    info = dataclasses.replace(
        company.info,
        industry_key="engineering-construction",
        sector_key="industrials",
        valuation_model=model,
    )
    balance = dataclasses.replace(company.balance, beta=beta)
    return dataclasses.replace(company, info=info, balance=balance)


# MarketInputs del fixture en modo bottom-up, con betas sectoriales opcionales.
def _bottom_up(market_inputs: MarketInputs, **sector: float) -> MarketInputs:
    return dataclasses.replace(
        market_inputs,
        beta=BetaSettings(BetaMode.BOTTOM_UP),
        sector_beta_by_key={k.replace("_", "-"): _rate(v) for k, v in sector.items()},
    )


# --- Beta bottom-up y Blume -------------------------------------------------------------


def test_bottom_up_reapalanca_la_beta_sectorial(
    company: Company, market_inputs: MarketInputs
) -> None:
    ke = compute_cost_of_equity(
        _company(company), _bottom_up(market_inputs, engineering_construction=1.0)
    )
    assert ke.beta_choice.value == pytest.approx(1.15, rel=REL)
    assert ke.beta_choice.unlevered_beta == 1.0
    assert ke.beta_choice.mode is BetaMode.BOTTOM_UP and ke.beta_choice.reason is None
    assert ke.cost_of_equity == pytest.approx(0.0875, rel=REL)
    assert ke.capm == pytest.approx(0.0875, rel=REL) and not ke.floor_applied


def test_bottom_up_prefiere_la_industria_al_sector(
    company: Company, market_inputs: MarketInputs
) -> None:
    m = _bottom_up(market_inputs, industrials=2.0, engineering_construction=1.0)
    assert compute_cost_of_equity(_company(company), m).beta_choice.unlevered_beta == 1.0
    m = _bottom_up(market_inputs, industrials=2.0)
    assert compute_cost_of_equity(_company(company), m).beta_choice.value == pytest.approx(2.3)


def test_bottom_up_en_financieras_no_reapalanca(
    company: Company, market_inputs: MarketInputs
) -> None:
    c = _company(company, model=ValuationModel.FCFE_FIN)
    ke = compute_cost_of_equity(c, _bottom_up(market_inputs, engineering_construction=1.1))
    assert ke.beta_choice.value == pytest.approx(1.1, rel=REL)
    assert "sin reapalancar" in ke.beta_choice.source


def test_sin_beta_sectorial_usa_blume(company: Company, market_inputs: MarketInputs) -> None:
    ke = compute_cost_of_equity(_company(company), _bottom_up(market_inputs))
    assert ke.beta_choice.value == pytest.approx(0.67 * 1.2 + 0.33, rel=REL)
    assert ke.cost_of_equity == pytest.approx(0.03 + 1.134 * 0.05, rel=REL)
    assert ke.beta_choice.reason is not None and "sin beta sectorial" in ke.beta_choice.reason
    assert any("Blume" in w for w in ke.warnings)


def test_por_defecto_es_bottom_up(company: Company, market_inputs: MarketInputs) -> None:
    m = dataclasses.replace(market_inputs, beta=BetaSettings())
    assert compute_cost_of_equity(_company(company), m).beta_choice.mode is BetaMode.BOTTOM_UP


def test_blume_sin_beta_valida_usa_la_del_fichero_o_falla(
    company: Company, market_inputs: MarketInputs
) -> None:
    c = _company(company, beta=-0.181)
    with pytest.raises(ValueError, match="sector_beta"):
        compute_cost_of_equity(c, _bottom_up(market_inputs))
    m = dataclasses.replace(market_inputs, beta=BetaSettings(BetaMode.BOTTOM_UP, _rate(1.1)))
    ke = compute_cost_of_equity(c, m)
    assert ke.beta_choice.value == 1.1
    assert ke.beta_choice.reason is not None and "negativa" in ke.beta_choice.reason


# --- Suelo de Ke ------------------------------------------------------------------------


def test_suelo_de_ke(company: Company, market_inputs: MarketInputs) -> None:
    c = _company(company, beta=0.5)
    ke = compute_cost_of_equity(c, market_inputs)  # modo yahoo del fixture
    assert ke.capm == pytest.approx(0.055, rel=REL)
    assert ke.floor is not None and ke.floor.value == pytest.approx(0.08, rel=REL)
    assert ke.cost_of_equity == pytest.approx(0.08, rel=REL) and ke.floor_applied
    assert any("suelo" in w for w in ke.warnings)
    m = dataclasses.replace(market_inputs, country_risk_premium_by_country={"spain": _rate(0.01)})
    assert compute_cost_of_equity(c, m).cost_of_equity == pytest.approx(0.09, rel=REL)


def test_suelo_entra_en_el_wacc(company: Company, market_inputs: MarketInputs) -> None:
    from dcf.model.wacc import compute_wacc

    w = compute_wacc(_company(company, beta=0.5), market_inputs)
    # WACC = 5/6 · 8 % + 1/6 · 5 % · 0,75
    assert w.wacc == pytest.approx(5 / 6 * 0.08 + 1 / 6 * 0.05 * 0.75, rel=REL)
    assert w.equity is not None and w.equity.floor_applied


@pytest.mark.parametrize(("country", "match"), [(None, "no publica el país"), ("Italy", "Italy")])
def test_suelo_falla_sin_prima_pais(
    company: Company, market_inputs: MarketInputs, country: str | None, match: str
) -> None:
    info = dataclasses.replace(company.info, country=country)
    with pytest.raises(ValueError, match=match):
        compute_cost_of_equity(dataclasses.replace(company, info=info), market_inputs)


def test_informe_muestra_suelo_y_beta(company: Company, market_inputs: MarketInputs) -> None:
    from dcf.valuation.fcff_cfo import value_company

    c = _company(company, beta=0.5)
    md = render_report(c, value_company(c, market_inputs, Assumptions(0.02), NOW), scale=1.0)
    assert "| Beta publicada por la fuente | 0,500 |" in md
    assert "| Ke por CAPM = rf + β · PRM | 5,50 % | CAPM |" in md
    assert "| Suelo de Ke = rf + PRM + prima país | 8,00 % |" in md
    assert "| **Coste del capital Ke = máx(CAPM, suelo)** | **8,00 %** | Suelo aplicado |" in md


def test_fichero_de_mercado_con_betas_sectoriales_y_prima_pais(tmp_path: Path) -> None:
    path = tmp_path / "m.toml"
    path.write_text(
        VALID + '\n[sector_beta."Engineering-Construction"]\nvalue = 0.9\nsource = "Damodaran"\n'
        "date = 2026-01-05\n",
        encoding="utf-8",
    )
    m = load_market_inputs(path)
    found = m.sector_beta_for("engineering-construction", None)
    assert found is not None and found[1].value == 0.9
    crp = m.country_risk_premium_for("SPAIN")
    assert crp is not None and crp.value == 0.0
    assert m.beta_settings_for("X").mode is BetaMode.BOTTOM_UP
    path.write_text(
        VALID + '\n[sector_beta."x"]\nvalue = -0.1\nsource = "x"\ndate = 2026-01-05\n', "utf-8"
    )
    with pytest.raises(ValueError, match="negativo"):
        load_market_inputs(path)


# --- Exclusión de escenarios por g implícito ---------------------------------------------


def test_growth_gap_error() -> None:
    # VT 1600 sobre CF_N 100 al 10 %: g implícito = 60 / 1700 = 3,53 %.
    assert growth_gap_error(ScenarioName.BEARISH, 1600, 100, 0.10, 0.02, 0.01) is not None
    assert growth_gap_error(ScenarioName.NEUTRAL, 1600, 100, 0.10, 0.02, 0.01) is None
    assert growth_gap_error(ScenarioName.BULLISH, 1600, 100, 0.10, 0.03, 0.01) is None
    assert growth_gap_error(ScenarioName.BULLISH, 1600, 100, 0.10, 0.02, None) is None


def test_escenarios_con_g_implicito_incoherente_se_excluyen(
    industrial: Company,  # noqa: F811
    market_inputs: MarketInputs,
) -> None:
    # Múltiplo 8 sobre EBITDA 332,75 (VT 2662) y FCFF_N 147,62. g implícito
    # = (r · 2662 − 147,62) / 2809,62: bajista (r 11 %, g 1,5 %) 5,17 % → 3,67 puntos,
    # excluido; alcista (r 9 %, g 2,5 %) 3,27 % → 0,77 puntos, válido.
    options = TerminalOptions(TerminalMethod.MULTIPLE, multiple=_rate(8.0))
    config = ScenarioConfig(frozenset({ScenarioMode.COST}), 0.01, 0.005)
    r = fcff.value_company(
        industrial, market_inputs, Assumptions(0.02, 2), NOW, config, _rate(0.10), options
    )
    s = {x.name: x for x in r.scenarios}
    bear = s[ScenarioName.BEARISH]
    assert bear.value_per_share is None and bear.error is not None
    assert "escenario excluido" in bear.error
    assert s[ScenarioName.BULLISH].value_per_share is not None
    assert s[ScenarioName.NEUTRAL].value_per_share == pytest.approx(r.value_per_share, rel=REL)
    assert any("umbral de exclusión" in w for w in r.checks)
    loose = TerminalOptions(
        TerminalMethod.MULTIPLE,
        multiple=_rate(8.0),
        thresholds=WarningThresholds(scenario_growth_gap=0.05),
    )
    r = fcff.value_company(
        industrial, market_inputs, Assumptions(0.02, 2), NOW, config, _rate(0.10), loose
    )
    assert all(x.value_per_share is not None for x in r.scenarios)


def test_umbral_de_exclusion_en_el_fichero(tmp_path: Path) -> None:
    path = tmp_path / "t.toml"
    path.write_text("[warnings]\nscenario_growth_gap = 0.02\n", encoding="utf-8")
    assert load_thresholds(path).scenario_growth_gap == 0.02
    assert load_thresholds(Path("config/thresholds.toml")).scenario_growth_gap == 0.01
