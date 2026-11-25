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

from dcf.company import Company, ValuationModel
from dcf.defaults import BLUME_WEIGHT, DEFAULT_BETA_MODE, KE_FLOOR_BETA
from dcf.model.tax import tax_rates


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
    BOTTOM_UP = "bottom-up"
    """Beta sectorial desapalancada del fichero, reapalancada con el D/E de la empresa;
    sin beta sectorial, la de la fuente ajustada por Blume (por defecto)."""


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
        reason: Por qué no se usa la beta principal del modo (en ``yahoo-fichero``, la
            de la fuente; en ``bottom-up``, la sectorial); ``None`` si se usa.
        unlevered_beta: En ``bottom-up``, beta sectorial desapalancada (riesgo del
            negocio sin deuda) antes de reapalancar; ``None`` en los demás casos.
    """

    value: float
    source: str
    date: datetime
    mode: BetaMode
    source_beta: float | None
    reason: str | None = None
    unlevered_beta: float | None = None


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
        sector_beta_by_key: Beta desapalancada por clave de industria o de sector de la
            fuente (``[sector_beta."engineering-construction"]``): riesgo sistemático
            del negocio sin deuda, p. ej. las de Damodaran. Claves en minúsculas.
        country_risk_premium_by_country: Prima de riesgo país por país de la fuente
            (``[country_risk_premium."Spain"]``): rentabilidad extra que exige invertir en
            ese país frente a uno sin riesgo de impago. Claves en minúsculas.
    """

    risk_free_rate: MarketRate
    market_risk_premium: MarketRate
    default_cost_of_debt: MarketRate | None = None
    beta: BetaSettings = BetaSettings()
    beta_by_ticker: Mapping[str, BetaSettings] = field(default_factory=dict)
    discount_rate_by_ticker: Mapping[str, MarketRate] = field(default_factory=dict)
    exit_multiple_by_ticker: Mapping[str, MarketRate] = field(default_factory=dict)
    ronic_by_ticker: Mapping[str, MarketRate] = field(default_factory=dict)
    sector_beta_by_key: Mapping[str, MarketRate] = field(default_factory=dict)
    country_risk_premium_by_country: Mapping[str, MarketRate] = field(default_factory=dict)

    # Beta sectorial desapalancada: primero la de la industria, después la del sector.
    def sector_beta_for(
        self, industry_key: str | None, sector_key: str | None
    ) -> tuple[str, MarketRate] | None:
        """Busca la beta sectorial desapalancada de una empresa.

        Args:
            industry_key: Clave de industria de la fuente (``None`` si no la hay).
            sector_key: Clave de sector de la fuente (``None`` si no la hay).

        Returns:
            Clave encontrada y beta con fuente y fecha, o ``None``.
        """
        for key in (industry_key, sector_key):
            if key is not None and key.lower() in self.sector_beta_by_key:
                return key.lower(), self.sector_beta_by_key[key.lower()]
        return None

    # Prima de riesgo país del fichero; None si no está.
    def country_risk_premium_for(self, country: str | None) -> MarketRate | None:
        """Devuelve la prima de riesgo país de un país.

        Args:
            country: País según la fuente (p. ej. "Spain"); no distingue mayúsculas.

        Returns:
            Prima con fuente y fecha, o ``None``.
        """
        if country is None:
            return None
        return self.country_risk_premium_by_country.get(country.lower())

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
            Configuración con modo (``bottom-up`` si no se indica en ningún sitio) y
            valor.
        """
        own = self.beta_by_ticker.get(ticker.upper(), BetaSettings())
        mode = own.mode or self.beta.mode or BetaMode(DEFAULT_BETA_MODE)
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
    mode = settings.mode or BetaMode(DEFAULT_BETA_MODE)
    if mode is BetaMode.BOTTOM_UP:
        raise ValueError("El modo bottom-up necesita la compañía: usa compute_cost_of_equity")
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
class KeFloor:
    """Suelo del coste de los fondos propios por riesgo país.

    Attributes:
        country: País de la empresa según la fuente.
        country_risk_premium: Prima de riesgo país (CRP) con fuente y fecha: lo que se
            exige de más por el riesgo soberano y macroeconómico del país.
        value: Ke mínimo = rf + 1 · PRM + CRP: lo que rinde el mercado del país; ninguna
            acción se descuenta a menos.
    """

    country: str
    country_risk_premium: MarketRate
    value: float


# Suelo de Ke: rf + 1 · PRM + prima de riesgo país del país de la empresa.
def cost_of_equity_floor(company: Company, market_inputs: MarketInputs) -> KeFloor:
    """Calcula el suelo de Ke por riesgo país (``docs/metodologia.md`` §4).

    Args:
        company: Compañía con su país.
        market_inputs: rf, PRM y primas de riesgo país.

    Returns:
        Suelo con la prima país utilizada.

    Raises:
        ValueError: Si la fuente no publica el país o el fichero no tiene su prima.
    """
    country = company.info.country
    if country is None:
        raise ValueError(
            f"{company.info.ticker}: la fuente no publica el país, necesario para el suelo de Ke"
        )
    crp = market_inputs.country_risk_premium_for(country)
    if crp is None:
        raise ValueError(
            f'{company.info.ticker}: falta la prima de riesgo país de "{country}". Añade en '
            f'config/data/market_inputs.toml [country_risk_premium."{country}"] con value '
            "(0 si el país no tiene prima), source y date"
        )
    value = (
        market_inputs.risk_free_rate.value
        + KE_FLOOR_BETA * market_inputs.market_risk_premium.value
        + crp.value
    )
    return KeFloor(country, crp, value)


# Beta bottom-up: sectorial reapalancada; sin sectorial, la de la fuente ajustada por Blume.
def bottom_up_beta(
    company: Company, market_inputs: MarketInputs, settings: BetaSettings
) -> BetaChoice:
    """Calcula la beta del modo ``bottom-up`` (``docs/metodologia.md`` §4).

    - Con beta sectorial: β = βu · (1 + (1 − t) · D / E), con D la deuda total
      contable, E la capitalización y t la mediana de los tipos efectivos. En
      ``fcfe_fin`` la beta sectorial se usa sin reapalancar: la deuda de una financiera
      es su materia prima y las betas de bancos y aseguradoras ya se publican así.
    - Sin beta sectorial: β = 0,67 · β_fuente + 0,33 (Blume); si la fuente no publica
      una beta válida, la del fichero (``[beta]``) si existe.

    Args:
        company: Compañía (claves de sector e industria, balance, impuestos y beta).
        market_inputs: Betas sectoriales.
        settings: Configuración efectiva de beta del ticker (beta de respaldo).

    Returns:
        Beta elegida con su origen.

    Raises:
        ValueError: Si no hay beta sectorial ni una beta de la fuente o del fichero válida.
    """
    info, balance = company.info, company.balance
    mode = BetaMode.BOTTOM_UP
    sector = market_inputs.sector_beta_for(info.industry_key, info.sector_key)
    if sector is not None:
        key, unlevered = sector
        if info.valuation_model is ValuationModel.FCFE_FIN:
            source = f"Beta sectorial «{key}» sin reapalancar (financiera): {unlevered.source}"
            return BetaChoice(
                unlevered.value, source, unlevered.date, mode, balance.beta, None, unlevered.value
            )
        debt = balance.total_debt
        if debt is None:
            raise ValueError(f"{info.ticker}: falta la deuda total para reapalancar la beta")
        equity = balance.share_price * balance.diluted_shares
        t = tax_rates(company.debt_cost_data, "el t de la beta").median
        beta = unlevered.value * (1.0 + (1.0 - t) * debt / equity)
        source = (
            f"Bottom-up: βu «{key}» {unlevered.value:g} ({unlevered.source}) reapalancada con "
            f"D/E {debt / equity:.3f} y t {t:.2%}"
        )
        return BetaChoice(beta, source, unlevered.date, mode, balance.beta, None, unlevered.value)

    missing = f"sin beta sectorial para «{info.industry_key or '—'}» ni «{info.sector_key or '—'}»"
    source_beta = balance.beta
    if source_beta is not None and source_beta >= 0:
        adjusted = BLUME_WEIGHT * source_beta + (1.0 - BLUME_WEIGHT) * 1.0
        source = (
            f"{info.source} ajustada por Blume "
            f"({BLUME_WEIGHT:g} · {source_beta:g} + {1 - BLUME_WEIGHT:g})"
        )
        return BetaChoice(adjusted, source, info.data_date, mode, source_beta, missing)
    problem = (
        "no publica beta" if source_beta is None else f"da una beta negativa ({source_beta:g})"
    )
    manual = settings.value
    if manual is None:
        raise ValueError(
            f'{info.ticker}: {missing} y {info.source} {problem}. Añade [sector_beta."'
            f'{info.industry_key or info.sector_key or "clave"}"] o [beta."{info.ticker}"] en '
            "config/data/market_inputs.toml"
        )
    return BetaChoice(
        manual.value,
        manual.source,
        manual.date,
        mode,
        source_beta,
        f"{missing} y la fuente {problem}",
    )


@dataclass(frozen=True, slots=True)
class CostOfEquityResult:
    """Coste de los fondos propios con sus componentes, para trazabilidad.

    Attributes:
        market_inputs: rf y PRM utilizados, con fuente y fecha.
        beta_choice: Beta utilizada y su origen (modo, fuente, fecha y motivo).
        cost_of_equity: Ke utilizado: el mayor entre el CAPM y el suelo; rentabilidad
            que exige el accionista.
        warnings: Avisos (p. ej. se usa la beta de respaldo, o se aplica el suelo).
        capm: Ke por CAPM, rf + β · PRM + prima país, antes del suelo; ``None`` = igual a
            ``cost_of_equity`` (resultados construidos sin suelo).
        floor: Suelo de Ke por riesgo país; ``None`` si no se calculó.
    """

    market_inputs: MarketInputs
    beta_choice: BetaChoice
    cost_of_equity: float
    warnings: tuple[str, ...] = ()
    capm: float | None = None
    floor: KeFloor | None = None

    # True si el suelo eleva Ke por encima del CAPM.
    @property
    def floor_applied(self) -> bool:
        """Indica si Ke es el suelo y no el CAPM."""
        return self.capm is not None and self.cost_of_equity > self.capm


# Ke de la compañía: CAPM con la beta según [beta] y suelo por riesgo país.
def compute_cost_of_equity(company: Company, market_inputs: MarketInputs) -> CostOfEquityResult:
    """Calcula el coste de los fondos propios de la compañía.

    Ke = max(rf + β · PRM + CRP, suelo), con CRP la prima de riesgo país y el suelo
    rf + 1 · PRM + CRP (manda cuando β < 1). PRM es la de un mercado maduro.

    Args:
        company: Compañía con la beta publicada por la fuente (si la hay), su país y sus
            claves de sector e industria.
        market_inputs: rf, PRM, configuración de la beta, betas sectoriales y primas de
            riesgo país.

    Returns:
        Ke con la beta utilizada, el CAPM, el suelo y avisos.

    Raises:
        ValueError: Si el modo de beta no permite obtener una beta válida, o falta la
            prima de riesgo país del país de la empresa.
    """
    settings = market_inputs.beta_settings_for(company.info.ticker)
    if settings.mode is BetaMode.BOTTOM_UP:
        choice = bottom_up_beta(company, market_inputs, settings)
    else:
        choice = resolve_beta(
            company.info.ticker,
            company.balance.beta,
            settings,
            company.info.source,
            company.info.data_date,
        )
    warnings: list[str] = []
    if choice.reason is not None:
        warnings.append(f"Beta de respaldo ({choice.value:.3f}, {choice.source}): {choice.reason}")
    floor = cost_of_equity_floor(company, market_inputs)
    # CAPM con prima país (Damodaran): rf + β · PRM madura + prima de riesgo país.
    capm = (
        cost_of_equity(
            market_inputs.risk_free_rate.value,
            choice.value,
            market_inputs.market_risk_premium.value,
        )
        + floor.country_risk_premium.value
    )
    if floor.value > capm:
        warnings.append(
            f"Ke por CAPM ({capm:.2%}) por debajo del suelo de {floor.country} ({floor.value:.2%} "
            f"= rf + PRM + prima país {floor.country_risk_premium.value:.2%}): se usa el suelo"
        )
    return CostOfEquityResult(
        market_inputs, choice, max(capm, floor.value), tuple(warnings), capm, floor
    )
