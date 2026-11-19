"""Modelo FCFF: proyección de ventas, Net Income y FCFF (funciones puras, sin I/O).

Fórmulas en ``docs/metodologia.md`` §3. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from dataclasses import dataclass

from dcf.company import Company
from dcf.model.fcff_ratios import HistoricalRatios
from dcf.model.revenue_projection import EstimateCase, RevenueSource, project_revenue


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
        warnings: Avisos de la proyección.
    """

    flows: tuple[ProjectedFlow, ...]
    projection_growth: float
    warnings: tuple[str, ...] = ()


# Proyecta ventas y Net Income (comunes) y FCFF = Net Income × FCFF/Net Income medio.
def project_cash_flows(
    company: Company,
    ratios: HistoricalRatios,
    projection_years: int,
    estimate_case: EstimateCase = EstimateCase.AVERAGE,
) -> Projection:
    """Proyecta los flujos FCFF del horizonte explícito.

    Las ventas y el Net Income salen de :func:`project_revenue`; el FCFF aplica la
    conversión media histórica FCFF / Net Income.

    Args:
        company: Compañía con históricos y, opcionalmente, estimaciones de ventas.
        ratios: Ratios históricos FCFF (ver ``compute_historical_ratios``).
        projection_years: Número de años a proyectar (≥ 1).
        estimate_case: Estimación de analistas a usar (baja, media o alta).

    Returns:
        Flujos proyectados, crecimiento medio aplicado y avisos.

    Raises:
        ValueError: Si ``projection_years`` < 1.
    """
    revenue = project_revenue(
        company,
        list(ratios.revenue_growth_by_year.values()),
        ratios.average_net_margin,
        projection_years,
        estimate_case,
    )
    flows = tuple(
        ProjectedFlow(
            fiscal_year=y.fiscal_year,
            revenue=y.revenue,
            revenue_growth=y.revenue_growth,
            revenue_source=y.revenue_source,
            net_income=y.net_income,
            fcff=y.net_income * ratios.average_fcff_to_net_income,
        )
        for y in revenue.years
    )
    return Projection(
        flows=flows, projection_growth=revenue.projection_growth, warnings=revenue.warnings
    )
