"""Modelo FCFF_CFO: FCFF desde el CFO (Net Income × FCFF/Net Income) descontado al WACC.

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §2-§7 y §12 (valor
terminal). Las piezas comunes a los modelos FCFF (WACC, VE, puente, sensibilidad,
escenarios) están en :mod:`dcf.valuation.enterprise`.
Tasas en decimal (0.08 = 8 %), importes en EUR (``float``, sin redondeo interno).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

import dcf
from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.checks import historical_flow_warnings
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.discount_rate import rate_warnings
from dcf.model.fcff_cfo_projection import Projection, project_cash_flows
from dcf.model.fcff_cfo_ratios import HistoricalRatios, compute_historical_ratios
from dcf.model.returns import historical_roic
from dcf.model.revenue_projection import EstimateCase
from dcf.model.tax import tax_rates
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
from dcf.valuation.fcff_cfo_result import FcffCfoProjectedYear, FcffCfoValuationResult
from dcf.valuation.scenarios import ScenarioConfig, ScenarioResult


# Base del VT de fcff_cfo: NOPAT_N y EBITDA_N con márgenes históricos sobre las ventas.
def terminal_basis(
    company: Company,
    projection: Projection,
    options: TerminalOptions,
) -> TerminalBasis:
    """Construye los datos del año N para el valor terminal de fcff_cfo.

    NOPAT_N = Ventas_N · margen EBIT medio · (1 − t mediano); EBITDA_N = Ventas_N ·
    (margen EBIT medio + D&A/ventas medio), si la fuente publica D&A. RONIC: el forzado
    o el ROIC histórico medio.

    Args:
        company: Compañía con EBIT, impuestos y, si hay, D&A, fondos propios y caja.
        projection: Proyección FCFF_CFO.
        options: Opciones del VT (RONIC forzado).

    Returns:
        Base del VT.
    """
    t = tax_rates(company.debt_cost_data, "el t del NOPAT").median
    ebit = {d.fiscal_year: d.ebit for d in company.debt_cost_data}
    margin = float(np.median([ebit[h.fiscal_year] / h.revenue for h in company.historicals]))
    last = projection.flows[-1]
    da = [h.depreciation_amortization for h in company.historicals]
    ebitda: float | None = None
    if all(v is not None for v in da):
        da_ratio = float(
            np.median(
                [
                    v / h.revenue
                    for v, h in zip(da, company.historicals, strict=True)
                    if v is not None
                ]
            )
        )
        ebitda = last.revenue * (margin + da_ratio)
    ronic = options.ronic or historical_roic(company, t).as_rate(company.info.data_date)
    return TerminalBasis(
        last_flow=last.fcff,
        profit_last=last.revenue * margin * (1.0 - t),
        profit_name="NOPAT",
        metric_last=ebitda,
        metric_name="EBITDA",
        return_name="RONIC",
        ronic=ronic,
    )


# Valora los escenarios bajista, neutro y alcista con la proyección FCFF_CFO.
def compute_scenarios(
    company: Company,
    ratios: HistoricalRatios,
    wacc: float,
    risk_free_rate: float,
    assumptions: Assumptions,
    config: ScenarioConfig,
    options: TerminalOptions | None = None,
) -> tuple[ScenarioResult, ...]:
    """Calcula el valor por acción de los tres escenarios.

    Args:
        company: Datos de la compañía en EUR.
        ratios: Ratios históricos (márgenes y conversión a caja comunes a todos).
        wacc: WACC central, en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.
        assumptions: g terminal central y horizonte.
        config: Modos activos y desplazamientos.
        options: Método de VT; ``None`` = Gordon clásico.

    Returns:
        Escenarios en orden bajista, neutro, alcista. Si un escenario incumple
        g < WACC o g < rf, se devuelve con ``error`` y sin valores.
    """

    def flows_for(case: EstimateCase) -> tuple[list[float], tuple[str, ...], TerminalFn | None]:
        p = project_cash_flows(company, ratios, assumptions.projection_years, case)
        fn = (
            None
            if options is None
            else terminal_function(
                options, terminal_basis(company, p, options), risk_free_rate, "WACC"
            )
        )
        return [f.fcff for f in p.flows], p.warnings, fn

    gap = None if options is None else options.thresholds.scenario_growth_gap
    return compute_fcff_scenarios(
        company, flows_for, wacc, risk_free_rate, assumptions, config, gap
    )


# Valoración FCFF_CFO: ratios → proyección → WACC → VE → fondos propios → por acción.
def value_company(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
    rate_override: MarketRate | None = None,
    terminal: TerminalOptions | None = None,
) -> FcffCfoValuationResult:
    """Valora la compañía con el modelo FCFF_CFO (FCFF desde el CFO, al WACC).

    Args:
        company: Datos de la compañía en EUR.
        market_inputs: rf y PRM con su fuente.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC (se pasa explícito para que
            la función sea pura y reproducible).
        scenario_config: Modos de escenario; ``None`` = sin escenarios.
        rate_override: WACC forzado (argumento o fichero), con fuente y fecha. Si se
            indica, el WACC calculado solo es informativo y, si no se puede calcular,
            queda como aviso en lugar de error.
        terminal: Método de VT, múltiplo, RONIC y umbrales; ``None`` = el método de
            ``company.info.terminal_method`` sin datos forzados.

    Returns:
        Resultado completo y trazable.

    Raises:
        ValueError: Si algún dato o supuesto es inválido (ver cada paso).
    """
    options = terminal or TerminalOptions(company.info.terminal_method)
    ratios = compute_historical_ratios(company)
    projection = project_cash_flows(company, ratios, assumptions.projection_years)
    wacc, rate = resolve_wacc(company, market_inputs, rate_override)
    rf, g = market_inputs.risk_free_rate.value, assumptions.terminal_growth
    fcffs = [f.fcff for f in projection.flows]
    basis = terminal_basis(company, projection, options)
    tv = terminal_value(options, basis, rate.value, g, rf, "WACC")
    fn = terminal_function(options, basis, rf, "WACC")
    ev = compute_enterprise_value(fcffs, rate.value, g, rf, fn)
    require_positive_value(
        "Valor de empresa",
        ev.enterprise_value,
        sum(ev.present_values),
        ev.terminal_value_present,
        "FCFF",
        "prueba --model fcff",
    )
    equity = equity_value(ev.enterprise_value, company.balance)

    projections = tuple(
        FcffCfoProjectedYear(
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
    checks = historical_flow_warnings("FCFF", ratios.fcff_by_year, options.thresholds)
    return FcffCfoValuationResult(
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
            compute_scenarios(
                company, ratios, rate.value, rf, assumptions, scenario_config, options
            )
            if scenario_config is not None
            else ()
        ),
        warnings=rate_warnings(rate) + projection.warnings,
        terminal=tv,
        checks=checks + tv.warnings,
    )
