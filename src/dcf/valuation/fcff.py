"""Modelo FCFF (por defecto): FCFF desde el EBIT descontado al WACC (método 1.1).

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §11 y §12 (valor terminal);
WACC, VE, puente, sensibilidad y escenarios en :mod:`dcf.valuation.enterprise`.
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
from dcf.model.fcff_projection import FcffProjection, FcffRatios, compute_fcff_ratios, project_fcff
from dcf.model.returns import historical_roic
from dcf.model.revenue_projection import EstimateCase
from dcf.model.terminal_methods import (
    TerminalBasis,
    TerminalOptions,
    terminal_function,
    terminal_value,
)
from dcf.valuation.discounting import require_positive_value, value_per_share
from dcf.valuation.enterprise import (
    TerminalFn,
    compute_enterprise_value,
    compute_fcff_scenarios,
    equity_value,
    resolve_wacc,
    sensitivity_table,
)
from dcf.valuation.fcff_result import FcffProjectedYear, FcffValuationResult
from dcf.valuation.scenarios import ScenarioConfig


# Base del VT de fcff: FCFF_N, NOPAT_N, EBITDA_N = EBIT_N + D&A_N y RONIC (ROIC histórico).
def terminal_basis(
    company: Company, ratios: FcffRatios, projection: FcffProjection, options: TerminalOptions
) -> TerminalBasis:
    """Construye los datos del año N para el valor terminal de fcff.

    Args:
        company: Compañía (fondos propios y caja para el ROIC histórico).
        ratios: Ratios FCFF (t mediano).
        projection: Proyección FCFF.
        options: Opciones del VT (RONIC forzado).

    Returns:
        Base del VT.
    """
    last = projection.flows[-1]
    ronic = options.ronic or historical_roic(company, ratios.tax_rate).as_rate(
        company.info.data_date
    )
    return TerminalBasis(
        last_flow=last.fcff,
        profit_last=last.nopat,
        profit_name="NOPAT",
        metric_last=last.ebit + last.depreciation_amortization,
        metric_name="EBITDA",
        return_name="RONIC",
        ronic=ronic,
    )


# Valoración FCFF: ratios → proyección desde el EBIT → WACC → VE → fondos propios → acción.
def value_company(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
    rate_override: MarketRate | None = None,
    terminal: TerminalOptions | None = None,
) -> FcffValuationResult:
    """Valora la compañía con el modelo FCFF (FCFF desde el EBIT, al WACC).

    Args:
        company: Datos de la compañía en EUR, con EBIT, D&A y circulante comercial.
        market_inputs: rf, PRM y configuración de la beta.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC.
        scenario_config: Modos de escenario; ``None`` = sin escenarios.
        rate_override: WACC forzado (argumento o fichero); el calculado pasa a informativo.
        terminal: Método de VT, múltiplo, RONIC y umbrales; ``None`` = el método de
            ``company.info.terminal_method``.

    Returns:
        Resultado completo y trazable.

    Raises:
        ValueError: Si algún dato o supuesto es inválido (ver cada paso).
    """
    options = terminal or TerminalOptions(company.info.terminal_method)
    ratios = compute_fcff_ratios(company)
    projection = project_fcff(company, ratios, assumptions.projection_years)
    wacc, rate = resolve_wacc(company, market_inputs, rate_override)
    rf, g = market_inputs.risk_free_rate.value, assumptions.terminal_growth
    fcffs = [f.fcff for f in projection.flows]
    basis = terminal_basis(company, ratios, projection, options)
    tv = terminal_value(options, basis, rate.value, g, rf, "WACC")
    fn = terminal_function(options, basis, rf, "WACC")
    ev = compute_enterprise_value(fcffs, rate.value, g, rf, fn)
    require_positive_value(
        "Valor de empresa",
        ev.enterprise_value,
        sum(ev.present_values),
        ev.terminal_value_present,
        "FCFF",
        "prueba --model fcff_cfo",
    )
    equity = equity_value(ev.enterprise_value, company.balance)

    def flows_for(case: EstimateCase) -> tuple[list[float], tuple[str, ...], TerminalFn | None]:
        p = project_fcff(company, ratios, assumptions.projection_years, case)
        scenario_fn = terminal_function(
            options, terminal_basis(company, ratios, p, options), rf, "WACC"
        )
        return [f.fcff for f in p.flows], p.warnings, scenario_fn

    projections = tuple(
        FcffProjectedYear(flow=f, discount_factor=factor, present_value=pv)
        for f, factor, pv in zip(
            projection.flows, ev.discount_factors, ev.present_values, strict=True
        )
    )
    checks = historical_flow_warnings("FCFF", ratios.fcff_by_year, options.thresholds)
    return FcffValuationResult(
        ticker=company.info.ticker,
        source=company.info.source,
        data_date=company.info.data_date,
        valuation_date=valuation_date,
        code_version=dcf.__version__,
        assumptions=assumptions,
        ratios=ratios,
        wacc=wacc,
        discount_rate=rate,
        market_inputs=market_inputs,
        projections=projections,
        projection_growth=projection.projection_growth,
        terminal_value=ev.terminal_value,
        terminal_value_present=ev.terminal_value_present,
        enterprise_value=ev.enterprise_value,
        equity_value=equity,
        value_per_share=value_per_share(equity, company.balance.diluted_shares),
        sensitivity=sensitivity_table(fcffs, company.balance, rate.value, g, rf, terminal=fn),
        scenarios=(
            compute_fcff_scenarios(
                company,
                flows_for,
                rate.value,
                rf,
                assumptions,
                scenario_config,
                options.thresholds.scenario_growth_gap,
            )
            if scenario_config is not None
            else ()
        ),
        warnings=rate_warnings(rate) + projection.warnings,
        terminal=tv,
        checks=checks + tv.warnings,
    )
