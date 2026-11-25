"""Modelo FCFF desde el EBIT sobre una empresa sintética, calculado a mano (tolerancia 1e-9).

Cifras inventadas y redondas (no son de ninguna empresa real):

- Históricos 2024 / 2025: ventas 1000 / 1100 (g 10 %), EBIT 200 / 220 (margen 20 %),
  BAI 180 / 200 e impuestos 45 / 50 (t 25 %), D&A 5 %, Capex 8 %, clientes 10 %,
  existencias 5 % y proveedores 5 % de las ventas (NWC 10 %). Sin estimaciones: g_t = 10 %.
- FCFF histórico 2025 = 220 · 0,75 + 55 − 88 − (110 − 100) = 122.
- 2026e: ventas 1210; NOPAT 242 · 0,75 = 181,5; D&A 60,5; Capex 96,8;
  ΔNWC = 121 − 110 = 11 → FCFF 134,2.
- 2027e: ventas 1331; NOPAT 199,65; D&A 66,55; Capex 106,48; ΔNWC 12,1 → FCFF 147,62.
- WACC forzado al 10 %, g = 2 %. Gordon clásico: VT = 147,62 · 1,02 / 0,08 = 1882,155.
- VE = 134,2 / 1,1 + 147,62 / 1,21 + 1882,155 / 1,21 = 122 + 122 + 1555,5 = 1799,5.
- Fondos propios = VE − 200 + 100 − 0 = 1699,5; 100 acciones → 16,995 € por acción.
- Value driver con RONIC = 10 %: VT = NOPAT_N · 1,02 · (1 − 0,02 / 0,10) / 0,08
  = 199,65 · 1,02 · 0,8 / 0,08 = 2036,43.
- Múltiplo EV/EBITDA 8: EBITDA_N = EBIT 266,2 + D&A 66,55 = 332,75; VT = 2662;
  g implícito = (0,10 · 2662 − 147,62) / (2662 + 147,62) = 0,0422… (aviso: difiere de g).
"""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf import cli
from dcf.company import (
    BalanceSnapshot,
    Company,
    CompanyInfo,
    CompanyType,
    DebtCostYear,
    HistoricalYear,
    TerminalMethod,
    ValuationModel,
    model_suitability_warning,
)
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.fcff_projection import compute_fcff_ratios, project_fcff
from dcf.model.terminal_methods import TerminalOptions
from dcf.model.wacc import compute_wacc
from dcf.reports.format import eur
from dcf.reports.markdown import render_report
from dcf.reports.summary import summary_row
from dcf.valuation import fcff
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode, ScenarioName
from tests.test_report_cli import _files

REL = 1e-9
NOW = datetime(2026, 11, 21, tzinfo=UTC)
TEN = MarketRate(0.10, "prueba", NOW)
G = 0.02
FCFF_1, FCFF_2 = 134.2, 147.62
TV = FCFF_2 * 1.02 / 0.08
EV = FCFF_1 / 1.1 + FCFF_2 / 1.21 + TV / 1.21
EQUITY = EV - 200 + 100


# Ejercicio sintético con todos los ratios sobre ventas.
def _year(fiscal_year: int, revenue: float) -> HistoricalYear:
    return HistoricalYear(
        fiscal_year=fiscal_year,
        revenue=revenue,
        net_income=revenue * 0.10,
        operating_cash_flow=None,
        capital_expenditure=revenue * 0.08,
        interest_expense=10.0,
        debt_issuance=0.0,
        debt_repayment=0.0,
        depreciation_amortization=revenue * 0.05,
        receivables=revenue * 0.10,
        inventory=revenue * 0.05,
        payables=revenue * 0.05,
    )


@pytest.fixture
def industrial() -> Company:
    info = CompanyInfo(
        country="Spain",
        ticker="IND",
        name="Industrial Sintética S.A.",
        source="fixture",
        data_date=NOW,
        original_currency="EUR",
        fx_rate_to_eur=1.0,
        fx_date=None,
        company_type=CompanyType.INDUSTRIAL,
        valuation_model=ValuationModel.FCFF,
        terminal_method=TerminalMethod.GORDON,
    )
    debt = tuple(
        DebtCostYear(y, 200.0, 10.0, ebit, pretax, tax)
        for y, ebit, pretax, tax in [(2024, 200.0, 180.0, 45.0), (2025, 220.0, 200.0, 50.0)]
    )
    balance = BalanceSnapshot(
        balance_date=datetime(2025, 12, 31, tzinfo=UTC),
        cash=100.0,
        total_debt=200.0,
        minority_interest=0.0,
        diluted_shares=100.0,
        share_price=10.0,
        beta=1.2,
    )
    return Company(
        info=info,
        historicals=(_year(2024, 1000.0), _year(2025, 1100.0)),
        debt_cost_data=debt,
        balance=balance,
    )


def _value(company: Company, market: MarketInputs, **kw: object) -> fcff.FcffValuationResult:
    scenarios = kw.get("scenario_config")
    assert scenarios is None or isinstance(scenarios, ScenarioConfig)
    terminal = kw.get("terminal")
    assert terminal is None or isinstance(terminal, TerminalOptions)
    return fcff.value_company(company, market, Assumptions(G, 2), NOW, scenarios, TEN, terminal)


def test_ratios(industrial: Company) -> None:
    r = compute_fcff_ratios(industrial)
    assert r.average_ebit_margin == pytest.approx(0.20, rel=REL)
    assert r.tax_rate == pytest.approx(0.25, rel=REL)
    assert r.average_da_to_revenue == pytest.approx(0.05, rel=REL)
    assert r.average_capex_to_revenue == pytest.approx(0.08, rel=REL)
    assert r.average_nwc_to_revenue == pytest.approx(0.10, rel=REL)
    assert r.nwc_by_year == {2024: pytest.approx(100.0), 2025: pytest.approx(110.0)}
    assert r.fcff_by_year == {2025: pytest.approx(122.0, rel=REL)}


def test_proyeccion_calculada_a_mano(industrial: Company) -> None:
    flows = project_fcff(industrial, compute_fcff_ratios(industrial), 2).flows
    assert [f.revenue for f in flows] == pytest.approx([1210.0, 1331.0], rel=REL)
    assert [f.nopat for f in flows] == pytest.approx([181.5, 199.65], rel=REL)
    assert [f.nwc_change for f in flows] == pytest.approx([11.0, 12.1], rel=REL)
    assert [f.fcff for f in flows] == pytest.approx([FCFF_1, FCFF_2], rel=REL)


def test_caso_referencia(industrial: Company, market_inputs: MarketInputs) -> None:
    r = _value(industrial, market_inputs)
    assert r.terminal_value == pytest.approx(1882.155, rel=REL)
    assert r.enterprise_value == pytest.approx(EV, rel=REL)
    assert r.enterprise_value == pytest.approx(1799.5, rel=REL)
    assert r.value_per_share == pytest.approx(16.995, rel=REL)
    assert r.equity_value == pytest.approx(EQUITY, rel=REL)
    assert r.value_per_share == pytest.approx(EQUITY / 100, rel=REL)
    assert r.sensitivity.loc[0.10, G] == pytest.approx(r.value_per_share, rel=REL)


def test_circulante_negativo_genera_caja_al_crecer(
    industrial: Company, market_inputs: MarketInputs
) -> None:
    # Proveedores 25 % de las ventas: NWC = −10 % → al crecer, ΔNWC < 0 (entra caja).
    years = tuple(dataclasses.replace(h, payables=h.revenue * 0.25) for h in industrial.historicals)
    flows = project_fcff(
        dataclasses.replace(industrial, historicals=years),
        compute_fcff_ratios(dataclasses.replace(industrial, historicals=years)),
        2,
    ).flows
    assert [f.nwc_change for f in flows] == pytest.approx([-11.0, -12.1], rel=REL)


def test_escenarios(industrial: Company, market_inputs: MarketInputs) -> None:
    config = ScenarioConfig(frozenset({ScenarioMode.COST}), 0.01, 0.005)
    s = {x.name: x for x in _value(industrial, market_inputs, scenario_config=config).scenarios}
    assert s[ScenarioName.NEUTRAL].value_per_share == pytest.approx(EQUITY / 100, rel=REL)
    bear_tv = FCFF_2 * 1.015 / (0.11 - 0.015)
    bear_ev = FCFF_1 / 1.11 + FCFF_2 / 1.11**2 + bear_tv / 1.11**2
    assert s[ScenarioName.BEARISH].value_per_share == pytest.approx((bear_ev - 100) / 100, rel=REL)


@pytest.mark.parametrize("field", ["depreciation_amortization", "receivables", "payables"])
def test_error_si_falta_un_dato(
    industrial: Company, market_inputs: MarketInputs, field: str
) -> None:
    years = (
        industrial.historicals[0],
        dataclasses.replace(industrial.historicals[1], **{field: None}),
    )
    with pytest.raises(ValueError, match="modelo fcff"):
        _value(dataclasses.replace(industrial, historicals=years), market_inputs)


def test_informe(industrial: Company, market_inputs: MarketInputs) -> None:
    r = _value(industrial, market_inputs)
    md = render_report(industrial, r, scale=1.0, unit="€")
    assert "### Valor terminal" in md and "| 1.882,2 |" in md
    assert "### Comprobaciones de consistencia" in md
    assert "# Valoración DCF (FCFF): Industrial Sintética S.A. (IND)" in md
    assert "Circulante comercial = clientes + existencias − proveedores" in md
    assert "NOPAT = EBIT × (1 − 25,00 %)" in md
    assert "**134,2**" in md and "**147,6**" in md
    assert f"**Valor intrínseco por acción** | **{eur(r.value_per_share)}**" in md
    assert "Kd medio · t mediano" in md


def test_resumen(industrial: Company, market_inputs: MarketInputs) -> None:
    row = summary_row(industrial, _value(industrial, market_inputs), "x")
    assert (row.model, row.rate_name, row.discount_rate) == ("fcff", "WACC", 0.10)


def test_wacc_usa_la_mediana_del_tipo_efectivo(
    company: Company, market_inputs: MarketInputs
) -> None:
    # t = 25 %, 25 %, 25 %, 91,64 % → media 41,6 %, mediana 25 %.
    debt = list(company.debt_cost_data)
    debt[1] = dataclasses.replace(debt[1], tax_provision=debt[1].pretax_income * 0.9164)
    w = compute_wacc(dataclasses.replace(company, debt_cost_data=tuple(debt)), market_inputs)
    assert w.tax_rate == pytest.approx(0.25, rel=REL)
    assert w.tax_rate_by_year[2023] == pytest.approx(0.9164, rel=REL)


def test_industrial_admite_fcff_y_fcff_cfo() -> None:
    assert model_suitability_warning(CompanyType.INDUSTRIAL, ValuationModel.FCFF) is None
    assert model_suitability_warning(CompanyType.INDUSTRIAL, ValuationModel.FCFF_CFO) is None
    warning = model_suitability_warning(CompanyType.BANK, ValuationModel.FCFF_CFO)
    assert warning is not None and "fcfe" in warning


@pytest.mark.parametrize(("model", "title"), [("fcff", "(FCFF)"), ("fcff_cfo", "(FCFF_CFO)")])
def test_cli_modelo(tmp_path: Path, model: str, title: str) -> None:
    assert cli.main([*_files(tmp_path), "--model", model], now=NOW) == 0
    md = next((tmp_path / "out").glob("SYN_*.md")).read_text(encoding="utf-8")
    assert f"# Valoración DCF {title}" in md


def test_vt_clasico_en_fcff_cfo_no_cambia(company: Company, market_inputs: MarketInputs) -> None:
    # fcff_cfo mantiene VT = FCFF_N · (1 + g) / (WACC − g): referencia de test_fcff_cfo.
    from dcf.valuation import fcff_cfo

    r = fcff_cfo.value_company(company, market_inputs, Assumptions(G), NOW)
    assert r.terminal_value == pytest.approx(r.projections[-1].fcff * 1.02 / (0.08125 - G), rel=REL)


def test_value_driver_con_ronic_forzado(industrial: Company, market_inputs: MarketInputs) -> None:
    ronic = MarketRate(0.10, "prueba", NOW)
    options = TerminalOptions(TerminalMethod.VALUE_DRIVER, ronic=ronic)
    r = _value(industrial, market_inputs, terminal=options)
    assert r.terminal_value == pytest.approx(199.65 * 1.02 * 0.8 / 0.08, rel=REL)
    assert r.terminal is not None and r.terminal.basis.profit_last == pytest.approx(199.65)
    ev = FCFF_1 / 1.1 + FCFF_2 / 1.21 + 2036.43 / 1.21
    assert r.enterprise_value == pytest.approx(ev, rel=REL)


def test_value_driver_con_roic_historico(industrial: Company, market_inputs: MarketInputs) -> None:
    # ROIC 2025 = NOPAT 165 / capital invertido 2024 (deuda 200 + FP − caja).
    options = TerminalOptions(TerminalMethod.VALUE_DRIVER)
    with pytest.raises(ValueError, match="RONIC"):
        _value(industrial, market_inputs, terminal=options)  # sin fondos propios: sin ROIC
    years = tuple(
        dataclasses.replace(h, stockholders_equity=650.0, cash=100.0)
        for h in industrial.historicals
    )
    r = _value(dataclasses.replace(industrial, historicals=years), market_inputs, terminal=options)
    assert r.terminal is not None and r.terminal.basis.ronic is not None
    assert r.terminal.basis.ronic.value == pytest.approx(165 / 750, rel=REL)


def test_multiplo_de_salida_y_g_implicito(industrial: Company, market_inputs: MarketInputs) -> None:
    options = TerminalOptions(TerminalMethod.MULTIPLE, multiple=MarketRate(8.0, "prueba", NOW))
    r = _value(industrial, market_inputs, terminal=options)
    assert r.terminal_value == pytest.approx(8 * 332.75, rel=REL)
    assert r.terminal is not None
    assert r.terminal.implied_growth == pytest.approx((266.2 - 147.62) / (2662 + 147.62), rel=REL)
    assert any("g implícito" in w for w in r.checks)
    with pytest.raises(ValueError, match="múltiplo"):
        _value(industrial, market_inputs, terminal=TerminalOptions(TerminalMethod.MULTIPLE))


def test_informe_muestra_nopat_y_roic(industrial: Company, market_inputs: MarketInputs) -> None:
    # NOPAT = EBIT · 0,75: 150 y 165; capital invertido = 200 + FP − 100: 750 y 800;
    # ROIC 2025 = 165 / 750 = 22 % (sobre el capital al inicio del ejercicio).
    years = tuple(
        dataclasses.replace(h, stockholders_equity=fp, cash=100.0)
        for h, fp in zip(industrial.historicals, (650.0, 700.0), strict=True)
    )
    company = dataclasses.replace(industrial, historicals=years)
    md = render_report(company, _value(company, market_inputs), scale=1.0, unit="€")
    assert "| NOPAT = EBIT × (1 − 25,00 %) (€) | 150,0 | 165,0 |  |" in md
    assert "| Capital invertido = deuda + fondos propios − caja (€) | 750,0 | 800,0 |  |" in md
    assert "| ROIC = NOPAT / capital invertido inicial | — | 22,00 % | 22,00 % |" in md


def test_informe_fcff_cfo_muestra_nopat_y_roic(
    company: Company, market_inputs: MarketInputs
) -> None:
    from dcf.valuation import fcff_cfo

    md = render_report(
        company, fcff_cfo.value_company(company, market_inputs, Assumptions(G), NOW), 1.0, "€"
    )
    assert "| EBIT (€) |" in md and "| Margen EBIT |" in md
    assert (
        "| NOPAT = EBIT × (1 − 25,00 %)" in md
        and "| ROIC = NOPAT / capital invertido inicial |" in md
    )


# Posición de la primera fila que empieza por cada partida.
def _order(md: str, labels: list[str]) -> list[int]:
    start = md.index("### 3.1")
    return [md.index(f"| {label}", start) for label in labels]


def test_historicos_en_cascada(
    industrial: Company, company: Company, market_inputs: MarketInputs
) -> None:
    from dcf.valuation import fcff_cfo

    md = render_report(industrial, _value(industrial, market_inputs), 1.0, "€")
    labels = ["Ventas", "EBIT (", "t efectivo", "NOPAT", "+ D&A", "− Capex", "FCFF =", "ROIC"]
    assert _order(md, labels) == sorted(_order(md, labels))
    r = fcff_cfo.value_company(company, market_inputs, Assumptions(G), NOW)
    md = render_report(company, r, 1.0, "€")
    labels = ["Ventas", "EBIT (", "− Intereses", "t efectivo", "NOPAT", "Net Income (", "CFO"]
    labels += ["− Capex", "FCFF =", "FCFF / Net Income", "Capital invertido", "ROIC"]
    assert _order(md, labels) == sorted(_order(md, labels))
