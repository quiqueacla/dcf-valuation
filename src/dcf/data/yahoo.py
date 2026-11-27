"""Descarga de datos de Yahoo Finance, caché en disco y construcción de :class:`Company`.

Tres piezas separadas para poder probar sin red:

1. :func:`fetch_yahoo` descarga los datos crudos (red).
2. :func:`save_raw` / :func:`load_raw` los guardan y leen de ``data/cache`` (disco).
3. :func:`build_company` los valida y transforma en ``Company`` en EUR (pura).

Correspondencia de campos en ``docs/metodologia.md`` §1. Yahoo Finance no es una API
oficial: cada dato obligatorio se valida y, si falta, se lanza un error claro.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dcf.company import (
    WORKING_CURRENCY,
    BalanceSnapshot,
    Company,
    CompanyInfo,
    CompanyType,
    DebtCostYear,
    HistoricalYear,
    RevenueEstimate,
    TerminalMethod,
    ValuationModel,
    model_suitability_warning,
)
from dcf.data.company_types import CompanyTypeRules, classify_company
from dcf.defaults import (
    ANALYST_ESTIMATE_YEARS,
    DEFAULT_TERMINAL_METHOD,
    DEFAULT_VALUATION_MODEL,
    HISTORICAL_YEARS,
)
from dcf.model.cost_of_equity import MarketRate

SOURCE = "yahoo_finance"
DEFAULT_CACHE_DIR = Path("data/cache")

# Filas de Yahoo por estado financiero (nombres tal como los devuelve yfinance).
INCOME = "income_stmt"
CASHFLOW = "cashflow"
BALANCE = "balance_sheet"
ROW_REVENUE = "Total Revenue"
ROW_NET_INCOME = "Net Income"
ROW_INTEREST = "Interest Expense"
ROW_EBIT = "EBIT"
ROW_PRETAX = "Pretax Income"
ROW_TAX = "Tax Provision"
ROW_DILUTED_SHARES = "Diluted Average Shares"
ROW_CFO = "Operating Cash Flow"
ROW_CAPEX = "Capital Expenditure"
ROW_DEBT_ISSUANCE = "Issuance Of Debt"
ROW_DEBT_REPAYMENT = "Repayment Of Debt"
ROW_TOTAL_DEBT = "Total Debt"
ROW_CASH = "Cash Cash Equivalents And Short Term Investments"
ROW_MINORITY = "Minority Interest"
ROW_EQUITY = "Stockholders Equity"
ROW_INVENTORY = "Inventory"
# Alternativas por orden de preferencia: Yahoo no usa siempre el mismo nombre de fila.
ROWS_DA_CASHFLOW = ("Depreciation And Amortization", "Depreciation Amortization Depletion")
ROWS_DA_INCOME = ("Reconciled Depreciation",)
ROWS_RECEIVABLES = ("Accounts Receivable", "Receivables")
ROWS_PAYABLES = ("Accounts Payable", "Payables", "Payables And Accrued Expenses")
"""Proveedores; «Payables» ya incluye «Other Payable» y «Total Tax Payable», y «Payables And
Accrued Expenses» además los gastos devengados."""
ROWS_OTHER_RECEIVABLES = ("Other Receivables", "Taxes Receivable")
"""Otras cuentas a cobrar; ya van dentro de «Receivables» si se usa esa fila."""
ROWS_OTHER_PAYABLES = ("Other Payable", "Total Tax Payable")
"""Otras cuentas a pagar; ya van dentro de «Payables» si se usa esa fila."""
ROWS_OTHER_OPERATING_ASSETS = ("Prepaid Assets", "Other Current Assets")
ROWS_OTHER_OPERATING_LIABILITIES = ("Other Current Liabilities", "Current Provisions")
"""Pasivos corrientes de la operación sin coste financiero (anticipos, provisiones)."""
# Deuda total por componentes si falta «Total Debt»: corto y largo plazo, cada uno con los
# arrendamientos (como «Total Debt») y, si Yahoo no da esa fila, sin ellos.
ROWS_CURRENT_DEBT = ("Current Debt And Capital Lease Obligation", "Current Debt")
ROWS_LONG_TERM_DEBT = ("Long Term Debt And Capital Lease Obligation", "Long Term Debt")
# Capex si falta «Capital Expenditure»: el importe publicado por la empresa y, si no, la
# compra de inmovilizado material (puede no incluir el inmaterial ni la exploración).
ROWS_CAPEX_FALLBACK = ("Capital Expenditure Reported", "Purchase Of PPE")

# Periodos de revenue_estimate: ejercicio en curso (+1) y siguiente (+2).
ESTIMATE_PERIODS = ("0y", "+1y")

# Subunidades de cotización: moneda principal y factor (p. ej. peniques → libras).
MINOR_CURRENCY_UNITS: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 0.01),
    "GBX": ("GBP", 0.01),
    "ZAc": ("ZAR", 0.01),
    "ILA": ("ILS", 0.01),
}

_STATEMENTS = ("income_stmt", "cashflow", "balance_sheet", "revenue_estimate")


@dataclass(frozen=True)
class YahooRawData:
    """Respuesta cruda de Yahoo Finance para un ticker, tal como se descargó.

    Attributes:
        ticker: Símbolo consultado.
        fetched_at: Momento de la descarga, en UTC.
        info: Ficha del ticker (moneda, cotización, beta, nombre...).
        income_stmt: Cuenta de resultados anual (filas = partidas, columnas = cierres).
        cashflow: Estado de flujos de efectivo anual.
        balance_sheet: Balance anual.
        revenue_estimate: Consenso de ventas por periodo ("0y", "+1y"...).
        fx_to_eur: EUR por unidad de cada moneda distinta de EUR usada en los datos.
    """

    ticker: str
    fetched_at: datetime
    info: dict[str, Any]
    income_stmt: pd.DataFrame
    cashflow: pd.DataFrame
    balance_sheet: pd.DataFrame
    revenue_estimate: pd.DataFrame
    fx_to_eur: dict[str, float] = field(default_factory=dict)


# Pasa una moneda de cotización con subunidad (GBp) a su unidad principal y factor.
def normalize_price_currency(currency: str) -> tuple[str, float]:
    """Normaliza la moneda de cotización a su unidad principal.

    Args:
        currency: Código de moneda de Yahoo (p. ej. "EUR", "GBp").

    Returns:
        ``(moneda principal, factor)``; p. ej. ``("GBP", 0.01)`` para "GBp".
    """
    return MINOR_CURRENCY_UNITS.get(currency, (currency, 1.0))


# Monedas distintas de EUR que aparecen en los datos crudos (estados, cotización, estimaciones).
def _currencies_needed(info: dict[str, Any], revenue_estimate: pd.DataFrame) -> set[str]:
    currencies = set()
    for key in ("financialCurrency", "currency"):
        value = info.get(key)
        if isinstance(value, str):
            currencies.add(normalize_price_currency(value)[0])
    if "currency" in revenue_estimate.columns:
        currencies.update(str(c) for c in revenue_estimate["currency"].dropna().unique())
    currencies.discard(WORKING_CURRENCY)
    return currencies


# Descarga de Yahoo estados anuales, ficha, consenso de ventas y tipos de cambio a EUR.
def fetch_yahoo(ticker: str) -> YahooRawData:  # pragma: no cover - requiere red
    """Descarga los datos crudos de un ticker desde Yahoo Finance.

    Args:
        ticker: Símbolo de Yahoo (p. ej. "ITX.MC").

    Returns:
        Datos crudos con la fecha de descarga y los tipos de cambio necesarios.

    Raises:
        ValueError: Si Yahoo no devuelve un tipo de cambio válido.
    """
    import yfinance as yf

    t = yf.Ticker(ticker)
    fetched_at = datetime.now(UTC)
    info = dict(t.info)
    revenue_estimate = t.revenue_estimate
    if not isinstance(revenue_estimate, pd.DataFrame):
        revenue_estimate = pd.DataFrame()
    fx: dict[str, float] = {}
    for currency in sorted(_currencies_needed(info, revenue_estimate)):
        rate = yf.Ticker(f"{currency}{WORKING_CURRENCY}=X").fast_info.last_price
        if rate is None or not math.isfinite(float(rate)) or float(rate) <= 0:
            raise ValueError(f"Yahoo no devolvió un tipo de cambio válido {currency}→EUR")
        fx[currency] = float(rate)
    return YahooRawData(
        ticker=ticker,
        fetched_at=fetched_at,
        info=info,
        income_stmt=t.income_stmt,
        cashflow=t.cashflow,
        balance_sheet=t.balance_sheet,
        revenue_estimate=revenue_estimate,
        fx_to_eur=fx,
    )


# Guarda los datos crudos en data/cache/<ticker>/<fecha UTC>/ (CSV + JSON).
def save_raw(raw: YahooRawData, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Guarda la respuesta cruda en disco para reproducir la valoración.

    Args:
        raw: Datos crudos descargados.
        cache_dir: Carpeta raíz de la caché.

    Returns:
        Carpeta donde se guardaron los ficheros.
    """
    folder = cache_dir / raw.ticker / raw.fetched_at.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    for name in _STATEMENTS:
        getattr(raw, name).to_csv(folder / f"{name}.csv")
    meta = {
        "ticker": raw.ticker,
        "fetched_at": raw.fetched_at.isoformat(),
        "fx_to_eur": raw.fx_to_eur,
        "info": raw.info,
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return folder


# Lee de la caché unos datos crudos guardados con save_raw.
def load_raw(folder: Path) -> YahooRawData:
    """Carga una respuesta cruda guardada con :func:`save_raw`.

    Args:
        folder: Carpeta con ``meta.json`` y los CSV de cada estado.

    Returns:
        Datos crudos equivalentes a los descargados.

    Raises:
        FileNotFoundError: Si falta algún fichero.
    """
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    frames: dict[str, pd.DataFrame] = {}
    for name in _STATEMENTS:
        df = pd.read_csv(folder / f"{name}.csv", index_col=0)
        if name != "revenue_estimate":
            df.columns = pd.to_datetime(df.columns)
        frames[name] = df
    return YahooRawData(
        ticker=meta["ticker"],
        fetched_at=datetime.fromisoformat(meta["fetched_at"]),
        info=meta["info"],
        income_stmt=frames["income_stmt"],
        cashflow=frames["cashflow"],
        balance_sheet=frames["balance_sheet"],
        revenue_estimate=frames["revenue_estimate"],
        fx_to_eur={k: float(v) for k, v in meta["fx_to_eur"].items()},
    )


# EUR por unidad de la moneda; error claro si falta el tipo de cambio.
def _fx(raw: YahooRawData, currency: str) -> float:
    if currency == WORKING_CURRENCY:
        return 1.0
    if currency not in raw.fx_to_eur:
        raise ValueError(f"Falta el tipo de cambio {currency}→EUR en los datos descargados")
    return raw.fx_to_eur[currency]


# Lee un campo obligatorio de la ficha (info); error si falta o no es del tipo esperado.
def _info_value(info: dict[str, Any], key: str, kind: type | tuple[type, ...]) -> Any:
    value = info.get(key)
    if value is None or not isinstance(value, kind) or isinstance(value, bool):
        raise ValueError(f"Yahoo: falta o no es válido info['{key}'] (recibido {value!r})")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Yahoo: info['{key}'] no es finito")
    return value


# Celda numérica de un DataFrame como float, o None si falta la fila/columna o es NaN.
def _cell(df: pd.DataFrame, row: object, column: object) -> float | None:
    if row not in df.index or column not in df.columns:
        return None
    value: Any = df.at[row, column]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


# Valor obligatorio de un estado; error claro si falta la fila o el dato del año.
def _required(df: pd.DataFrame, statement: str, row: str, column: pd.Timestamp) -> float:
    if row not in df.index:
        raise ValueError(f"Yahoo: falta la fila '{row}' en {statement}")
    value = _cell(df, row, column)
    if value is None:
        raise ValueError(f"Yahoo: '{row}' sin dato en {statement} para el cierre {column.date()}")
    return value


# Valor que Yahoo omite cuando es 0: devuelve 0 y registra un aviso si falta.
def _zero_if_missing(
    df: pd.DataFrame, statement: str, row: str, column: pd.Timestamp, warnings: list[str]
) -> float:
    value = _cell(df, row, column)
    if value is None:
        warnings.append(f"'{row}' ausente en {statement} ({column.date()}): se usa 0")
        return 0.0
    return value


# Cierres comunes a los tres estados con datos, ordenados; se toman los últimos n.
def _select_columns(raw: YahooRawData, years: int, warnings: list[str]) -> list[pd.Timestamp]:
    common: set[pd.Timestamp] | None = None
    for statement in (INCOME, CASHFLOW, BALANCE):
        df: pd.DataFrame = getattr(raw, statement)
        if df.empty:
            raise ValueError(f"Yahoo: {statement} vacío para {raw.ticker}")
        with_data = {pd.Timestamp(c) for c in df.columns if df[c].notna().any()}
        common = with_data if common is None else common & with_data
    columns = sorted(common or set())
    if len(columns) < years:
        warnings.append(f"Solo hay {len(columns)} ejercicios comunes, se esperaban {years}")
    return columns[-years:]


# Estimaciones de ventas +1 y +2 en EUR; se detiene en el primer periodo sin dato.
def _estimates(
    raw: YahooRawData, last_year: int, default_currency: str, warnings: list[str]
) -> tuple[RevenueEstimate, ...]:
    df = raw.revenue_estimate
    result: list[RevenueEstimate] = []
    for offset, period in enumerate(ESTIMATE_PERIODS[:ANALYST_ESTIMATE_YEARS], start=1):
        if df.empty or period not in df.index or "avg" not in df.columns:
            warnings.append(f"Sin estimación de ventas de analistas para '{period}'")
            break
        avg = _cell(df, period, "avg")
        has_count = "numberOfAnalysts" in df.columns
        analysts = _cell(df, period, "numberOfAnalysts")
        if avg is None or avg <= 0 or (has_count and (analysts is None or analysts <= 0)):
            warnings.append(f"Estimación de ventas de analistas no válida para '{period}'")
            break
        currency = default_currency
        if "currency" in df.columns:
            raw_currency: Any = df.at[period, "currency"]
            if isinstance(raw_currency, str) and raw_currency:
                currency = raw_currency
        rate = _fx(raw, currency)
        low, high = _cell(df, period, "low"), _cell(df, period, "high")
        result.append(
            RevenueEstimate(
                fiscal_year=last_year + offset,
                revenue=avg * rate,
                num_analysts=int(analysts) if analysts is not None else None,
                revenue_low=low * rate if low is not None and low > 0 else None,
                revenue_high=high * rate if high is not None and high > 0 else None,
            )
        )
    return tuple(result)


# Intereses del ejercicio en EUR; si Yahoo no los da, Kd por defecto × deuda total con aviso.
def _interest(
    income: pd.DataFrame,
    column: pd.Timestamp,
    total_debt_eur: float,
    fx: float,
    default_cost_of_debt: MarketRate | None,
    warnings: list[str],
) -> float:
    value = _cell(income, ROW_INTEREST, column)
    if value is not None:
        return abs(value) * fx
    if default_cost_of_debt is None:
        raise ValueError(
            f"Yahoo: '{ROW_INTEREST}' sin dato en {INCOME} para el cierre {column.date()}. "
            "Para estimarlo, añade [default_cost_of_debt] a config/data/market_inputs.toml"
        )
    estimated = default_cost_of_debt.value * total_debt_eur
    warnings.append(
        f"'{ROW_INTEREST}' ausente ({column.date()}): estimado como "
        f"{default_cost_of_debt.value:.2%} × deuda total = {estimated:,.0f} EUR "
        f"(fuente: {default_cost_of_debt.source})"
    )
    return estimated


# Texto opcional de info (sector, industria...): None si falta o está vacío.
def _info_text(info: dict[str, Any], key: str) -> str | None:
    value = info.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


# Clave en minúsculas (o None).
def _lower(value: str | None) -> str | None:
    return None if value is None else value.lower()


# Sector, industria y tipo de empresa; aviso si Yahoo no publica sector ni industria.
def _classification(
    info: dict[str, Any], rules: CompanyTypeRules | None, warnings: list[str]
) -> tuple[str | None, str | None, CompanyType | None]:
    sector, industry = _info_text(info, "sector"), _info_text(info, "industry")
    if rules is None:
        return sector, industry, None
    company_type = classify_company(
        _info_text(info, "sectorKey"), _info_text(info, "industryKey"), rules
    )
    if company_type is None:
        warnings.append("Yahoo no publica sector ni industria: tipo de empresa sin clasificar")
    return sector, industry, company_type


# Modelo de valoración: el forzado, el de la tabla de tipos o, en su defecto, el fcff.
def _choose_model(
    company_type: CompanyType | None,
    rules: CompanyTypeRules | None,
    model: ValuationModel | None,
) -> ValuationModel:
    if model is not None:
        return model
    if rules is not None:
        return rules.model_for(company_type)
    return ValuationModel(DEFAULT_VALUATION_MODEL)


# Método de VT: el forzado, el de la tabla de tipos o, en su defecto, gordon_value_driver.
def _choose_terminal(
    company_type: CompanyType | None,
    rules: CompanyTypeRules | None,
    terminal: TerminalMethod | None,
) -> TerminalMethod:
    if terminal is not None:
        return terminal
    if rules is not None:
        return rules.terminal_for(company_type)
    return TerminalMethod(DEFAULT_TERMINAL_METHOD)


# Primera fila disponible de una lista de alternativas (Yahoo cambia nombres entre empresas).
def _first_cell(df: pd.DataFrame, rows: Sequence[str], column: pd.Timestamp) -> float | None:
    for row in rows:
        value = _cell(df, row, column)
        if value is not None:
            return value
    return None


# Caja, D&A y circulante operativo; D&A, clientes y proveedores obligatorios si se piden.
def _operating_items(
    raw: YahooRawData, column: pd.Timestamp, fx: float, required: bool, warnings: list[str]
) -> dict[str, float | None]:
    items = {
        "depreciation_amortization": (raw.cashflow, CASHFLOW, ROWS_DA_CASHFLOW, raw.income_stmt),
        "receivables": (raw.balance_sheet, BALANCE, ROWS_RECEIVABLES, None),
        "payables": (raw.balance_sheet, BALANCE, ROWS_PAYABLES, None),
    }
    result: dict[str, float | None] = {"cash": _optional(raw.balance_sheet, ROW_CASH, column, fx)}
    for name, (df, statement, rows, fallback) in items.items():
        value = _first_cell(df, rows, column)
        if value is None and fallback is not None:
            value = _first_cell(fallback, ROWS_DA_INCOME, column)
        if value is None and required:
            raise ValueError(
                f"Yahoo: falta {' / '.join(rows)} en {statement} para el cierre {column.date()} "
                "(necesario para los modelos fcff y fcfe; prueba --model fcff_cfo)"
            )
        result[name] = None if value is None else abs(value) * fx
    payables_detail = _cell(raw.balance_sheet, ROWS_PAYABLES[0], column) is not None
    if not payables_detail and result["payables"] is not None and required:
        row = next(r for r in ROWS_PAYABLES if _cell(raw.balance_sheet, r, column) is not None)
        warnings.append(
            f"'{ROWS_PAYABLES[0]}' ausente en {BALANCE} ({column.date()}): se usa '{row}', "
            f"que ya incluye {' y '.join(ROWS_OTHER_PAYABLES)}"
        )
    inventory = _cell(raw.balance_sheet, ROW_INVENTORY, column)
    if inventory is None and required:
        warnings.append(f"'{ROW_INVENTORY}' ausente en {BALANCE} ({column.date()}): se usa 0")
        inventory = 0.0
    result["inventory"] = None if inventory is None else abs(inventory) * fx

    # Resto del circulante operativo: filas opcionales, 0 con aviso si faltan.
    bs = raw.balance_sheet
    with_detail = _cell(bs, ROWS_RECEIVABLES[0], column) is not None
    asset_rows = (ROWS_OTHER_RECEIVABLES if with_detail else ()) + ROWS_OTHER_OPERATING_ASSETS
    missing: list[str] = []

    def total(rows: Sequence[str]) -> float:
        amount = 0.0
        for row in rows:
            value = _cell(bs, row, column)
            if value is None:
                missing.append(row)
            else:
                amount += abs(value)
        return amount * fx

    result["other_operating_assets"] = total(asset_rows)
    liability_rows = (ROWS_OTHER_PAYABLES if payables_detail else ()) + (
        ROWS_OTHER_OPERATING_LIABILITIES
    )
    result["other_operating_liabilities"] = total(liability_rows)
    if missing and required:
        warnings.append(
            f"Circulante operativo ({column.date()}): Yahoo no publica {', '.join(missing)}; "
            "se usan 0"
        )
    return result


# Valida los datos crudos y construye Company con todos los importes en EUR.
def build_company(
    raw: YahooRawData,
    default_cost_of_debt: MarketRate | None = None,
    historical_years: int = HISTORICAL_YEARS,
    type_rules: CompanyTypeRules | None = None,
    model: ValuationModel | None = None,
    terminal: TerminalMethod | None = None,
) -> Company:
    """Construye la compañía a partir de la respuesta cruda de Yahoo.

    Los datos obligatorios dependen del modelo: fcff, fcff_cfo y fcfe exigen deuda,
    caja, EBIT, BAI, impuestos, intereses y Capex; además fcff y fcfe exigen D&A,
    clientes y proveedores (existencias 0 con aviso) y fcff_cfo el CFO. fcfe_fin exige
    los fondos propios (Stockholders Equity). El resto se carga si está (``None`` si no).

    Args:
        raw: Datos crudos (descargados o leídos de la caché).
        default_cost_of_debt: Kd antes de impuestos (de ``market_inputs.toml``) para
            estimar los intereses de los ejercicios en que Yahoo no los publica:
            intereses = Kd por defecto × deuda total del ejercicio. ``None`` = error.
            Solo se usa en FCFF.
        historical_years: Ejercicios históricos a tomar (los más recientes).
        type_rules: Tabla de tipos de empresa (``config/company_types.toml``) para
            clasificar por ``sectorKey`` e ``industryKey`` y elegir el modelo. ``None``
            = no se clasifica (``company_type`` queda en ``None``).
        model: Modelo forzado; ``None`` = el de la tabla para el tipo de empresa (o
            fcff sin tabla).
        terminal: Método de VT forzado; ``None`` = el de la tabla (o
            gordon_value_driver sin tabla).

    Returns:
        Compañía con importes en EUR y avisos de carga en ``info.data_warnings``.

    Raises:
        ValueError: Si falta algún dato obligatorio para el modelo, un tipo de cambio,
            o los intereses de un ejercicio sin ``default_cost_of_debt`` (FCFF). Si el
            modelo no es adecuado para el tipo de empresa, el mensaje lo indica.
    """
    warnings: list[str] = []
    classification = _classification(raw.info, type_rules, warnings)
    chosen = _choose_model(classification[2], type_rules, model)
    method = _choose_terminal(classification[2], type_rules, terminal)
    try:
        return _build_company(
            raw, default_cost_of_debt, historical_years, classification, chosen, method, warnings
        )
    except ValueError as exc:
        company_type = classification[2]
        note = model_suitability_warning(company_type, chosen) if company_type else None
        if note is None:
            raise
        raise ValueError(f"{exc}. {note}") from exc


# Importe opcional de un estado en EUR (valor absoluto si se pide); None si falta.
def _optional(
    df: pd.DataFrame, row: str, column: pd.Timestamp, fx: float, absolute: bool = False
) -> float | None:
    value = _cell(df, row, column)
    if value is None:
        return None
    return (abs(value) if absolute else value) * fx


# Deuda total en EUR: «Total Debt»; si falta, corto + largo plazo con aviso, y 0 con aviso
# si Yahoo no publica ninguna fila de deuda ese año (empresa sin deuda).
def _total_debt(bs: pd.DataFrame, column: pd.Timestamp, fx: float, warnings: list[str]) -> float:
    value = _cell(bs, ROW_TOTAL_DEBT, column)
    if value is not None:
        return value * fx
    current = _first_cell(bs, ROWS_CURRENT_DEBT, column)
    long_term = _first_cell(bs, ROWS_LONG_TERM_DEBT, column)
    if current is None and long_term is None:
        warnings.append(
            f"'{ROW_TOTAL_DEBT}' ausente en {BALANCE} ({column.date()}) y sin filas de deuda a "
            "corto ni a largo plazo: se usa 0"
        )
        return 0.0
    short, long = abs(current or 0.0) * fx, abs(long_term or 0.0) * fx
    warnings.append(
        f"'{ROW_TOTAL_DEBT}' ausente en {BALANCE} ({column.date()}): se usa deuda a corto "
        f"({short:,.0f} EUR) + largo plazo ({long:,.0f} EUR)"
    )
    return short + long


# Capex (valor absoluto, moneda original): «Capital Expenditure»; si falta, la primera fila
# alternativa con aviso; sin ninguna, el error de dato obligatorio.
def _capex(cf: pd.DataFrame, column: pd.Timestamp, warnings: list[str]) -> float:
    if _cell(cf, ROW_CAPEX, column) is None:
        for row in ROWS_CAPEX_FALLBACK:
            value = _cell(cf, row, column)
            if value is not None:
                warnings.append(
                    f"'{ROW_CAPEX}' ausente en {CASHFLOW} ({column.date()}): se usa '{row}'"
                )
                return abs(value)
    return abs(_required(cf, CASHFLOW, ROW_CAPEX, column))


# Minoritarios en EUR: 0 con aviso si faltan; si son negativos (filiales con patrimonio
# negativo), se aceptan con aviso porque suman al valor de los fondos propios.
def _minority(bs: pd.DataFrame, column: pd.Timestamp, fx: float, warnings: list[str]) -> float:
    value = _zero_if_missing(bs, BALANCE, ROW_MINORITY, column, warnings) * fx
    if value < 0:
        warnings.append(
            f"'{ROW_MINORITY}' negativo en {BALANCE} ({column.date()}): {value:,.0f} EUR "
            "(participaciones no dominantes con patrimonio negativo); suma al valor de los "
            "fondos propios"
        )
    return value


# Cuerpo de build_company: estados, balance, estimaciones e información de la compañía.
def _build_company(
    raw: YahooRawData,
    default_cost_of_debt: MarketRate | None,
    historical_years: int,
    classification: tuple[str | None, str | None, CompanyType | None],
    model: ValuationModel,
    terminal: TerminalMethod,
    warnings: list[str],
) -> Company:
    financial_currency = str(_info_value(raw.info, "financialCurrency", str))
    price_currency, price_unit = normalize_price_currency(
        str(_info_value(raw.info, "currency", str))
    )
    fx = _fx(raw, financial_currency)
    price_fx = _fx(raw, price_currency)

    columns = _select_columns(raw, historical_years, warnings)
    inc, cf, bs = raw.income_stmt, raw.cashflow, raw.balance_sheet
    fcff = model is not ValuationModel.FCFE_FIN
    operating = model in (ValuationModel.FCFF, ValuationModel.FCFE)

    historicals: list[HistoricalYear] = []
    debt_cost: list[DebtCostYear] = []
    for col in columns:
        revenue = _required(inc, INCOME, ROW_REVENUE, col) * fx
        net_income = _required(inc, INCOME, ROW_NET_INCOME, col) * fx
        if fcff:
            total_debt = _total_debt(bs, col, fx, warnings)
            interest = _interest(inc, col, total_debt, fx, default_cost_of_debt, warnings)
            year = HistoricalYear(
                fiscal_year=col.year,
                revenue=revenue,
                net_income=net_income,
                operating_cash_flow=(
                    _required(cf, CASHFLOW, ROW_CFO, col) * fx
                    if model is ValuationModel.FCFF_CFO
                    else _optional(cf, ROW_CFO, col, fx)
                ),
                capital_expenditure=_capex(cf, col, warnings) * fx,
                interest_expense=interest,
                debt_issuance=abs(_zero_if_missing(cf, CASHFLOW, ROW_DEBT_ISSUANCE, col, warnings))
                * fx,
                debt_repayment=abs(
                    _zero_if_missing(cf, CASHFLOW, ROW_DEBT_REPAYMENT, col, warnings)
                )
                * fx,
                stockholders_equity=_optional(bs, ROW_EQUITY, col, fx),
                **_operating_items(raw, col, fx, operating, warnings),
            )
            debt_cost.append(
                DebtCostYear(
                    fiscal_year=col.year,
                    total_debt=total_debt,
                    interest_expense=interest,
                    ebit=_required(inc, INCOME, ROW_EBIT, col) * fx,
                    pretax_income=_required(inc, INCOME, ROW_PRETAX, col) * fx,
                    tax_provision=_required(inc, INCOME, ROW_TAX, col) * fx,
                )
            )
        else:
            year = HistoricalYear(
                fiscal_year=col.year,
                revenue=revenue,
                net_income=net_income,
                operating_cash_flow=_optional(cf, ROW_CFO, col, fx),
                capital_expenditure=_optional(cf, ROW_CAPEX, col, fx, absolute=True),
                interest_expense=_optional(inc, ROW_INTEREST, col, fx, absolute=True),
                debt_issuance=_optional(cf, ROW_DEBT_ISSUANCE, col, fx, absolute=True),
                debt_repayment=_optional(cf, ROW_DEBT_REPAYMENT, col, fx, absolute=True),
                stockholders_equity=_required(bs, BALANCE, ROW_EQUITY, col) * fx,
                **_operating_items(raw, col, fx, False, warnings),
            )
        historicals.append(year)

    last = columns[-1]
    price = float(_info_value(raw.info, "currentPrice", (int, float))) * price_unit * price_fx
    balance = BalanceSnapshot(
        balance_date=datetime(last.year, last.month, last.day, tzinfo=UTC),
        cash=(
            _required(bs, BALANCE, ROW_CASH, last) * fx
            if fcff
            else _optional(bs, ROW_CASH, last, fx)
        ),
        total_debt=(debt_cost[-1].total_debt if fcff else _optional(bs, ROW_TOTAL_DEBT, last, fx)),
        minority_interest=_minority(bs, last, fx, warnings),
        diluted_shares=_required(inc, INCOME, ROW_DILUTED_SHARES, last),
        share_price=price,
        # Beta opcional: si falta, el modo de [beta] decide (error o beta del fichero).
        beta=(
            float(_info_value(raw.info, "beta", (int, float)))
            if raw.info.get("beta") is not None
            else None
        ),
    )
    estimates = _estimates(raw, last.year, financial_currency, warnings)

    uses_fx = financial_currency != WORKING_CURRENCY or price_currency != WORKING_CURRENCY
    uses_fx = uses_fx or any(c != WORKING_CURRENCY for c in raw.fx_to_eur)
    name = raw.info.get("longName") or raw.info.get("shortName") or raw.ticker
    sector, industry, company_type = classification
    info = CompanyInfo(
        ticker=raw.ticker,
        name=str(name),
        source=SOURCE,
        data_date=raw.fetched_at,
        original_currency=financial_currency,
        fx_rate_to_eur=fx,
        fx_date=raw.fetched_at if uses_fx else None,
        price_currency=price_currency,
        price_fx_rate_to_eur=price_fx,
        data_warnings=tuple(warnings),
        sector=sector,
        industry=industry,
        company_type=company_type,
        country=_info_text(raw.info, "country"),
        sector_key=_lower(_info_text(raw.info, "sectorKey")),
        industry_key=_lower(_info_text(raw.info, "industryKey")),
        valuation_model=model,
        terminal_method=terminal,
    )
    return Company(
        info=info,
        historicals=tuple(historicals),
        debt_cost_data=tuple(debt_cost),
        balance=balance,
        revenue_estimates=estimates,
    )


# Descarga, guarda en caché y construye la compañía.
def fetch_company(
    ticker: str,
    default_cost_of_debt: MarketRate | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    type_rules: CompanyTypeRules | None = None,
    model: ValuationModel | None = None,
    terminal: TerminalMethod | None = None,
) -> Company:  # pragma: no cover - requiere red
    """Descarga un ticker de Yahoo, guarda la respuesta en caché y construye ``Company``.

    Args:
        ticker: Símbolo de Yahoo.
        default_cost_of_debt: Kd para estimar intereses ausentes (ver ``build_company``).
        cache_dir: Carpeta raíz de la caché.
        type_rules: Tabla de tipos de empresa (ver ``build_company``).
        model: Modelo forzado; ``None`` = el de la tabla (ver ``build_company``).
        terminal: Método de VT forzado; ``None`` = el de la tabla.

    Returns:
        Compañía con importes en EUR.
    """
    raw = fetch_yahoo(ticker)
    save_raw(raw, cache_dir)
    return build_company(
        raw, default_cost_of_debt, type_rules=type_rules, model=model, terminal=terminal
    )
