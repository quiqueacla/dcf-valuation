"""Modelo FCFE (1.2, industriales): FCFE = FCFF − Int·(1−t) + ΔDeuda neta. Puro, sin I/O.

Parte de la proyección del modelo fcff (EBIT, D&A, Capex, circulante) y modela la deuda
con apalancamiento constante: la deuda neta financia la parte D/(D+E) de la reinversión
neta. Fórmulas en ``docs/metodologia.md`` §13 (``docs/dcf_metodos.md`` §1.2).
Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcf.company import Company, ValuationModel, required
from dcf.model.fcff_projection import FcffFlow, FcffRatios, project_fcff
from dcf.model.revenue_projection import EstimateCase

FCFE = ValuationModel.FCFE


@dataclass(frozen=True, slots=True)
class FcfeLeverage:
    """Supuestos de deuda del modelo FCFE.

    Attributes:
        cost_of_debt: Kd medio histórico (intereses / deuda total), antes de impuestos.
        debt_ratio: D / (D + E) con D contable y E de mercado: parte de la reinversión
            neta que se financia con deuda (apalancamiento constante).
        net_debt_0: Deuda neta al cierre del último ejercicio (deuda total − caja).
        tax_rate: Tipo impositivo (mediana) para el ahorro fiscal de los intereses.
    """

    cost_of_debt: float
    debt_ratio: float
    net_debt_0: float
    tax_rate: float


@dataclass(frozen=True, slots=True)
class FcfeFlow:
    """Un año proyectado del modelo FCFE, antes de descontar.

    Attributes:
        operating: Año FCFF del que parte (ventas, EBIT, NOPAT, D&A, Capex, ΔNWC, FCFF).
        net_debt_begin: Deuda neta al inicio del año.
        interest: Intereses del año: Kd × deuda neta inicial (negativo si hay caja neta).
        reinvestment: Reinversión neta: Capex − D&A + ΔNWC.
        net_debt_change: Variación de la deuda neta: D/(D+E) × reinversión neta.
        net_income: Beneficio neto: (EBIT − intereses) · (1 − t).
        fcfe: Flujo para el accionista: FCFF − intereses · (1 − t) + ΔDeuda neta.
        net_debt_end: Deuda neta al cierre.
    """

    operating: FcffFlow
    net_debt_begin: float
    interest: float
    reinvestment: float
    net_debt_change: float
    net_income: float
    fcfe: float
    net_debt_end: float

    # Ejercicio proyectado.
    @property
    def fiscal_year(self) -> int:
        """Ejercicio proyectado."""
        return self.operating.fiscal_year


@dataclass(frozen=True, slots=True)
class FcfeProjection:
    """Proyección FCFE del horizonte explícito.

    Attributes:
        flows: Años proyectados, en orden.
        projection_growth: Crecimiento de ventas aplicado sin estimación de analistas.
        warnings: Avisos de la proyección.
    """

    flows: tuple[FcfeFlow, ...]
    projection_growth: float
    warnings: tuple[str, ...] = ()


# Kd medio, D/(D+E) con E de mercado y deuda neta inicial.
def leverage_inputs(company: Company, tax_rate: float) -> FcfeLeverage:
    """Calcula los supuestos de deuda del modelo FCFE.

    Args:
        company: Compañía con deuda e intereses históricos, balance y cotización.
        tax_rate: Tipo impositivo (mediana) en decimal.

    Returns:
        Kd, D/(D+E), deuda neta inicial y t.

    Raises:
        ValueError: Si falta la deuda total o la caja del último balance, o la empresa
            tiene deuda pero ningún año permite calcular Kd.
    """
    balance = company.balance
    debt = required(balance.total_debt, "la deuda total", FCFE)
    cash = required(balance.cash, "la caja", FCFE)
    kd_years = [
        d.interest_expense / d.total_debt for d in company.debt_cost_data if d.total_debt > 0
    ]
    if debt > 0 and not kd_years:
        raise ValueError("La empresa tiene deuda pero ningún ejercicio permite calcular Kd")
    equity = balance.share_price * balance.diluted_shares
    return FcfeLeverage(
        cost_of_debt=float(np.mean(kd_years)) if kd_years else 0.0,
        debt_ratio=debt / (debt + equity),
        net_debt_0=debt - cash,
        tax_rate=tax_rate,
    )


# FCFE_t = FCFF_t − Kd·DN_{t−1}·(1−t) + D/(D+E)·(Capex − D&A + ΔNWC).
def project_fcfe(
    company: Company,
    ratios: FcffRatios,
    leverage: FcfeLeverage,
    projection_years: int,
    estimate_case: EstimateCase = EstimateCase.AVERAGE,
) -> FcfeProjection:
    """Proyecta los FCFE del horizonte explícito desde la proyección FCFF.

    Args:
        company: Compañía con históricos y, opcionalmente, estimaciones de ventas.
        ratios: Ratios FCFF (márgenes, t y circulante).
        leverage: Supuestos de deuda.
        projection_years: Número de años a proyectar (≥ 1).
        estimate_case: Estimación de analistas a usar (baja, media o alta).

    Returns:
        FCFE proyectados, crecimiento medio aplicado y avisos.
    """
    operating = project_fcff(company, ratios, projection_years, estimate_case)
    t = leverage.tax_rate
    net_debt = leverage.net_debt_0
    flows: list[FcfeFlow] = []
    for f in operating.flows:
        interest = leverage.cost_of_debt * net_debt
        reinvestment = f.capital_expenditure - f.depreciation_amortization + f.nwc_change
        change = leverage.debt_ratio * reinvestment
        flows.append(
            FcfeFlow(
                operating=f,
                net_debt_begin=net_debt,
                interest=interest,
                reinvestment=reinvestment,
                net_debt_change=change,
                net_income=(f.ebit - interest) * (1.0 - t),
                fcfe=f.fcff - interest * (1.0 - t) + change,
                net_debt_end=net_debt + change,
            )
        )
        net_debt += change
    return FcfeProjection(tuple(flows), operating.projection_growth, operating.warnings)


# Deuda neta de cada cierre: deuda total − caja.
def historical_net_debt(company: Company) -> dict[int, float]:
    """Calcula la deuda neta histórica de cada ejercicio.

    Args:
        company: Compañía con deuda total (coste de la deuda) y caja de cada ejercicio.

    Returns:
        Deuda neta = deuda total − caja por ejercicio, en EUR (deuda financiera que queda
        tras usar toda la caja); se omiten los años sin caja publicada.
    """
    debt = {d.fiscal_year: d.total_debt for d in company.debt_cost_data}
    return {
        h.fiscal_year: debt[h.fiscal_year] - h.cash
        for h in company.historicals
        if h.cash is not None and h.fiscal_year in debt
    }


# FCFE histórico: FCFF_i − Int_i·(1−t) + (DN_i − DN_{i−1}), con DN = deuda total − caja.
def historical_fcfe(company: Company, ratios: FcffRatios) -> dict[int, float]:
    """Calcula el FCFE histórico con el mismo criterio que la proyección.

    Args:
        company: Compañía con deuda, intereses y caja de cada ejercicio.
        ratios: Ratios FCFF (FCFF histórico y t).

    Returns:
        FCFE por ejercicio desde el segundo; se omiten los años sin caja publicada.
    """
    debt = {d.fiscal_year: d for d in company.debt_cost_data}
    net_debt = historical_net_debt(company)
    result: dict[int, float] = {}
    for prev, curr in zip(company.historicals, company.historicals[1:], strict=False):
        y = curr.fiscal_year
        if y not in ratios.fcff_by_year or y not in net_debt or prev.fiscal_year not in net_debt:
            continue
        result[y] = (
            ratios.fcff_by_year[y]
            - debt[y].interest_expense * (1.0 - ratios.tax_rate)
            + net_debt[y]
            - net_debt[prev.fiscal_year]
        )
    return result
