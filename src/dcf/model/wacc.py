"""Coste medio ponderado del capital (WACC). Funciones puras, sin I/O.

Fórmulas en ``docs/metodologia.md`` §4. Tasas en decimal (0.08 = 8 %), importes en EUR.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np

from dcf.company import Company
from dcf.model.ratios import effective_tax_rate

WEIGHT_TOLERANCE = 1e-9
"""Tolerancia para comprobar que los pesos suman 1 (error de redondeo en float)."""


@dataclass(frozen=True, slots=True)
class MarketRate:
    """Una tasa de mercado introducida por el usuario, con su trazabilidad.

    Attributes:
        value: Tasa en decimal (0.03 = 3 %).
        source: De dónde sale el dato (p. ej. "Bund 10 años, Bundesbank").
        date: Fecha del dato, en UTC.
    """

    value: float
    source: str
    date: datetime

    # Valida tasa finita, fuente no vacía y fecha con zona.
    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError(f"La tasa debe ser finita, recibido {self.value!r}")
        if not self.source.strip():
            raise ValueError("Toda tasa de mercado debe indicar su fuente")
        if self.date.tzinfo is None or self.date.utcoffset() is None:
            raise ValueError("La fecha de la tasa debe tener zona horaria (UTC)")


class BetaMode(StrEnum):
    """De dónde se toma la beta (``[beta].mode`` en ``market_inputs.toml``)."""

    YAHOO = "yahoo"
    """Solo la beta de la fuente de datos; error si falta o es negativa."""
    FILE = "fichero"
    """Siempre la beta del fichero (override de la de la fuente)."""
    YAHOO_FILE = "yahoo-fichero"
    """La de la fuente; la del fichero solo si la fuente no la publica o es negativa."""


@dataclass(frozen=True, slots=True)
class BetaSettings:
    """Configuración de la beta, general o de un ticker concreto.

    Attributes:
        mode: Modo de selección; ``None`` = heredar (de la general o, en su defecto,
            ``yahoo``).
        value: Beta introducida por el usuario, con fuente y fecha: sensibilidad del
            rendimiento de la acción al del mercado (riesgo sistemático), p. ej. una
            beta sectorial de Damodaran. ``None`` si no se indica.
    """

    mode: BetaMode | None = None
    value: MarketRate | None = None

    # Valida que la beta del fichero no sea negativa.
    def __post_init__(self) -> None:
        if self.value is not None and self.value.value < 0:
            raise ValueError(
                f"La beta del fichero no puede ser negativa, recibido {self.value.value}"
            )


@dataclass(frozen=True, slots=True)
class BetaChoice:
    """Beta utilizada finalmente en el CAPM y su origen.

    Attributes:
        value: Beta utilizada.
        source: Fuente de la beta utilizada.
        date: Fecha de la beta utilizada (la de la descarga si es de la fuente), en UTC.
        mode: Modo de selección aplicado.
        source_beta: Beta publicada por la fuente de datos; ``None`` si no la publica.
        reason: En el modo ``yahoo-fichero``, por qué se usa la del fichero;
            ``None`` en los demás casos.
    """

    value: float
    source: str
    date: datetime
    mode: BetaMode
    source_beta: float | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MarketInputs:
    """Datos de mercado que no vienen de la compañía.

    Attributes:
        risk_free_rate: Rentabilidad libre de riesgo (rf): lo que rinde una inversión
            sin riesgo de impago, normalmente el bono soberano a 10 años.
        market_risk_premium: Prima de riesgo de mercado (PRM): rentabilidad extra que
            exige el inversor por invertir en renta variable frente a rf.
        default_cost_of_debt: Coste de la deuda antes de impuestos que se aplica a la
            deuda total de los ejercicios en los que la fuente no publica intereses.
            ``None`` si no se indica: entonces faltar intereses es un error.
        beta: Configuración general de la beta (sección ``[beta]``).
        beta_by_ticker: Configuración por ticker (``[beta."REP.MC"]``), que prevalece
            sobre la general en cada campo que indique. Claves en mayúsculas.
    """

    risk_free_rate: MarketRate
    market_risk_premium: MarketRate
    default_cost_of_debt: MarketRate | None = None
    beta: BetaSettings = BetaSettings()
    beta_by_ticker: Mapping[str, BetaSettings] = field(default_factory=dict)

    # Configuración de beta efectiva de un ticker: la suya y, en lo que falte, la general.
    def beta_settings_for(self, ticker: str) -> BetaSettings:
        """Combina la configuración de beta del ticker con la general.

        Args:
            ticker: Ticker de la compañía (no distingue mayúsculas).

        Returns:
            Configuración con modo (``yahoo`` si no se indica en ningún sitio) y valor.
        """
        own = self.beta_by_ticker.get(ticker.upper(), BetaSettings())
        mode = own.mode or self.beta.mode or BetaMode.YAHOO
        return BetaSettings(mode=mode, value=own.value or self.beta.value)

    # Valida prima de riesgo positiva y Kd por defecto no negativo.
    def __post_init__(self) -> None:
        if self.market_risk_premium.value <= 0:
            raise ValueError(
                f"La prima de riesgo debe ser positiva, recibido {self.market_risk_premium.value}"
            )
        if self.default_cost_of_debt is not None and self.default_cost_of_debt.value < 0:
            raise ValueError(
                "El coste de la deuda por defecto no puede ser negativo, "
                f"recibido {self.default_cost_of_debt.value}"
            )


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


# CAPM: Ke = rf + β · PRM.
def cost_of_equity(risk_free_rate: float, beta: float, market_risk_premium: float) -> float:
    """Calcula el coste de los fondos propios con el CAPM.

    Args:
        risk_free_rate: rf en decimal.
        beta: Beta de la acción.
        market_risk_premium: PRM en decimal.

    Returns:
        Ke en decimal.
    """
    return risk_free_rate + beta * market_risk_premium


# Elige la beta según el modo: fuente (Yahoo), fichero, o fuente con respaldo del fichero.
def resolve_beta(
    ticker: str,
    source_beta: float | None,
    settings: BetaSettings,
    data_source: str,
    data_date: datetime,
) -> BetaChoice:
    """Decide qué beta se usa en el CAPM (``docs/metodologia.md`` §4).

    - ``yahoo``: la de la fuente; error si no la publica o es negativa.
    - ``fichero``: siempre la del fichero; error si no está.
    - ``yahoo-fichero``: la de la fuente; si no la publica o es negativa, la del
      fichero, registrando el motivo; error si tampoco está en el fichero.

    Args:
        ticker: Ticker, para los mensajes.
        source_beta: Beta publicada por la fuente de datos (``None`` si no la hay).
        settings: Configuración efectiva (ver :meth:`MarketInputs.beta_settings_for`).
        data_source: Nombre de la fuente de datos (p. ej. "Yahoo Finance").
        data_date: Fecha de los datos de la fuente, en UTC.

    Returns:
        Beta elegida con su origen.

    Raises:
        ValueError: Si el modo no permite obtener una beta válida, indicando el motivo.
    """
    mode = settings.mode or BetaMode.YAHOO
    manual = settings.value
    hint = (
        f'Añade en config/data/market_inputs.toml una sección [beta."{ticker.upper()}"] '
        "con value, source y date"
    )

    if mode is BetaMode.FILE:
        if manual is None:
            raise ValueError(f'{ticker}: modo de beta "fichero" sin beta en el fichero. {hint}')
        return BetaChoice(manual.value, manual.source, manual.date, mode, source_beta)

    if source_beta is None:
        problem = f"{data_source} no publica beta"
    elif source_beta < 0:
        problem = f"la beta de {data_source} es negativa ({source_beta:g}), no válida para el CAPM"
    else:
        return BetaChoice(source_beta, data_source, data_date, mode, source_beta)

    if mode is BetaMode.YAHOO:
        raise ValueError(
            f'{ticker}: {problem} (modo de beta "yahoo"). {hint}, y usa en [beta] '
            'mode = "yahoo-fichero" o "fichero"'
        )
    if manual is None:
        raise ValueError(f"{ticker}: {problem} y no hay beta de respaldo en el fichero. {hint}")
    return BetaChoice(manual.value, manual.source, manual.date, mode, source_beta, problem)


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
    debt_value = balance.total_debt
    if debt_value > 0 and not kd_by_year:
        raise ValueError("La empresa tiene deuda pero ningún ejercicio permite calcular Kd")
    kd = float(np.mean(list(kd_by_year.values()))) if kd_by_year else None

    choice = resolve_beta(
        company.info.ticker,
        balance.beta,
        market_inputs.beta_settings_for(company.info.ticker),
        company.info.source,
        company.info.data_date,
    )
    if choice.reason is not None:
        warnings.append(f"Se usa la beta del fichero ({choice.value:g}): {choice.reason}")
    ke = cost_of_equity(
        market_inputs.risk_free_rate.value, choice.value, market_inputs.market_risk_premium.value
    )
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
