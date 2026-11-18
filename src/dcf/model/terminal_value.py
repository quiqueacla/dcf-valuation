"""Valor terminal por el método de Gordon (funciones puras, sin I/O).

Fórmula en ``docs/metodologia.md`` §5. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

import math


# Comprueba g < WACC y g < rf; lanza ValueError si no se cumple.
def validate_terminal_growth(terminal_growth: float, wacc: float, risk_free_rate: float) -> None:
    """Valida el crecimiento terminal frente al WACC y la rentabilidad libre de riesgo.

    Args:
        terminal_growth: g terminal en decimal.
        wacc: WACC en decimal.
        risk_free_rate: rf en decimal.

    Raises:
        ValueError: Si g no es finito, si g ≥ WACC o si g ≥ rf.
    """
    if not math.isfinite(terminal_growth):
        raise ValueError(f"terminal_growth debe ser finito, recibido {terminal_growth!r}")
    if terminal_growth >= wacc:
        raise ValueError(f"terminal_growth ({terminal_growth}) debe ser menor que el WACC ({wacc})")
    if terminal_growth >= risk_free_rate:
        raise ValueError(
            f"terminal_growth ({terminal_growth}) debe ser menor que rf ({risk_free_rate})"
        )


# Gordon: VT = FCFF_N · (1 + g) / (WACC − g), valor al final del año N.
def gordon_terminal_value(
    last_fcff: float, wacc: float, terminal_growth: float, risk_free_rate: float
) -> float:
    """Calcula el valor terminal con crecimiento perpetuo (Gordon).

    Args:
        last_fcff: FCFF del último año proyectado, en EUR.
        wacc: WACC en decimal.
        terminal_growth: g terminal en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.

    Returns:
        Valor terminal en EUR, a fecha de final del último año proyectado (sin descontar).

    Raises:
        ValueError: Si g ≥ WACC o g ≥ rf.
    """
    validate_terminal_growth(terminal_growth, wacc, risk_free_rate)
    return last_fcff * (1.0 + terminal_growth) / (wacc - terminal_growth)
