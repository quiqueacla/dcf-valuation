"""Resultado completo y trazable de una valoración DCF.

Importes en EUR (unidades, ``float``); tasas en decimal (0.08 = 8 %).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from dcf.model.assumptions import Assumptions
from dcf.model.fcff_ratios import HistoricalRatios
from dcf.model.revenue_projection import RevenueSource
from dcf.model.terminal_value import validate_terminal_growth
from dcf.model.wacc import WaccResult
from dcf.valuation.scenarios import ScenarioResult


@dataclass(frozen=True, slots=True)
class ProjectedYear:
    """Un año de la proyección explícita.

    Attributes:
        fiscal_year: Ejercicio proyectado.
        revenue: Ventas proyectadas.
        revenue_growth: Crecimiento de ventas respecto al año anterior.
        revenue_source: Si las ventas vienen de analistas o del crecimiento medio.
        net_income: Beneficio neto proyectado (ventas × margen neto medio).
        fcff: Flujo de caja libre para la empresa (Net Income × FCFF/Net Income medio).
        discount_factor: 1 / (1 + WACC)^t, con t = años desde la valoración.
        present_value: Valor actual del FCFF (fcff × discount_factor).
    """

    fiscal_year: int
    revenue: float
    revenue_growth: float
    revenue_source: RevenueSource
    net_income: float
    fcff: float
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class ValuationResult:
    """Resultado de la valoración con todo lo necesario para reproducirla.

    Attributes:
        ticker: Símbolo de la compañía valorada.
        source: Fuente de los datos.
        data_date: Fecha de los datos utilizados, en UTC.
        valuation_date: Momento en que se calculó la valoración, en UTC.
        code_version: Versión del paquete ``dcf`` que produjo el resultado.
        assumptions: Supuestos completos utilizados.
        ratios: Medias históricas utilizadas en la proyección.
        wacc: WACC con todos sus componentes (rf, PRM, beta, Ke, Kd, t, pesos).
        projections: Años de la proyección explícita, en orden.
        projection_growth: Crecimiento de ventas aplicado a los años sin estimación de
            analistas (media de crecimientos históricos y de analistas).
        terminal_value: Valor terminal (Gordon) al final del horizonte, sin descontar.
        terminal_value_present: Valor terminal descontado a hoy.
        enterprise_value: Valor de empresa (VA de los FCFF + VA del valor terminal).
        equity_value: Valor de los fondos propios tras el puente deuda/caja/minoritarios.
        value_per_share: Valor intrínseco por acción diluida, en EUR.
        sensitivity: Valor por acción por WACC (filas) × crecimiento terminal (columnas).
        scenarios: Escenarios bajista, neutro y alcista (vacío si no se pidieron).
        warnings: Avisos de la valoración (proyección del escenario central).
    """

    ticker: str
    source: str
    data_date: datetime
    valuation_date: datetime
    code_version: str
    assumptions: Assumptions
    ratios: HistoricalRatios
    wacc: WaccResult
    projections: tuple[ProjectedYear, ...]
    projection_growth: float
    terminal_value: float
    terminal_value_present: float
    enterprise_value: float
    equity_value: float
    value_per_share: float
    sensitivity: pd.DataFrame
    scenarios: tuple[ScenarioResult, ...] = ()
    warnings: tuple[str, ...] = ()

    # Valida fechas con zona, g < WACC y g < rf, horizonte coherente y VE positivo.
    def __post_init__(self) -> None:
        validate_terminal_growth(
            self.assumptions.terminal_growth,
            self.wacc.wacc,
            self.wacc.market_inputs.risk_free_rate.value,
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
