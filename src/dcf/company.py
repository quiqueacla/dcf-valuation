"""Datos de una compañía necesarios para el DCF.

Todas las cifras monetarias están en EUR, en unidades (no millones), como ``float``.
La conversión desde la moneda de origen la hace el módulo de ``data/`` y queda
registrada en :class:`CompanyInfo`. Estas clases solo almacenan y validan datos
brutos: los ratios (crecimiento, márgenes, tipo impositivo) se calculan en ``model/``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

WORKING_CURRENCY = "EUR"
"""Moneda de trabajo del proyecto (decisión 2026-11-18, ver CLAUDE.md)."""


class CompanyType(StrEnum):
    """Tipo de empresa a efectos del modelo de valoración (``config/company_types.toml``)."""

    INDUSTRIAL = "industrial"
    """Empresa operativa (industria, servicios, consumo...)."""
    BANK = "banco"
    """Banco: la deuda (depósitos) es materia prima del negocio, no financiación."""
    INSURANCE = "aseguradora"
    """Aseguradora: invierte las primas; reservas técnicas en lugar de deuda financiera."""
    REAL_ESTATE = "inmobiliaria"
    """Inmobiliaria o SOCIMI/REIT: el valor está sobre todo en los activos inmobiliarios."""


class ValuationModel(StrEnum):
    """Modelo de valoración (``docs/metodologia.md``)."""

    FCFF_CFO = "fcff_cfo"
    """FCFF desde el CFO: Net Income × media histórica de FCFF/Net Income, al WACC; puente
    VE → fondos propios (industriales)."""
    FCFE = "fcfe"
    """Flujo de caja libre para el accionista descontado a Ke (financieras)."""


# Modelos adecuados para cada tipo de empresa (conocimiento del modelo, no configuración).
SUITABLE_MODELS: dict[CompanyType, frozenset[ValuationModel]] = {
    CompanyType.INDUSTRIAL: frozenset({ValuationModel.FCFF_CFO}),
    CompanyType.BANK: frozenset({ValuationModel.FCFE}),
    CompanyType.INSURANCE: frozenset({ValuationModel.FCFE}),
    CompanyType.REAL_ESTATE: frozenset(),
}

# Motivo por el que un modelo no es adecuado para un tipo de empresa.
UNSUITABLE_NOTES: dict[tuple[CompanyType, ValuationModel], str] = {
    (CompanyType.BANK, ValuationModel.FCFF_CFO): (
        "en un banco la deuda es materia prima del negocio, así que el FCFF y el WACC no "
        "son significativos; usa el modelo fcfe"
    ),
    (CompanyType.INSURANCE, ValuationModel.FCFF_CFO): (
        "en una aseguradora las primas invertidas y las reservas técnicas hacen que el FCFF "
        "y la deuda no sean comparables; usa el modelo fcfe"
    ),
    (CompanyType.INDUSTRIAL, ValuationModel.FCFE): (
        "el FCFE de este proyecto supone que el crecimiento se financia reteniendo beneficio "
        "en fondos propios, como en una financiera; en una industrial el FCFF recoge la "
        "inversión y la deuda"
    ),
}

REAL_ESTATE_NOTE = (
    "en una inmobiliaria o SOCIMI el valor está en los activos y las compras de inmuebles "
    "distorsionan los flujos; se suele usar el valor neto de los activos (NAV) o FFO/AFFO"
)


# Aviso si el modelo aplicado no es adecuado para el tipo de empresa; None si lo es.
def model_suitability_warning(
    company_type: CompanyType | None, model: ValuationModel = ValuationModel.FCFF_CFO
) -> str | None:
    """Explica si el modelo de valoración no es adecuado para el tipo de empresa.

    Args:
        company_type: Tipo de empresa; ``None`` si no se ha clasificado.
        model: Modelo con el que se valora.

    Returns:
        Texto del aviso, o ``None`` si el modelo es adecuado para el tipo.
    """
    if company_type is None:
        return f"Tipo de empresa sin clasificar: comprueba que el modelo {model.value} es adecuado"
    if model in SUITABLE_MODELS[company_type]:
        return None
    note = (
        REAL_ESTATE_NOTE
        if company_type is CompanyType.REAL_ESTATE
        else UNSUITABLE_NOTES[(company_type, model)]
    )
    return (
        f"Empresa de tipo {company_type.value}: el modelo {model.value} puede no ser "
        f"adecuado y el resultado puede no ser significativo ({note})"
    )


# Devuelve el dato si existe; error claro si la fuente no lo publica y el modelo lo necesita.
def required(value: float | None, name: str, model: ValuationModel) -> float:
    """Exige un dato opcional que el modelo necesita.

    Args:
        value: Dato (``None`` si la fuente no lo publica).
        name: Nombre del dato, para el mensaje.
        model: Modelo que lo necesita.

    Returns:
        El dato.

    Raises:
        ValueError: Si el dato es ``None``.
    """
    if value is None:
        raise ValueError(f"Falta {name}, necesario para el modelo {model.value}")
    return value


# Lanza ValueError si el valor no es un número finito.
def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} debe ser un número finito, recibido {value!r}")


# Lanza ValueError si el valor no es finito o es negativo.
def _require_non_negative(name: str, value: float) -> None:
    _require_finite(name, value)
    if value < 0:
        raise ValueError(f"{name} no puede ser negativo, recibido {value!r}")


# Lanza ValueError si el valor no es finito o no es estrictamente positivo.
def _require_positive(name: str, value: float) -> None:
    _require_finite(name, value)
    if value <= 0:
        raise ValueError(f"{name} debe ser positivo, recibido {value!r}")


# Aplica una validación solo si el dato opcional existe.
def _if_present(check: Callable[[str, float], None], name: str, value: float | None) -> None:
    if value is not None:
        check(name, value)


# Lanza ValueError si la fecha no lleva zona horaria.
def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} debe ser un datetime con zona horaria (UTC)")


# Comprueba que los ejercicios son consecutivos y en orden ascendente.
def _require_consecutive_years(name: str, years: list[int]) -> None:
    for prev, curr in zip(years, years[1:], strict=False):
        if curr != prev + 1:
            raise ValueError(
                f"{name}: los ejercicios deben ser consecutivos y ascendentes, recibido {years}"
            )


@dataclass(frozen=True, slots=True)
class CompanyInfo:
    """Identificación de la compañía y trazabilidad de los datos.

    Attributes:
        ticker: Símbolo bursátil (p. ej. ``"SAN.MC"``).
        name: Nombre legal o comercial de la compañía.
        source: Fuente de los datos (p. ej. ``"yahoo_finance"``).
        data_date: Momento de la descarga de los datos, en UTC.
        original_currency: Moneda en la que la fuente reporta los estados financieros.
        fx_rate_to_eur: Tipo de cambio aplicado: EUR por unidad de moneda original
            (1.0 si la moneda original ya es EUR).
        fx_date: Fecha de los tipos de cambio aplicados, en UTC. ``None`` solo si
            todas las monedas son EUR.
        price_currency: Moneda en la que cotiza la acción (unidad principal, p. ej.
            GBP aunque la fuente dé GBp).
        price_fx_rate_to_eur: EUR por unidad de la moneda de cotización.
        data_warnings: Avisos de la carga de datos (p. ej. filas ausentes tratadas como 0).
        sector: Sector de actividad según la fuente (p. ej. "Energy"); ``None`` si no
            lo publica.
        industry: Industria dentro del sector según la fuente (p. ej. "Banks -
            Diversified"); ``None`` si no la publica.
        company_type: Tipo de empresa a efectos del modelo (industrial, banco,
            aseguradora, inmobiliaria), derivado de sector e industria; ``None`` si no
            se ha clasificado.
        valuation_model: Modelo de valoración para el que se cargaron los datos (fcff o
            fcfe): el de la tabla de tipos o el forzado por el usuario.
    """

    ticker: str
    name: str
    source: str
    data_date: datetime
    original_currency: str
    fx_rate_to_eur: float
    fx_date: datetime | None
    price_currency: str = WORKING_CURRENCY
    price_fx_rate_to_eur: float = 1.0
    data_warnings: tuple[str, ...] = ()
    sector: str | None = None
    industry: str | None = None
    company_type: CompanyType | None = None
    valuation_model: ValuationModel = ValuationModel.FCFF_CFO

    # Valida identificación, fechas con zona y coherencia de los tipos de cambio.
    def __post_init__(self) -> None:
        if not self.ticker.strip():
            raise ValueError("ticker no puede estar vacío")
        if not self.source.strip():
            raise ValueError("source no puede estar vacío")
        _require_aware("data_date", self.data_date)
        for currency, rate, name in (
            (self.original_currency, self.fx_rate_to_eur, "fx_rate_to_eur"),
            (self.price_currency, self.price_fx_rate_to_eur, "price_fx_rate_to_eur"),
        ):
            _require_positive(name, rate)
            if currency == WORKING_CURRENCY:
                if rate != 1.0:
                    raise ValueError(f"{name} debe ser 1.0 si la moneda es EUR")
            elif self.fx_date is None:
                raise ValueError(f"fx_date es obligatorio al convertir desde {currency} a EUR")
        if self.fx_date is not None:
            _require_aware("fx_date", self.fx_date)


@dataclass(frozen=True, slots=True)
class HistoricalYear:
    """Datos de un ejercicio histórico para la proyección de flujos (EUR).

    Ventas y Net Income los usan los dos modelos. Los flujos de caja los necesita el
    FCFF y los fondos propios el FCFE; cada uno es ``None`` si la fuente no lo publica
    o el modelo aplicado no lo necesita (p. ej. el CFO de un banco).

    Attributes:
        fiscal_year: Ejercicio fiscal (año de cierre).
        revenue: Ventas (cifra de negocio). Debe ser positiva para calcular márgenes.
        net_income: Beneficio neto atribuible. Puede ser negativo (pérdidas).
        operating_cash_flow: Flujo de caja de las operaciones (CFO). Puede ser negativo.
        capital_expenditure: Inversión en activo fijo (CapEx), como importe positivo
            de salida de caja.
        interest_expense: Gasto financiero por intereses, como importe positivo.
        debt_issuance: Deuda nueva obtenida en el ejercicio, importe positivo.
        debt_repayment: Deuda devuelta en el ejercicio, importe positivo.
        stockholders_equity: Fondos propios contables atribuibles a la dominante al
            cierre (patrimonio neto sin minoritarios): el capital que sostiene el
            negocio de una financiera.
    """

    fiscal_year: int
    revenue: float
    net_income: float
    operating_cash_flow: float | None
    capital_expenditure: float | None
    interest_expense: float | None
    debt_issuance: float | None
    debt_repayment: float | None
    stockholders_equity: float | None = None

    # Valida signos: ventas positivas, salidas de caja como importes no negativos.
    def __post_init__(self) -> None:
        _require_positive("revenue", self.revenue)
        _require_finite("net_income", self.net_income)
        _if_present(_require_finite, "operating_cash_flow", self.operating_cash_flow)
        _if_present(_require_non_negative, "capital_expenditure", self.capital_expenditure)
        _if_present(_require_non_negative, "interest_expense", self.interest_expense)
        _if_present(_require_non_negative, "debt_issuance", self.debt_issuance)
        _if_present(_require_non_negative, "debt_repayment", self.debt_repayment)
        _if_present(_require_finite, "stockholders_equity", self.stockholders_equity)


@dataclass(frozen=True, slots=True)
class DebtCostYear:
    """Datos de un ejercicio histórico para el coste de la deuda y el tipo impositivo (EUR).

    Attributes:
        fiscal_year: Ejercicio fiscal (año de cierre).
        total_debt: Deuda financiera total (corto + largo plazo) al cierre.
        interest_expense: Gasto financiero por intereses, como importe positivo.
        ebit: Resultado operativo (beneficio antes de intereses e impuestos).
        pretax_income: Beneficio antes de impuestos (BAI).
        tax_provision: Gasto por impuesto sobre beneficios del ejercicio.
    """

    fiscal_year: int
    total_debt: float
    interest_expense: float
    ebit: float
    pretax_income: float
    tax_provision: float

    # Valida que deuda e intereses no sean negativos y el resto sean finitos.
    def __post_init__(self) -> None:
        _require_non_negative("total_debt", self.total_debt)
        _require_non_negative("interest_expense", self.interest_expense)
        _require_finite("ebit", self.ebit)
        _require_finite("pretax_income", self.pretax_income)
        _require_finite("tax_provision", self.tax_provision)


@dataclass(frozen=True, slots=True)
class RevenueEstimate:
    """Estimación de ventas del consenso de analistas (EUR).

    Attributes:
        fiscal_year: Ejercicio estimado (+1 = ejercicio en curso, +2 = siguiente).
        revenue: Ventas medias estimadas por el consenso (escenario neutro).
        num_analysts: Número de analistas que componen el consenso, si se conoce.
        revenue_low: Estimación más baja de los analistas (escenario bajista), si se conoce.
        revenue_high: Estimación más alta de los analistas (escenario alcista), si se conoce.
    """

    fiscal_year: int
    revenue: float
    num_analysts: int | None = None
    revenue_low: float | None = None
    revenue_high: float | None = None

    # Valida que las estimaciones sean positivas.
    def __post_init__(self) -> None:
        _require_positive("revenue", self.revenue)
        if self.num_analysts is not None and self.num_analysts <= 0:
            raise ValueError("num_analysts debe ser positivo si se indica")
        if self.revenue_low is not None:
            _require_positive("revenue_low", self.revenue_low)
        if self.revenue_high is not None:
            _require_positive("revenue_high", self.revenue_high)


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    """Partidas del último balance y de mercado (puente VE → valor por acción y WACC).

    Attributes:
        balance_date: Fecha del balance utilizado, en UTC.
        cash: Caja y equivalentes (incluye inversiones financieras a corto plazo).
            ``None`` si el modelo no la necesita (en FCFE no hay puente de caja).
        total_debt: Deuda financiera total al cierre (peso D del WACC, valor contable).
            ``None`` si el modelo no la necesita (FCFE).
        minority_interest: Intereses minoritarios (participaciones no dominantes).
        diluted_shares: Número de acciones diluidas en circulación.
        share_price: Cotización de la acción, en EUR.
        beta: Sensibilidad del rendimiento de la acción al del mercado (riesgo
            sistemático), según la fuente de datos. ``None`` si la fuente no la publica.
            La beta que se usa en el CAPM se decide según ``[beta]`` de
            ``market_inputs.toml``.
    """

    balance_date: datetime
    cash: float | None
    total_debt: float | None
    minority_interest: float
    diluted_shares: float
    share_price: float
    beta: float | None

    # Valida importes no negativos, acciones y precio positivos y beta finita si existe.
    def __post_init__(self) -> None:
        _require_aware("balance_date", self.balance_date)
        _if_present(_require_finite, "beta", self.beta)
        _if_present(_require_non_negative, "cash", self.cash)
        _if_present(_require_non_negative, "total_debt", self.total_debt)
        _require_non_negative("minority_interest", self.minority_interest)
        _require_positive("diluted_shares", self.diluted_shares)
        _require_positive("share_price", self.share_price)


@dataclass(frozen=True, slots=True)
class Company:
    """Todos los datos de una compañía necesarios para calcular su DCF.

    Attributes:
        info: Identificación y trazabilidad (fuente, fecha, tipo de cambio).
        historicals: Ejercicios históricos para la proyección, ascendentes y consecutivos.
        debt_cost_data: Ejercicios históricos para el coste de la deuda y el tipo
            impositivo, ascendentes y consecutivos.
        balance: Último balance y cotización, para el puente VE → valor por acción.
        revenue_estimates: Estimaciones de ventas de analistas para +1 y +2. Vacío si
            no hay cobertura de analistas.
    """

    info: CompanyInfo
    historicals: tuple[HistoricalYear, ...]
    debt_cost_data: tuple[DebtCostYear, ...]
    balance: BalanceSnapshot
    revenue_estimates: tuple[RevenueEstimate, ...] = ()

    MIN_HISTORICAL_YEARS = 2
    """Mínimo para calcular al menos un crecimiento de ventas."""

    # Valida orden y continuidad de los ejercicios y que las estimaciones sean futuras.
    def __post_init__(self) -> None:
        if len(self.historicals) < self.MIN_HISTORICAL_YEARS:
            raise ValueError(
                f"Se necesitan al menos {self.MIN_HISTORICAL_YEARS} ejercicios históricos, "
                f"recibidos {len(self.historicals)}"
            )
        hist_years = [h.fiscal_year for h in self.historicals]
        _require_consecutive_years("historicals", hist_years)
        _require_consecutive_years("debt_cost_data", [d.fiscal_year for d in self.debt_cost_data])

        estimate_years = [e.fiscal_year for e in self.revenue_estimates]
        _require_consecutive_years("revenue_estimates", estimate_years)
        if estimate_years and estimate_years[0] != hist_years[-1] + 1:
            raise ValueError(
                "revenue_estimates debe empezar en el ejercicio siguiente al último histórico "
                f"({hist_years[-1] + 1}), recibido {estimate_years[0]}"
            )

    # Último ejercicio histórico disponible.
    @property
    def last_fiscal_year(self) -> int:
        """Ejercicio fiscal del último histórico."""
        return self.historicals[-1].fiscal_year
