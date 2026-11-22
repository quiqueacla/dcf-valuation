"""Modelo FCFE_FIN (financieras): FCFE = NI − reinversión en fondos propios, a Ke.

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §10 y §12 (valor terminal).
Tasas en decimal (0.08 = 8 %), importes en EUR (``float``, sin redondeo interno).
"""

from __future__ import annotations

from datetime import datetime

import dcf
from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.checks import historical_flow_warnings
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.discount_rate import rate_warnings
from dcf.model.fcfe_fin_projection import (
    FcfeFinProjection,
    FcfeFinRatios,
    compute_fcfe_fin_ratios,
    project_fcfe_fin,
)
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
from dcf.valuation.fcfe_fin_result import FcfeFinProjectedYear, FcfeFinValuationResult
from dcf.valuation.scenarios import ScenarioConfig


# Base del VT: FCFE_N, Net Income_N (P/E y value driver) y ROE (forzado o histórico).
def terminal_basis(
    company: Company, projection: FcfeFinProjection, options: TerminalOptions
) -> TerminalBasis:
    """Construye los datos del año N para el valor terminal de fcfe_fin.

    Args:
        company: Compañía con Net Income y fondos propios.
        projection: Proyección FCFE_FIN.
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


# FCFE histórico de una financiera: NI_i − (FP_i − FP_{i−1}).
def historical_fcfe(ratios: FcfeFinRatios, company: Company) -> dict[int, float]:
    """Calcula el FCFE histórico: beneficio menos el aumento de fondos propios.

    Args:
        ratios: Ratios FCFE_FIN (fondos propios por año).
        company: Compañía (Net Income por año).

    Returns:
        FCFE por ejercicio, desde el segundo.
    """
    equity = ratios.equity_by_year
    return {
        curr.fiscal_year: curr.net_income - (equity[curr.fiscal_year] - equity[prev.fiscal_year])
        for prev, curr in zip(company.historicals, company.historicals[1:], strict=False)
    }


# Valoración FCFE_FIN: ratios → proyección → Ke → fondos propios → por acción.
def value_company(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
    rate_override: MarketRate | None = None,
    terminal: TerminalOptions | None = None,
) -> FcfeFinValuationResult:
    """Valora la compañía con el modelo FCFE_FIN (financieras, a Ke).

    Args:
        company: Datos de la compañía en EUR, con fondos propios de cada ejercicio.
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
    ratios = compute_fcfe_fin_ratios(company)
    projection = project_fcfe_fin(company, ratios, assumptions.projection_years)
    equity_cost, rate = resolve_cost_of_equity(company, market_inputs, rate_override)
    ke, rf, g = rate.value, market_inputs.risk_free_rate.value, assumptions.terminal_growth
    basis = terminal_basis(company, projection, options)
    tv = terminal_value(options, basis, ke, g, rf, "Ke")
    fn = terminal_function(options, basis, rf, "Ke")
    flows = [f.fcfe for f in projection.flows]
    d = discount_equity(flows, ke, g, fn)
    shares = company.balance.diluted_shares

    def value_for(r: float, growth: float) -> float:
        return value_per_share(discount_equity(flows, r, growth, fn).total, shares)

    def flows_for(case: EstimateCase) -> tuple[list[float], tuple[str, ...], TerminalFn]:
        p = project_fcfe_fin(company, ratios, assumptions.projection_years, case)
        scenario_fn = terminal_function(options, terminal_basis(company, p, options), rf, "Ke")
        return [f.fcfe for f in p.flows], p.warnings, scenario_fn

    projections = tuple(
        FcfeFinProjectedYear(flow=f, discount_factor=factor, present_value=pv)
        for f, factor, pv in zip(
            projection.flows, d.discount_factors, d.present_values, strict=True
        )
    )
    checks = historical_flow_warnings("FCFE", historical_fcfe(ratios, company), options.thresholds)
    return FcfeFinValuationResult(
        ticker=company.info.ticker,
        source=company.info.source,
        data_date=company.info.data_date,
        valuation_date=valuation_date,
        code_version=dcf.__version__,
        assumptions=assumptions,
        ratios=ratios,
        cost_of_equity=equity_cost,
        discount_rate=rate,
        market_inputs=market_inputs,
        projections=projections,
        projection_growth=projection.projection_growth,
        terminal_fcfe_fin=tv.next_flow if tv.next_flow is not None else float("nan"),
        terminal_value=d.terminal_value,
        terminal_value_present=d.terminal_value_present,
        equity_value=d.total,
        value_per_share=value_per_share(d.total, shares),
        sensitivity=sensitivity_grid(value_for, ke, g, rf),
        scenarios=(
            compute_equity_scenarios(company, flows_for, ke, assumptions, scenario_config)
            if scenario_config is not None
            else ()
        ),
        warnings=(
            rate_warnings(rate)
            + (() if equity_cost is None else equity_cost.warnings)
            + projection.warnings
        ),
        terminal=tv,
        checks=checks + tv.warnings,
    )
