"""Métodos de valor terminal, comprobaciones de consistencia, umbrales y FCFE 1.2 (sin red).

Casos calculados a mano (tolerancia relativa 1e-9):

- Base: CF_N = 100, beneficio_N = 150, métrica_N = 200, tasa 10 %, g 2 %, rf 3 %.
- Gordon: VT = 100 · 1,02 / 0,08 = 1275 (g implícito = g).
- Value driver con RONIC 10 %: VT = 150 · 1,02 · (1 − 0,02 / 0,10) / 0,08 = 1530;
  g implícito = (0,1 · 1530 − 100) / (1530 + 100) = 53 / 1630 = 3,25 % → aviso (> 0,75 puntos).
- Múltiplo 8: VT = 8 · 200 = 1600; g implícito = 60 / 1700 = 3,53 %.
- FCFE 1.2 sobre la industrial sintética de test_fcff (deuda 200, caja 100, 100 acciones a
  10 € → E = 1000, D/(D+E) = 1/6; Kd = 10 / 200 = 5 %; t 25 %; DN_0 = 100; Ke forzado 10 %):
  - 2026e: intereses 5; reinversión 96,8 − 60,5 + 11 = 47,3; ΔDN = 7,8833…;
    FCFE = 134,2 − 3,75 + 7,8833… = 138,3333…
  - 2027e: DN 107,8833…; intereses 5,394166…; reinversión 106,48 − 66,55 + 12,1 = 52,03;
    ΔDN = 8,671666…; FCFE = 147,62 − 4,045625 + 8,671666… = 152,246041…
  - Gordon: VT = 152,246041… · 1,02 / 0,08; fondos propios = Σ FCFE / 1,1^k + VT / 1,21.
"""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf import cli
from dcf.company import Company, CompanyType, TerminalMethod, ValuationModel
from dcf.data.company_types import load_company_type_rules
from dcf.data.market_inputs import load_market_inputs
from dcf.model.assumptions import Assumptions
from dcf.model.checks import WarningThresholds, historical_flow_warnings
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.returns import historical_roe, historical_roic
from dcf.model.terminal_methods import (
    TerminalBasis,
    TerminalOptions,
    implied_growth,
    pick_override,
    terminal_value,
)
from dcf.reports.markdown import render_report
from dcf.settings import apply_overrides, load_thresholds
from dcf.valuation import fcfe
from dcf.valuation.run import TerminalOverrides, terminal_options
from tests.test_cli_options import BASE
from tests.test_fcff import industrial  # noqa: F401 (fixture)
from tests.test_market_inputs import VALID
from tests.test_report_cli import _files

REL = 1e-9
NOW = datetime(2026, 11, 21, tzinfo=UTC)
TEN = MarketRate(0.10, "prueba", NOW)


def _rate(value: float) -> MarketRate:
    return MarketRate(value, "prueba", NOW)


def _basis(ronic: float | None = 0.10, metric: float | None = 200.0) -> TerminalBasis:
    return TerminalBasis(
        last_flow=100.0,
        profit_last=150.0,
        profit_name="NOPAT",
        metric_last=metric,
        metric_name="EBITDA",
        return_name="RONIC",
        ronic=None if ronic is None else _rate(ronic),
    )


def _tv(method: TerminalMethod, basis: TerminalBasis, **kw: object) -> float:
    multiple = kw.get("multiple")
    assert multiple is None or isinstance(multiple, MarketRate)
    options = TerminalOptions(method, multiple=multiple)
    return terminal_value(options, basis, 0.10, 0.02, 0.03, "WACC").value


# --- Métodos de VT ---------------------------------------------------------------------


def test_gordon_clasico() -> None:
    r = terminal_value(TerminalOptions(TerminalMethod.GORDON), _basis(), 0.10, 0.02, 0.03, "WACC")
    assert r.value == pytest.approx(1275.0, rel=REL)
    assert r.next_flow == pytest.approx(102.0, rel=REL)
    assert r.implied_growth == pytest.approx(0.02, rel=REL)
    assert r.implied_multiple == pytest.approx(1275.0 / 200.0, rel=REL)
    assert r.warnings == ()  # en Gordon no se compara g implícito


def test_value_driver() -> None:
    options = TerminalOptions(TerminalMethod.VALUE_DRIVER)
    r = terminal_value(options, _basis(), 0.10, 0.02, 0.03, "WACC")
    assert r.value == pytest.approx(1530.0, rel=REL)
    assert r.implied_growth == pytest.approx(53 / 1630, rel=REL)
    assert len(r.warnings) == 1 and "g implícito" in r.warnings[0]


def test_value_driver_con_ronic_igual_a_la_tasa_no_crea_valor() -> None:
    # RONIC = WACC: VT = beneficio_N · (1 + g) / WACC, sin importar g.
    r = terminal_value(
        TerminalOptions(TerminalMethod.VALUE_DRIVER), _basis(0.10), 0.10, 0.02, 0.03, "WACC"
    )
    assert r.value == pytest.approx(150 * 1.02 / 0.10, rel=REL)


def test_multiplo_de_salida() -> None:
    options = TerminalOptions(TerminalMethod.MULTIPLE, multiple=_rate(8.0))
    r = terminal_value(options, _basis(), 0.10, 0.02, 0.03, "WACC")
    assert r.value == pytest.approx(1600.0, rel=REL)
    assert r.next_flow is None
    assert r.implied_growth == pytest.approx(60 / 1700, rel=REL)
    assert r.implied_multiple == pytest.approx(8.0, rel=REL)
    assert r.basis.multiple is not None and r.basis.multiple.value == 8.0
    assert any("revisa el múltiplo" in w for w in r.warnings)


def test_multiplo_coherente_sin_aviso() -> None:
    # M = 1275 / 200 reproduce el Gordon: g implícito = g, sin aviso.
    options = TerminalOptions(TerminalMethod.MULTIPLE, multiple=_rate(1275 / 200))
    r = terminal_value(options, _basis(), 0.10, 0.02, 0.03, "WACC")
    assert r.implied_growth == pytest.approx(0.02, rel=1e-9) and r.warnings == ()


def test_aviso_ronic_muy_alto() -> None:
    options = TerminalOptions(TerminalMethod.VALUE_DRIVER)
    r = terminal_value(options, _basis(0.25), 0.10, 0.02, 0.03, "WACC")
    assert any("RONIC 25.00% > 2 × WACC" in w for w in r.warnings)
    loose = TerminalOptions(
        TerminalMethod.VALUE_DRIVER, thresholds=WarningThresholds(ronic_to_rate=3)
    )
    assert not any(
        "RONIC" in w and "×" in w
        for w in terminal_value(loose, _basis(0.25), 0.10, 0.02, 0.03, "WACC").warnings
    )


@pytest.mark.parametrize(
    ("method", "basis", "match"),
    [
        (TerminalMethod.VALUE_DRIVER, _basis(ronic=None), "Falta el RONIC"),
        (TerminalMethod.VALUE_DRIVER, _basis(ronic=-0.05), "positivo"),
        (TerminalMethod.MULTIPLE, _basis(), "Falta el múltiplo"),
        (TerminalMethod.GORDON, _basis(), "g"),
    ],
)
def test_errores(method: TerminalMethod, basis: TerminalBasis, match: str) -> None:
    g = 0.12 if method is TerminalMethod.GORDON else 0.02  # g ≥ tasa
    with pytest.raises(ValueError, match=match):
        terminal_value(TerminalOptions(method), basis, 0.10, g, 0.15, "WACC")


def test_multiplo_sin_metrica() -> None:
    options = TerminalOptions(TerminalMethod.MULTIPLE, multiple=_rate(8.0))
    with pytest.raises(ValueError, match="EBITDA"):
        terminal_value(options, _basis(metric=None), 0.10, 0.02, 0.03, "WACC")


def test_g_implicito_y_precedencia() -> None:
    assert implied_growth(1275.0, 100.0, 0.10) == pytest.approx(0.02, rel=REL)
    a, f, c = _rate(1.0), _rate(2.0), _rate(3.0)
    assert pick_override(a, f, c) is a
    assert pick_override(None, f, c) is f
    assert pick_override(None, None, c) is c
    assert pick_override(None, None, None) is None


# --- Comprobaciones de los flujos históricos -------------------------------------------


def test_avisos_de_flujos_historicos() -> None:
    t = WarningThresholds()
    # Media de los anteriores 100; último 140 → +40 % > 33 %.
    w = historical_flow_warnings("FCFF", {2022: 100e6, 2023: 100e6, 2024: 140e6}, t)
    assert len(w) == 1 and "40% por encima" in w[0] and "sobrevaloración" in w[0]
    # Último 130 → +30 %: sin aviso.
    assert historical_flow_warnings("FCFF", {2023: 100e6, 2024: 130e6}, t) == ()
    # Negativos y último por debajo.
    w = historical_flow_warnings("FCFE", {2023: -10e6, 2024: 100e6, 2025: 10e6}, t)
    assert "FCFE histórico negativo en 2023 (-10.0 M€)" in w[0]
    assert "por debajo" in w[1] and "infravaloración" in w[1]
    # Umbral más amplio: sin aviso de desviación.
    assert (
        historical_flow_warnings("FCFF", {2023: 100e6, 2024: 140e6}, WarningThresholds(0.5)) == ()
    )


def test_umbrales_invalidos() -> None:
    with pytest.raises(ValueError, match="positivo"):
        WarningThresholds(last_flow_deviation=0)
    with pytest.raises(ValueError, match="positivo"):
        WarningThresholds(ronic_to_rate=float("nan"))


def test_fichero_de_umbrales(tmp_path: Path) -> None:
    assert load_thresholds(tmp_path / "no.toml") == WarningThresholds()
    path = tmp_path / "t.toml"
    path.write_text("[warnings]\nlast_flow_deviation = 0.5\n", encoding="utf-8")
    t = load_thresholds(path)
    assert t.last_flow_deviation == 0.5 and t.implied_growth_gap == 0.0075
    assert load_thresholds(Path("config/thresholds.toml")) == WarningThresholds()
    for text, match in [
        ("[avisos]\n", "secciones desconocidas"),
        ("[warnings]\nfoo = 1\n", "claves desconocidas"),
        ("[warnings]\nronic_to_rate = 'x'\n", "número"),
        ("[warnings]\nronic_to_rate = -1\n", "positivo"),
    ]:
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=match):
            load_thresholds(path)


# --- ROIC y ROE históricos -------------------------------------------------------------


def test_roic_y_roe_historicos(industrial: Company) -> None:  # noqa: F811
    years = tuple(
        dataclasses.replace(h, stockholders_equity=fp, cash=100.0)
        for h, fp in zip(industrial.historicals, (650.0, 700.0), strict=True)
    )
    company = dataclasses.replace(industrial, historicals=years)
    roic = historical_roic(company, 0.25)
    assert roic.by_year == {2025: pytest.approx(220 * 0.75 / 750, rel=REL)}
    roe = historical_roe(company)
    assert roe.by_year[2025] == pytest.approx(company.historicals[1].net_income / 650, rel=REL)
    rate = roic.as_rate(NOW)
    assert rate is not None and "2025" in rate.source
    assert historical_roic(industrial, 0.25).as_rate(NOW) is None  # sin fondos propios


# --- FCFE 1.2 --------------------------------------------------------------------------


def _fcfe_reference() -> tuple[float, float, float]:
    dr = 200 / 1200
    fcfe_1 = 134.2 - 5 * 0.75 + dr * 47.3
    nd_1 = 100 + dr * 47.3
    fcfe_2 = 147.62 - 0.05 * nd_1 * 0.75 + dr * 52.03
    tv = fcfe_2 * 1.02 / 0.08
    return fcfe_1, fcfe_2, fcfe_1 / 1.1 + fcfe_2 / 1.21 + tv / 1.21


def test_fcfe_industrial_calculado_a_mano(
    industrial: Company,  # noqa: F811
    market_inputs: MarketInputs,
) -> None:
    fcfe_1, fcfe_2, equity = _fcfe_reference()
    assert fcfe_1 == pytest.approx(138.333333, rel=1e-6)
    assert fcfe_2 == pytest.approx(152.246042, rel=1e-6)
    r = fcfe.value_company(industrial, market_inputs, Assumptions(0.02, 2), NOW, None, TEN)
    flows = [p.flow for p in r.projections]
    assert [f.fcfe for f in flows] == pytest.approx([fcfe_1, fcfe_2], rel=REL)
    assert r.leverage.debt_ratio == pytest.approx(1 / 6, rel=REL)
    assert r.leverage.cost_of_debt == pytest.approx(0.05, rel=REL)
    assert flows[1].net_income == pytest.approx((266.2 - 0.05 * flows[1].net_debt_begin) * 0.75)
    assert r.equity_value == pytest.approx(equity, rel=REL)
    assert r.value_per_share == pytest.approx(equity / 100, rel=REL)
    md = render_report(industrial, r, scale=1.0, unit="€")
    assert "# Valoración DCF (FCFE): Industrial Sintética S.A. (IND)" in md
    assert "FCFE = FCFF − Int·(1−t) + ΔDeuda neta" in md


def test_fcfe_sin_deuda_es_el_fcff(industrial: Company, market_inputs: MarketInputs) -> None:  # noqa: F811
    # Sin deuda ni caja: FCFE = FCFF y el valor coincide con el FCFF al mismo tipo.
    balance = dataclasses.replace(industrial.balance, total_debt=0.0, cash=0.0)
    company = dataclasses.replace(industrial, balance=balance)
    r = fcfe.value_company(company, market_inputs, Assumptions(0.02, 2), NOW, None, TEN)
    assert [p.flow.fcfe for p in r.projections] == pytest.approx([134.2, 147.62], rel=REL)


# --- Configuración: company_types, market_inputs y --set -------------------------------


def test_tabla_con_default_y_vt(tmp_path: Path) -> None:
    path = tmp_path / "types.toml"
    path.write_text(
        '[default]\nmodel = "fcff_cfo"\nvt = "vt_mult"\n\n'
        '[banco]\nmodel = "fcfe_fin"\nvt = "gordon"\nindustries = ["banks-regional"]\n',
        encoding="utf-8",
    )
    rules = load_company_type_rules(path)
    assert rules.model_for(CompanyType.INDUSTRIAL) is ValuationModel.FCFF_CFO
    assert rules.terminal_for(CompanyType.INDUSTRIAL) is TerminalMethod.MULTIPLE
    assert rules.terminal_for(CompanyType.BANK) is TerminalMethod.GORDON
    for text, match in [
        ('[default]\nvt = "otro"\n', "no válido"),
        ('[default]\nindustries = ["x"]\n', "claves desconocidas"),
    ]:
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=match):
            load_company_type_rules(path)


def test_market_inputs_multiplo_y_ronic(tmp_path: Path) -> None:
    path = tmp_path / "m.toml"
    path.write_text(
        VALID
        + '\n[exit_multiple."IDR.MC"]\nvalue = 9\nsource = "comparables"\ndate = 2026-11-21\n'
        + '\n[ronic."idr.mc"]\nvalue = 0.12\nsource = "propia"\ndate = 2026-11-21\n',
        encoding="utf-8",
    )
    m = load_market_inputs(path)
    multiple, ronic = m.exit_multiple_for("IDR.MC"), m.ronic_for("IDR.MC")
    assert multiple is not None and multiple.value == 9 and multiple.source == "comparables"
    assert ronic is not None and ronic.value == 0.12
    assert m.exit_multiple_for("SAN.MC") is None and m.ronic_for("SAN.MC") is None
    path.write_text(VALID + '\n[ronic]\nvalue = 0.1\nsource = "x"\ndate = 2026-11-21\n', "utf-8")
    with pytest.raises(ValueError, match="por ticker"):
        load_market_inputs(path)


def test_precedencia_argumento_fichero(
    industrial: Company,  # noqa: F811
    market_inputs: MarketInputs,
) -> None:
    from_file = dataclasses.replace(
        market_inputs,
        exit_multiple_by_ticker={"IND": _rate(9.0)},
        ronic_by_ticker={"IND": _rate(0.12)},
    )
    o = terminal_options(industrial, from_file, TerminalOverrides())
    assert o.multiple is not None and o.multiple.value == 9.0
    assert o.ronic is not None and o.ronic.value == 0.12
    o = terminal_options(industrial, from_file, TerminalOverrides(_rate(7.0), _rate(0.15)))
    assert o.multiple is not None and o.multiple.value == 7.0
    assert o.ronic is not None and o.ronic.value == 0.15
    assert o.method is TerminalMethod.GORDON  # el de la compañía (fixture)


def test_set_multiplo_y_ronic() -> None:
    s = apply_overrides(BASE, ["exit_multiple=8", "ronic=12%"])
    assert s.exit_multiple == 8.0 and s.ronic == pytest.approx(0.12)
    assert apply_overrides(BASE, ["multiple=7,5"]).exit_multiple == 7.5
    for pair, match in [
        ("exit_multiple=0", "positivo"),
        ("exit_multiple=8%", "positivo"),
        ("ronic=-1%", "positivo"),
    ]:
        with pytest.raises(ValueError, match=match):
            apply_overrides(BASE, [pair])


# --- Línea de comandos -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("extra", "label"),
    [
        (["--vt", "gordon"], "Gordon clásico"),
        (["--vt", "vt_mult", "--set", "exit_multiple=10"], "Múltiplo de salida"),
        (["--model", "fcfe", "--vt", "gordon"], "Gordon clásico"),
    ],
)
def test_cli_vt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], label: str
) -> None:
    assert cli.main([*_files(tmp_path), *extra], now=NOW) == 0
    md = next((tmp_path / "out").glob("SYN_*.md")).read_text(encoding="utf-8")
    assert "### Valor terminal" in md and f"| Método | {label} |" in md
    assert "### Comprobaciones de consistencia" in md
    assert "### Valor terminal" in capsys.readouterr().out  # un ticker: informe en consola


def test_cli_vt_mult_sin_multiplo_falla(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([*_files(tmp_path), "--vt", "vt_mult"], now=NOW) != 0
    assert "Falta el múltiplo" in capsys.readouterr().err


def test_cli_umbrales(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "t.toml"
    path.write_text("[warnings]\nronic_to_rate = -1\n", encoding="utf-8")
    assert cli.main([*_files(tmp_path), "--thresholds", str(path)], now=NOW) != 0
    assert "positivo" in capsys.readouterr().err
