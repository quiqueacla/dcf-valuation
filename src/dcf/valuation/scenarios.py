"""Configuración y resultado de los escenarios bajista, neutro y alcista.

Metodología en ``docs/metodologia.md`` §8. Tasas en decimal (0.01 = 1 punto).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from dcf.model.revenue_projection import EstimateCase
from dcf.model.terminal_methods import implied_growth


class ScenarioMode(StrEnum):
    """Modos de escenario; se pueden combinar."""

    SALES = "ventas"
    """Ventas +1/+2 con la estimación baja / media / alta de los analistas."""
    COST = "coste"
    """WACC y g desplazados: bajista = WACC↑ y g↓; alcista = WACC↓ y g↑."""


class ScenarioName(StrEnum):
    """Nombre del escenario."""

    BEARISH = "bajista"
    NEUTRAL = "neutro"
    BULLISH = "alcista"


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    """Qué modos se aplican y cuánto se desplazan WACC y g en el modo coste.

    Attributes:
        modes: Modos activos. Vacío = bajista y alcista iguales al neutro.
        wacc_shift: Puntos que sube (bajista) o baja (alcista) el WACC, en decimal.
        growth_shift: Puntos que baja (bajista) o sube (alcista) el g terminal, en decimal.
    """

    modes: frozenset[ScenarioMode]
    wacc_shift: float
    growth_shift: float

    # Valida desplazamientos finitos y no negativos.
    def __post_init__(self) -> None:
        for name in ("wacc_shift", "growth_shift"):
            value: float = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} debe ser un número ≥ 0, recibido {value!r}")


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Valoración de un escenario.

    Attributes:
        name: Bajista, neutro o alcista.
        estimate_case: Estimación de ventas de analistas usada para +1 y +2.
        discount_rate: Tasa de descuento del escenario en decimal: WACC en FCFF, Ke en FCFE.
        terminal_growth: g terminal del escenario, en decimal.
        total_value: Valor descontado en EUR: valor de empresa en FCFF, fondos propios en
            FCFE; ``None`` si el escenario no es válido.
        terminal_value_weight: Peso del VT descontado sobre ``total_value``; ``None`` si
            no es válido.
        value_per_share: Valor por acción diluida en EUR; ``None`` si no es válido.
        error: Motivo por el que el escenario no es válido (p. ej. g ≥ rf).
        warnings: Avisos de la proyección del escenario.
    """

    name: ScenarioName
    estimate_case: EstimateCase
    discount_rate: float
    terminal_growth: float
    total_value: float | None
    terminal_value_weight: float | None
    value_per_share: float | None
    error: str | None = None
    warnings: tuple[str, ...] = ()


# Motivo de exclusión de un escenario bajista o alcista por g implícito incoherente.
def growth_gap_error(
    name: ScenarioName,
    terminal_value: float,
    last_flow: float,
    rate: float,
    terminal_growth: float,
    max_gap: float | None,
) -> str | None:
    """Comprueba el g implícito del valor terminal de un escenario.

    El escenario neutro nunca se excluye (es la valoración central, que solo avisa).

    Args:
        name: Escenario.
        terminal_value: VT del escenario al final del año N, en EUR.
        last_flow: Flujo del año N del escenario, en EUR.
        rate: Tasa de descuento del escenario, en decimal.
        terminal_growth: g del escenario, en decimal.
        max_gap: Diferencia máxima admitida en puntos (0.01 = 1 punto); ``None`` = sin
            comprobación.

    Returns:
        Motivo de exclusión, o ``None`` si el escenario es válido.
    """
    if max_gap is None or name is ScenarioName.NEUTRAL:
        return None
    implied = implied_growth(terminal_value, last_flow, rate)
    gap = abs(implied - terminal_growth)
    if gap <= max_gap:
        return None
    return (
        f"g implícito en el VT {implied:.2%} difiere {gap * 100:.2f} puntos del g del escenario "
        f"({terminal_growth:.2%}), más de {max_gap * 100:.2f}: escenario excluido"
    )
