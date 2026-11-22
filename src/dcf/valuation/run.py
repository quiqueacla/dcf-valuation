"""Elige el modelo (fcff, fcff_cfo, fcfe, fcfe_fin) y el valor terminal. Puro, sin I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from dcf.company import Company, ValuationModel
from dcf.model.assumptions import Assumptions
from dcf.model.checks import WarningThresholds
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.terminal_methods import TerminalOptions, pick_override
from dcf.valuation import fcfe, fcfe_fin, fcff, fcff_cfo
from dcf.valuation.fcfe_fin_result import FcfeFinValuationResult
from dcf.valuation.fcfe_result import FcfeValuationResult
from dcf.valuation.fcff_cfo_result import FcffCfoValuationResult
from dcf.valuation.fcff_result import FcffValuationResult
from dcf.valuation.scenarios import ScenarioConfig

AnyValuationResult = (
    FcffValuationResult | FcffCfoValuationResult | FcfeValuationResult | FcfeFinValuationResult
)
"""Resultado de cualquiera de los modelos."""


@dataclass(frozen=True, slots=True)
class TerminalOverrides:
    """Datos del valor terminal forzados por argumento para todos los tickers.

    Attributes:
        multiple: Múltiplo de salida (``--set exit_multiple=``); ``None`` = el del fichero.
        ronic: RONIC / ROE (``--set ronic=``); ``None`` = el del fichero o el histórico.
        thresholds: Umbrales de los avisos (``config/thresholds.toml``).
    """

    multiple: MarketRate | None = None
    ronic: MarketRate | None = None
    thresholds: WarningThresholds = WarningThresholds()


# Opciones del VT de un ticker: método de la compañía y datos por precedencia.
def terminal_options(
    company: Company, market_inputs: MarketInputs, overrides: TerminalOverrides
) -> TerminalOptions:
    """Construye las opciones del valor terminal de una compañía.

    Método: ``company.info.terminal_method`` (tabla de tipos o ``--vt``). Múltiplo y
    RONIC: argumento > ``[exit_multiple."TICKER"]`` / ``[ronic."TICKER"]`` del fichero >
    (RONIC) histórico calculado por el modelo.

    Args:
        company: Compañía (ticker y método).
        market_inputs: Datos por ticker del fichero.
        overrides: Datos forzados por argumento.

    Returns:
        Opciones del VT.
    """
    ticker = company.info.ticker
    return TerminalOptions(
        method=company.info.terminal_method,
        multiple=pick_override(overrides.multiple, market_inputs.exit_multiple_for(ticker), None),
        ronic=pick_override(overrides.ronic, market_inputs.ronic_for(ticker), None),
        thresholds=overrides.thresholds,
    )


# Valora con el modelo y el VT para los que se cargaron los datos.
def run_valuation(
    company: Company,
    market_inputs: MarketInputs,
    assumptions: Assumptions,
    valuation_date: datetime,
    scenario_config: ScenarioConfig | None = None,
    argument_rate: MarketRate | None = None,
    overrides: TerminalOverrides | None = None,
) -> AnyValuationResult:
    """Valora la compañía con su modelo y su método de valor terminal.

    Tasa de descuento (WACC o Ke), por precedencia: ``argument_rate`` (``--set rate``) >
    ``[discount_rate."TICKER"]`` de ``market_inputs.toml`` > calculada.

    Args:
        company: Datos de la compañía en EUR.
        market_inputs: rf, PRM, Kd por defecto, beta y datos forzados por ticker.
        assumptions: g terminal y horizonte.
        valuation_date: Momento de la valoración, en UTC.
        scenario_config: Modos de escenario; ``None`` = sin escenarios.
        argument_rate: Tasa forzada por argumento para todos los tickers; ``None`` si no.
        overrides: Múltiplo, RONIC y umbrales del VT; ``None`` = sin datos forzados.

    Returns:
        Resultado del modelo aplicado.

    Raises:
        ValueError: Si algún dato o supuesto es inválido para el modelo.
    """
    rate = argument_rate or market_inputs.discount_rate_for(company.info.ticker)
    options = terminal_options(company, market_inputs, overrides or TerminalOverrides())
    model = company.info.valuation_model
    if model is ValuationModel.FCFE_FIN:
        return fcfe_fin.value_company(
            company, market_inputs, assumptions, valuation_date, scenario_config, rate, options
        )
    if model is ValuationModel.FCFE:
        return fcfe.value_company(
            company, market_inputs, assumptions, valuation_date, scenario_config, rate, options
        )
    if model is ValuationModel.FCFF_CFO:
        return fcff_cfo.value_company(
            company, market_inputs, assumptions, valuation_date, scenario_config, rate, options
        )
    return fcff.value_company(
        company, market_inputs, assumptions, valuation_date, scenario_config, rate, options
    )
