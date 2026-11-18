"""Lectura de la configuración de la aplicación (``config/settings.toml``)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode

DEFAULT_SETTINGS_PATH = Path("config/settings.toml")


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Configuración del modo de la aplicación.

    Attributes:
        terminal_growth: g terminal en decimal; ``None`` si no se fija aquí (entonces
            debe darse por línea de comandos).
        scenarios: Modos de escenario y desplazamientos.
    """

    terminal_growth: float | None
    scenarios: ScenarioConfig


# Número de una sección TOML; error claro si falta o no es numérico.
def _number(section: dict[str, Any], key: str, path: Path, name: str) -> float:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{path}: [{name}].{key} debe ser un número en decimal")
    return float(value)


# Lee settings.toml: g terminal opcional y configuración de escenarios obligatoria.
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

    if "scenarios" not in data:
        raise ValueError(f"{path}: falta la sección [scenarios]")
    sc = data["scenarios"]
    raw_modes = sc.get("modes", [])
    if not isinstance(raw_modes, list):
        raise ValueError(f"{path}: [scenarios].modes debe ser una lista")
    valid = {m.value for m in ScenarioMode}
    unknown = [m for m in raw_modes if m not in valid]
    if unknown:
        raise ValueError(f"{path}: modos desconocidos {unknown}; válidos: {sorted(valid)}")
    scenarios = ScenarioConfig(
        modes=frozenset(ScenarioMode(m) for m in raw_modes),
        wacc_shift=_number(sc, "wacc_shift", path, "scenarios"),
        growth_shift=_number(sc, "growth_shift", path, "scenarios"),
    )
    return AppSettings(terminal_growth=growth, scenarios=scenarios)
