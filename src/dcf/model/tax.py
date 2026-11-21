"""Tipo impositivo efectivo por ejercicio y su mediana (funciones puras, sin I/O).

Común al WACC (ahorro fiscal de la deuda) y al NOPAT del modelo fcff. Tasas en decimal
(0.25 = 25 %), importes en EUR. Ver ``docs/metodologia.md`` §2 y §4.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from dcf.company import DebtCostYear


@dataclass(frozen=True, slots=True)
class TaxRates:
    """Tipos efectivos históricos y el representativo de la empresa.

    Attributes:
        by_year: Tipo efectivo (provisión / BAI) de cada ejercicio válido.
        median: Mediana de los tipos válidos: tipo impositivo normalizado, menos sensible
            que la media a un año anómalo (p. ej. un ajuste fiscal extraordinario).
        warnings: Ejercicios excluidos y su motivo.
    """

    by_year: dict[int, float]
    median: float
    warnings: tuple[str, ...] = ()


# Tipo efectivo provisión/BAI; devuelve None y el motivo si no tiene sentido económico.
def effective_tax_rate(debt_year: DebtCostYear) -> tuple[float | None, str | None]:
    """Calcula el tipo impositivo efectivo de un ejercicio.

    Args:
        debt_year: Datos del ejercicio con BAI y provisión de impuestos (EUR).

    Returns:
        ``(t, None)`` con t en decimal si es válido, o ``(None, motivo)`` si el BAI es
        ≤ 0 o t queda fuera de [0, 1].
    """
    if debt_year.pretax_income <= 0:
        return None, f"BAI ≤ 0 ({debt_year.pretax_income:,.0f} EUR)"
    rate = debt_year.tax_provision / debt_year.pretax_income
    if not 0.0 <= rate <= 1.0:
        return None, f"tipo efectivo {rate:.1%} fuera de [0 %, 100 %]"
    return rate, None


# Tipos efectivos válidos de cada año y su mediana; error si ningún año es válido.
def tax_rates(debt_cost_data: Sequence[DebtCostYear], purpose: str) -> TaxRates:
    """Calcula los tipos efectivos históricos y su mediana.

    Args:
        debt_cost_data: Ejercicios con BAI y provisión de impuestos.
        purpose: Uso del tipo, para los avisos (p. ej. "el t del WACC").

    Returns:
        Tipos por año, mediana y avisos de años excluidos.

    Raises:
        ValueError: Si ningún ejercicio tiene un tipo efectivo válido.
    """
    by_year: dict[int, float] = {}
    warnings: list[str] = []
    for d in debt_cost_data:
        rate, reason = effective_tax_rate(d)
        if rate is None:
            warnings.append(f"{d.fiscal_year} excluido de {purpose}: {reason}")
        else:
            by_year[d.fiscal_year] = rate
    if not by_year:
        raise ValueError("Ningún ejercicio tiene un tipo efectivo válido: " + "; ".join(warnings))
    return TaxRates(by_year, float(np.median(list(by_year.values()))), tuple(warnings))
