"""Modelo FCFE (financieras): ratios, fondos propios y FCFE proyectado. Puro, sin I/O.

FCFE_t = Net Income_t − g_t · FP_{t−1}: la financiera retiene el beneficio necesario
para que sus fondos propios (capital regulatorio) crezcan al ritmo del negocio y el
resto queda disponible para el accionista. Fórmulas en ``docs/metodologia.md`` §3 y §5.
Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcf.company import Company, ValuationModel, required
from dcf.model.revenue_projection import (
    EstimateCase,
    RevenueSource,
    net_margin_by_year,
    project_revenue,
    revenue_growth_by_year,
)

FCFE = ValuationModel.FCFE_FIN


@dataclass(frozen=True, slots=True)
class FcfeFinRatios:
    """Ratios históricos del modelo FCFE.

    Attributes:
        revenue_growth_by_year: Crecimiento de ventas de cada ejercicio respecto al anterior.
        net_margin_by_year: Margen neto (Net Income / ventas), incluye años con pérdidas.
        equity_by_year: Fondos propios contables al cierre de cada ejercicio.
        return_on_equity_by_year: Rentabilidad de los fondos propios (ROE) de cada
            ejercicio: Net Income / fondos propios al inicio (cierre del anterior).
            Informativo: el modelo no lo usa para proyectar.
        average_revenue_growth: Media de los crecimientos históricos.
        average_net_margin: Media de los márgenes netos.
        last_equity: Fondos propios al cierre del último ejercicio (FP_0).
    """

    revenue_growth_by_year: dict[int, float]
    net_margin_by_year: dict[int, float]
    equity_by_year: dict[int, float]
    return_on_equity_by_year: dict[int, float]
    average_revenue_growth: float
    average_net_margin: float
    last_equity: float


@dataclass(frozen=True, slots=True)
class FcfeFinFlow:
    """Un año proyectado del modelo FCFE, antes de descontar.

    Attributes:
        fiscal_year: Ejercicio proyectado.
        revenue: Ventas proyectadas.
        revenue_growth: Crecimiento de ventas respecto al año anterior (g_t).
        revenue_source: Si las ventas vienen de analistas o del crecimiento medio.
        net_income: Beneficio neto proyectado (ventas × margen neto medio).
        equity_begin: Fondos propios al inicio del año (FP_{t−1}).
        equity_reinvestment: Beneficio retenido para que los fondos propios crezcan al
            ritmo de las ventas: g_t · FP_{t−1}.
        fcfe: Flujo de caja libre para el accionista: Net Income − reinversión.
        equity_end: Fondos propios al cierre: FP_{t−1} · (1 + g_t).
        implied_roe: ROE implícito en la proyección: Net Income / FP_{t−1}.
    """

    fiscal_year: int
    revenue: float
    revenue_growth: float
    revenue_source: RevenueSource
    net_income: float
    equity_begin: float
    equity_reinvestment: float
    fcfe: float
    equity_end: float
    implied_roe: float


@dataclass(frozen=True, slots=True)
class FcfeFinProjection:
    """Proyección FCFE del horizonte explícito.

    Attributes:
        flows: Años proyectados, en orden.
        projection_growth: Crecimiento aplicado a los años sin estimación de analistas.
        warnings: Avisos de la proyección.
    """

    flows: tuple[FcfeFinFlow, ...]
    projection_growth: float
    warnings: tuple[str, ...] = ()


# Ratios FCFE: crecimiento, margen, fondos propios y ROE histórico.
def compute_fcfe_fin_ratios(company: Company) -> FcfeFinRatios:
    """Calcula los ratios históricos del modelo FCFE.

    Args:
        company: Compañía con ventas, Net Income y fondos propios de cada ejercicio.

    Returns:
        Ratios por ejercicio y medias.

    Raises:
        ValueError: Si falta algún dato de fondos propios o los del último ejercicio
            no son positivos.
    """
    equity = {
        h.fiscal_year: required(
            h.stockholders_equity, f"los fondos propios de {h.fiscal_year}", FCFE
        )
        for h in company.historicals
    }
    last_equity = equity[company.last_fiscal_year]
    if last_equity <= 0:
        raise ValueError(
            f"Los fondos propios del último ejercicio deben ser positivos para el modelo "
            f"fcfe, recibido {last_equity:,.0f} EUR"
        )
    roe = {
        curr.fiscal_year: curr.net_income / equity[prev.fiscal_year]
        for prev, curr in zip(company.historicals, company.historicals[1:], strict=False)
        if equity[prev.fiscal_year] > 0
    }
    growth = revenue_growth_by_year(company.historicals)
    margin = net_margin_by_year(company.historicals)
    return FcfeFinRatios(
        revenue_growth_by_year=growth,
        net_margin_by_year=margin,
        equity_by_year=equity,
        return_on_equity_by_year=roe,
        average_revenue_growth=float(np.mean(list(growth.values()))),
        average_net_margin=float(np.mean(list(margin.values()))),
        last_equity=last_equity,
    )


# FCFE_t = NI_t − g_t · FP_{t−1}; FP_t = FP_{t−1} · (1 + g_t).
def project_fcfe_fin(
    company: Company,
    ratios: FcfeFinRatios,
    projection_years: int,
    estimate_case: EstimateCase = EstimateCase.AVERAGE,
) -> FcfeFinProjection:
    """Proyecta los FCFE del horizonte explícito.

    Ventas y Net Income como en FCFF (:func:`project_revenue`). Los fondos propios
    crecen al ritmo de las ventas y ese crecimiento se financia con beneficio retenido.

    Args:
        company: Compañía con históricos y, opcionalmente, estimaciones de ventas.
        ratios: Ratios FCFE (ver :func:`compute_fcfe_fin_ratios`).
        projection_years: Número de años a proyectar (≥ 1).
        estimate_case: Estimación de analistas a usar (baja, media o alta).

    Returns:
        Flujos FCFE proyectados, crecimiento medio aplicado y avisos.

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
    flows: list[FcfeFinFlow] = []
    equity = ratios.last_equity
    for y in revenue.years:
        reinvestment = y.revenue_growth * equity
        flows.append(
            FcfeFinFlow(
                fiscal_year=y.fiscal_year,
                revenue=y.revenue,
                revenue_growth=y.revenue_growth,
                revenue_source=y.revenue_source,
                net_income=y.net_income,
                equity_begin=equity,
                equity_reinvestment=reinvestment,
                fcfe=y.net_income - reinvestment,
                equity_end=equity + reinvestment,
                implied_roe=y.net_income / equity,
            )
        )
        equity += reinvestment
    return FcfeFinProjection(
        flows=tuple(flows), projection_growth=revenue.projection_growth, warnings=revenue.warnings
    )


# FCFE del año N+1 en el valor terminal: NI_N · (1 + g) − g · FP_N.
def terminal_fcfe_fin(last: FcfeFinFlow, terminal_growth: float) -> float:
    """Calcula el FCFE del primer año tras el horizonte.

    Args:
        last: Último año proyectado.
        terminal_growth: g terminal en decimal.

    Returns:
        FCFE del año N+1 en EUR: el Net Income crece a g y solo se retiene lo necesario
        para que los fondos propios crezcan a g.
    """
    return last.net_income * (1.0 + terminal_growth) - terminal_growth * last.equity_end
