"""Modelo FCFE (financieras): FCFE descontado a Ke y valor por acción.

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §3, §5 y §6.
Tasas en decimal (0.08 = 8 %), importes en EUR (``float``, sin redondeo interno).
"""

from __future__ import annotations

from datetime import datetime

import dcf
from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs, compute_cost_of_equity
from dcf.model.fcfe_projection import (
    FcfeProjection,
    FcfeRatios,
    compute_fcfe_ratios,
    project_fcfe,
    terminal_fcfe,
)
from dcf.model.terminal_value import gordon_from_next_flow
from dcf.valuation.discounting import (
    DiscountedFlows,
    discount_with_terminal_value,
    scenario_inputs,
    sensitivity_grid,
    value_per_share,
)
from dcf.valuation.fcfe_result import FcfeProjectedYear, FcfeValuationResult
from dcf.valuation.scenarios import ScenarioConfig, ScenarioName, ScenarioResult


# Fondos propios = Σ FCFE_k / (1 + Ke)^k + VT / (1 + Ke)^N, con VT = FCFE_{N+1} / (Ke − g).
def discount_fcfe(
    projection: FcfeProjection, cost_of_equity: float, terminal_growth: float, risk_free_rate: float
) -> tuple[float, DiscountedFlows]:
    """Descuenta los FCFE proyectados y el valor terminal a Ke.

    Args:
        projection: FCFE proyectados (al menos un año).
        cost_of_equity: Ke en decimal.
        terminal_growth: g terminal en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.

    Returns:
        FCFE del año N+1 y el descuento (``total`` = valor de los fondos propios).

    Raises:
        ValueError: Si no hay flujos, si g ≥ Ke o g ≥ rf.
    """
    if not projection.flows:
        raise ValueError("Se necesita al menos un FCFE proyectado")
    next_fcfe = terminal_fcfe(projection.flows[-1], terminal_growth)
    tv = gordon_from_next_flow(next_fcfe, cost_of_equity, terminal_growth, risk_free_rate)
    flows = [f.fcfe for f in projection.flows]
    return next_fcfe, discount_with_terminal_value(flows, cost_of_equity, tv)


# Valora los escenarios bajista, neutro y alcista; un escenario inválido no detiene el resto.
def compute_scenarios(
    company: Company,
    ratios: FcfeRatios,
    cost_of_equity: float,
    risk_free_rate: float,
    assumptions: Assumptions,
    config: ScenarioConfig,
) -> tuple[ScenarioResult, ...]:
    """Calcula el valor por acción de los tres escenarios con el modelo FCFE.

    El modo ``coste`` desplaza Ke (en lugar del WACC) con ``wacc_shift``.

    Args:
        company: Datos de la compañía en EUR.
        ratios: Ratios FCFE (margen y fondos propios comunes a todos).
        cost_of_equity: Ke central, en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.
        assumptions: g terminal central y horizonte.
        config: Modos activos y desplazamientos.

    Returns:
        Escenarios en orden bajista, neutro, alcista. Si un escenario incumple
        g < Ke o g < rf, se devuelve con ``error`` y sin valores.
    """
    results: list[ScenarioResult] = []
    for name in ScenarioName:
        case, ke, g = scenario_inputs(name, config, cost_of_equity, assumptions.terminal_growth)
        projection = project_fcfe(company, ratios, assumptions.projection_years, case)
        try:
            if ke <= 0:
                raise ValueError(f"Ke del escenario no positivo ({ke})")
            _, d = discount_fcfe(projection, ke, g, risk_free_rate)
            if d.total <= 0:
                raise ValueError(f"Valor de los fondos propios no positivo ({d.total:,.0f} EUR)")
        except ValueError as exc:
            results.append(
                ScenarioResult(name, case, ke, g, None, None, None, str(exc), projection.warnings)
            )
            continue
        results.append(
            ScenarioResult(
                name=name,
                estimate_case=case,
                discount_rate=ke,
                terminal_growth=g,
                total_value=d.total,
                terminal_value_weight=d.terminal_value_present / d.total,
                value_per_share=value_per_share(d.total, company.balance.diluted_shares),
                warnings=projection.warnings,
            )
        )
    return tuple(results)


# Valoración FCFE completa: ratios → proyección → Ke → fondos propios → por acción.
def value_company(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
) -> FcfeValuationResult:
    """Valora la compañía con el modelo FCFE (FCFE descontado a Ke).

    Args:
        company: Datos de la compañía en EUR, con fondos propios de cada ejercicio.
        market_inputs: rf, PRM y configuración de la beta.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC.
        scenario_config: Modos de escenario; ``None`` = sin escenarios.

    Returns:
        Resultado completo y trazable.

    Raises:
        ValueError: Si algún dato o supuesto es inválido (ver cada paso).
    """
    ratios = compute_fcfe_ratios(company)
    projection = project_fcfe(company, ratios, assumptions.projection_years)
    equity_cost = compute_cost_of_equity(company, market_inputs)
    ke, rf = equity_cost.cost_of_equity, market_inputs.risk_free_rate.value
    g = assumptions.terminal_growth
    next_fcfe, d = discount_fcfe(projection, ke, g, rf)
    shares = company.balance.diluted_shares

    def value_for(rate: float, growth: float) -> float:
        return value_per_share(discount_fcfe(projection, rate, growth, rf)[1].total, shares)

    projections = tuple(
        FcfeProjectedYear(flow=f, discount_factor=factor, present_value=pv)
        for f, factor, pv in zip(
            projection.flows, d.discount_factors, d.present_values, strict=True
        )
    )
    return FcfeValuationResult(
        ticker=company.info.ticker,
        source=company.info.source,
        data_date=company.info.data_date,
        valuation_date=valuation_date,
        code_version=dcf.__version__,
        assumptions=assumptions,
        ratios=ratios,
        cost_of_equity=equity_cost,
        projections=projections,
        projection_growth=projection.projection_growth,
        terminal_fcfe=next_fcfe,
        terminal_value=d.terminal_value,
        terminal_value_present=d.terminal_value_present,
        equity_value=d.total,
        value_per_share=value_per_share(d.total, shares),
        sensitivity=sensitivity_grid(value_for, ke, g, rf),
        scenarios=(
            compute_scenarios(company, ratios, ke, rf, assumptions, scenario_config)
            if scenario_config is not None
            else ()
        ),
        warnings=equity_cost.warnings + projection.warnings,
    )
