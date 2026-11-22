"""Resultado completo y trazable de una valoración con el modelo FCFE.

Importes en EUR (unidades, ``float``); tasas en decimal (0.08 = 8 %).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import CostOfEquityResult, MarketInputs
from dcf.model.discount_rate import DiscountRateChoice
from dcf.model.fcfe_fin_projection import FcfeFinFlow, FcfeFinRatios
from dcf.model.terminal_methods import TerminalValueResult
from dcf.model.terminal_value import validate_terminal_growth
from dcf.valuation.scenarios import ScenarioResult


@dataclass(frozen=True, slots=True)
class FcfeFinProjectedYear:
    """Un año de la proyección FCFE, con su descuento.

    Attributes:
        flow: Ventas, Net Income, fondos propios, reinversión y FCFE del año.
        discount_factor: 1 / (1 + Ke)^t, con t = años desde la valoración.
        present_value: Valor actual del FCFE (fcfe × discount_factor).
    """

    flow: FcfeFinFlow
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class FcfeFinValuationResult:
    """Resultado de la valoración FCFE con todo lo necesario para reproducirla.

    Attributes:
        ticker: Símbolo de la compañía valorada.
        source: Fuente de los datos.
        data_date: Fecha de los datos utilizados, en UTC.
        valuation_date: Momento en que se calculó la valoración, en UTC.
        code_version: Versión del paquete ``dcf`` que produjo el resultado.
        assumptions: Supuestos completos utilizados.
        ratios: Ratios históricos (crecimiento, margen, fondos propios, ROE).
        cost_of_equity: Ke calculado con rf, PRM y beta; ``None`` si no se pudo calcular
            y la tasa está forzada.
        discount_rate: Tasa con la que se descuenta (Ke calculado o forzado) y su origen.
        market_inputs: rf, PRM y configuración de la beta usados.
        projections: Años de la proyección explícita, en orden.
        projection_growth: Crecimiento de ventas aplicado a los años sin estimación de
            analistas (media de crecimientos históricos y de analistas).
        terminal_fcfe_fin: FCFE del año N+1: NI_N · (1 + g) − g · FP_N.
        terminal_value: Valor terminal (Gordon) al final del horizonte, sin descontar.
        terminal_value_present: Valor terminal descontado a hoy.
        equity_value: Valor de los fondos propios (VA de los FCFE + VA del valor
            terminal). No hay puente: el FCFE ya es el flujo del accionista.
        value_per_share: Valor intrínseco por acción diluida, en EUR.
        sensitivity: Valor por acción por Ke (filas) × crecimiento terminal (columnas).
        scenarios: Escenarios bajista, neutro y alcista (vacío si no se pidieron).
        warnings: Avisos de la valoración (Ke y proyección del escenario central).
        terminal: Valor terminal con su método, entradas y chequeos (g implícito,
            múltiplo implícito, RONIC); ``None`` solo en resultados construidos a mano.
        checks: Comprobaciones de consistencia: flujos históricos negativos, último año
            atípico y avisos del valor terminal.
    """

    ticker: str
    source: str
    data_date: datetime
    valuation_date: datetime
    code_version: str
    assumptions: Assumptions
    ratios: FcfeFinRatios
    cost_of_equity: CostOfEquityResult | None
    discount_rate: DiscountRateChoice
    market_inputs: MarketInputs
    projections: tuple[FcfeFinProjectedYear, ...]
    projection_growth: float
    terminal_fcfe_fin: float
    terminal_value: float
    terminal_value_present: float
    equity_value: float
    value_per_share: float
    sensitivity: pd.DataFrame
    scenarios: tuple[ScenarioResult, ...] = ()
    warnings: tuple[str, ...] = ()
    terminal: TerminalValueResult | None = None
    checks: tuple[str, ...] = ()

    # Valida fechas con zona, g < Ke y g < rf, horizonte coherente y fondos propios positivos.
    def __post_init__(self) -> None:
        validate_terminal_growth(
            self.assumptions.terminal_growth,
            self.discount_rate.value,
            self.market_inputs.risk_free_rate.value,
            "Ke",
        )
        for name in ("data_date", "valuation_date"):
            value: datetime = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} debe ser un datetime con zona horaria (UTC)")
        if len(self.projections) != self.assumptions.projection_years:
            raise ValueError(
                f"Se esperaban {self.assumptions.projection_years} años proyectados, "
                f"recibidos {len(self.projections)}"
            )
        if self.equity_value <= 0:
            raise ValueError(f"equity_value debe ser positivo, recibido {self.equity_value}")

    # Peso del valor terminal descontado sobre el valor de los fondos propios (0-1).
    @property
    def terminal_value_weight(self) -> float:
        """Fracción del valor de los fondos propios que aporta el valor terminal."""
        return self.terminal_value_present / self.equity_value
