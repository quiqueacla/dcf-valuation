"""Supuestos explícitos de una valoración DCF.

Los ratios de proyección (crecimiento, margen neto, FCFF/Net Income) y el WACC no son
supuestos del usuario: se calculan en ``model/`` a partir de los datos. Aquí solo están
los parámetros que el modelo no puede deducir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dcf.defaults import ANALYST_ESTIMATE_YEARS, DEFAULT_PROJECTION_YEARS


@dataclass(frozen=True, slots=True)
class Assumptions:
    """Parámetros de la valoración. Tasas en decimal (0.08 = 8 %).

    Attributes:
        terminal_growth: Crecimiento perpetuo del FCFF tras el horizonte (Gordon).
            Debe ser menor que el WACC y que rf; se valida al construir el resultado,
            cuando ambos son conocidos.
        projection_years: Número de años de proyección explícita.
    """

    terminal_growth: float
    projection_years: int = DEFAULT_PROJECTION_YEARS

    # Valida g finito y un horizonte que cubra los años de analistas.
    def __post_init__(self) -> None:
        if not math.isfinite(self.terminal_growth):
            raise ValueError(f"terminal_growth debe ser finito, recibido {self.terminal_growth!r}")
        if self.projection_years < ANALYST_ESTIMATE_YEARS:
            raise ValueError(
                f"projection_years debe ser al menos {ANALYST_ESTIMATE_YEARS}, "
                f"recibido {self.projection_years}"
            )
