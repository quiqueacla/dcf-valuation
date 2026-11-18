"""Ratios históricos que alimentan la proyección (funciones puras, sin I/O).

Fórmulas en ``docs/metodologia.md`` §2. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcf.company import Company, DebtCostYear, HistoricalYear


@dataclass(frozen=True, slots=True)
class HistoricalRatios:
    """Ratios históricos por ejercicio y sus medias.

    Attributes:
        revenue_growth_by_year: Crecimiento de ventas de cada ejercicio respecto al
            anterior (el primer ejercicio no tiene crecimiento).
        net_margin_by_year: Margen neto (Net Income / ventas), incluye años con pérdidas.
        tax_rate_by_year: Tipo efectivo (provisión / BAI) de los años en que es válido.
        fcff_by_year: Flujo de caja libre para la empresa de los años con t válido.
        fcff_to_net_income_by_year: Conversión del beneficio en caja (FCFF / Net Income)
            de los años válidos (t válido y Net Income > 0).
        average_revenue_growth: Media de los crecimientos históricos.
        average_net_margin: Media de los márgenes netos.
        average_fcff_to_net_income: Media de los ratios FCFF / Net Income válidos.
        warnings: Avisos sobre años excluidos de alguna media y su motivo.
    """

    revenue_growth_by_year: dict[int, float]
    net_margin_by_year: dict[int, float]
    tax_rate_by_year: dict[int, float]
    fcff_by_year: dict[int, float]
    fcff_to_net_income_by_year: dict[int, float]
    average_revenue_growth: float
    average_net_margin: float
    average_fcff_to_net_income: float
    warnings: tuple[str, ...]


# Tipo efectivo provisión/BAI; devuelve None y el motivo si no tiene sentido económico.
def effective_tax_rate(debt_year: DebtCostYear) -> tuple[float | None, str | None]:
    """Calcula el tipo impositivo efectivo de un ejercicio.

    Args:
        debt_year: Datos del ejercicio con BAI y provisión de impuestos (EUR).

    Returns:
        ``(t, None)`` con t en decimal si es válido, o ``(None, motivo)`` si el BAI es
        ≤ 0 o t queda fuera de [0, 1].
    """
    if debt_year.pretax_income <= 0:
        return None, f"BAI ≤ 0 ({debt_year.pretax_income:,.0f} EUR)"
    rate = debt_year.tax_provision / debt_year.pretax_income
    if not 0.0 <= rate <= 1.0:
        return None, f"tipo efectivo {rate:.1%} fuera de [0 %, 100 %]"
    return rate, None


# FCFF histórico = CFO + intereses·(1 − t) − Capex.
def historical_fcff(year: HistoricalYear, tax_rate: float) -> float:
    """Calcula el flujo de caja libre para la empresa de un ejercicio histórico.

    Args:
        year: Datos del ejercicio (EUR).
        tax_rate: Tipo impositivo efectivo del ejercicio, en decimal.

    Returns:
        FCFF en EUR.
    """
    return (
        year.operating_cash_flow
        + year.interest_expense * (1.0 - tax_rate)
        - year.capital_expenditure
    )


# Calcula crecimientos, márgenes, t, FCFF y FCFF/Net Income por año y sus medias.
def compute_historical_ratios(company: Company) -> HistoricalRatios:
    """Calcula los ratios históricos de la compañía.

    Args:
        company: Compañía con al menos 2 ejercicios históricos y datos de impuestos
            para cada uno de ellos.

    Returns:
        Ratios por ejercicio, medias y avisos de años excluidos.

    Raises:
        ValueError: Si falta el BAI/provisión de algún ejercicio histórico o si
            ningún año permite calcular el ratio FCFF / Net Income.
    """
    debt_by_year = {d.fiscal_year: d for d in company.debt_cost_data}
    missing = [h.fiscal_year for h in company.historicals if h.fiscal_year not in debt_by_year]
    if missing:
        raise ValueError(
            f"Faltan datos de impuestos (BAI, provisión) para los ejercicios {missing}"
        )

    growth = {
        curr.fiscal_year: curr.revenue / prev.revenue - 1.0
        for prev, curr in zip(company.historicals, company.historicals[1:], strict=False)
    }
    margin = {h.fiscal_year: h.net_income / h.revenue for h in company.historicals}

    tax_rates: dict[int, float] = {}
    fcff: dict[int, float] = {}
    conversion: dict[int, float] = {}
    warnings: list[str] = []
    for h in company.historicals:
        rate, reason = effective_tax_rate(debt_by_year[h.fiscal_year])
        if rate is None:
            warnings.append(f"{h.fiscal_year} excluido de FCFF/Net Income: {reason}")
            continue
        tax_rates[h.fiscal_year] = rate
        fcff[h.fiscal_year] = historical_fcff(h, rate)
        if h.net_income <= 0:
            warnings.append(
                f"{h.fiscal_year} excluido de FCFF/Net Income: Net Income ≤ 0 "
                f"({h.net_income:,.0f} EUR)"
            )
            continue
        conversion[h.fiscal_year] = fcff[h.fiscal_year] / h.net_income

    if not conversion:
        raise ValueError(
            "Ningún ejercicio permite calcular FCFF / Net Income: " + "; ".join(warnings)
        )

    return HistoricalRatios(
        revenue_growth_by_year=growth,
        net_margin_by_year=margin,
        tax_rate_by_year=tax_rates,
        fcff_by_year=fcff,
        fcff_to_net_income_by_year=conversion,
        average_revenue_growth=float(np.mean(list(growth.values()))),
        average_net_margin=float(np.mean(list(margin.values()))),
        average_fcff_to_net_income=float(np.mean(list(conversion.values()))),
        warnings=tuple(warnings),
    )
