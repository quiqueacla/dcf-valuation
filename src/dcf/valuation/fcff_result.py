"""Resultado completo y trazable de una valoración con el modelo FCFF (desde el EBIT).

Importes en EUR (unidades, ``float``); tasas en decimal (0.08 = 8 %).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.model.discount_rate import DiscountRateChoice
from dcf.model.fcff_projection import FcffFlow, FcffRatios
from dcf.model.terminal_methods import TerminalValueResult
from dcf.model.terminal_value import validate_terminal_growth
from dcf.model.wacc import WaccResult
from dcf.valuation.scenarios import ScenarioResult


@dataclass(frozen=True, slots=True)
class FcffProjectedYear:
    """Un año de la proyección FCFF, con su descuento.

    Attributes:
        flow: Ventas, EBIT, NOPAT, D&A, Capex, circulante y FCFF del año.
        discount_factor: 1 / (1 + WACC)^t, con t = años desde la valoración.
        present_value: Valor actual del FCFF (fcff × discount_factor).
    """

    flow: FcffFlow
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class FcffValuationResult:
    """Resultado de la valoración FCFF con todo lo necesario para reproducirla.

    Attributes:
        ticker: Símbolo de la compañía valorada.
        source: Fuente de los datos.
        data_date: Fecha de los datos utilizados, en UTC.
        valuation_date: Momento en que se calculó la valoración, en UTC.
        code_version: Versión del paquete ``dcf`` que produjo el resultado.
        assumptions: Supuestos completos utilizados.
        ratios: Márgenes, circulante y tipo impositivo históricos.
        wacc: WACC calculado con sus componentes; ``None`` si no se pudo calcular y la
            tasa está forzada.
        discount_rate: Tasa con la que se descuenta (WACC calculado o forzado) y su origen.
        market_inputs: rf, PRM y configuración de la beta usados.
        projections: Años de la proyección explícita, en orden.
        projection_growth: Crecimiento de ventas aplicado a los años sin estimación de
            analistas.
        terminal_value: Valor terminal al final del horizonte (método de ``terminal``).
        terminal_value_present: Valor terminal descontado a hoy.
        enterprise_value: Valor de empresa (VA de los FCFF + VA del valor terminal).
        equity_value: Valor de los fondos propios tras el puente deuda/caja/minoritarios.
        value_per_share: Valor intrínseco por acción diluida, en EUR.
        sensitivity: Valor por acción por WACC (filas) × crecimiento terminal (columnas).
        scenarios: Escenarios bajista, neutro y alcista (vacío si no se pidieron).
        warnings: Avisos de la valoración.
        terminal: Valor terminal con su método, entradas y chequeos.
        checks: Comprobaciones de consistencia (FCFF históricos negativos, último año
            atípico y avisos del valor terminal).
    """

    ticker: str
    source: str
    data_date: datetime
    valuation_date: datetime
    code_version: str
    assumptions: Assumptions
    ratios: FcffRatios
    wacc: WaccResult | None
    discount_rate: DiscountRateChoice
    market_inputs: MarketInputs
    projections: tuple[FcffProjectedYear, ...]
    projection_growth: float
    terminal_value: float
    terminal_value_present: float
    enterprise_value: float
    equity_value: float
    value_per_share: float
    sensitivity: pd.DataFrame
    scenarios: tuple[ScenarioResult, ...] = ()
    warnings: tuple[str, ...] = ()
    terminal: TerminalValueResult | None = None
    checks: tuple[str, ...] = ()

    # Valida fechas con zona, g < WACC y g < rf, horizonte coherente y VE positivo.
    def __post_init__(self) -> None:
        validate_terminal_growth(
            self.assumptions.terminal_growth,
            self.discount_rate.value,
            self.market_inputs.risk_free_rate.value,
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
        if self.enterprise_value <= 0:
            raise ValueError(
                f"enterprise_value debe ser positivo, recibido {self.enterprise_value}"
            )

    # Peso del valor terminal descontado sobre el valor de empresa (0-1).
    @property
    def terminal_value_weight(self) -> float:
        """Fracción del valor de empresa que aporta el valor terminal (0.7 = 70 %)."""
        return self.terminal_value_present / self.enterprise_value
