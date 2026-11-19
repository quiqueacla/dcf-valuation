"""Ventas y Net Income: ratios históricos y proyección comunes a FCFF y FCFE.

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §2-§3.
Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from dcf.company import Company, HistoricalYear, RevenueEstimate
from dcf.defaults import ANALYST_ESTIMATE_YEARS


class RevenueSource(StrEnum):
    """Origen de las ventas proyectadas de un año."""

    ANALYST_ESTIMATE = "analyst_estimate"
    """Ventas del consenso de analistas (+1, +2)."""
    AVERAGE_GROWTH = "average_growth"
    """Ventas del año anterior × (1 + crecimiento medio)."""


class EstimateCase(StrEnum):
    """Qué estimación de ventas de analistas se usa para +1 y +2."""

    LOW = "low"
    """La más baja del consenso (escenario bajista)."""
    AVERAGE = "avg"
    """La media del consenso (escenario neutro)."""
    HIGH = "high"
    """La más alta del consenso (escenario alcista)."""


@dataclass(frozen=True, slots=True)
class RevenueYear:
    """Ventas y beneficio de un año proyectado.

    Attributes:
        fiscal_year: Ejercicio proyectado.
        revenue: Ventas proyectadas.
        revenue_growth: Crecimiento de ventas respecto al año anterior.
        revenue_source: Si las ventas vienen de analistas o del crecimiento medio.
        net_income: Beneficio neto proyectado (ventas × margen neto medio).
    """

    fiscal_year: int
    revenue: float
    revenue_growth: float
    revenue_source: RevenueSource
    net_income: float


@dataclass(frozen=True, slots=True)
class RevenueProjection:
    """Proyección de ventas y Net Income del horizonte explícito.

    Attributes:
        years: Años proyectados, en orden.
        projection_growth: Crecimiento aplicado a los años sin estimación de analistas:
            media de los crecimientos históricos y de los de analistas (+1, +2).
        warnings: Avisos (p. ej. falta la estimación baja o alta).
    """

    years: tuple[RevenueYear, ...]
    projection_growth: float
    warnings: tuple[str, ...] = ()


# Crecimiento de ventas de cada ejercicio respecto al anterior (el primero no tiene).
def revenue_growth_by_year(historicals: Sequence[HistoricalYear]) -> dict[int, float]:
    """Calcula g_i = Ventas_i / Ventas_{i−1} − 1.

    Args:
        historicals: Ejercicios históricos ascendentes y consecutivos.

    Returns:
        Crecimiento en decimal por ejercicio, desde el segundo.
    """
    return {
        curr.fiscal_year: curr.revenue / prev.revenue - 1.0
        for prev, curr in zip(historicals, historicals[1:], strict=False)
    }


# Margen neto de cada ejercicio (Net Income / ventas), incluidos los años con pérdidas.
def net_margin_by_year(historicals: Sequence[HistoricalYear]) -> dict[int, float]:
    """Calcula m_i = Net Income_i / Ventas_i.

    Args:
        historicals: Ejercicios históricos.

    Returns:
        Margen neto en decimal por ejercicio.
    """
    return {h.fiscal_year: h.net_income / h.revenue for h in historicals}


# Ventas estimadas según el caso; si falta low/high se usa la media y se avisa.
def _estimate_revenue(estimate: RevenueEstimate, case: EstimateCase, warnings: list[str]) -> float:
    value = {
        EstimateCase.LOW: estimate.revenue_low,
        EstimateCase.AVERAGE: estimate.revenue,
        EstimateCase.HIGH: estimate.revenue_high,
    }[case]
    if value is None:
        warnings.append(
            f"Sin estimación '{case}' para {estimate.fiscal_year}: se usa la media del consenso"
        )
        return estimate.revenue
    return value


# Proyecta ventas (analistas + crecimiento medio) y Net Income (ventas × margen medio).
def project_revenue(
    company: Company,
    historical_growth: Sequence[float],
    average_net_margin: float,
    projection_years: int,
    estimate_case: EstimateCase = EstimateCase.AVERAGE,
) -> RevenueProjection:
    """Proyecta ventas y Net Income del horizonte explícito.

    Los años +1 y +2 usan las estimaciones de analistas si existen. El resto crece a
    la media de los crecimientos históricos y de los implícitos en las estimaciones.

    Args:
        company: Compañía con históricos y, opcionalmente, estimaciones de ventas.
        historical_growth: Crecimientos históricos de ventas, en decimal.
        average_net_margin: Margen neto medio histórico, en decimal.
        projection_years: Número de años a proyectar (≥ 1).
        estimate_case: Estimación de analistas a usar (baja, media o alta). Si la
            elegida no existe para un año, se usa la media.

    Returns:
        Ventas y Net Income proyectados, crecimiento medio aplicado y avisos.

    Raises:
        ValueError: Si ``projection_years`` < 1.
    """
    if projection_years < 1:
        raise ValueError(f"projection_years debe ser ≥ 1, recibido {projection_years}")

    warnings: list[str] = []
    estimates = company.revenue_estimates[: min(ANALYST_ESTIMATE_YEARS, projection_years)]
    estimated = [_estimate_revenue(e, estimate_case, warnings) for e in estimates]
    previous = company.historicals[-1].revenue
    analyst_growth: list[float] = []
    for revenue in estimated:
        analyst_growth.append(revenue / previous - 1.0)
        previous = revenue

    projection_growth = float(np.mean([*historical_growth, *analyst_growth]))

    years: list[RevenueYear] = []
    previous = company.historicals[-1].revenue
    for i in range(projection_years):
        if i < len(estimates):
            revenue, growth, source = (
                estimated[i],
                analyst_growth[i],
                RevenueSource.ANALYST_ESTIMATE,
            )
        else:
            revenue = previous * (1.0 + projection_growth)
            growth, source = projection_growth, RevenueSource.AVERAGE_GROWTH
        years.append(
            RevenueYear(
                fiscal_year=company.last_fiscal_year + 1 + i,
                revenue=revenue,
                revenue_growth=growth,
                revenue_source=source,
                net_income=revenue * average_net_margin,
            )
        )
        previous = revenue

    return RevenueProjection(
        years=tuple(years), projection_growth=projection_growth, warnings=tuple(warnings)
    )
