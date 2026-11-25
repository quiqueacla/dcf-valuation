"""Umbrales y avisos de consistencia de la valoración (funciones puras, sin I/O).

Los umbrales por defecto están en :mod:`dcf.defaults` y se pueden cambiar en
``config/thresholds.toml``. Ver ``docs/metodologia.md`` §12.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from dcf.defaults import IMPLIED_GROWTH_GAP, LAST_FLOW_DEVIATION, RONIC_TO_RATE, SCENARIO_GROWTH_GAP


@dataclass(frozen=True, slots=True)
class WarningThresholds:
    """Umbrales a partir de los que la valoración avisa de posibles incoherencias.

    Attributes:
        last_flow_deviation: Desviación relativa máxima del último flujo histórico frente
            a la media de los anteriores (0.33 = 33 %). Por encima, posible valoración
            apoyada en un año puntual.
        implied_growth_gap: Diferencia máxima, en puntos (decimal: 0.0075 = 0,75 puntos),
            entre el g implícito en el valor terminal y el g supuesto.
        ronic_to_rate: Cociente máximo entre el RONIC (o ROE) del value driver y la tasa
            de descuento; por encima, la ventaja competitiva supuesta es muy alta.
        scenario_growth_gap: Diferencia máxima, en puntos (0.01 = 1 punto), entre el g
            implícito y el g de un escenario bajista o alcista; por encima, el
            escenario se excluye (no válido). En la valoración central solo se avisa.
    """

    last_flow_deviation: float = LAST_FLOW_DEVIATION
    implied_growth_gap: float = IMPLIED_GROWTH_GAP
    ronic_to_rate: float = RONIC_TO_RATE
    scenario_growth_gap: float = SCENARIO_GROWTH_GAP

    # Valida umbrales finitos y positivos.
    def __post_init__(self) -> None:
        for name in (
            "last_flow_deviation",
            "implied_growth_gap",
            "ronic_to_rate",
            "scenario_growth_gap",
        ):
            value: float = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} debe ser un número positivo, recibido {value!r}")


# Avisos sobre la serie histórica de flujos: años negativos y último año atípico.
def historical_flow_warnings(
    flow_name: str, by_year: Mapping[int, float], thresholds: WarningThresholds
) -> tuple[str, ...]:
    """Revisa los flujos históricos del modelo.

    Avisa de cada año con flujo negativo y de un último año que se desvía de la media de
    los anteriores más que ``thresholds.last_flow_deviation``: si está muy por encima,
    la valoración puede apoyarse en un año puntual (posible sobrevaloración).

    Args:
        flow_name: Nombre del flujo para los mensajes (p. ej. "FCFF").
        by_year: Flujo histórico por ejercicio, en EUR.
        thresholds: Umbrales de los avisos.

    Returns:
        Avisos, en orden.
    """
    warnings = [
        f"{flow_name} histórico negativo en {year} ({value / 1e6:,.1f} M€)"
        for year, value in sorted(by_year.items())
        if value < 0
    ]
    years = sorted(by_year)
    if len(years) >= 2:
        last = by_year[years[-1]]
        mean_prev = float(np.mean([by_year[y] for y in years[:-1]]))
        if mean_prev != 0:
            deviation = (last - mean_prev) / abs(mean_prev)
            if abs(deviation) > thresholds.last_flow_deviation:
                direction = "por encima" if deviation > 0 else "por debajo"
                risk = "sobrevaloración" if deviation > 0 else "infravaloración"
                warnings.append(
                    f"El {flow_name} de {years[-1]} ({last / 1e6:,.1f} M€) está un "
                    f"{abs(deviation):.0%} {direction} de la media de los años anteriores "
                    f"({mean_prev / 1e6:,.1f} M€): posible {risk} si es puntual"
                )
    return tuple(warnings)
