"""Rentabilidades históricas para el value driver: ROIC (modelos FCFF) y ROE (FCFE).

Funciones puras, sin I/O. Ver ``docs/metodologia.md`` §12. Tasas en decimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from dcf.company import Company
from dcf.model.cost_of_equity import MarketRate


@dataclass(frozen=True, slots=True)
class HistoricalReturn:
    """Rentabilidad histórica de un año y su media.

    Attributes:
        name: "ROIC" o "ROE".
        by_year: Rentabilidad de cada ejercicio con dato válido.
        mean: Media de los años válidos; ``None`` si no hay ninguno.
        warnings: Años excluidos y motivo.
        profit_by_year: Beneficio del numerador de cada ejercicio, en EUR: NOPAT =
            EBIT · (1 − t) en el ROIC (beneficio operativo después de impuestos, sin
            efecto de la financiación); vacío en el ROE.
        capital_by_year: Capital del denominador al cierre de cada ejercicio, en EUR:
            capital invertido = deuda total + fondos propios − caja en el ROIC (lo que
            financian accionistas y acreedores para operar); vacío en el ROE.
    """

    name: str
    by_year: dict[int, float]
    mean: float | None
    warnings: tuple[str, ...] = ()
    profit_by_year: dict[int, float] = field(default_factory=dict)
    capital_by_year: dict[int, float] = field(default_factory=dict)

    # Media como dato con origen, para el value driver.
    def as_rate(self, data_date: datetime) -> MarketRate | None:
        """Devuelve la media como :class:`MarketRate` con su origen.

        Args:
            data_date: Fecha de los datos de la compañía, en UTC.

        Returns:
            Media con fuente «<nombre> histórico medio (años)», o ``None`` sin datos.
        """
        if self.mean is None:
            return None
        years = ", ".join(map(str, sorted(self.by_year)))
        return MarketRate(self.mean, f"{self.name} histórico medio ({years})", data_date)


# ROIC_i = NOPAT_i / capital invertido_{i−1}; capital invertido = deuda + FP − caja.
def historical_roic(company: Company, tax_rate: float) -> HistoricalReturn:
    """Calcula el ROIC histórico: rentabilidad del capital invertido en el negocio.

    Args:
        company: Compañía con EBIT y deuda (coste de la deuda) y fondos propios y caja de
            cada ejercicio.
        tax_rate: Tipo impositivo del NOPAT, en decimal.

    Returns:
        ROIC por año (desde el segundo, sobre el capital invertido al inicio) y media,
        con el NOPAT de cada año con EBIT y el capital invertido de cada cierre.
    """
    debt = {d.fiscal_year: d for d in company.debt_cost_data}
    nopat = {
        h.fiscal_year: debt[h.fiscal_year].ebit * (1.0 - tax_rate)
        for h in company.historicals
        if h.fiscal_year in debt
    }
    invested: dict[int, float] = {}
    warnings: list[str] = []
    for h in company.historicals:
        d = debt.get(h.fiscal_year)
        if d is None or h.stockholders_equity is None or h.cash is None:
            warnings.append(f"{h.fiscal_year}: sin deuda, fondos propios o caja para el ROIC")
            continue
        invested[h.fiscal_year] = d.total_debt + h.stockholders_equity - h.cash
    roic: dict[int, float] = {}
    for prev, curr in zip(company.historicals, company.historicals[1:], strict=False):
        start = invested.get(prev.fiscal_year)
        d = debt.get(curr.fiscal_year)
        if start is None or d is None:
            continue
        if start <= 0:
            warnings.append(f"{curr.fiscal_year} excluido del ROIC: capital invertido inicial ≤ 0")
            continue
        roic[curr.fiscal_year] = nopat[curr.fiscal_year] / start
    mean = float(np.mean(list(roic.values()))) if roic else None
    return HistoricalReturn("ROIC", roic, mean, tuple(warnings), nopat, invested)


# ROE_i = Net Income_i / fondos propios_{i−1}.
def historical_roe(company: Company) -> HistoricalReturn:
    """Calcula el ROE histórico: rentabilidad de los fondos propios del accionista.

    Args:
        company: Compañía con Net Income y fondos propios de cada ejercicio.

    Returns:
        ROE por año (desde el segundo, sobre los fondos propios al inicio) y media.
    """
    roe: dict[int, float] = {}
    warnings: list[str] = []
    for prev, curr in zip(company.historicals, company.historicals[1:], strict=False):
        equity = prev.stockholders_equity
        if equity is None or equity <= 0:
            warnings.append(
                f"{curr.fiscal_year} excluido del ROE: fondos propios iniciales ≤ 0 o ausentes"
            )
            continue
        roe[curr.fiscal_year] = curr.net_income / equity
    mean = float(np.mean(list(roe.values()))) if roe else None
    return HistoricalReturn("ROE", roe, mean, tuple(warnings))
