"""Modelo FCFF: FCFF descontado al WACC, puente a fondos propios y valor por acción.

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §5-§7.
Tasas en decimal (0.08 = 8 %), importes en EUR (``float``, sin redondeo interno).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

import dcf
from dcf.company import BalanceSnapshot, Company, ValuationModel, required
from dcf.defaults import (
    SENSITIVITY_GROWTH_STEP,
    SENSITIVITY_STEPS_EACH_SIDE,
    SENSITIVITY_WACC_STEP,
)
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.model.fcff_projection import project_cash_flows
from dcf.model.fcff_ratios import HistoricalRatios, compute_historical_ratios
from dcf.model.terminal_value import gordon_terminal_value
from dcf.model.wacc import compute_wacc
from dcf.valuation.discounting import (
    discount_with_terminal_value,
    scenario_inputs,
    sensitivity_grid,
    value_per_share,
)
from dcf.valuation.fcff_result import ProjectedYear, ValuationResult
from dcf.valuation.scenarios import ScenarioConfig, ScenarioName, ScenarioResult

FCFF = ValuationModel.FCFF


@dataclass(frozen=True, slots=True)
class EnterpriseValue:
    """Valor de empresa y su descomposición.

    Attributes:
        discount_factors: 1 / (1 + WACC)^k para k = 1..N.
        present_values: Valor actual de cada FCFF proyectado.
        terminal_value: Valor terminal (Gordon) al final del año N, sin descontar.
        terminal_value_present: Valor terminal descontado a hoy.
        enterprise_value: Suma de los valores actuales de los FCFF y del valor terminal.
    """

    discount_factors: tuple[float, ...]
    present_values: tuple[float, ...]
    terminal_value: float
    terminal_value_present: float
    enterprise_value: float


# VE = Σ FCFF_k / (1 + WACC)^k + VT_Gordon / (1 + WACC)^N.
def compute_enterprise_value(
    fcffs: Sequence[float], wacc: float, terminal_growth: float, risk_free_rate: float
) -> EnterpriseValue:
    """Descuenta los FCFF proyectados y el valor terminal.

    Args:
        fcffs: FCFF proyectados, en EUR, años 1..N en orden.
        wacc: WACC en decimal.
        terminal_growth: g terminal en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.

    Returns:
        Valor de empresa y su descomposición.

    Raises:
        ValueError: Si no hay flujos, si g ≥ WACC o g ≥ rf.
    """
    if not fcffs:
        raise ValueError("Se necesita al menos un FCFF proyectado")
    tv = gordon_terminal_value(float(fcffs[-1]), wacc, terminal_growth, risk_free_rate)
    d = discount_with_terminal_value(fcffs, wacc, tv)
    return EnterpriseValue(
        discount_factors=d.discount_factors,
        present_values=d.present_values,
        terminal_value=d.terminal_value,
        terminal_value_present=d.terminal_value_present,
        enterprise_value=d.total,
    )


# Fondos propios = VE − deuda total + caja − minoritarios.
def equity_value(enterprise_value: float, balance: BalanceSnapshot) -> float:
    """Pasa del valor de empresa al valor de los fondos propios.

    Args:
        enterprise_value: Valor de empresa, en EUR.
        balance: Último balance (deuda total, caja, minoritarios), en EUR.

    Returns:
        Valor de los fondos propios en EUR (puede ser negativo).

    Raises:
        ValueError: Si el balance no tiene deuda total o caja.
    """
    debt = required(balance.total_debt, "la deuda total", FCFF)
    cash = required(balance.cash, "la caja", FCFF)
    return enterprise_value - debt + cash - balance.minority_interest


# Tabla de valor por acción para WACC (filas) × g (columnas); NaN si g ≥ WACC o g ≥ rf.
def sensitivity_table(
    fcffs: Sequence[float],
    balance: BalanceSnapshot,
    wacc: float,
    terminal_growth: float,
    risk_free_rate: float,
    wacc_step: float = SENSITIVITY_WACC_STEP,
    growth_step: float = SENSITIVITY_GROWTH_STEP,
    steps_each_side: int = SENSITIVITY_STEPS_EACH_SIDE,
) -> pd.DataFrame:
    """Calcula la sensibilidad del valor por acción al WACC y al g terminal.

    Args:
        fcffs: FCFF proyectados, en EUR (no dependen del WACC ni de g).
        balance: Último balance para el puente a fondos propios.
        wacc: WACC central, en decimal.
        terminal_growth: g central, en decimal.
        risk_free_rate: rf en decimal, para invalidar celdas con g ≥ rf.
        wacc_step: Paso entre filas, en decimal.
        growth_step: Paso entre columnas, en decimal.
        steps_each_side: Pasos a cada lado del valor central.

    Returns:
        DataFrame con índice ``discount_rate`` (WACC) y columnas ``terminal_growth``
        (en decimal) y el valor por acción en EUR. Celdas inválidas a NaN.
    """

    def value_for(w: float, g: float) -> float:
        ev = compute_enterprise_value(fcffs, w, g, risk_free_rate)
        return value_per_share(equity_value(ev.enterprise_value, balance), balance.diluted_shares)

    return sensitivity_grid(
        value_for, wacc, terminal_growth, risk_free_rate, wacc_step, growth_step, steps_each_side
    )


# Valora los escenarios bajista, neutro y alcista; un escenario inválido no detiene el resto.
def compute_scenarios(
    company: Company,
    ratios: HistoricalRatios,
    wacc: float,
    risk_free_rate: float,
    assumptions: Assumptions,
    config: ScenarioConfig,
) -> tuple[ScenarioResult, ...]:
    """Calcula el valor por acción de los tres escenarios.

    Args:
        company: Datos de la compañía en EUR.
        ratios: Ratios históricos (márgenes y conversión a caja comunes a todos).
        wacc: WACC central, en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.
        assumptions: g terminal central y horizonte.
        config: Modos activos y desplazamientos.

    Returns:
        Escenarios en orden bajista, neutro, alcista. Si un escenario incumple
        g < WACC o g < rf, se devuelve con ``error`` y sin valores.
    """
    results: list[ScenarioResult] = []
    for name in ScenarioName:
        case, w, g = scenario_inputs(name, config, wacc, assumptions.terminal_growth)
        projection = project_cash_flows(company, ratios, assumptions.projection_years, case)
        try:
            if w <= 0:
                raise ValueError(f"WACC del escenario no positivo ({w})")
            ev = compute_enterprise_value([f.fcff for f in projection.flows], w, g, risk_free_rate)
        except ValueError as exc:
            results.append(
                ScenarioResult(name, case, w, g, None, None, None, str(exc), projection.warnings)
            )
            continue
        equity = equity_value(ev.enterprise_value, company.balance)
        results.append(
            ScenarioResult(
                name=name,
                estimate_case=case,
                discount_rate=w,
                terminal_growth=g,
                total_value=ev.enterprise_value,
                terminal_value_weight=ev.terminal_value_present / ev.enterprise_value,
                value_per_share=value_per_share(equity, company.balance.diluted_shares),
                warnings=projection.warnings,
            )
        )
    return tuple(results)


# Valoración FCFF completa: ratios → proyección → WACC → VE → fondos propios → por acción.
def value_company(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
) -> ValuationResult:
    """Valora la compañía con el modelo FCFF (FCFF descontado al WACC).

    Args:
        company: Datos de la compañía en EUR.
        market_inputs: rf y PRM con su fuente.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC (se pasa explícito para que
            la función sea pura y reproducible).
        scenario_config: Modos de escenario; ``None`` = sin escenarios.

    Returns:
        Resultado completo y trazable.

    Raises:
        ValueError: Si algún dato o supuesto es inválido (ver cada paso).
    """
    ratios = compute_historical_ratios(company)
    projection = project_cash_flows(company, ratios, assumptions.projection_years)
    wacc = compute_wacc(company, market_inputs)
    rf = market_inputs.risk_free_rate.value
    fcffs = [f.fcff for f in projection.flows]
    ev = compute_enterprise_value(fcffs, wacc.wacc, assumptions.terminal_growth, rf)
    equity = equity_value(ev.enterprise_value, company.balance)

    projections = tuple(
        ProjectedYear(
            fiscal_year=f.fiscal_year,
            revenue=f.revenue,
            revenue_growth=f.revenue_growth,
            revenue_source=f.revenue_source,
            net_income=f.net_income,
            fcff=f.fcff,
            discount_factor=factor,
            present_value=pv,
        )
        for f, factor, pv in zip(
            projection.flows, ev.discount_factors, ev.present_values, strict=True
        )
    )

    return ValuationResult(
        ticker=company.info.ticker,
        source=company.info.source,
        data_date=company.info.data_date,
        valuation_date=valuation_date,
        code_version=dcf.__version__,
        assumptions=assumptions,
        ratios=ratios,
        wacc=wacc,
        projections=projections,
        projection_growth=projection.projection_growth,
        terminal_value=ev.terminal_value,
        terminal_value_present=ev.terminal_value_present,
        enterprise_value=ev.enterprise_value,
        equity_value=equity,
        value_per_share=value_per_share(equity, company.balance.diluted_shares),
        sensitivity=sensitivity_table(
            fcffs, company.balance, wacc.wacc, assumptions.terminal_growth, rf
        ),
        scenarios=(
            compute_scenarios(company, ratios, wacc.wacc, rf, assumptions, scenario_config)
            if scenario_config is not None
            else ()
        ),
        warnings=projection.warnings,
    )
