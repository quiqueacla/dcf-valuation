"""Modelo FCFE (1.2, industriales): FCFE = FCFF − Int·(1−t) + ΔDeuda neta, a Ke.

Útil en industriales con mucha deuda o deuda variable: valora directamente el flujo del
accionista. Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §13.
Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from datetime import datetime

import dcf
from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.checks import historical_flow_warnings
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.discount_rate import rate_warnings
from dcf.model.fcfe_projection import (
    FcfeProjection,
    historical_fcfe,
    leverage_inputs,
    project_fcfe,
)
from dcf.model.fcff_projection import compute_fcff_ratios
from dcf.model.returns import historical_roe
from dcf.model.revenue_projection import EstimateCase
from dcf.model.terminal_methods import (
    TerminalBasis,
    TerminalOptions,
    terminal_function,
    terminal_value,
)
from dcf.valuation.discounting import sensitivity_grid, value_per_share
from dcf.valuation.enterprise import TerminalFn
from dcf.valuation.equity import compute_equity_scenarios, discount_equity, resolve_cost_of_equity
from dcf.valuation.fcfe_result import FcfeProjectedYear, FcfeValuationResult
from dcf.valuation.scenarios import ScenarioConfig


# Base del VT: FCFE_N, Net Income_N (P/E y value driver) y ROE (forzado o histórico).
def terminal_basis(
    company: Company, projection: FcfeProjection, options: TerminalOptions
) -> TerminalBasis:
    """Construye los datos del año N para el valor terminal del FCFE.

    Args:
        company: Compañía (fondos propios para el ROE histórico).
        projection: Proyección FCFE.
        options: Opciones del VT (ROE forzado).

    Returns:
        Base del VT.
    """
    last = projection.flows[-1]
    roe = options.ronic or historical_roe(company).as_rate(company.info.data_date)
    return TerminalBasis(
        last_flow=last.fcfe,
        profit_last=last.net_income,
        profit_name="Net Income",
        metric_last=last.net_income,
        metric_name="Net Income",
        return_name="ROE",
        ronic=roe,
    )


# Valoración FCFE: ratios FCFF → deuda → FCFE → Ke → fondos propios → por acción.
def value_company(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
    rate_override: MarketRate | None = None,
    terminal: TerminalOptions | None = None,
) -> FcfeValuationResult:
    """Valora la compañía con el modelo FCFE 1.2 (industriales, a Ke).

    Args:
        company: Datos de la compañía en EUR (los del modelo fcff más deuda y caja).
        market_inputs: rf, PRM y configuración de la beta.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC.
        scenario_config: Modos de escenario; ``None`` = sin escenarios.
        rate_override: Ke forzado; el calculado pasa a informativo.
        terminal: Método de VT, múltiplo, ROE y umbrales; ``None`` = el método de
            ``company.info.terminal_method``.

    Returns:
        Resultado completo y trazable.

    Raises:
        ValueError: Si algún dato o supuesto es inválido (ver cada paso).
    """
    options = terminal or TerminalOptions(company.info.terminal_method)
    ratios = compute_fcff_ratios(company)
    leverage = leverage_inputs(company, ratios.tax_rate)
    projection = project_fcfe(company, ratios, leverage, assumptions.projection_years)
    equity_cost, rate = resolve_cost_of_equity(company, market_inputs, rate_override)
    ke, rf, g = rate.value, market_inputs.risk_free_rate.value, assumptions.terminal_growth
    basis = terminal_basis(company, projection, options)
    tv = terminal_value(options, basis, ke, g, rf, "Ke")
    fn = terminal_function(options, basis, rf, "Ke")
    flows = [f.fcfe for f in projection.flows]
    d = discount_equity(flows, ke, g, fn)
    minority = company.balance.minority_interest
    shares = company.balance.diluted_shares
    equity = d.total - minority

    def value_for(r: float, growth: float) -> float:
        return value_per_share(discount_equity(flows, r, growth, fn).total - minority, shares)

    def flows_for(case: EstimateCase) -> tuple[list[float], tuple[str, ...], TerminalFn]:
        p = project_fcfe(company, ratios, leverage, assumptions.projection_years, case)
        scenario_fn = terminal_function(options, terminal_basis(company, p, options), rf, "Ke")
        return [f.fcfe for f in p.flows], p.warnings, scenario_fn

    projections = tuple(
        FcfeProjectedYear(flow=f, discount_factor=factor, present_value=pv)
        for f, factor, pv in zip(
            projection.flows, d.discount_factors, d.present_values, strict=True
        )
    )
    checks = historical_flow_warnings(
        "FCFE", historical_fcfe(company, ratios), options.thresholds
    ) + historical_flow_warnings("FCFF", ratios.fcff_by_year, options.thresholds)
    return FcfeValuationResult(
        ticker=company.info.ticker,
        source=company.info.source,
        data_date=company.info.data_date,
        valuation_date=valuation_date,
        code_version=dcf.__version__,
        assumptions=assumptions,
        ratios=ratios,
        leverage=leverage,
        cost_of_equity=equity_cost,
        discount_rate=rate,
        market_inputs=market_inputs,
        projections=projections,
        projection_growth=projection.projection_growth,
        terminal_value=d.terminal_value,
        terminal_value_present=d.terminal_value_present,
        present_value_total=d.total,
        minority_interest=minority,
        equity_value=equity,
        value_per_share=value_per_share(equity, shares),
        sensitivity=sensitivity_grid(value_for, ke, g, rf),
        scenarios=(
            compute_equity_scenarios(company, flows_for, ke, assumptions, scenario_config, minority)
            if scenario_config is not None
            else ()
        ),
        warnings=(
            rate_warnings(rate)
            + (() if equity_cost is None else equity_cost.warnings)
            + projection.warnings
            + ratios.warnings
        ),
        terminal=tv,
        checks=checks + tv.warnings,
    )
