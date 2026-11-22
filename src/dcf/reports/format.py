"""Formato y secciones comunes de los informes Markdown (funciones puras, devuelven texto).

Redondeo solo de presentación (los cálculos no se redondean): importes con 1 decimal en
la escala indicada (millones de EUR por defecto), valores por acción con 2 decimales,
tasas en % con 2 decimales. Redondeo comercial (mitad hacia arriba: 8,125 → 8,13) sobre
la representación decimal más corta del float. Formato numérico español (1.234,5).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from dcf.company import Company, model_suitability_warning
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import CostOfEquityResult
from dcf.model.discount_rate import DiscountRateChoice
from dcf.model.terminal_methods import TerminalValueResult
from dcf.valuation.scenarios import ScenarioResult

MILLIONS = 1e6
"""Escala por defecto de los importes del informe: millones de EUR."""

DISCLAIMER = "Herramienta educativa y analítica. Este informe no es una recomendación de inversión."

CASE_LABEL = {"low": "Estimación baja", "avg": "Estimación media", "high": "Estimación alta"}
"""Etiqueta de la estimación de ventas de analistas usada en cada escenario."""

SOURCE_LABEL = {"analyst_estimate": "Analistas", "average_growth": "Crec. medio"}
"""Etiqueta del origen de las ventas proyectadas."""


# Número redondeado mitad hacia arriba, con miles "." y decimal "," (formato español).
def num(value: float | None, decimals: int) -> str:
    """Formatea un número en español con redondeo mitad hacia arriba.

    Args:
        value: Número; ``None`` o no finito se muestra como «—».
        decimals: Decimales a mostrar.

    Returns:
        Texto, p. ej. ``1.234,5``.
    """
    if value is None or not math.isfinite(value):
        return "—"
    rounded = Decimal(repr(value)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    text = f"{rounded:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# Importe en la escala del informe, 1 decimal ("—" si falta).
def amount(value: float | None, scale: float) -> str:
    """Formatea un importe en EUR en la escala del informe.

    Args:
        value: Importe en EUR; ``None`` si no se publica.
        scale: Divisor (1e6 = millones).

    Returns:
        Texto con 1 decimal o «—».
    """
    return "—" if value is None else num(value / scale, 1)


# Tasa en decimal como porcentaje con 2 decimales (0.08125 → "8,13 %").
def pct(value: float | None) -> str:
    """Formatea una tasa en decimal como porcentaje con 2 decimales.

    Args:
        value: Tasa en decimal (0.08 = 8 %); ``None`` = «—».

    Returns:
        Texto, p. ej. ``8,13 %``.
    """
    return "—" if value is None else f"{num(value * 100, 2)} %"


# Valor por acción en EUR con 2 decimales.
def eur(value: float | None) -> str:
    """Formatea un valor por acción en EUR con 2 decimales.

    Args:
        value: Importe en EUR; ``None`` = «—».

    Returns:
        Texto, p. ej. ``30,37 €``.
    """
    return "—" if value is None else f"{num(value, 2)} €"


# Tabla Markdown a partir de cabecera y filas de texto.
def table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    text_columns: frozenset[int] = frozenset({0}),
) -> str:
    """Construye una tabla Markdown (columnas de texto a la izquierda, números a la derecha).

    Args:
        headers: Cabecera.
        rows: Filas de texto.
        text_columns: Índices de las columnas alineadas a la izquierda (por defecto la 1.ª).

    Returns:
        Tabla Markdown.
    """
    align = ["---" if i in text_columns else "---:" for i in range(len(headers))]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(align) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# Lista de avisos en Markdown, o cadena vacía si no hay.
def warnings_block(title: str, items: Sequence[str]) -> str:
    """Construye una lista de avisos con título.

    Args:
        title: Título de la lista.
        items: Avisos; si no hay, devuelve cadena vacía.

    Returns:
        Bloque Markdown.
    """
    if not items:
        return ""
    return f"\n**{title}:**\n\n" + "\n".join(f"- {w}" for w in items) + "\n"


# Moneda con su tipo de cambio a EUR, p. ej. "USD (1 USD = 0,9000 EUR)".
def _fx_label(currency: str, rate: float) -> str:
    return f"{currency} (1 {currency} = {num(rate, 4)} EUR)"


# Cabecera común: título, aviso legal, aviso de modelo y trazabilidad.
def report_header(
    company: Company,
    model_label: str,
    valuation_date: datetime,
    data_date: datetime,
    source: str,
    code_version: str,
    assumptions: Assumptions,
    unit: str,
) -> str:
    """Construye la cabecera del informe.

    Args:
        company: Compañía valorada.
        model_label: Nombre del modelo para el título (p. ej. "FCFF").
        valuation_date: Momento de la valoración, en UTC.
        data_date: Fecha de los datos, en UTC.
        source: Fuente de los datos.
        code_version: Versión del paquete ``dcf``.
        assumptions: Supuestos (horizonte y g).
        unit: Etiqueta de la unidad de los importes.

    Returns:
        Cabecera Markdown.
    """
    suitability = model_suitability_warning(company.info.company_type, company.info.valuation_model)
    a = assumptions
    return (
        f"# Valoración DCF ({model_label}): {company.info.name} ({company.info.ticker})\n\n"
        f"> {DISCLAIMER}\n\n"
        + ("" if suitability is None else f"> **Aviso de modelo:** {suitability}.\n\n")
        + f"- Modelo: {model_label}\n"
        f"- Fecha de valoración (UTC): {valuation_date:%Y-%m-%d %H:%M}\n"
        f"- Datos: {source}, {data_date:%Y-%m-%d %H:%M} UTC\n"
        f"- Versión del código: dcf {code_version}\n"
        f"- Supuestos: horizonte {a.projection_years} años, g terminal {pct(a.terminal_growth)},"
        f" descuento a final de año\n"
        f"- Unidades: importes en {unit} (1 decimal); por acción en € (2 decimales)\n"
    )


# Sección 1: identificación, mercado y balance.
def company_section(company: Company, scale: float, unit: str) -> str:
    """Construye la sección 1 del informe (información de la compañía).

    Args:
        company: Compañía valorada.
        scale: Divisor de los importes.
        unit: Etiqueta de la unidad.

    Returns:
        Sección Markdown.
    """
    info, b = company.info, company.balance
    rows = [
        ["Ticker", info.ticker],
        ["Nombre", info.name],
        ["Sector", info.sector or "no publicado"],
        ["Industria", info.industry or "no publicada"],
        [
            "Tipo de empresa",
            "sin clasificar" if info.company_type is None else info.company_type.value,
        ],
        ["Modelo de valoración", info.valuation_model.value],
        ["Fuente", info.source],
        ["Fecha de los datos (UTC)", info.data_date.strftime("%Y-%m-%d %H:%M")],
        [
            "Moneda de los estados financieros",
            _fx_label(info.original_currency, info.fx_rate_to_eur),
        ],
        ["Moneda de cotización", _fx_label(info.price_currency, info.price_fx_rate_to_eur)],
        ["Fecha del último balance", b.balance_date.strftime("%Y-%m-%d")],
        ["Cotización", eur(b.share_price)],
        ["Acciones diluidas (millones)", num(b.diluted_shares / 1e6, 2)],
        [f"Capitalización ({unit})", amount(b.share_price * b.diluted_shares, scale)],
        [f"Deuda total, incl. arrendamientos ({unit})", amount(b.total_debt, scale)],
        [f"Caja y equivalentes ({unit})", amount(b.cash, scale)],
        [f"Minoritarios ({unit})", amount(b.minority_interest, scale)],
        [f"Beta publicada ({info.source})", "no publicada" if b.beta is None else num(b.beta, 3)],
    ]
    return (
        "## 1. Información de la compañía\n\n"
        + table(["Dato", "Valor"], rows)
        + "\n"
        + warnings_block("Avisos de la carga de datos", info.data_warnings)
    )


# Filas de Ke por CAPM: rf, PRM, beta (con su origen) y Ke.
def cost_of_equity_rows(equity: CostOfEquityResult) -> list[list[str]]:
    """Construye las filas de la tabla del coste de los fondos propios.

    Args:
        equity: Ke con rf, PRM y beta utilizados.

    Returns:
        Filas [componente, valor, fuente].
    """
    rf, prm = equity.market_inputs.risk_free_rate, equity.market_inputs.market_risk_premium
    beta = equity.beta_choice
    beta_origin = f"{beta.source} ({beta.date:%Y-%m-%d}); modo {beta.mode.value}"
    if beta.reason is not None:
        beta_origin += f"; se usa la del fichero porque {beta.reason}"
    return [
        ["Rentabilidad libre de riesgo (rf)", pct(rf.value), f"{rf.source} ({rf.date:%Y-%m-%d})"],
        ["Prima de riesgo de mercado (PRM)", pct(prm.value), f"{prm.source} ({prm.date:%Y-%m-%d})"],
        ["Beta (β)", num(beta.value, 3), beta_origin],
        ["**Coste del capital Ke = rf + β · PRM**", f"**{pct(equity.cost_of_equity)}**", "CAPM"],
    ]


# Nota de la tasa forzada: valor usado, fuente y tasa calculada (cadena vacía si no está forzada).
def discount_rate_note(choice: DiscountRateChoice) -> str:
    """Construye la nota que explica que la tasa de descuento está forzada.

    Args:
        choice: Tasa elegida.

    Returns:
        Bloque Markdown, o cadena vacía si se usa la tasa calculada.
    """
    if choice.override is None:
        return ""
    calc = (
        f"no se pudo calcular ({choice.calculation_error})"
        if choice.calculated is None
        else f"{pct(choice.calculated)}, solo informativo"
    )
    return (
        f"\n> **Tasa de descuento forzada: {choice.name} = {pct(choice.value)}** "
        f"({choice.override.source}, {choice.override.date:%Y-%m-%d}). "
        f"{choice.name} calculado: {calc}.\n"
    )


# Tabla de escenarios (o cadena vacía si no hay) con sus avisos.
def scenarios_block(
    scenarios: Sequence[ScenarioResult],
    rate_label: str,
    value_label: str,
    price: float,
    scale: float,
    unit: str,
) -> str:
    """Construye la subsección de escenarios.

    Args:
        scenarios: Escenarios valorados; vacío = sin subsección.
        rate_label: Nombre de la tasa de descuento ("WACC" o "Ke").
        value_label: Nombre del valor descontado ("VE" o "Fondos propios").
        price: Cotización en EUR, para comparar.
        scale: Divisor de los importes.
        unit: Etiqueta de la unidad.

    Returns:
        Bloque Markdown.
    """
    if not scenarios:
        return ""
    rows = [
        [
            f"**{s.name.capitalize()}**",
            CASE_LABEL[str(s.estimate_case)],
            pct(s.discount_rate),
            pct(s.terminal_growth),
            amount(s.total_value, scale),
            pct(s.terminal_value_weight),
            f"**{eur(s.value_per_share)}**",
            vs_price(s.value_per_share, price),
        ]
        for s in scenarios
    ]
    errors = [f"{s.name}: {s.error}" for s in scenarios if s.error]
    notes = sorted({w for s in scenarios for w in s.warnings})
    headers = [
        "Escenario",
        "Ventas +1/+2",
        rate_label,
        "g terminal",
        f"{value_label} ({unit})",
        "Peso VT",
        "Valor por acción",
        "vs. cotización",
    ]
    return (
        "\n### 4.2 Escenarios\n\n"
        + table(headers, rows)
        + "\n"
        + warnings_block("Escenarios no válidos", errors)
        + warnings_block("Avisos de los escenarios", notes)
    )


# Tabla de sensibilidad del valor por acción (tasa de descuento × g).
def sensitivity_block(sensitivity: pd.DataFrame, rate_label: str) -> str:
    """Construye la subsección de sensibilidad.

    Args:
        sensitivity: Valor por acción por tasa (filas) × g (columnas).
        rate_label: Nombre de la tasa de descuento ("WACC" o "Ke").

    Returns:
        Bloque Markdown.
    """
    rows = [
        [pct(float(r)), *[eur(None if math.isnan(v) else float(v)) for v in sensitivity.loc[r]]]
        for r in sensitivity.index
    ]
    return (
        f"\n### 4.3 Sensibilidad del valor por acción ({rate_label} × g terminal)\n\n"
        + table([f"{rate_label} \\ g", *[pct(float(g)) for g in sensitivity.columns]], rows)
        + f"\n\nCeldas con «—»: g ≥ {rate_label} o g ≥ rf (no válidas).\n"
    )


# Diferencia porcentual entre un valor por acción y la cotización.
def vs_price(value: float | None, price: float) -> str:
    """Formatea la diferencia del valor intrínseco frente a la cotización.

    Args:
        value: Valor por acción en EUR; ``None`` = «—».
        price: Cotización en EUR.

    Returns:
        Texto en porcentaje.
    """
    return "—" if value is None else pct(value / price - 1)


TERMINAL_LABEL = {
    "gordon": "Gordon clásico",
    "gordon_value_driver": "Gordon con value driver",
    "vt_mult": "Múltiplo de salida",
}
"""Nombre de cada método de valor terminal en el informe."""


# Subsección del valor terminal: método, fórmula, entradas y g / múltiplo implícitos.
def terminal_block(
    terminal: TerminalValueResult | None,
    rate_name: str,
    terminal_growth: float,
    scale: float,
    unit: str,
) -> str:
    """Construye la subsección del valor terminal.

    Args:
        terminal: Valor terminal calculado; ``None`` = sin detalle.
        rate_name: "WACC" o "Ke".
        terminal_growth: g supuesto, en decimal.
        scale: Divisor de los importes.
        unit: Etiqueta de la unidad.

    Returns:
        Bloque Markdown (vacío si no hay detalle).
    """
    if terminal is None:
        return ""
    b = terminal.basis
    flow = "FCFF" if rate_name == "WACC" else "FCFE"
    multiple_name = "EV/EBITDA" if b.metric_name == "EBITDA" else "P/E"
    method = terminal.method.value
    rows: list[list[str]] = [["Método", TERMINAL_LABEL[method]]]
    if method == "gordon":
        rows += [
            ["Fórmula", f"VT = {flow}_N · (1 + g) / ({rate_name} − g)"],
            [f"{flow}_N ({unit})", amount(b.last_flow, scale)],
        ]
    elif method == "gordon_value_driver":
        ronic = b.ronic
        rows += [
            [
                "Fórmula",
                f"VT = {b.profit_name}_N · (1 + g) · (1 − g / {b.return_name}) / ({rate_name} − g)",
            ],
            [f"{b.profit_name}_N ({unit})", amount(b.profit_last, scale)],
            [
                b.return_name,
                "—" if ronic is None else f"{pct(ronic.value)} ({ronic.source})",
            ],
            [
                f"Reinversión g / {b.return_name}",
                "—" if ronic is None else pct(terminal_growth / ronic.value),
            ],
        ]
    else:
        multiple = b.multiple
        rows += [
            ["Fórmula", f"VT = M × {b.metric_name}_N ({multiple_name})"],
            [
                "Múltiplo M",
                "—" if multiple is None else f"{num(multiple.value, 2)} ({multiple.source})",
            ],
            [f"{b.metric_name}_N ({unit})", amount(b.metric_last, scale)],
        ]
    if terminal.next_flow is not None:
        rows.append([f"Flujo del año N+1 ({unit})", amount(terminal.next_flow, scale)])
    rows += [
        [f"**Valor terminal** ({unit})", f"**{amount(terminal.value, scale)}**"],
        [
            f"g implícito = ({rate_name} · VT − {flow}_N) / (VT + {flow}_N)",
            f"{pct(terminal.implied_growth)} (g supuesto {pct(terminal_growth)})",
        ],
        [f"{multiple_name} implícito = VT / {b.metric_name}_N", num(terminal.implied_multiple, 2)],
    ]
    return "\n### Valor terminal\n\n" + table(["Concepto", "Valor"], rows) + "\n"


# Lista de comprobaciones de consistencia (o mensaje de que no hay avisos).
def checks_block(checks: Sequence[str]) -> str:
    """Construye la subsección de comprobaciones de consistencia.

    Args:
        checks: Avisos de flujos históricos y del valor terminal.

    Returns:
        Bloque Markdown.
    """
    body = (
        "\n".join(f"- ⚠ {c}" for c in checks)
        if checks
        else "- Sin avisos: flujos históricos positivos, último año en línea y VT coherente."
    )
    return "\n### Comprobaciones de consistencia\n\n" + body + "\n"
