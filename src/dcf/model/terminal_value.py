"""Valor terminal por el método de Gordon (funciones puras, sin I/O).

Fórmula en ``docs/metodologia.md`` §5. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

import math


# Comprueba g < tasa de descuento (WACC o Ke) y g < rf; lanza ValueError si no se cumple.
def validate_terminal_growth(
    terminal_growth: float, wacc: float, risk_free_rate: float, rate_name: str = "WACC"
) -> None:
    """Valida el crecimiento terminal frente a la tasa de descuento y a rf.

    Args:
        terminal_growth: g terminal en decimal.
        wacc: Tasa de descuento en decimal (WACC en FCFF, Ke en FCFE).
        risk_free_rate: rf en decimal.
        rate_name: Nombre de la tasa para el mensaje de error.

    Raises:
        ValueError: Si g no es finito, si g ≥ tasa o si g ≥ rf.
    """
    if not math.isfinite(terminal_growth):
        raise ValueError(f"terminal_growth debe ser finito, recibido {terminal_growth!r}")
    if terminal_growth >= wacc:
        raise ValueError(
            f"terminal_growth ({terminal_growth}) debe ser menor que el {rate_name} ({wacc})"
        )
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


# Gordon con el flujo del año N+1 ya calculado: VT = flujo_{N+1} / (tasa − g).
def gordon_from_next_flow(
    next_flow: float,
    rate: float,
    terminal_growth: float,
    risk_free_rate: float,
    rate_name: str = "Ke",
) -> float:
    """Calcula el valor terminal a partir del flujo del primer año tras el horizonte.

    Se usa en FCFE, donde el flujo del año N+1 no es FCFE_N · (1 + g): la reinversión
    en fondos propios pasa a ser g · FP_N (ver ``docs/metodologia.md`` §5).

    Args:
        next_flow: Flujo del año N+1, en EUR.
        rate: Tasa de descuento en decimal.
        terminal_growth: g terminal en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.
        rate_name: Nombre de la tasa para el mensaje de error.

    Returns:
        Valor terminal en EUR al final del año N (sin descontar).

    Raises:
        ValueError: Si g ≥ tasa o g ≥ rf.
    """
    validate_terminal_growth(terminal_growth, rate, risk_free_rate, rate_name)
    return next_flow / (rate - terminal_growth)
