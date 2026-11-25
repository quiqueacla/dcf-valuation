from datetime import UTC, datetime
from pathlib import Path

import pytest

from dcf.data.market_inputs import load_market_inputs

VALID = """
[risk_free_rate]
value = 0.03
source = "fixture rf"
date = 2026-11-17

[market_risk_premium]
value = 0.05
source = "fixture prm"
date = 2026-11-01

[country_risk_premium."Spain"]
value = 0.0
source = "fixture crp"
date = 2026-11-01
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "market_inputs.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_carga_fichero_valido(tmp_path: Path) -> None:
    m = load_market_inputs(_write(tmp_path, VALID))
    assert m.risk_free_rate.value == 0.03
    assert m.risk_free_rate.source == "fixture rf"
    assert m.risk_free_rate.date == datetime(2026, 11, 17, tzinfo=UTC)
    assert m.market_risk_premium.value == 0.05


def test_error_si_no_existe(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="example"):
        load_market_inputs(tmp_path / "no_existe.toml")


def test_error_si_falta_seccion(tmp_path: Path) -> None:
    text = VALID.split("[market_risk_premium]")[0]
    with pytest.raises(ValueError, match="market_risk_premium"):
        load_market_inputs(_write(tmp_path, text))


def test_error_si_falta_clave(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source"):
        load_market_inputs(_write(tmp_path, VALID.replace('source = "fixture rf"', "")))


def test_error_si_valor_no_numerico(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="value"):
        load_market_inputs(_write(tmp_path, VALID.replace("value = 0.03", 'value = "3 %"')))


def test_plantilla_sin_rellenar_falla() -> None:
    template = Path(__file__).parents[1] / "config/data/market_inputs.example.toml"
    with pytest.raises(ValueError, match="faltan las claves"):
        load_market_inputs(template)


def test_kd_por_defecto_es_opcional(tmp_path: Path) -> None:
    assert load_market_inputs(_write(tmp_path, VALID)).default_cost_of_debt is None


def test_carga_kd_por_defecto(tmp_path: Path) -> None:
    text = (
        VALID
        + '\n[default_cost_of_debt]\nvalue = 0.045\nsource = "fixture kd"\ndate = 2026-11-10\n'
    )
    kd = load_market_inputs(_write(tmp_path, text)).default_cost_of_debt
    assert kd is not None and kd.value == 0.045 and kd.source == "fixture kd"


def test_kd_por_defecto_incompleto_da_error(tmp_path: Path) -> None:
    text = VALID + "\n[default_cost_of_debt]\nvalue = 0.045\n"
    with pytest.raises(ValueError, match="default_cost_of_debt"):
        load_market_inputs(_write(tmp_path, text))
