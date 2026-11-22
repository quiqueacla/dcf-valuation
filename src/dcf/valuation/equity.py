"""Piezas comunes a los modelos FCFE (fcfe y fcfe_fin): Ke elegido, descuento y escenarios.

Funciones puras, sin I/O. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import (
    CostOfEquityResult,
    MarketInputs,
    MarketRate,
    compute_cost_of_equity,
)
from dcf.model.discount_rate import DiscountRateChoice, choose_discount_rate
from dcf.model.revenue_projection import EstimateCase
from dcf.valuation.discounting import (
    DiscountedFlows,
    discount_with_terminal_value,
    scenario_inputs,
    value_per_share,
)
from dcf.valuation.enterprise import TerminalFn
from dcf.valuation.scenarios import ScenarioConfig, ScenarioName, ScenarioResult

EquityFlowsForCase = Callable[[EstimateCase], tuple[list[float], tuple[str, ...], TerminalFn]]
"""Función (estimación de ventas) → (FCFE proyectados, avisos, VT en función de (Ke, g))."""


# Ke calculado (o None si falla y hay override) y tasa elegida por precedencia.
def resolve_cost_of_equity(
    company: Company, market_inputs: MarketInputs, rate_override: MarketRate | None
) -> tuple[CostOfEquityResult | None, DiscountRateChoice]:
    """Calcula Ke y elige la tasa de descuento (forzada o calculada).

    Args:
        company: Compañía con la beta de la fuente.
        market_inputs: rf, PRM y beta.
        rate_override: Ke forzado; ``None`` = el calculado.

    Returns:
        Ke calculado (``None`` si no se pudo y hay override) y tasa elegida.

    Raises:
        ValueError: Si Ke no se puede calcular y no hay override.
    """
    equity_cost: CostOfEquityResult | None
    try:
        equity_cost, error = compute_cost_of_equity(company, market_inputs), None
    except ValueError as exc:
        if rate_override is None:
            raise
        equity_cost, error = None, str(exc)
    rate = choose_discount_rate(
        "Ke", None if equity_cost is None else equity_cost.cost_of_equity, error, rate_override
    )
    return equity_cost, rate


# Valor de los fondos propios: Σ FCFE_k / (1 + Ke)^k + VT / (1 + Ke)^N.
def discount_equity(
    flows: Sequence[float], cost_of_equity: float, terminal_growth: float, terminal: TerminalFn
) -> DiscountedFlows:
    """Descuenta los FCFE proyectados y el valor terminal a Ke.

    Args:
        flows: FCFE proyectados, años 1..N (al menos uno).
        cost_of_equity: Ke en decimal.
        terminal_growth: g terminal en decimal.
        terminal: VT en función de (Ke, g).

    Returns:
        Descuento; ``total`` = valor de los fondos propios antes de minoritarios.

    Raises:
        ValueError: Si no hay flujos o el VT no es válido (g ≥ Ke, g ≥ rf…).
    """
    if not flows:
        raise ValueError("Se necesita al menos un FCFE proyectado")
    return discount_with_terminal_value(
        flows, cost_of_equity, terminal(cost_of_equity, terminal_growth)
    )


# Escenarios FCFE: cada uno proyecta sus FCFE y los descuenta a su Ke y g.
def compute_equity_scenarios(
    company: Company,
    flows_for: EquityFlowsForCase,
    cost_of_equity: float,
    assumptions: Assumptions,
    config: ScenarioConfig,
    minority_interest: float = 0.0,
) -> tuple[ScenarioResult, ...]:
    """Calcula el valor por acción de los tres escenarios de un modelo FCFE.

    El modo ``coste`` desplaza Ke con ``wacc_shift``.

    Args:
        company: Compañía (acciones diluidas).
        flows_for: Proyección FCFE del modelo para una estimación de ventas.
        cost_of_equity: Ke central, en decimal.
        assumptions: g terminal central.
        config: Modos activos y desplazamientos.
        minority_interest: Minoritarios que se restan al valor descontado (fcfe desde el
            FCFF consolidado); 0 en fcfe_fin, cuyo Net Income ya es el atribuible.

    Returns:
        Escenarios en orden bajista, neutro, alcista; los no válidos con ``error``.
    """
    results: list[ScenarioResult] = []
    for name in ScenarioName:
        case, ke, g = scenario_inputs(name, config, cost_of_equity, assumptions.terminal_growth)
        flows, warnings, terminal = flows_for(case)
        try:
            if ke <= 0:
                raise ValueError(f"Ke del escenario no positivo ({ke})")
            d = discount_equity(flows, ke, g, terminal)
            equity = d.total - minority_interest
            if equity <= 0:
                raise ValueError(f"Valor de los fondos propios no positivo ({equity:,.0f} EUR)")
        except ValueError as exc:
            results.append(ScenarioResult(name, case, ke, g, None, None, None, str(exc), warnings))
            continue
        results.append(
            ScenarioResult(
                name=name,
                estimate_case=case,
                discount_rate=ke,
                terminal_growth=g,
                total_value=equity,
                terminal_value_weight=d.terminal_value_present / d.total,
                value_per_share=value_per_share(equity, company.balance.diluted_shares),
                warnings=warnings,
            )
        )
    return tuple(results)
