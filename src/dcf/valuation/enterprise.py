"""Piezas del modelo FCFF (fcff_cfo) separadas de su proyección.

WACC elegido, valor de empresa, puente a fondos propios, sensibilidad y escenarios.
Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §4-§8.
Tasas en decimal (0.08 = 8 %), importes en EUR (``float``, sin redondeo interno).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from dcf.company import BalanceSnapshot, Company, ValuationModel, required
from dcf.defaults import (
    SENSITIVITY_GROWTH_STEP,
    SENSITIVITY_STEPS_EACH_SIDE,
    SENSITIVITY_WACC_STEP,
)
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs, MarketRate
from dcf.model.discount_rate import DiscountRateChoice, choose_discount_rate
from dcf.model.revenue_projection import EstimateCase
from dcf.model.terminal_value import gordon_terminal_value
from dcf.model.wacc import WaccResult, compute_wacc
from dcf.valuation.discounting import (
    discount_with_terminal_value,
    scenario_inputs,
    sensitivity_grid,
    value_per_share,
)
from dcf.valuation.scenarios import ScenarioConfig, ScenarioName, ScenarioResult

FCFF = ValuationModel.FCFF_CFO

FlowsForCase = Callable[[EstimateCase], tuple[list[float], tuple[str, ...]]]
"""Función (estimación de ventas) → (FCFF proyectados, avisos de la proyección)."""


@dataclass(frozen=True, slots=True)
class EnterpriseValue:
    """Valor de empresa y su descomposición.

    Attributes:
        discount_factors: 1 / (1 + WACC)^k para k = 1..N.
        present_values: Valor actual de cada FCFF proyectado.
        terminal_value: Valor terminal (Gordon) al final del año N, sin descontar.
        terminal_value_present: Valor terminal descontado a hoy.
        enterprise_value: Suma de los valores actuales de los FCFF y del valor terminal.
    """

    discount_factors: tuple[float, ...]
    present_values: tuple[float, ...]
    terminal_value: float
    terminal_value_present: float
    enterprise_value: float


# WACC calculado (o None si falla y hay override) y tasa elegida por precedencia.
def resolve_wacc(
    company: Company, market_inputs: MarketInputs, rate_override: MarketRate | None
) -> tuple[WaccResult | None, DiscountRateChoice]:
    """Calcula el WACC y elige la tasa de descuento (forzada o calculada).

    Args:
        company: Compañía con datos de deuda, impuestos y mercado.
        market_inputs: rf, PRM, beta.
        rate_override: WACC forzado; ``None`` = el calculado.

    Returns:
        WACC calculado (``None`` si no se pudo y hay override) y tasa elegida.

    Raises:
        ValueError: Si el WACC no se puede calcular y no hay override.
    """
    wacc: WaccResult | None
    try:
        wacc, error = compute_wacc(company, market_inputs), None
    except ValueError as exc:
        if rate_override is None:
            raise
        wacc, error = None, str(exc)
    rate = choose_discount_rate("WACC", None if wacc is None else wacc.wacc, error, rate_override)
    return wacc, rate


# VE = Σ FCFF_k / (1 + WACC)^k + VT_Gordon / (1 + WACC)^N.
def compute_enterprise_value(
    fcffs: Sequence[float],
    wacc: float,
    terminal_growth: float,
    risk_free_rate: float,
) -> EnterpriseValue:
    """Descuenta los FCFF proyectados y el valor terminal.

    Args:
        fcffs: FCFF proyectados, en EUR, años 1..N en orden.
        wacc: WACC en decimal.
        terminal_growth: g terminal en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.

    Returns:
        Valor de empresa y su descomposición.

    Raises:
        ValueError: Si no hay flujos, si g ≥ WACC o g ≥ rf.
    """
    if not fcffs:
        raise ValueError("Se necesita al menos un FCFF proyectado")
    tv = gordon_terminal_value(float(fcffs[-1]), wacc, terminal_growth, risk_free_rate)
    d = discount_with_terminal_value(fcffs, wacc, tv)
    return EnterpriseValue(
        discount_factors=d.discount_factors,
        present_values=d.present_values,
        terminal_value=d.terminal_value,
        terminal_value_present=d.terminal_value_present,
        enterprise_value=d.total,
    )


# Fondos propios = VE − deuda total + caja − minoritarios.
def equity_value(enterprise_value: float, balance: BalanceSnapshot) -> float:
    """Pasa del valor de empresa al valor de los fondos propios.

    Args:
        enterprise_value: Valor de empresa, en EUR.
        balance: Último balance (deuda total, caja, minoritarios), en EUR.

    Returns:
        Valor de los fondos propios en EUR (puede ser negativo).

    Raises:
        ValueError: Si el balance no tiene deuda total o caja.
    """
    debt = required(balance.total_debt, "la deuda total", FCFF)
    cash = required(balance.cash, "la caja", FCFF)
    return enterprise_value - debt + cash - balance.minority_interest


# Tabla de valor por acción para WACC (filas) × g (columnas); NaN si g ≥ WACC o g ≥ rf.
def sensitivity_table(
    fcffs: Sequence[float],
    balance: BalanceSnapshot,
    wacc: float,
    terminal_growth: float,
    risk_free_rate: float,
    wacc_step: float = SENSITIVITY_WACC_STEP,
    growth_step: float = SENSITIVITY_GROWTH_STEP,
    steps_each_side: int = SENSITIVITY_STEPS_EACH_SIDE,
) -> pd.DataFrame:
    """Calcula la sensibilidad del valor por acción al WACC y al g terminal.

    Args:
        fcffs: FCFF proyectados, en EUR (no dependen del WACC ni de g).
        balance: Último balance para el puente a fondos propios.
        wacc: WACC central, en decimal.
        terminal_growth: g central, en decimal.
        risk_free_rate: rf en decimal, para invalidar celdas con g ≥ rf.
        wacc_step: Paso entre filas, en decimal.
        growth_step: Paso entre columnas, en decimal.
        steps_each_side: Pasos a cada lado del valor central.

    Returns:
        DataFrame con índice ``discount_rate`` (WACC) y columnas ``terminal_growth``
        (en decimal) y el valor por acción en EUR. Celdas inválidas a NaN.
    """

    def value_for(w: float, g: float) -> float:
        ev = compute_enterprise_value(fcffs, w, g, risk_free_rate)
        return value_per_share(equity_value(ev.enterprise_value, balance), balance.diluted_shares)

    return sensitivity_grid(
        value_for, wacc, terminal_growth, risk_free_rate, wacc_step, growth_step, steps_each_side
    )


# Escenarios FCFF: cada uno proyecta sus FCFF y los descuenta a su WACC y g.
def compute_fcff_scenarios(
    company: Company,
    flows_for: FlowsForCase,
    wacc: float,
    risk_free_rate: float,
    assumptions: Assumptions,
    config: ScenarioConfig,
) -> tuple[ScenarioResult, ...]:
    """Calcula el valor por acción de los tres escenarios de un modelo FCFF.

    Args:
        company: Datos de la compañía en EUR (balance para el puente).
        flows_for: Proyección de FCFF del modelo para una estimación de ventas.
        wacc: WACC central, en decimal.
        risk_free_rate: rf en decimal, para validar g < rf.
        assumptions: g terminal central.
        config: Modos activos y desplazamientos.

    Returns:
        Escenarios en orden bajista, neutro, alcista. Si un escenario incumple
        g < WACC o g < rf, se devuelve con ``error`` y sin valores.
    """
    results: list[ScenarioResult] = []
    for name in ScenarioName:
        case, w, g = scenario_inputs(name, config, wacc, assumptions.terminal_growth)
        flows, warnings = flows_for(case)
        try:
            if w <= 0:
                raise ValueError(f"WACC del escenario no positivo ({w})")
            ev = compute_enterprise_value(flows, w, g, risk_free_rate)
        except ValueError as exc:
            results.append(ScenarioResult(name, case, w, g, None, None, None, str(exc), warnings))
            continue
        equity = equity_value(ev.enterprise_value, company.balance)
        results.append(
            ScenarioResult(
                name=name,
                estimate_case=case,
                discount_rate=w,
                terminal_growth=g,
                total_value=ev.enterprise_value,
                terminal_value_weight=ev.terminal_value_present / ev.enterprise_value,
                value_per_share=value_per_share(equity, company.balance.diluted_shares),
                warnings=warnings,
            )
        )
    return tuple(results)
