"""Lectura de rf, prima de riesgo, Kd por defecto y beta desde ``market_inputs.toml``."""

from __future__ import annotations

import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from dcf.model.cost_of_equity import BetaMode, BetaSettings, MarketInputs, MarketRate

DEFAULT_MARKET_INPUTS_PATH = Path("config/data/market_inputs.toml")
"""Ubicación por defecto (relativa a la raíz del repo). Plantilla en ``*.example.toml``."""

BETA_KEYS = frozenset({"mode", "value", "source", "date"})
"""Claves admitidas en ``[beta]`` y en cada ``[beta."TICKER"]``."""


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


# Una tabla de beta {mode?, value?, source?, date?}: value, source y date van juntos.
def _parse_beta_settings(raw: dict[str, Any], label: str, path: Path) -> BetaSettings:
    unknown = sorted(set(raw) - BETA_KEYS)
    if unknown:
        raise ValueError(f"{path}: claves desconocidas {unknown} en [{label}]")
    mode: BetaMode | None = None
    if "mode" in raw:
        valid = [m.value for m in BetaMode]
        if raw["mode"] not in valid:
            raise ValueError(f"{path}: [{label}].mode = {raw['mode']!r} no válido; usa {valid}")
        mode = BetaMode(raw["mode"])
    has_value = bool({"value", "source", "date"} & raw.keys())
    value = _parse_rate({label: raw}, label, path) if has_value else None
    return BetaSettings(mode=mode, value=value)


# Sección [beta]: claves generales y subtablas por ticker ([beta."REP.MC"]).
def _parse_beta(data: dict[str, Any], path: Path) -> tuple[BetaSettings, dict[str, BetaSettings]]:
    raw: dict[str, Any] = data.get("beta", {})
    general = {k: v for k, v in raw.items() if not isinstance(v, dict)}
    by_ticker = {
        ticker.upper(): _parse_beta_settings(table, f'beta."{ticker}"', path)
        for ticker, table in raw.items()
        if isinstance(table, dict)
    }
    return _parse_beta_settings(general, "beta", path), by_ticker


# Lee el fichero TOML de datos de mercado y devuelve MarketInputs validado.
def load_market_inputs(path: Path = DEFAULT_MARKET_INPUTS_PATH) -> MarketInputs:
    """Carga rf, PRM y, si están, Kd por defecto y configuración de beta.

    La sección ``[beta]`` es opcional (sin ella, modo ``yahoo``). Admite ``mode``
    (``yahoo``, ``fichero`` o ``yahoo-fichero``), una beta general con ``value``,
    ``source`` y ``date``, y subtablas por ticker ``[beta."REP.MC"]`` con las mismas
    claves, que prevalecen sobre la general.

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
    beta, beta_by_ticker = _parse_beta(data, path)
    return MarketInputs(
        risk_free_rate=_parse_rate(data, "risk_free_rate", path),
        market_risk_premium=_parse_rate(data, "market_risk_premium", path),
        default_cost_of_debt=(
            _parse_rate(data, "default_cost_of_debt", path)
            if "default_cost_of_debt" in data
            else None
        ),
        beta=beta,
        beta_by_ticker=beta_by_ticker,
    )
