"""Descuento de flujos, valor por acción, sensibilidad y escenarios comunes a FCFF y FCFE.

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §5-§8.
Tasas en decimal (0.08 = 8 %), importes en EUR (``float``, sin redondeo interno).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from dcf.defaults import (
    SENSITIVITY_GROWTH_STEP,
    SENSITIVITY_STEPS_EACH_SIDE,
    SENSITIVITY_WACC_STEP,
)
from dcf.model.revenue_projection import EstimateCase
from dcf.valuation.scenarios import ScenarioConfig, ScenarioMode, ScenarioName

GRID_DECIMALS = 10
"""Decimales de la rejilla de sensibilidad: elimina el ruido de float al sumar pasos."""


@dataclass(frozen=True, slots=True)
class DiscountedFlows:
    """Valor actual de unos flujos y de su valor terminal.

    Attributes:
        discount_factors: 1 / (1 + tasa)^k para k = 1..N.
        present_values: Valor actual de cada flujo proyectado.
        terminal_value: Valor terminal al final del año N, sin descontar.
        terminal_value_present: Valor terminal descontado a hoy.
        total: Suma de los valores actuales de los flujos y del valor terminal (VE en
            FCFF; fondos propios en FCFE).
    """

    discount_factors: tuple[float, ...]
    present_values: tuple[float, ...]
    terminal_value: float
    terminal_value_present: float
    total: float


# Error claro si el valor descontado (VE o fondos propios) no es positivo, con su desglose.
def require_positive_value(
    label: str,
    value: float,
    flows_present: float,
    terminal_present: float,
    flow_name: str,
    hint: str | None = None,
) -> None:
    """Comprueba que el valor descontado sea positivo y, si no, explica por qué.

    Un valor negativo o nulo sale de flujos proyectados o de un valor terminal negativos
    (márgenes, Capex o circulante que consumen más caja de la que genera la empresa): el
    DCF no da un valor significativo con ese modelo.

    Args:
        label: Nombre del valor ("Valor de empresa", "Fondos propios").
        value: Valor descontado total, en EUR.
        flows_present: Suma de los valores actuales de los flujos proyectados, en EUR.
        terminal_present: Valor terminal descontado, en EUR.
        flow_name: Nombre del flujo ("FCFF", "FCFE").
        hint: Sugerencia final (p. ej. otro modelo); ``None`` = sin sugerencia.

    Raises:
        ValueError: Si ``value`` ≤ 0, con el desglose en millones de EUR.
    """
    if value > 0:
        return
    millions = 1e6
    message = (
        f"{label} negativo o nulo ({value / millions:,.1f} M EUR): valor actual de los "
        f"{flow_name} proyectados {flows_present / millions:,.1f} M EUR y del valor terminal "
        f"{terminal_present / millions:,.1f} M EUR. Los {flow_name} proyectados o el valor "
        "terminal son negativos (márgenes, Capex o circulante que consumen más caja de la que "
        "se genera): el DCF no da un valor significativo con este modelo"
    )
    raise ValueError(f"{message}; {hint}" if hint else message)


# Factores de descuento a final de año: 1 / (1 + tasa)^k, k = 1..n.
def discount_factors(rate: float, years: int) -> np.ndarray:
    """Calcula los factores de descuento a final de año.

    Args:
        rate: Tasa de descuento en decimal (WACC o Ke; > −1).
        years: Número de años (≥ 1).

    Returns:
        Array de longitud ``years`` con 1 / (1 + tasa)^k.

    Raises:
        ValueError: Si ``years`` < 1 o la tasa ≤ −1.
    """
    if years < 1:
        raise ValueError(f"years debe ser ≥ 1, recibido {years}")
    if rate <= -1:
        raise ValueError(f"La tasa de descuento debe ser > −1, recibido {rate}")
    factors: np.ndarray = np.power(1.0 + rate, -np.arange(1, years + 1, dtype=float))
    return factors


# Σ flujo_k / (1 + tasa)^k + VT / (1 + tasa)^N.
def discount_with_terminal_value(
    flows: Sequence[float], rate: float, terminal_value: float
) -> DiscountedFlows:
    """Descuenta los flujos proyectados y un valor terminal ya calculado.

    Args:
        flows: Flujos proyectados en EUR, años 1..N en orden (al menos uno).
        rate: Tasa de descuento en decimal.
        terminal_value: Valor terminal al final del año N, en EUR.

    Returns:
        Valores actuales y total.

    Raises:
        ValueError: Si no hay flujos o la tasa ≤ −1.
    """
    values = np.asarray(flows, dtype=float)
    factors = discount_factors(rate, len(values))
    present = values * factors
    tv_present = terminal_value * float(factors[-1])
    return DiscountedFlows(
        discount_factors=tuple(float(x) for x in factors),
        present_values=tuple(float(x) for x in present),
        terminal_value=terminal_value,
        terminal_value_present=tv_present,
        total=float(present.sum()) + tv_present,
    )


# Valor por acción = fondos propios / acciones diluidas.
def value_per_share(equity: float, diluted_shares: float) -> float:
    """Reparte el valor de los fondos propios entre las acciones diluidas.

    Args:
        equity: Valor de los fondos propios, en EUR.
        diluted_shares: Número de acciones diluidas.

    Returns:
        Valor por acción, en EUR.

    Raises:
        ValueError: Si ``diluted_shares`` ≤ 0.
    """
    if diluted_shares <= 0:
        raise ValueError(f"diluted_shares debe ser positivo, recibido {diluted_shares}")
    return equity / diluted_shares


# Rejilla tasa (filas) × g (columnas) con el valor por acción; NaN si g ≥ tasa o g ≥ rf.
def sensitivity_grid(
    value_for: Callable[[float, float], float],
    rate: float,
    terminal_growth: float,
    risk_free_rate: float,
    rate_step: float = SENSITIVITY_WACC_STEP,
    growth_step: float = SENSITIVITY_GROWTH_STEP,
    steps_each_side: int = SENSITIVITY_STEPS_EACH_SIDE,
) -> pd.DataFrame:
    """Calcula la sensibilidad del valor por acción a la tasa de descuento y a g.

    Args:
        value_for: Función (tasa, g) → valor por acción en EUR.
        rate: Tasa de descuento central (WACC o Ke), en decimal.
        terminal_growth: g central, en decimal.
        risk_free_rate: rf en decimal, para invalidar celdas con g ≥ rf.
        rate_step: Paso entre filas, en decimal.
        growth_step: Paso entre columnas, en decimal.
        steps_each_side: Pasos a cada lado del valor central.

    Returns:
        DataFrame con índice ``discount_rate`` y columnas ``terminal_growth`` (en
        decimal) y el valor por acción en EUR. Celdas inválidas a NaN.
    """
    offsets = np.arange(-steps_each_side, steps_each_side + 1, dtype=float)
    # Se redondea a 10 decimales para que g y la tasa iguales lo sean también en float
    # (si no, g = tasa − 1e-18 da un valor terminal absurdo en vez de una celda vacía).
    rates = np.round(rate + offsets * rate_step, GRID_DECIMALS)
    growths = np.round(terminal_growth + offsets * growth_step, GRID_DECIMALS)
    values = np.full((len(rates), len(growths)), np.nan)
    for i, r in enumerate(rates):
        if r <= 0:
            continue
        for j, g in enumerate(growths):
            if g >= r or g >= risk_free_rate:
                continue
            values[i, j] = value_for(float(r), float(g))
    return pd.DataFrame(
        values,
        index=pd.Index(rates, name="discount_rate"),
        columns=pd.Index(growths, name="terminal_growth"),
    )


# Parámetros (caso de ventas, tasa, g) de un escenario según los modos activos.
def scenario_inputs(
    name: ScenarioName, config: ScenarioConfig, rate: float, growth: float
) -> tuple[EstimateCase, float, float]:
    """Calcula los supuestos de un escenario.

    Args:
        name: Bajista, neutro o alcista.
        config: Modos activos y desplazamientos.
        rate: Tasa de descuento central (WACC o Ke), en decimal.
        growth: g terminal central, en decimal.

    Returns:
        Estimación de ventas a usar, tasa y g del escenario.
    """
    sign = {ScenarioName.BEARISH: -1.0, ScenarioName.NEUTRAL: 0.0, ScenarioName.BULLISH: 1.0}[name]
    case = EstimateCase.AVERAGE
    if ScenarioMode.SALES in config.modes and sign != 0:
        case = EstimateCase.HIGH if sign > 0 else EstimateCase.LOW
    if ScenarioMode.COST in config.modes:
        rate -= sign * config.wacc_shift
        growth += sign * config.growth_shift
    return case, rate, growth
