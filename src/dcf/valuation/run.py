"""Elige el modelo de valoración (FCFF o FCFE) según la compañía. Puro, sin I/O."""

from __future__ import annotations

from datetime import datetime

from dcf.company import Company, ValuationModel
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.valuation import fcfe, fcff
from dcf.valuation.fcfe_result import FcfeValuationResult
from dcf.valuation.fcff_result import ValuationResult
from dcf.valuation.scenarios import ScenarioConfig

AnyValuationResult = ValuationResult | FcfeValuationResult
"""Resultado de cualquiera de los dos modelos."""


# Valora con el modelo para el que se cargaron los datos (company.info.valuation_model).
def run_valuation(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
) -> AnyValuationResult:
    """Valora la compañía con su modelo: FCFF (empresas industriales) o FCFE (financieras).

    Args:
        company: Datos de la compañía en EUR.
        market_inputs: rf, PRM, Kd por defecto y configuración de la beta.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC.
        scenario_config: Modos de escenario; ``None`` = sin escenarios.

    Returns:
        Resultado del modelo aplicado.

    Raises:
        ValueError: Si algún dato o supuesto es inválido para el modelo.
    """
    if company.info.valuation_model is ValuationModel.FCFE:
        return fcfe.value_company(
            company, market_inputs, assumptions, valuation_date, scenario_config
        )
    return fcff.value_company(company, market_inputs, assumptions, valuation_date, scenario_config)
