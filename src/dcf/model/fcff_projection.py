"""Modelo FCFF (por defecto): FCFF desde el EBIT con márgenes sobre ventas. Puro, sin I/O.

FCFF = EBIT · (1 − t) + D&A − Capex − ΔNWC, con NWC = clientes + existencias − proveedores
(circulante comercial). Se proyecta con el crecimiento de ventas y las medianas históricas de
margen EBIT, D&A/ventas, Capex/ventas y NWC/ventas; t es la mediana de los tipos efectivos.
Fórmulas en ``docs/metodologia.md`` §11 (``docs/dcf_metodos.md`` §1.1).
Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcf.company import Company, HistoricalYear, ValuationModel, required
from dcf.model.revenue_projection import (
    EstimateCase,
    RevenueSource,
    net_margin_by_year,
    project_revenue,
    revenue_growth_by_year,
)
from dcf.model.tax import TaxRates, tax_rates

FCFF = ValuationModel.FCFF


@dataclass(frozen=True, slots=True)
class FcffRatios:
    """Ratios históricos del modelo FCFF (desde el EBIT).

    Attributes:
        revenue_growth_by_year: Crecimiento de ventas de cada ejercicio respecto al anterior.
        net_margin_by_year: Margen neto; solo informativo (el FCFF no sale del Net Income).
        ebit_margin_by_year: Margen operativo (EBIT / ventas): beneficio de la actividad
            antes de intereses e impuestos por cada euro vendido.
        da_to_revenue_by_year: Amortizaciones / ventas.
        capex_to_revenue_by_year: Inversión en activo fijo / ventas.
        nwc_by_year: Circulante comercial (clientes + existencias − proveedores). Negativo si
            los proveedores financian más que clientes y existencias.
        nwc_to_revenue_by_year: Circulante comercial / ventas.
        fcff_by_year: FCFF histórico con el mismo criterio (desde el segundo ejercicio, que
            ya tiene ΔNWC): EBIT·(1−t) + D&A − Capex − ΔNWC.
        taxes: Tipos efectivos por año y su mediana (t del NOPAT).
        average_revenue_growth: Mediana de los crecimientos históricos.
        average_net_margin: Mediana de los márgenes netos (para el Net Income informativo).
        average_ebit_margin: Mediana de los márgenes EBIT.
        average_da_to_revenue: Mediana de D&A / ventas.
        average_capex_to_revenue: Mediana de Capex / ventas.
        average_nwc_to_revenue: Mediana de NWC / ventas.
        warnings: Avisos (años excluidos del tipo impositivo).
    """

    revenue_growth_by_year: dict[int, float]
    net_margin_by_year: dict[int, float]
    ebit_margin_by_year: dict[int, float]
    da_to_revenue_by_year: dict[int, float]
    capex_to_revenue_by_year: dict[int, float]
    nwc_by_year: dict[int, float]
    nwc_to_revenue_by_year: dict[int, float]
    fcff_by_year: dict[int, float]
    taxes: TaxRates
    average_revenue_growth: float
    average_net_margin: float
    average_ebit_margin: float
    average_da_to_revenue: float
    average_capex_to_revenue: float
    average_nwc_to_revenue: float
    warnings: tuple[str, ...]

    # Tipo impositivo del NOPAT: mediana de los tipos efectivos.
    @property
    def tax_rate(self) -> float:
        """Tipo impositivo normalizado (mediana), en decimal."""
        return self.taxes.median


@dataclass(frozen=True, slots=True)
class FcffFlow:
    """Un año proyectado del modelo FCFF, antes de descontar.

    Attributes:
        fiscal_year: Ejercicio proyectado.
        revenue: Ventas proyectadas.
        revenue_growth: Crecimiento de ventas respecto al año anterior.
        revenue_source: Si las ventas vienen de analistas o del crecimiento medio.
        net_income: Beneficio neto informativo (ventas × margen neto medio).
        ebit: Resultado operativo (ventas × margen EBIT medio).
        nopat: Beneficio operativo después de impuestos: EBIT · (1 − t).
        depreciation_amortization: Amortizaciones (ventas × D&A/ventas medio).
        capital_expenditure: Inversión en activo fijo (ventas × Capex/ventas medio).
        nwc: Circulante comercial (ventas × NWC/ventas medio).
        nwc_change: Variación del circulante: NWC_t − NWC_{t−1} (positiva = consume caja).
        fcff: NOPAT + D&A − Capex − ΔNWC.
    """

    fiscal_year: int
    revenue: float
    revenue_growth: float
    revenue_source: RevenueSource
    net_income: float
    ebit: float
    nopat: float
    depreciation_amortization: float
    capital_expenditure: float
    nwc: float
    nwc_change: float
    fcff: float


@dataclass(frozen=True, slots=True)
class FcffProjection:
    """Proyección FCFF del horizonte explícito.

    Attributes:
        flows: Años proyectados, en orden.
        projection_growth: Crecimiento aplicado a los años sin estimación de analistas.
        warnings: Avisos de la proyección.
    """

    flows: tuple[FcffFlow, ...]
    projection_growth: float
    warnings: tuple[str, ...] = ()


# Circulante comercial de un ejercicio: clientes + existencias − proveedores.
def trade_working_capital(year: HistoricalYear) -> float:
    """Calcula el circulante comercial (NWC) de un ejercicio.

    Args:
        year: Ejercicio con clientes, existencias y proveedores.

    Returns:
        NWC en EUR.

    Raises:
        ValueError: Si falta clientes, existencias o proveedores.
    """
    label = str(year.fiscal_year)
    return (
        required(year.receivables, f"los clientes de {label}", FCFF)
        + required(year.inventory, f"las existencias de {label}", FCFF)
        - required(year.payables, f"los proveedores de {label}", FCFF)
    )


# Ratios FCFF: márgenes sobre ventas, NWC, t mediano y FCFF histórico.
def compute_fcff_ratios(company: Company) -> FcffRatios:
    """Calcula los ratios históricos del modelo FCFF.

    Args:
        company: Compañía con ventas, EBIT, D&A, Capex, circulante comercial, BAI e
            impuestos de cada ejercicio.

    Returns:
        Ratios por ejercicio y medianas.

    Raises:
        ValueError: Si falta algún dato necesario o ningún año tiene t válido.
    """
    ebit_by_year = {d.fiscal_year: d.ebit for d in company.debt_cost_data}
    missing = [h.fiscal_year for h in company.historicals if h.fiscal_year not in ebit_by_year]
    if missing:
        raise ValueError(
            f"Falta el EBIT de los ejercicios {missing}, necesario para el modelo fcff"
        )
    taxes = tax_rates(company.debt_cost_data, "el t del NOPAT")

    ebit_margin: dict[int, float] = {}
    da_ratio: dict[int, float] = {}
    capex_ratio: dict[int, float] = {}
    nwc: dict[int, float] = {}
    nwc_ratio: dict[int, float] = {}
    for h in company.historicals:
        y = h.fiscal_year
        ebit_margin[y] = ebit_by_year[y] / h.revenue
        da_ratio[y] = required(h.depreciation_amortization, f"la D&A de {y}", FCFF) / h.revenue
        capex_ratio[y] = required(h.capital_expenditure, f"el Capex de {y}", FCFF) / h.revenue
        nwc[y] = trade_working_capital(h)
        nwc_ratio[y] = nwc[y] / h.revenue

    t = taxes.median
    fcff = {
        curr.fiscal_year: ebit_by_year[curr.fiscal_year] * (1.0 - t)
        + da_ratio[curr.fiscal_year] * curr.revenue
        - capex_ratio[curr.fiscal_year] * curr.revenue
        - (nwc[curr.fiscal_year] - nwc[prev.fiscal_year])
        for prev, curr in zip(company.historicals, company.historicals[1:], strict=False)
    }
    growth = revenue_growth_by_year(company.historicals)
    margin = net_margin_by_year(company.historicals)

    # Mediana: un año atípico no arrastra el ratio (metodología §2).
    def mean(values: dict[int, float]) -> float:
        return float(np.median(list(values.values())))

    return FcffRatios(
        revenue_growth_by_year=growth,
        net_margin_by_year=margin,
        ebit_margin_by_year=ebit_margin,
        da_to_revenue_by_year=da_ratio,
        capex_to_revenue_by_year=capex_ratio,
        nwc_by_year=nwc,
        nwc_to_revenue_by_year=nwc_ratio,
        fcff_by_year=fcff,
        taxes=taxes,
        average_revenue_growth=mean(growth),
        average_net_margin=mean(margin),
        average_ebit_margin=mean(ebit_margin),
        average_da_to_revenue=mean(da_ratio),
        average_capex_to_revenue=mean(capex_ratio),
        average_nwc_to_revenue=mean(nwc_ratio),
        warnings=taxes.warnings,
    )


# FCFF_t = EBIT_t·(1−t) + D&A_t − Capex_t − ΔNWC_t, todo como % medio de las ventas.
def project_fcff(
    company: Company,
    ratios: FcffRatios,
    projection_years: int,
    estimate_case: EstimateCase = EstimateCase.AVERAGE,
) -> FcffProjection:
    """Proyecta los FCFF del horizonte explícito desde el EBIT.

    Las ventas salen de :func:`project_revenue` (analistas +1/+2, después el crecimiento
    medio). El circulante de partida es NWC/ventas medio × ventas del último ejercicio,
    de modo que ΔNWC_t = NWC/ventas medio × (ventas_t − ventas_{t−1}) y los saltos
    históricos del circulante (p. ej. anticipos de obra) no se extrapolan.

    Args:
        company: Compañía con históricos y, opcionalmente, estimaciones de ventas.
        ratios: Ratios FCFF (ver :func:`compute_fcff_ratios`).
        projection_years: Número de años a proyectar (≥ 1).
        estimate_case: Estimación de analistas a usar (baja, media o alta).

    Returns:
        FCFF proyectados, crecimiento medio aplicado y avisos.

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
    t = ratios.tax_rate
    nwc_prev = ratios.average_nwc_to_revenue * company.historicals[-1].revenue
    flows: list[FcffFlow] = []
    for y in revenue.years:
        ebit = y.revenue * ratios.average_ebit_margin
        nopat = ebit * (1.0 - t)
        da = y.revenue * ratios.average_da_to_revenue
        capex = y.revenue * ratios.average_capex_to_revenue
        nwc = y.revenue * ratios.average_nwc_to_revenue
        change = nwc - nwc_prev
        flows.append(
            FcffFlow(
                fiscal_year=y.fiscal_year,
                revenue=y.revenue,
                revenue_growth=y.revenue_growth,
                revenue_source=y.revenue_source,
                net_income=y.net_income,
                ebit=ebit,
                nopat=nopat,
                depreciation_amortization=da,
                capital_expenditure=capex,
                nwc=nwc,
                nwc_change=change,
                fcff=nopat + da - capex - change,
            )
        )
        nwc_prev = nwc
    return FcffProjection(
        flows=tuple(flows), projection_growth=revenue.projection_growth, warnings=revenue.warnings
    )
