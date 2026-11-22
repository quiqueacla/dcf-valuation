"""Tasa de descuento forzada (WACC o Ke): precedencia argumento > fichero > calculada.

Casos calculados a mano (tolerancia relativa 1e-9):

- Banco sintético FCFE_FIN (ver test_fcfe_fin) con Ke forzado al 10 % y Gordon clásico:
  VT = 23,1 · 1,02 / (0,10 − 0,02) = 294,525;
  fondos propios = 21 / 1,1 + 23,1 / 1,21 + 294,525 / 1,21 = 19,0909 + 19,0909 + 243,4091
  = 281,5909… → 2,82 € por acción.
- Fixture FCFF con WACC forzado al 10 %: los factores de descuento son 1 / 1,1^k.
"""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf import cli
from dcf.company import Company
from dcf.data.market_inputs import load_market_inputs
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import BetaMode, BetaSettings, MarketInputs, MarketRate
from dcf.model.discount_rate import choose_discount_rate, rate_warnings
from dcf.reports.markdown import render_report
from dcf.reports.summary import summary_row
from dcf.settings import apply_overrides
from dcf.valuation import fcfe_fin, fcff_cfo
from dcf.valuation.run import run_valuation
from tests.test_cli_options import BASE
from tests.test_fcfe_fin import bank  # noqa: F401 (fixture)
from tests.test_market_inputs import VALID
from tests.test_report_cli import _files

REL = 1e-9
NOW = datetime(2026, 11, 21, tzinfo=UTC)
TEN = MarketRate(0.10, "prueba", NOW)
BANK_TV = 23.1 * 1.02 / (0.10 - 0.02)
BANK_EQUITY = 21 / 1.1 + 23.1 / 1.21 + BANK_TV / 1.21


# --- Elección de la tasa ---


def test_sin_override_usa_la_calculada() -> None:
    choice = choose_discount_rate("WACC", 0.08, None, None)
    assert (choice.value, choice.is_forced) == (0.08, False)
    assert rate_warnings(choice) == ()


def test_override_prevalece_y_conserva_la_calculada() -> None:
    choice = choose_discount_rate("WACC", 0.08, None, TEN)
    assert (choice.value, choice.calculated, choice.is_forced) == (0.10, 0.08, True)
    assert "forzada al 10,00 %" in rate_warnings(choice)[0]
    assert "calculado: 8,00 %" in choice.describe()


def test_override_sin_calculada_indica_el_motivo() -> None:
    choice = choose_discount_rate("Ke", None, "beta negativa", TEN)
    assert choice.value == 0.10 and "no calculable: beta negativa" in choice.describe()


def test_sin_override_ni_calculada_es_error() -> None:
    with pytest.raises(ValueError, match="beta negativa"):
        choose_discount_rate("Ke", None, "beta negativa", None)


def test_override_no_positivo_es_error() -> None:
    with pytest.raises(ValueError, match="positiva"):
        choose_discount_rate("WACC", 0.08, None, MarketRate(0.0, "x", NOW))


# --- FCFF ---


def test_fcff_con_wacc_forzado(company: Company, market_inputs: MarketInputs) -> None:
    r = fcff_cfo.value_company(company, market_inputs, Assumptions(0.02), NOW, rate_override=TEN)
    assert r.discount_rate.value == 0.10
    assert r.wacc is not None and r.wacc.wacc == pytest.approx(0.08125, rel=REL)  # informativo
    assert [p.discount_factor for p in r.projections] == pytest.approx(
        [1.1**-k for k in range(1, 6)], rel=REL
    )
    assert r.sensitivity.loc[0.10, 0.02] == pytest.approx(r.value_per_share, rel=REL)
    assert any("forzada al 10,00 %" in w for w in r.warnings)
    base = fcff_cfo.value_company(company, market_inputs, Assumptions(0.02), NOW)
    assert r.value_per_share < base.value_per_share  # WACC mayor → menor valor


def test_fcff_beta_negativa_con_override_es_aviso(
    company: Company, market_inputs: MarketInputs
) -> None:
    negative = dataclasses.replace(
        company, balance=dataclasses.replace(company.balance, beta=-0.181)
    )
    with pytest.raises(ValueError, match="negativa"):
        fcff_cfo.value_company(negative, market_inputs, Assumptions(0.02), NOW)
    r = fcff_cfo.value_company(negative, market_inputs, Assumptions(0.02), NOW, rate_override=TEN)
    assert r.wacc is None and r.discount_rate.calculation_error is not None
    md = render_report(negative, r)
    assert "Tasa de descuento forzada: WACC = 10,00 %" in md
    assert "no se pudo calcular" in md and "### 2.1" not in md


def test_rechaza_g_mayor_o_igual_que_la_tasa_forzada(
    company: Company, market_inputs: MarketInputs
) -> None:
    with pytest.raises(ValueError, match="WACC"):
        fcff_cfo.value_company(
            company,
            market_inputs,
            Assumptions(0.025),
            NOW,
            rate_override=MarketRate(0.02, "x", NOW),
        )


# --- FCFE ---


def test_fcfe_con_ke_forzado_calculado_a_mano(
    bank: Company,  # noqa: F811
    market_inputs: MarketInputs,
) -> None:
    r = fcfe_fin.value_company(bank, market_inputs, Assumptions(0.02, 2), NOW, rate_override=TEN)
    assert r.terminal_value == pytest.approx(BANK_TV, rel=REL)
    assert r.equity_value == pytest.approx(BANK_EQUITY, rel=REL)
    assert r.equity_value == pytest.approx(281.590909, rel=1e-6)
    assert r.value_per_share == pytest.approx(2.81590909, rel=1e-6)
    assert r.cost_of_equity is not None
    assert r.cost_of_equity.cost_of_equity == pytest.approx(0.09, rel=REL)  # informativo
    md = render_report(bank, r, scale=1.0, unit="€")
    assert "Tasa de descuento forzada: Ke = 10,00 %" in md and "Ke calculado: 9,00 %" in md


def test_fcfe_beta_negativa_con_override(
    bank: Company,  # noqa: F811
    market_inputs: MarketInputs,
) -> None:
    negative = dataclasses.replace(bank, balance=dataclasses.replace(bank.balance, beta=-0.2))
    r = fcfe_fin.value_company(
        negative, market_inputs, Assumptions(0.02, 2), NOW, rate_override=TEN
    )
    assert r.cost_of_equity is None
    assert r.equity_value == pytest.approx(BANK_EQUITY, rel=REL)


# --- Precedencia y configuración ---


def test_precedencia_argumento_fichero_calculada(
    company: Company, market_inputs: MarketInputs
) -> None:
    from_file = MarketRate(0.09, "fichero", NOW)
    m = dataclasses.replace(market_inputs, discount_rate_by_ticker={"TEST": from_file})
    a = Assumptions(0.02)
    assert run_valuation(company, market_inputs, a, NOW).discount_rate.value == pytest.approx(
        0.08125, rel=REL
    )
    assert run_valuation(company, m, a, NOW).discount_rate.value == 0.09
    assert run_valuation(company, m, a, NOW, argument_rate=TEN).discount_rate.value == 0.10


def test_la_tasa_del_fichero_solo_afecta_a_su_ticker(market_inputs: MarketInputs) -> None:
    m = dataclasses.replace(market_inputs, discount_rate_by_ticker={"REP.MC": TEN})
    assert m.discount_rate_for("rep.mc") == TEN
    assert m.discount_rate_for("ITX.MC") is None


def _load(tmp_path: Path, extra: str) -> MarketInputs:
    path = tmp_path / "m.toml"
    path.write_text(VALID + extra, encoding="utf-8")
    return load_market_inputs(path)


def test_carga_discount_rate_por_ticker(tmp_path: Path) -> None:
    m = _load(
        tmp_path, '[discount_rate."REP.MC"]\nvalue = 0.075\nsource = "propia"\ndate = 2026-11-21\n'
    )
    rate = m.discount_rate_for("REP.MC")
    assert rate is not None and rate.value == 0.075 and rate.source == "propia"


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        ('[discount_rate]\nvalue = 0.08\nsource = "x"\ndate = 2026-11-21\n', "por ticker"),
        ('[discount_rate."X"]\nvalue = 0.08\n', "faltan las claves"),
        ('[discount_rate."X"]\nvalue = 0\nsource = "x"\ndate = 2026-11-21\n', "positivo"),
        ('[discount_rate."X"]\nvalor = 1\n', "desconocidas"),
    ],
)
def test_discount_rate_invalido(tmp_path: Path, extra: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _load(tmp_path, extra)


def test_set_rate() -> None:
    assert apply_overrides(BASE, ["rate=8%"]).discount_rate == pytest.approx(0.08)
    assert apply_overrides(BASE, ["discount_rate=0.075"]).discount_rate == pytest.approx(0.075)
    assert BASE.discount_rate is None
    with pytest.raises(ValueError, match="positiva"):
        apply_overrides(BASE, ["rate=0"])


def test_cli_set_rate(tmp_path: Path) -> None:
    assert cli.main([*_files(tmp_path), "--set", "rate=10%"], now=NOW) == 0
    md = next((tmp_path / "out").glob("SYN_*.md")).read_text(encoding="utf-8")
    assert "Tasa de descuento forzada: WACC = 10,00 %** (argumento --set rate" in md


def test_resumen_indica_tasa_forzada(company: Company, market_inputs: MarketInputs) -> None:
    r = fcff_cfo.value_company(company, market_inputs, Assumptions(0.02), NOW, rate_override=TEN)
    row = summary_row(company, r, "x")
    assert row.discount_rate == 0.10 and row.rate_sources is not None
    assert row.rate_sources.startswith("forzado (prueba, 2026-11-21); calculado 8,13 %: rf")


def test_beta_settings_siguen_igual(market_inputs: MarketInputs) -> None:
    # La tasa forzada no altera la configuración de la beta.
    assert market_inputs.beta_settings_for("TEST") == BetaSettings(BetaMode.YAHOO)
