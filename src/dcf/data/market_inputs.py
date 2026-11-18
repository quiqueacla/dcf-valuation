"""Lectura de rf y prima de riesgo desde ``config/data/market_inputs.toml``."""

from __future__ import annotations

import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from dcf.model.wacc import MarketInputs, MarketRate

DEFAULT_MARKET_INPUTS_PATH = Path("config/data/market_inputs.toml")
"""Ubicación por defecto (relativa a la raíz del repo). Plantilla en ``*.example.toml``."""


# Convierte una sección TOML {value, source, date} en MarketRate, con errores claros.
def _parse_rate(data: dict[str, Any], section: str, path: Path) -> MarketRate:
    if section not in data:
        raise ValueError(f"{path}: falta la sección [{section}]")
    raw = data[section]
    missing = [k for k in ("value", "source", "date") if k not in raw]
    if missing:
        raise ValueError(f"{path}: faltan las claves {missing} en [{section}]")
    value, source, when = raw["value"], raw["source"], raw["date"]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{path}: [{section}].value debe ser un número en decimal (0.03 = 3 %)")
    if not isinstance(source, str):
        raise ValueError(f"{path}: [{section}].source debe ser texto")
    if isinstance(when, datetime):
        moment = when if when.tzinfo is not None else when.replace(tzinfo=UTC)
    elif isinstance(when, date):
        moment = datetime(when.year, when.month, when.day, tzinfo=UTC)
    else:
        raise ValueError(f"{path}: [{section}].date debe ser una fecha TOML (AAAA-MM-DD)")
    return MarketRate(value=float(value), source=source, date=moment)


# Lee el fichero TOML de datos de mercado y devuelve MarketInputs validado.
def load_market_inputs(path: Path = DEFAULT_MARKET_INPUTS_PATH) -> MarketInputs:
    """Carga rf y PRM desde un fichero TOML.

    Args:
        path: Ruta al fichero (ver ``config/data/market_inputs.example.toml``).

    Returns:
        Datos de mercado con valor, fuente y fecha.

    Raises:
        FileNotFoundError: Si el fichero no existe.
        ValueError: Si falta alguna sección o clave, o tiene un tipo incorrecto.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"No existe {path}. Copia config/data/market_inputs.example.toml y rellena los datos."
        )
    with path.open("rb") as f:
        data = tomllib.load(f)
    return MarketInputs(
        risk_free_rate=_parse_rate(data, "risk_free_rate", path),
        market_risk_premium=_parse_rate(data, "market_risk_premium", path),
        default_cost_of_debt=(
            _parse_rate(data, "default_cost_of_debt", path)
            if "default_cost_of_debt" in data
            else None
        ),
    )
