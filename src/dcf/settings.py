"""Configuración de la aplicación (``config/settings.toml``) y ajustes ``--set``."""

from __future__ import annotations

import dataclasses
import math
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dcf.defaults import DEFAULT_PROJECTION_YEARS
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode

DEFAULT_SETTINGS_PATH = Path("config/settings.toml")

# Claves admitidas por --set (y alias) → campo de la configuración.
OVERRIDE_KEYS = {
    "terminal_growth": "terminal_growth",
    "g": "terminal_growth",
    "projection_years": "projection_years",
    "modes": "modes",
    "wacc_shift": "wacc_shift",
    "growth_shift": "growth_shift",
}


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Configuración del modo de la aplicación.

    Attributes:
        terminal_growth: g terminal en decimal; ``None`` si no se fija aquí (entonces
            debe darse por línea de comandos).
        scenarios: Modos de escenario y desplazamientos.
        projection_years: Años de proyección explícita.
    """

    terminal_growth: float | None
    scenarios: ScenarioConfig
    projection_years: int = DEFAULT_PROJECTION_YEARS


# Número de una sección TOML; error claro si falta o no es numérico.
def _number(section: dict[str, Any], key: str, path: Path, name: str) -> float:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{path}: [{name}].{key} debe ser un número en decimal")
    return float(value)


# Convierte nombres de modo en ScenarioMode; error si alguno no existe.
def _modes(names: Iterable[str], origin: str) -> frozenset[ScenarioMode]:
    valid = {m.value for m in ScenarioMode}
    names = [n.strip() for n in names if n.strip()]
    unknown = [n for n in names if n not in valid]
    if unknown:
        raise ValueError(f"{origin}: modos desconocidos {unknown}; válidos: {sorted(valid)}")
    return frozenset(ScenarioMode(n) for n in names)


# Lee settings.toml: g y horizonte opcionales, configuración de escenarios obligatoria.
def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    """Carga la configuración de la aplicación.

    Args:
        path: Ruta al fichero TOML.

    Returns:
        Configuración validada.

    Raises:
        FileNotFoundError: Si el fichero no existe.
        ValueError: Si falta la sección [scenarios] o algún valor es inválido.
    """
    if not path.is_file():
        raise FileNotFoundError(f"No existe el fichero de configuración {path}")
    with path.open("rb") as f:
        data = tomllib.load(f)

    valuation = data.get("valuation", {})
    growth = (
        _number(valuation, "terminal_growth", path, "valuation")
        if "terminal_growth" in valuation
        else None
    )
    years = DEFAULT_PROJECTION_YEARS
    if "projection_years" in valuation:
        years_value = valuation["projection_years"]
        if isinstance(years_value, bool) or not isinstance(years_value, int):
            raise ValueError(f"{path}: [valuation].projection_years debe ser un entero")
        years = years_value

    if "scenarios" not in data:
        raise ValueError(f"{path}: falta la sección [scenarios]")
    sc = data["scenarios"]
    raw_modes = sc.get("modes", [])
    if not isinstance(raw_modes, list):
        raise ValueError(f"{path}: [scenarios].modes debe ser una lista")
    scenarios = ScenarioConfig(
        modes=_modes(raw_modes, str(path)),
        wacc_shift=_number(sc, "wacc_shift", path, "scenarios"),
        growth_shift=_number(sc, "growth_shift", path, "scenarios"),
    )
    return AppSettings(terminal_growth=growth, scenarios=scenarios, projection_years=years)


# Tasa escrita como "2%", "2 %", "0.02" o "0,02" → decimal (0.02).
def parse_rate(text: str) -> float:
    """Convierte una tasa de texto a decimal.

    Args:
        text: Tasa con o sin signo de porcentaje; admite coma decimal.

    Returns:
        Tasa en decimal (``"2%"`` → 0.02, ``"0.02"`` → 0.02).

    Raises:
        ValueError: Si no es un número finito.
    """
    clean = text.strip().replace(",", ".")
    percent = clean.endswith("%")
    try:
        value = float(clean.rstrip("%").strip())
    except ValueError:
        raise ValueError(f"'{text}' no es una tasa válida (p. ej. 2% o 0.02)") from None
    if not math.isfinite(value):
        raise ValueError(f"'{text}' no es una tasa finita")
    return value / 100 if percent else value


# Aplica ajustes "clave=valor" de --set sobre la configuración leída del fichero.
def apply_overrides(settings: AppSettings, pairs: Sequence[str]) -> AppSettings:
    """Sobrescribe valores de la configuración desde la línea de comandos.

    Claves: ``terminal_growth`` (o ``g``), ``projection_years``, ``modes``
    (lista separada por comas; vacío = solo neutro), ``wacc_shift``, ``growth_shift``.
    Las tasas admiten ``2%`` o ``0.02``.

    Args:
        settings: Configuración de partida.
        pairs: Ajustes con formato ``clave=valor``.

    Returns:
        Nueva configuración con los ajustes aplicados.

    Raises:
        ValueError: Si un ajuste no tiene formato ``clave=valor``, la clave no existe
            o el valor no es válido.
    """
    result = settings
    for pair in pairs:
        key, sep, value = pair.partition("=")
        key = key.strip().lower()
        if not sep or key not in OVERRIDE_KEYS:
            raise ValueError(
                f"--set '{pair}': usa clave=valor con clave en {sorted(OVERRIDE_KEYS)}"
            )
        target = OVERRIDE_KEYS[key]
        if target == "terminal_growth":
            result = dataclasses.replace(result, terminal_growth=parse_rate(value))
        elif target == "projection_years":
            if not value.strip().isdigit():
                raise ValueError(f"--set '{pair}': projection_years debe ser un entero")
            result = dataclasses.replace(result, projection_years=int(value))
        elif target == "modes":
            modes = _modes(value.split(","), f"--set '{pair}'")
            result = dataclasses.replace(
                result, scenarios=dataclasses.replace(result.scenarios, modes=modes)
            )
        elif target == "wacc_shift":
            scenarios = dataclasses.replace(result.scenarios, wacc_shift=parse_rate(value))
            result = dataclasses.replace(result, scenarios=scenarios)
        else:
            scenarios = dataclasses.replace(result.scenarios, growth_shift=parse_rate(value))
            result = dataclasses.replace(result, scenarios=scenarios)
    return result
