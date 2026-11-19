"""Selección de la beta: modos yahoo, fichero y yahoo-fichero (sin red).

Caso de referencia (fixture sintético, ver test_wacc): con β = 1,2, Ke = 9 % y
WACC = 8,125 %. Con β del fichero = 0,8: Ke = 3 % + 0,8 × 5 % = 7 % y
WACC = 5/6 × 7 % + 1/6 × 5 % × 0,75 = 5,8333… % + 0,625 % = 6,4583… %.
"""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf.company import Company
from dcf.data.market_inputs import load_market_inputs
from dcf.model.cost_of_equity import BetaMode, BetaSettings, MarketInputs, MarketRate, resolve_beta
from dcf.model.wacc import compute_wacc
from tests.test_market_inputs import VALID

REL = 1e-9
NOW = datetime(2026, 11, 18, tzinfo=UTC)
MANUAL = MarketRate(0.8, "Damodaran, sector", NOW)
WACC_MANUAL = 5 / 6 * 0.07 + 1 / 6 * 0.05 * 0.75


# Compañía del fixture con otra beta de la fuente.
def _with_beta(company: Company, beta: float | None) -> Company:
    return dataclasses.replace(company, balance=dataclasses.replace(company.balance, beta=beta))


# MarketInputs del fixture con una configuración de beta general.
def _inputs(market_inputs: MarketInputs, mode: BetaMode, value: MarketRate | None) -> MarketInputs:
    return dataclasses.replace(market_inputs, beta=BetaSettings(mode, value))


def test_por_defecto_es_yahoo(company: Company, market_inputs: MarketInputs) -> None:
    w = compute_wacc(company, market_inputs)
    assert w.beta == 1.2
    assert w.beta_choice.mode is BetaMode.YAHOO
    assert w.beta_choice.reason is None


@pytest.mark.parametrize(("beta", "motivo"), [(None, "no publica"), (-0.181, "negativa")])
def test_yahoo_falla_sin_beta_o_negativa(
    company: Company, market_inputs: MarketInputs, beta: float | None, motivo: str
) -> None:
    with pytest.raises(ValueError, match=motivo):
        compute_wacc(_with_beta(company, beta), market_inputs)


def test_fichero_sobrescribe_yahoo(company: Company, market_inputs: MarketInputs) -> None:
    w = compute_wacc(company, _inputs(market_inputs, BetaMode.FILE, MANUAL))
    assert w.beta == 0.8
    assert w.beta_choice.source == "Damodaran, sector"
    assert w.beta_choice.source_beta == 1.2
    assert w.cost_of_equity == pytest.approx(0.07, rel=REL)
    assert w.wacc == pytest.approx(WACC_MANUAL, rel=REL)
    assert w.warnings == ()


def test_fichero_sin_valor_es_error(company: Company, market_inputs: MarketInputs) -> None:
    with pytest.raises(ValueError, match="fichero"):
        compute_wacc(company, _inputs(market_inputs, BetaMode.FILE, None))


def test_yahoo_fichero_usa_yahoo_si_es_valida(
    company: Company, market_inputs: MarketInputs
) -> None:
    w = compute_wacc(company, _inputs(market_inputs, BetaMode.YAHOO_FILE, MANUAL))
    assert w.beta == 1.2
    assert w.beta_choice.reason is None


@pytest.mark.parametrize(("beta", "motivo"), [(None, "no publica"), (-0.181, "negativa")])
def test_yahoo_fichero_recurre_al_fichero_e_indica_motivo(
    company: Company, market_inputs: MarketInputs, beta: float | None, motivo: str
) -> None:
    w = compute_wacc(_with_beta(company, beta), _inputs(market_inputs, BetaMode.YAHOO_FILE, MANUAL))
    assert w.beta == 0.8
    assert w.beta_choice.reason is not None and motivo in w.beta_choice.reason
    assert any(motivo in m for m in w.warnings)
    assert w.wacc == pytest.approx(WACC_MANUAL, rel=REL)


def test_yahoo_fichero_sin_respaldo_es_error(company: Company, market_inputs: MarketInputs) -> None:
    with pytest.raises(ValueError, match="negativa.*no hay beta de respaldo"):
        compute_wacc(_with_beta(company, -0.2), _inputs(market_inputs, BetaMode.YAHOO_FILE, None))


def test_beta_cero_de_yahoo_es_valida() -> None:
    choice = resolve_beta("X", 0.0, BetaSettings(BetaMode.YAHOO), "Yahoo", NOW)
    assert choice.value == 0.0


def test_beta_del_fichero_no_puede_ser_negativa() -> None:
    with pytest.raises(ValueError, match="negativa"):
        BetaSettings(BetaMode.FILE, MarketRate(-0.1, "x", NOW))


def test_config_por_ticker_prevalece_sobre_la_general(market_inputs: MarketInputs) -> None:
    other = MarketRate(1.1, "general", NOW)
    m = dataclasses.replace(
        market_inputs,
        beta=BetaSettings(BetaMode.YAHOO_FILE, other),
        beta_by_ticker={"REP.MC": BetaSettings(BetaMode.FILE, MANUAL)},
    )
    assert m.beta_settings_for("rep.mc") == BetaSettings(BetaMode.FILE, MANUAL)
    assert m.beta_settings_for("AAPL") == BetaSettings(BetaMode.YAHOO_FILE, other)


def test_ticker_hereda_modo_general(market_inputs: MarketInputs) -> None:
    m = dataclasses.replace(
        market_inputs,
        beta=BetaSettings(BetaMode.YAHOO_FILE),
        beta_by_ticker={"REP.MC": BetaSettings(value=MANUAL)},
    )
    assert m.beta_settings_for("REP.MC") == BetaSettings(BetaMode.YAHOO_FILE, MANUAL)


# --- Lectura del TOML ---

BETA_TOML = """
[beta]
mode = "yahoo-fichero"

[beta."REP.MC"]
value = 0.9
source = "Damodaran, Oil/Gas (Integrated)"
date = 2026-01-05

[beta."AAPL"]
mode = "fichero"
value = 1.1
source = "propia"
date = 2026-11-01
"""


def _load(tmp_path: Path, extra: str) -> MarketInputs:
    path = tmp_path / "m.toml"
    path.write_text(VALID + extra, encoding="utf-8")
    return load_market_inputs(path)


def test_sin_seccion_beta_es_modo_yahoo(tmp_path: Path) -> None:
    m = _load(tmp_path, "")
    assert m.beta_settings_for("ITX.MC") == BetaSettings(BetaMode.YAHOO)


def test_carga_seccion_beta(tmp_path: Path) -> None:
    m = _load(tmp_path, BETA_TOML)
    rep = m.beta_settings_for("REP.MC")
    assert rep.mode is BetaMode.YAHOO_FILE
    assert rep.value is not None and rep.value.value == 0.9
    assert rep.value.date == datetime(2026, 1, 5, tzinfo=UTC)
    assert m.beta_settings_for("AAPL").mode is BetaMode.FILE
    assert m.beta_settings_for("ITX.MC") == BetaSettings(BetaMode.YAHOO_FILE)


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        ('[beta]\nmode = "manual"\n', "mode"),
        ("[beta]\nvalor = 1\n", "desconocidas"),
        ('[beta."REP.MC"]\nvalue = 0.9\n', "faltan las claves"),
        ('[beta."REP.MC"]\nvalue = -0.5\nsource = "x"\ndate = 2026-01-01\n', "negativa"),
    ],
)
def test_seccion_beta_invalida(tmp_path: Path, extra: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _load(tmp_path, extra)


def test_informe_indica_origen_y_motivo(company: Company, market_inputs: MarketInputs) -> None:
    from dcf.model.assumptions import Assumptions
    from dcf.reports.markdown import render_report
    from dcf.valuation.fcff import value_company

    c = _with_beta(company, -0.181)
    m = _inputs(market_inputs, BetaMode.YAHOO_FILE, MANUAL)
    md = render_report(c, value_company(c, m, Assumptions(terminal_growth=0.02), NOW), scale=1.0)
    assert "modo yahoo-fichero" in md
    assert "se usa la del fichero porque la beta de" in md and "negativa" in md
    assert "Damodaran, sector" in md
