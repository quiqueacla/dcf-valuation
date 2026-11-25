"""Informe Markdown, configuración y línea de comandos (sin red: se usa la caché)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf.cli import main
from dcf.company import Company
from dcf.data.yahoo import save_raw
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.reports.format import num as _num
from dcf.reports.markdown import render_report
from dcf.settings import load_settings
from dcf.valuation.fcff_cfo import value_company
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode
from tests.test_yahoo import _raw

NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)
BOTH = ScenarioConfig(frozenset({ScenarioMode.SALES, ScenarioMode.COST}), 0.01, 0.005)

MARKET = """
[risk_free_rate]
value = 0.03
source = "fixture rf"
date = 2026-11-17

[market_risk_premium]
value = 0.05
source = "fixture prm"
date = 2026-11-01

[beta]
mode = "yahoo"

[country_risk_premium."Spain"]
value = 0.0
source = "fixture crp"
date = 2026-11-01
"""

SETTINGS = """
[valuation]
terminal_growth = 0.015

[scenarios]
modes = ["ventas", "coste"]
wacc_shift = 0.01
growth_shift = 0.005
"""


def test_formato_numerico_espanol() -> None:
    assert _num(1234567.891, 1) == "1.234.567,9"
    assert _num(-0.5, 2) == "-0,50"


def test_informe_tiene_las_cuatro_secciones(company: Company, market_inputs: MarketInputs) -> None:
    r = value_company(company, market_inputs, Assumptions(terminal_growth=0.02), NOW, BOTH)
    md = render_report(company, r, scale=1.0, unit="€")
    for title in (
        "## 1. Información de la compañía",
        "## 2. Coste de la deuda y del capital (WACC)",
        "## 3. Históricos y proyecciones",
        "## 4. Valor intrínseco",
        "### 4.2 Escenarios",
        "### 4.3 Sensibilidad",
    ):
        assert title in md
    assert "no es una recomendación de inversión" in md
    assert "**8,13 %**" in md  # WACC 8,125 %
    assert "**30,99 €**" in md  # valor por acción del caso de referencia
    assert "**Bajista**" in md and "**Neutro**" in md and "**Alcista**" in md
    assert "fixture" in md  # fuente de rf / datos
    assert "dcf 0.1.0" in md


def test_informe_sin_escenarios(company: Company, market_inputs: MarketInputs) -> None:
    r = value_company(company, market_inputs, Assumptions(terminal_growth=0.02), NOW)
    assert "### 4.2 Escenarios" not in render_report(company, r, scale=1.0)


def test_carga_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text(SETTINGS, encoding="utf-8")
    s = load_settings(path)
    assert s.terminal_growth == 0.015
    assert s.scenarios.modes == frozenset({ScenarioMode.SALES, ScenarioMode.COST})


def test_settings_rechaza_modo_desconocido(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text(SETTINGS.replace('"coste"', '"otro"'), encoding="utf-8")
    with pytest.raises(ValueError, match="otro"):
        load_settings(path)


def test_settings_del_repo_es_valido() -> None:
    s = load_settings(Path(__file__).parents[1] / "config/settings.toml")
    assert s.projection_years >= 2
    assert s.scenarios.wacc_shift == 0.01


def _files(tmp_path: Path, settings: str = SETTINGS) -> list[str]:
    (tmp_path / "s.toml").write_text(settings, encoding="utf-8")
    (tmp_path / "m.toml").write_text(MARKET, encoding="utf-8")
    cache = save_raw(_raw(), tmp_path / "cache")
    return [
        "SYN",
        "--settings",
        str(tmp_path / "s.toml"),
        "--market-inputs",
        str(tmp_path / "m.toml"),
        "--from-cache",
        str(cache),
        "--output-dir",
        str(tmp_path / "out"),
    ]


def test_cli_genera_informe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(_files(tmp_path), now=NOW) == 0
    report = tmp_path / "out" / "SYN_20261118T120000Z.md"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Empresa Sintética Inc." in text and "## 4. Valor intrínseco" in text
    assert "## 1. Información de la compañía" in capsys.readouterr().out


def test_cli_g_por_argumento_prevalece(tmp_path: Path) -> None:
    assert main([*_files(tmp_path), "--g", "0.01"], now=NOW) == 0
    text = (tmp_path / "out" / "SYN_20261118T120000Z.md").read_text(encoding="utf-8")
    assert "g terminal 1,00 %" in text


def test_cli_error_sin_g(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = _files(tmp_path, SETTINGS.replace("terminal_growth = 0.015", ""))
    assert main(argv, now=NOW) == 1
    assert "crecimiento terminal" in capsys.readouterr().err


def test_cli_error_si_cache_de_otro_ticker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _files(tmp_path)
    argv[0] = "OTRO"
    assert main(argv, now=NOW) == 1
    assert "SYN" in capsys.readouterr().err


def test_redondeo_mitad_hacia_arriba() -> None:
    assert _num(8.125, 2) == "8,13"
    assert _num(2.5, 0) == "3"
    assert _num(-8.125, 2) == "-8,13"
