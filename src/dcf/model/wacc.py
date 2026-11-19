"""Modelo FCFF: coste medio ponderado del capital (WACC). Funciones puras, sin I/O.

Ke, beta y datos de mercado están en :mod:`dcf.model.cost_of_equity` (comunes a FCFE).
Fórmulas en ``docs/metodologia.md`` §4. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcf.company import Company, ValuationModel, required
from dcf.model.cost_of_equity import BetaChoice, MarketInputs, compute_cost_of_equity
from dcf.model.fcff_ratios import effective_tax_rate

WEIGHT_TOLERANCE = 1e-9
"""Tolerancia para comprobar que los pesos suman 1 (error de redondeo en float)."""


@dataclass(frozen=True, slots=True)
class WaccResult:
    """WACC y todos sus componentes, para trazabilidad.

    Attributes:
        market_inputs: rf y PRM utilizados, con fuente y fecha.
        beta: Beta de la acción utilizada.
        beta_choice: Origen de la beta utilizada (modo, fuente, fecha y motivo).
        cost_of_equity: Coste de los fondos propios (Ke, CAPM).
        cost_of_debt_by_year: Kd de cada ejercicio con deuda (intereses / deuda total).
        cost_of_debt: Kd medio, antes de impuestos. ``None`` si la empresa no tiene deuda.
        tax_rate_by_year: Tipo efectivo de cada ejercicio válido.
        tax_rate: Tipo efectivo medio, para el ahorro fiscal de la deuda.
        equity_value: Valor de mercado de los fondos propios (E).
        debt_value: Deuda financiera total contable (D).
        equity_weight: E / (D + E).
        debt_weight: D / (D + E).
        wacc: Coste medio ponderado del capital.
        warnings: Avisos sobre años excluidos de alguna media.
    """

    market_inputs: MarketInputs
    beta: float
    beta_choice: BetaChoice
    cost_of_equity: float
    cost_of_debt_by_year: dict[int, float]
    cost_of_debt: float | None
    tax_rate_by_year: dict[int, float]
    tax_rate: float
    equity_value: float
    debt_value: float
    equity_weight: float
    debt_weight: float
    wacc: float
    warnings: tuple[str, ...]


# WACC = We · Ke + Wd · Kd · (1 − t), validando pesos y tasas.
def weighted_average_cost_of_capital(
    equity_weight: float,
    debt_weight: float,
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
) -> float:
    """Calcula el WACC a partir de sus componentes.

    Args:
        equity_weight: E / (D + E), en [0, 1].
        debt_weight: D / (D + E), en [0, 1].
        cost_of_equity: Ke en decimal.
        cost_of_debt: Kd antes de impuestos en decimal (≥ 0).
        tax_rate: Tipo impositivo en decimal, en [0, 1].

    Returns:
        WACC en decimal.

    Raises:
        ValueError: Si los pesos no están en [0, 1] o no suman 1, si Kd < 0, si t
            está fuera de [0, 1] o si el WACC resultante no es positivo.
    """
    for name, weight in (("equity_weight", equity_weight), ("debt_weight", debt_weight)):
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"{name} debe estar en [0, 1], recibido {weight}")
    if abs(equity_weight + debt_weight - 1.0) > WEIGHT_TOLERANCE:
        raise ValueError(f"Los pesos deben sumar 1, suman {equity_weight + debt_weight}")
    if cost_of_debt < 0:
        raise ValueError(f"cost_of_debt no puede ser negativo, recibido {cost_of_debt}")
    if not 0.0 <= tax_rate <= 1.0:
        raise ValueError(f"tax_rate debe estar en [0, 1], recibido {tax_rate}")
    wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt * (1.0 - tax_rate)
    if wacc <= 0:
        raise ValueError(f"El WACC resultante debe ser positivo, recibido {wacc}")
    return wacc


# Calcula el WACC de la compañía: Ke por CAPM, Kd y t medios, pesos E mercado / D contable.
def compute_wacc(company: Company, market_inputs: MarketInputs) -> WaccResult:
    """Calcula el WACC de la compañía y sus componentes.

    Args:
        company: Compañía con último balance (precio, acciones, deuda, beta) y datos
            históricos de deuda e impuestos.
        market_inputs: rf, PRM y configuración de la beta, con su fuente.

    Returns:
        WACC con todos sus componentes y avisos.

    Raises:
        ValueError: Si el modo de beta no permite obtener una beta válida, si no hay
            ningún año con tipo efectivo válido, o si la empresa tiene deuda pero ningún
            año permite calcular Kd.
    """
    warnings: list[str] = []

    tax_rates: dict[int, float] = {}
    for d in company.debt_cost_data:
        rate, reason = effective_tax_rate(d)
        if rate is None:
            warnings.append(f"{d.fiscal_year} excluido del t medio: {reason}")
        else:
            tax_rates[d.fiscal_year] = rate
    if not tax_rates:
        raise ValueError("Ningún ejercicio tiene un tipo efectivo válido: " + "; ".join(warnings))
    tax_rate = float(np.mean(list(tax_rates.values())))

    kd_by_year: dict[int, float] = {}
    for d in company.debt_cost_data:
        if d.total_debt > 0:
            kd_by_year[d.fiscal_year] = d.interest_expense / d.total_debt
        else:
            warnings.append(f"{d.fiscal_year} excluido del Kd medio: deuda total 0")

    balance = company.balance
    equity_value = balance.share_price * balance.diluted_shares
    debt_value = required(balance.total_debt, "la deuda total", ValuationModel.FCFF)
    if debt_value > 0 and not kd_by_year:
        raise ValueError("La empresa tiene deuda pero ningún ejercicio permite calcular Kd")
    kd = float(np.mean(list(kd_by_year.values()))) if kd_by_year else None

    equity_cost = compute_cost_of_equity(company, market_inputs)
    choice, ke = equity_cost.beta_choice, equity_cost.cost_of_equity
    warnings.extend(equity_cost.warnings)
    total = equity_value + debt_value
    equity_weight, debt_weight = equity_value / total, debt_value / total
    wacc = weighted_average_cost_of_capital(
        equity_weight, debt_weight, ke, kd if kd is not None else 0.0, tax_rate
    )

    return WaccResult(
        market_inputs=market_inputs,
        beta=choice.value,
        beta_choice=choice,
        cost_of_equity=ke,
        cost_of_debt_by_year=kd_by_year,
        cost_of_debt=kd,
        tax_rate_by_year=tax_rates,
        tax_rate=tax_rate,
        equity_value=equity_value,
        debt_value=debt_value,
        equity_weight=equity_weight,
        debt_weight=debt_weight,
        wacc=wacc,
        warnings=tuple(warnings),
    )
