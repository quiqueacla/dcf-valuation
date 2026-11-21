"""Elige el modelo de valoración (fcff_cfo o fcfe) según la compañía. Puro, sin I/O."""

from __future__ import annotations

from datetime import datetime

from dcf.company import Company, ValuationModel
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.valuation import fcfe, fcff_cfo
from dcf.valuation.fcfe_result import FcfeValuationResult
from dcf.valuation.fcff_cfo_result import FcffCfoValuationResult
from dcf.valuation.scenarios import ScenarioConfig

AnyValuationResult = FcffCfoValuationResult | FcfeValuationResult
"""Resultado de cualquiera de los modelos."""


# Valora con el modelo para el que se cargaron los datos (company.info.valuation_model).
def run_valuation(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
    argument_rate: MarketRate | None = None,
) -> AnyValuationResult:
    """Valora la compañía con su modelo: fcff_cfo (industriales) o fcfe (financieras).

    Tasa de descuento (WACC o Ke), por precedencia: ``argument_rate`` (``--set rate``) >
    ``[discount_rate."TICKER"]`` de ``market_inputs.toml`` > calculada.

    Args:
        company: Datos de la compañía en EUR.
        market_inputs: rf, PRM, Kd por defecto, beta y tasas forzadas por ticker.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC.
        scenario_config: Modos de escenario; ``None`` = sin escenarios.
        argument_rate: Tasa forzada por argumento para todos los tickers; ``None`` si no.

    Returns:
        Resultado del modelo aplicado.

    Raises:
        ValueError: Si algún dato o supuesto es inválido para el modelo.
    """
    override = argument_rate or market_inputs.discount_rate_for(company.info.ticker)
    if company.info.valuation_model is ValuationModel.FCFE:
        return fcfe.value_company(
            company, market_inputs, assumptions, valuation_date, scenario_config, override
        )
    return fcff_cfo.value_company(
        company, market_inputs, assumptions, valuation_date, scenario_config, override
    )
