"""Resumen de un lote de tickers en Markdown y CSV (sin red).

Cifras del fixture FCFF_CFO (conftest: valor 30,99 €, WACC 8,125 %, Gordon clásico) y del
banco sintético FCFE_FIN (test_fcfe_fin: 3,22 €, Ke 9 %), calculadas a mano en sus tests.
"""

import io
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from dcf import cli
from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.reports.summary import (
    CSV_DECIMAL,
    CSV_SEPARATOR,
    error_row,
    render_summary,
    summary_csv,
    summary_frame,
    summary_row,
)
from dcf.valuation import fcfe_fin, fcff_cfo
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode
from tests.test_cli_options import _fake_fetch
from tests.test_fcfe_fin import bank  # noqa: F401 (fixture)
from tests.test_report_cli import MARKET, SETTINGS

REL = 1e-9
NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)
COST = ScenarioConfig(frozenset({ScenarioMode.COST}), 0.01, 0.005)


def test_fila_fcff(company: Company, market_inputs: MarketInputs) -> None:
    r = fcff_cfo.value_company(company, market_inputs, Assumptions(0.02), NOW, COST)
    row = summary_row(company, r, "config/settings.toml")
    assert (row.ticker, row.model, row.rate_name) == ("TEST", "fcff_cfo", "WACC")
    assert row.neutral == pytest.approx(30.98564888595216, rel=REL)
    assert row.upside(row.neutral) == pytest.approx(30.98564888595216 / 10 - 1, rel=REL)
    assert row.bearish is not None and row.bullish is not None
    assert row.bearish < row.neutral < row.bullish
    assert row.discount_rate == pytest.approx(0.08125, rel=REL)
    assert row.terminal_growth == 0.02
    assert row.rate_sources is not None
    assert "rf 3,00 % (fixture" in row.rate_sources and "Kd 5,00 %" in row.rate_sources
    assert row.growth_source == "config/settings.toml"


def test_fila_fcfe(bank: Company, market_inputs: MarketInputs) -> None:  # noqa: F811
    r = fcfe_fin.value_company(bank, market_inputs, Assumptions(0.02, 2), NOW)
    row = summary_row(bank, r, "argumento --g")
    assert (row.model, row.rate_name) == ("fcfe_fin", "Ke")
    assert row.terminal_method == "gordon"
    assert row.discount_rate == pytest.approx(0.09, rel=REL)
    assert row.neutral == pytest.approx(3.220183, rel=1e-6)
    assert row.bearish is None and row.bullish is None  # sin escenarios
    assert row.rate_sources is not None and "Kd" not in row.rate_sources


def test_avisos_incluyen_modelo_y_escenarios_no_validos(
    company: Company, market_inputs: MarketInputs
) -> None:
    # g = 2,5 % y alcista g + 0,5 = 3 % = rf → escenario alcista no válido.
    r = fcff_cfo.value_company(company, market_inputs, Assumptions(0.025), NOW, COST)
    row = summary_row(company, r, "x")
    assert row.bullish is None
    assert any(w.startswith("Escenario alcista no válido") for w in row.warnings)
    assert any("sin clasificar" in w for w in row.warnings)  # fixture sin tipo


def test_markdown(company: Company, market_inputs: MarketInputs) -> None:
    r = fcff_cfo.value_company(company, market_inputs, Assumptions(0.02), NOW, COST)
    rows = [summary_row(company, r, "config/settings.toml"), error_row("MALO", "falta EBIT")]
    md = render_summary(rows, NOW, "0.1.0")
    assert "# Resumen de valoraciones DCF" in md and "no es una recomendación" in md
    assert "Tickers valorados: 1 de 2" in md
    assert "| **TEST** | Empresa Sintética S.A. | fcff_cfo | gordon | 10,00 € |" in md
    assert "**30,99 €** | 209,86 % |" in md
    assert "WACC 8,13 %" in md and "Fuente de g" in md
    assert "## Tickers no valorados" in md and "**MALO**: falta EBIT" in md
    assert "### TEST" in md  # avisos del ticker


def test_csv_formato_excel_espanol(company: Company, market_inputs: MarketInputs) -> None:
    r = fcff_cfo.value_company(company, market_inputs, Assumptions(0.02), NOW, COST)
    rows = [summary_row(company, r, "x"), error_row("MALO", "falta EBIT")]
    text = summary_csv(rows)
    header = text.splitlines()[0].split(CSV_SEPARATOR)
    assert header[:6] == ["ticker", "empresa", "modelo", "vt", "cotizacion_eur", "bajista_eur"]
    assert "30,985648" in text  # decimal con coma
    back = pd.read_csv(io.StringIO(text), sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
    assert back["neutro_eur"].iloc[0] == pytest.approx(30.98564888595216, rel=1e-9)
    assert back["error"].iloc[1] == "falta EBIT" and pd.isna(back["neutro_eur"].iloc[1])
    assert list(summary_frame(rows).columns) == header


def test_cli_guarda_resumen_con_errores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "fetch_company", _fake_fetch)
    (tmp_path / "s.toml").write_text(SETTINGS, encoding="utf-8")
    (tmp_path / "m.toml").write_text(MARKET, encoding="utf-8")
    argv = ["AAA", "MALO", "BANCO", "-c", str(tmp_path / "s.toml"), "-m", str(tmp_path / "m.toml")]
    assert cli.main([*argv, "-o", str(tmp_path / "out"), "--set", "g=1%"], now=NOW) == 1
    md = (tmp_path / "out" / "resumen_20261118T120000Z.md").read_text(encoding="utf-8")
    assert "Tickers valorados: 2 de 3" in md and "**MALO**" in md
    raw = (tmp_path / "out" / "resumen_20261118T120000Z.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 con BOM para Excel
    df = pd.read_csv(
        tmp_path / "out" / "resumen_20261118T120000Z.csv",
        sep=CSV_SEPARATOR,
        decimal=CSV_DECIMAL,
        encoding="utf-8-sig",
    )
    assert list(df["ticker"]) == ["AAA", "MALO", "BANCO"]
    assert list(df["modelo"].fillna("")) == ["fcff", "", "fcfe_fin"]
    assert list(df["vt"].fillna("")) == ["gordon_value_driver", "", "gordon"]
    assert list(df["tasa"].fillna("")) == ["WACC", "", "Ke"]
    assert set(df["fuente_g"].dropna()) == {"argumento --set"}
    assert "Total Revenue" in df["error"].iloc[1]


def test_un_solo_ticker_no_guarda_resumen(tmp_path: Path) -> None:
    from tests.test_report_cli import _files

    assert cli.main(_files(tmp_path), now=NOW) == 0
    assert not list((tmp_path / "out").glob("resumen_*"))
