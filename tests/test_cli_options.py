"""Opciones de la línea de comandos: varios tickers, -f, --set, --no-extras (sin red)."""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf import cli
from dcf.company import Company, TerminalMethod, ValuationModel
from dcf.data.company_types import CompanyTypeRules
from dcf.data.yahoo import build_company
from dcf.model.cost_of_equity import MarketRate
from dcf.settings import AppSettings, apply_overrides, parse_rate
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode
from tests.test_report_cli import MARKET, SETTINGS, _files
from tests.test_yahoo import _raw

NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)
BASE = AppSettings(0.02, ScenarioConfig(frozenset({ScenarioMode.COST}), 0.01, 0.005))


@pytest.mark.parametrize(
    ("text", "value"),
    [("2%", 0.02), ("2 %", 0.02), ("0.02", 0.02), ("0,5%", 0.005), ("-1%", -0.01)],
)
def test_parse_rate(text: str, value: float) -> None:
    assert parse_rate(text) == pytest.approx(value)


def test_parse_rate_invalida() -> None:
    with pytest.raises(ValueError, match="tasa"):
        parse_rate("dos")


def test_overrides() -> None:
    s = apply_overrides(
        BASE,
        [
            "g=1.5%",
            "projection_years=7",
            "modes=ventas,coste",
            "wacc_shift=2%",
            "growth_shift=0.01",
        ],
    )
    assert s.terminal_growth == pytest.approx(0.015)
    assert s.projection_years == 7
    assert s.scenarios.modes == frozenset({ScenarioMode.SALES, ScenarioMode.COST})
    assert s.scenarios.wacc_shift == pytest.approx(0.02)
    assert s.scenarios.growth_shift == pytest.approx(0.01)


def test_override_modes_vacio_es_solo_neutro() -> None:
    assert apply_overrides(BASE, ["modes="]).scenarios.modes == frozenset()


@pytest.mark.parametrize(
    "pair", ["beta=1", "g", "modes=otro", "projection_years=x", "wacc_shift=-1%"]
)
def test_override_invalido(pair: str) -> None:
    with pytest.raises(ValueError):
        apply_overrides(BASE, [pair])


def test_read_tickers(tmp_path: Path) -> None:
    path = tmp_path / "t.txt"
    path.write_text("# lista\nITX.MC\n\nSAN.MC, IBE.MC  # comentario\nAAPL\n", encoding="utf-8")
    assert cli.read_tickers(path) == ["ITX.MC", "SAN.MC", "IBE.MC", "AAPL"]


def test_fichero_de_ejemplo_del_repo() -> None:
    tickers = cli.read_tickers(Path(__file__).parents[1] / "tickers.example.txt")
    assert tickers and all(" " not in t for t in tickers)


def test_sin_tickers(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([], now=NOW) == 2
    assert "ticker" in capsys.readouterr().err


def test_from_cache_con_varios_tickers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = _files(tmp_path)
    assert cli.main(["OTRO", *argv], now=NOW) == 1
    assert "--from-cache" in capsys.readouterr().err


def test_no_extras_omite_escenarios(tmp_path: Path) -> None:
    assert cli.main([*_files(tmp_path), "--no-extras"], now=NOW) == 0
    text = (tmp_path / "out" / "SYN_20261118T120000Z.md").read_text(encoding="utf-8")
    assert "Escenarios" not in text
    assert "Sensibilidad" in text


def test_set_sobrescribe_el_fichero(tmp_path: Path) -> None:
    argv = [*_files(tmp_path), "--set", "g=1%", "--set", "projection_years=6"]
    assert cli.main(argv, now=NOW) == 0
    text = (tmp_path / "out" / "SYN_20261118T120000Z.md").read_text(encoding="utf-8")
    assert "horizonte 6 años, g terminal 1,00 %" in text


def test_alias_cortos(tmp_path: Path) -> None:
    long_argv = _files(tmp_path)
    short = [
        long_argv[0],
        "-c",
        long_argv[2],
        "-m",
        long_argv[4],
        "--from-cache",
        long_argv[6],
        "-o",
        str(tmp_path / "corto"),
    ]
    assert cli.main(short, now=NOW) == 0
    assert (tmp_path / "corto" / "SYN_20261118T120000Z.md").is_file()


def _fake_fetch(
    ticker: str,
    kd: MarketRate | None,
    cache_dir: Path,
    type_rules: CompanyTypeRules,
    model: ValuationModel | None,
    terminal: TerminalMethod | None = None,
) -> Company:
    if ticker == "MALO":
        raise ValueError("Yahoo: falta la fila 'Total Revenue' en income_stmt")
    raw = dataclasses.replace(_raw(), ticker=ticker)
    if ticker == "BANCO":
        raw = dataclasses.replace(raw, info={**raw.info, "industryKey": "banks-regional"})
    return build_company(raw, kd, type_rules=type_rules, model=model, terminal=terminal)


def test_varios_tickers_con_fichero_y_un_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "fetch_company", _fake_fetch)
    (tmp_path / "s.toml").write_text(SETTINGS, encoding="utf-8")
    (tmp_path / "m.toml").write_text(MARKET, encoding="utf-8")
    (tmp_path / "t.txt").write_text("BBB\nMALO\nAAA  # repetido abajo\n", encoding="utf-8")
    argv = [
        "AAA",
        "-f",
        str(tmp_path / "t.txt"),
        "-c",
        str(tmp_path / "s.toml"),
        "-m",
        str(tmp_path / "m.toml"),
        "-o",
        str(tmp_path / "out"),
    ]
    assert cli.main(argv, now=NOW) == 1  # un ticker falló
    out, err = capsys.readouterr()
    assert "Error en MALO" in err
    assert "AAA:" in out and "BBB:" in out and "2 de 3 tickers valorados" in out
    assert "## 1. Información" not in out  # con varios tickers solo resumen
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "AAA_20261118T120000Z.md",
        "BBB_20261118T120000Z.md",
        "resumen_20261118T120000Z.csv",
        "resumen_20261118T120000Z.md",
    ]
    assert "Resumen guardado en" in out


def _two_tickers(tmp_path: Path, *extra: str) -> list[str]:
    (tmp_path / "s.toml").write_text(SETTINGS, encoding="utf-8")
    (tmp_path / "m.toml").write_text(MARKET, encoding="utf-8")
    return [
        "AAA",
        "BANCO",
        "-c",
        str(tmp_path / "s.toml"),
        "-m",
        str(tmp_path / "m.toml"),
        "-o",
        str(tmp_path / "out"),
        *extra,
    ]


# Línea del resumen que empieza por el ticker.
def _line(out: str, ticker: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(f"{ticker}:"))


def test_banco_se_valora_con_fcfe_fin_por_la_tabla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "fetch_company", _fake_fetch)
    assert cli.main(_two_tickers(tmp_path), now=NOW) == 0
    out = capsys.readouterr().out
    assert "fcff + gordon_value_driver, WACC" in _line(out, "AAA")
    assert "AVISO" not in _line(out, "AAA")
    assert "fcfe_fin + gordon, Ke" in _line(out, "BANCO") and "AVISO" not in _line(out, "BANCO")
    report = (tmp_path / "out" / "BANCO_20261118T120000Z.md").read_text(encoding="utf-8")
    assert "# Valoración DCF (FCFE_FIN)" in report and "Aviso de modelo" not in report


def test_modelo_forzado_avisa_si_no_es_adecuado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "fetch_company", _fake_fetch)
    assert cli.main(_two_tickers(tmp_path, "--model", "fcff_cfo"), now=NOW) == 0
    banco = _line(capsys.readouterr().out, "BANCO")
    assert "fcff_cfo + gordon, WACC" in banco and "AVISO: tipo banco, el modelo fcff_cfo" in banco
    report = (tmp_path / "out" / "BANCO_20261118T120000Z.md").read_text(encoding="utf-8")
    assert "**Aviso de modelo:** Empresa de tipo banco" in report


# Fallo de red en un ticker: no para el lote y el resumen se guarda con el error.
def _fetch_con_error_de_red(
    ticker: str,
    kd: MarketRate | None,
    cache_dir: Path,
    type_rules: CompanyTypeRules,
    model: ValuationModel | None,
    terminal: TerminalMethod | None = None,
) -> Company:
    if ticker == "RED":
        raise ConnectionError("SSL certificate problem")
    if ticker == "STOP":
        raise KeyboardInterrupt
    return _fake_fetch(ticker, kd, cache_dir, type_rules, model, terminal)


def test_error_de_red_no_para_el_lote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "fetch_company", _fetch_con_error_de_red)
    argv = _two_tickers(tmp_path)
    argv[1:1] = ["RED"]  # AAA, RED, BANCO
    assert cli.main(argv, now=NOW) == 1
    out, err = capsys.readouterr()
    assert "Error en RED: ConnectionError: SSL certificate problem" in err
    assert "2 de 3 tickers valorados" in out
    assert (tmp_path / "out" / "resumen_20261118T120000Z.csv").is_file()


def test_ctrl_c_guarda_el_resumen_parcial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "fetch_company", _fetch_con_error_de_red)
    argv = _two_tickers(tmp_path)
    argv[1:1] = ["STOP"]  # AAA, STOP, BANCO
    assert cli.main(argv, now=NOW) == 130
    out, err = capsys.readouterr()
    assert "Interrumpido: 1 de 3" in err and "1 de 3 tickers valorados" in out
    md = (tmp_path / "out" / "resumen_20261118T120000Z.md").read_text(encoding="utf-8")
    assert "AAA" in md and "BANCO" not in md
