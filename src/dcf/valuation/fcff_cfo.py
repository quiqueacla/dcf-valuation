"""Modelo FCFF_CFO: FCFF desde el CFO (Net Income × FCFF/Net Income) descontado al WACC.

Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §2-§7. Las piezas comunes a
los modelos FCFF (WACC, VE, puente, sensibilidad, escenarios) están en
:mod:`dcf.valuation.enterprise`.
Tasas en decimal (0.08 = 8 %), importes en EUR (``float``, sin redondeo interno).
"""

from __future__ import annotations

from datetime import datetime

import dcf
from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.discount_rate import rate_warnings
from dcf.model.fcff_cfo_projection import project_cash_flows
from dcf.model.fcff_cfo_ratios import HistoricalRatios, compute_historical_ratios
from dcf.model.revenue_projection import EstimateCase
from dcf.valuation.discounting import value_per_share
from dcf.valuation.enterprise import (
    compute_enterprise_value,
    compute_fcff_scenarios,
    equity_value,
    resolve_wacc,
    sensitivity_table,
)
from dcf.valuation.fcff_cfo_result import FcffCfoProjectedYear, FcffCfoValuationResult
from dcf.valuation.scenarios import ScenarioConfig, ScenarioResult


# Valora los escenarios bajista, neutro y alcista con la proyección FCFF_CFO.
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

    def flows_for(case: EstimateCase) -> tuple[list[float], tuple[str, ...]]:
        p = project_cash_flows(company, ratios, assumptions.projection_years, case)
        return [f.fcff for f in p.flows], p.warnings

    return compute_fcff_scenarios(company, flows_for, wacc, risk_free_rate, assumptions, config)


# Valoración FCFF_CFO: ratios → proyección → WACC → VE → fondos propios → por acción.
def value_company(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
    rate_override: MarketRate | None = None,
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

    Returns:
        Resultado completo y trazable.

    Raises:
        ValueError: Si algún dato o supuesto es inválido (ver cada paso).
    """
    ratios = compute_historical_ratios(company)
    projection = project_cash_flows(company, ratios, assumptions.projection_years)
    wacc, rate = resolve_wacc(company, market_inputs, rate_override)
    rf = market_inputs.risk_free_rate.value
    fcffs = [f.fcff for f in projection.flows]
    ev = compute_enterprise_value(fcffs, rate.value, assumptions.terminal_growth, rf)
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
        sensitivity=sensitivity_table(
            fcffs, company.balance, rate.value, assumptions.terminal_growth, rf
        ),
        scenarios=(
            compute_scenarios(company, ratios, rate.value, rf, assumptions, scenario_config)
            if scenario_config is not None
            else ()
        ),
        warnings=rate_warnings(rate) + projection.warnings,
    )
