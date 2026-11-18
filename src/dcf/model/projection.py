"""Proyección de ventas, Net Income y FCFF (funciones puras, sin I/O).

Fórmulas en ``docs/metodologia.md`` §3. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from dcf.company import Company, RevenueEstimate
from dcf.defaults import ANALYST_ESTIMATE_YEARS
from dcf.model.ratios import HistoricalRatios


class RevenueSource(StrEnum):
    """Origen de las ventas proyectadas de un año."""

    ANALYST_ESTIMATE = "analyst_estimate"
    """Ventas del consenso de analistas (+1, +2)."""
    AVERAGE_GROWTH = "average_growth"
    """Ventas del año anterior × (1 + crecimiento medio)."""


@dataclass(frozen=True, slots=True)
class ProjectedFlow:
    """Un año proyectado, antes de descontar.

    Attributes:
        fiscal_year: Ejercicio proyectado.
        revenue: Ventas proyectadas.
        revenue_growth: Crecimiento de ventas respecto al año anterior.
        revenue_source: Si las ventas vienen de analistas o del crecimiento medio.
        net_income: Beneficio neto proyectado (ventas × margen neto medio).
        fcff: Flujo de caja libre para la empresa (Net Income × FCFF/Net Income medio).
    """

    fiscal_year: int
    revenue: float
    revenue_growth: float
    revenue_source: RevenueSource
    net_income: float
    fcff: float


@dataclass(frozen=True, slots=True)
class Projection:
    """Proyección completa del horizonte explícito.

    Attributes:
        flows: Años proyectados, en orden.
        projection_growth: Crecimiento aplicado a los años sin estimación de analistas:
            media de los crecimientos históricos y de los de analistas (+1, +2).
    """

    flows: tuple[ProjectedFlow, ...]
    projection_growth: float
    warnings: tuple[str, ...] = ()


class EstimateCase(StrEnum):
    """Qué estimación de ventas de analistas se usa para +1 y +2."""

    LOW = "low"
    """La más baja del consenso (escenario bajista)."""
    AVERAGE = "avg"
    """La media del consenso (escenario neutro)."""
    HIGH = "high"
    """La más alta del consenso (escenario alcista)."""


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


# Proyecta ventas (analistas + crecimiento medio), Net Income y FCFF del horizonte.
def project_cash_flows(
    company: Company,
    ratios: HistoricalRatios,
    projection_years: int,
    estimate_case: EstimateCase = EstimateCase.AVERAGE,
) -> Projection:
    """Proyecta los flujos del horizonte explícito.

    Los años +1 y +2 usan las estimaciones de analistas si existen. El resto crece a
    la media de los crecimientos históricos y de los implícitos en las estimaciones.

    Args:
        company: Compañía con históricos y, opcionalmente, estimaciones de ventas.
        ratios: Ratios históricos de la compañía (ver ``compute_historical_ratios``).
        projection_years: Número de años a proyectar (≥ 1).
        estimate_case: Estimación de analistas a usar (baja, media o alta). Si la
            elegida no existe para un año, se usa la media.

    Returns:
        Flujos proyectados, crecimiento medio aplicado y avisos.

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

    growth_rates = list(ratios.revenue_growth_by_year.values()) + analyst_growth
    projection_growth = float(np.mean(growth_rates))

    flows: list[ProjectedFlow] = []
    previous = company.historicals[-1].revenue
    for i in range(projection_years):
        year = company.last_fiscal_year + 1 + i
        if i < len(estimates):
            revenue, growth, source = (
                estimated[i],
                analyst_growth[i],
                RevenueSource.ANALYST_ESTIMATE,
            )
        else:
            revenue = previous * (1.0 + projection_growth)
            growth, source = projection_growth, RevenueSource.AVERAGE_GROWTH
        net_income = revenue * ratios.average_net_margin
        flows.append(
            ProjectedFlow(
                fiscal_year=year,
                revenue=revenue,
                revenue_growth=growth,
                revenue_source=source,
                net_income=net_income,
                fcff=net_income * ratios.average_fcff_to_net_income,
            )
        )
        previous = revenue

    return Projection(
        flows=tuple(flows), projection_growth=projection_growth, warnings=tuple(warnings)
    )
