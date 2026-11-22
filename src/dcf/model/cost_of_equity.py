"""Coste de los fondos propios (Ke) por CAPM, beta y datos de mercado.

Común a los modelos FCFF (Ke entra en el WACC) y FCFE (Ke es la tasa de descuento).
Funciones puras, sin I/O. Fórmulas en ``docs/metodologia.md`` §4.
Tasas en decimal (0.08 = 8 %).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from dcf.company import Company


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
        discount_rate_by_ticker: Tasa de descuento forzada por ticker
            (``[discount_rate."REP.MC"]``): sustituye al WACC (FCFF) o a Ke (FCFE)
            calculados. Claves en mayúsculas.
        exit_multiple_by_ticker: Múltiplo de salida del VT por ticker
            (``[exit_multiple."REP.MC"]``): EV/EBITDA en FCFF, P/E en FCFE.
        ronic_by_ticker: RONIC (ROE en FCFE) del value driver por ticker
            (``[ronic."REP.MC"]``); sin él se usa el histórico.
    """

    risk_free_rate: MarketRate
    market_risk_premium: MarketRate
    default_cost_of_debt: MarketRate | None = None
    beta: BetaSettings = BetaSettings()
    beta_by_ticker: Mapping[str, BetaSettings] = field(default_factory=dict)
    discount_rate_by_ticker: Mapping[str, MarketRate] = field(default_factory=dict)
    exit_multiple_by_ticker: Mapping[str, MarketRate] = field(default_factory=dict)
    ronic_by_ticker: Mapping[str, MarketRate] = field(default_factory=dict)

    # Múltiplo de salida del fichero para un ticker; None si no hay.
    def exit_multiple_for(self, ticker: str) -> MarketRate | None:
        """Devuelve el múltiplo de salida del fichero para un ticker.

        Args:
            ticker: Ticker (no distingue mayúsculas).

        Returns:
            Múltiplo (EV/EBITDA en FCFF, P/E en FCFE) con fuente y fecha, o ``None``.
        """
        return self.exit_multiple_by_ticker.get(ticker.upper())

    # RONIC / ROE del fichero para un ticker; None si no hay.
    def ronic_for(self, ticker: str) -> MarketRate | None:
        """Devuelve el RONIC (o ROE en FCFE) del fichero para un ticker.

        Args:
            ticker: Ticker (no distingue mayúsculas).

        Returns:
            RONIC con fuente y fecha, o ``None`` (se usa el histórico).
        """
        return self.ronic_by_ticker.get(ticker.upper())

    # Tasa de descuento forzada en el fichero para un ticker; None si no hay.
    def discount_rate_for(self, ticker: str) -> MarketRate | None:
        """Devuelve la tasa de descuento forzada para un ticker en el fichero.

        Args:
            ticker: Ticker de la compañía (no distingue mayúsculas).

        Returns:
            Tasa con fuente y fecha, o ``None`` si se usa la calculada.
        """
        return self.discount_rate_by_ticker.get(ticker.upper())

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


@dataclass(frozen=True, slots=True)
class CostOfEquityResult:
    """Coste de los fondos propios con sus componentes, para trazabilidad.

    Attributes:
        market_inputs: rf y PRM utilizados, con fuente y fecha.
        beta_choice: Beta utilizada y su origen (modo, fuente, fecha y motivo).
        cost_of_equity: Ke = rf + β · PRM: rentabilidad que exige el accionista.
        warnings: Avisos (p. ej. se usa la beta del fichero porque la de la fuente falta).
    """

    market_inputs: MarketInputs
    beta_choice: BetaChoice
    cost_of_equity: float
    warnings: tuple[str, ...] = ()


# Ke de la compañía por CAPM, con la beta elegida según [beta] de market_inputs.
def compute_cost_of_equity(company: Company, market_inputs: MarketInputs) -> CostOfEquityResult:
    """Calcula el coste de los fondos propios de la compañía.

    Args:
        company: Compañía con la beta publicada por la fuente (si la hay).
        market_inputs: rf, PRM y configuración de la beta.

    Returns:
        Ke con la beta utilizada y avisos.

    Raises:
        ValueError: Si el modo de beta no permite obtener una beta válida.
    """
    choice = resolve_beta(
        company.info.ticker,
        company.balance.beta,
        market_inputs.beta_settings_for(company.info.ticker),
        company.info.source,
        company.info.data_date,
    )
    warnings = (
        (f"Se usa la beta del fichero ({choice.value:g}): {choice.reason}",)
        if choice.reason is not None
        else ()
    )
    ke = cost_of_equity(
        market_inputs.risk_free_rate.value, choice.value, market_inputs.market_risk_premium.value
    )
    return CostOfEquityResult(market_inputs, choice, ke, warnings)
