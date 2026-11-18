"""Informe de valoración en Markdown (función pura: devuelve texto, no escribe).

Secciones: 1) compañía, 2) coste de la deuda y del capital → WACC, 3) históricos y
proyecciones, 4) valor intrínseco con escenarios y sensibilidad.

Redondeo solo de presentación (los cálculos no se redondean): importes con 1 decimal en
la escala indicada (millones de EUR por defecto), valores por acción con 2 decimales,
tasas en % con 2 decimales. Redondeo comercial (mitad hacia arriba: 8,125 → 8,13) sobre
la representación decimal más corta del float. Formato numérico español (1.234,5).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from dcf.company import Company
from dcf.valuation.result import ValuationResult

MILLIONS = 1e6
"""Escala por defecto de los importes del informe: millones de EUR."""

DISCLAIMER = "Herramienta educativa y analítica. Este informe no es una recomendación de inversión."


# Número redondeado mitad hacia arriba, con miles "." y decimal "," (formato español).
def _num(value: float, decimals: int) -> str:
    if not math.isfinite(value):
        return "—"
    rounded = Decimal(repr(value)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    text = f"{rounded:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# Importe en la escala del informe, 1 decimal.
def _amount(value: float, scale: float) -> str:
    return _num(value / scale, 1)


# Tasa en decimal como porcentaje con 2 decimales (0.08125 → "8,13 %").
def _pct(value: float | None) -> str:
    return "—" if value is None else f"{_num(value * 100, 2)} %"


# Valor por acción en EUR con 2 decimales.
def _eur(value: float | None) -> str:
    return "—" if value is None else f"{_num(value, 2)} €"


# Tabla Markdown a partir de cabecera y filas de texto.
def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    align = ["---"] + ["---:"] * (len(headers) - 1)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(align) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# Lista de avisos en Markdown, o cadena vacía si no hay.
def _warnings(title: str, items: Sequence[str]) -> str:
    if not items:
        return ""
    return f"\n**{title}:**\n\n" + "\n".join(f"- {w}" for w in items) + "\n"


# Moneda con su tipo de cambio a EUR, p. ej. "USD (1 USD = 0,9000 EUR)".
def _fx_label(currency: str, rate: float) -> str:
    return f"{currency} (1 {currency} = {_num(rate, 4)} EUR)"


# Sección 1: identificación, mercado y balance.
def _company_section(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
    info, b = company.info, company.balance
    fx = _fx_label(info.original_currency, info.fx_rate_to_eur)
    price_fx = _fx_label(info.price_currency, info.price_fx_rate_to_eur)
    rows = [
        ["Ticker", info.ticker],
        ["Nombre", info.name],
        ["Fuente", info.source],
        ["Fecha de los datos (UTC)", info.data_date.strftime("%Y-%m-%d %H:%M")],
        ["Moneda de los estados financieros", fx],
        ["Moneda de cotización", price_fx],
        ["Fecha del último balance", b.balance_date.strftime("%Y-%m-%d")],
        ["Cotización", _eur(b.share_price)],
        ["Acciones diluidas (millones)", _num(b.diluted_shares / 1e6, 2)],
        [f"Capitalización ({unit})", _amount(result.wacc.equity_value, scale)],
        [f"Deuda total, incl. arrendamientos ({unit})", _amount(b.total_debt, scale)],
        [f"Caja y equivalentes ({unit})", _amount(b.cash, scale)],
        [f"Minoritarios ({unit})", _amount(b.minority_interest, scale)],
        [f"Beta publicada ({info.source})", "no publicada" if b.beta is None else _num(b.beta, 3)],
    ]
    return (
        "## 1. Información de la compañía\n\n"
        + _table(["Dato", "Valor"], rows)
        + "\n"
        + _warnings("Avisos de la carga de datos", info.data_warnings)
    )


# Sección 2: Ke por CAPM, Kd y t por año, pesos y WACC.
def _wacc_section(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
    w = result.wacc
    rf, prm = w.market_inputs.risk_free_rate, w.market_inputs.market_risk_premium
    beta = w.beta_choice
    beta_origin = f"{beta.source} ({beta.date:%Y-%m-%d}); modo {beta.mode.value}"
    if beta.reason is not None:
        beta_origin += f"; se usa la del fichero porque {beta.reason}"
    ke_rows = [
        ["Rentabilidad libre de riesgo (rf)", _pct(rf.value), f"{rf.source} ({rf.date:%Y-%m-%d})"],
        [
            "Prima de riesgo de mercado (PRM)",
            _pct(prm.value),
            f"{prm.source} ({prm.date:%Y-%m-%d})",
        ],
        ["Beta (β)", _num(w.beta, 3), beta_origin],
        ["**Coste del capital Ke = rf + β · PRM**", f"**{_pct(w.cost_of_equity)}**", "CAPM"],
    ]
    kd_rows = [
        [
            str(d.fiscal_year),
            _amount(d.total_debt, scale),
            _amount(d.interest_expense, scale),
            _pct(w.cost_of_debt_by_year.get(d.fiscal_year)),
            _amount(d.pretax_income, scale),
            _amount(d.tax_provision, scale),
            _pct(w.tax_rate_by_year.get(d.fiscal_year)),
        ]
        for d in company.debt_cost_data
    ]
    kd_rows.append(
        ["**Media**", "", "", f"**{_pct(w.cost_of_debt)}**", "", "", f"**{_pct(w.tax_rate)}**"]
    )
    after_tax = None if w.cost_of_debt is None else w.cost_of_debt * (1 - w.tax_rate)
    wacc_rows = [
        [
            f"Fondos propios E (mercado, {unit})",
            _amount(w.equity_value, scale),
            _pct(w.equity_weight),
        ],
        [f"Deuda D (contable, {unit})", _amount(w.debt_value, scale), _pct(w.debt_weight)],
        ["Coste del capital Ke", _pct(w.cost_of_equity), ""],
        ["Coste de la deuda después de impuestos Kd · (1 − t)", _pct(after_tax), ""],
        ["**WACC = We · Ke + Wd · Kd · (1 − t)**", f"**{_pct(w.wacc)}**", ""],
    ]
    return (
        "## 2. Coste de la deuda y del capital (WACC)\n\n"
        "### 2.1 Coste del capital (Ke)\n\n"
        + _table(["Componente", "Valor", "Fuente"], ke_rows)
        + "\n\n### 2.2 Coste de la deuda (Kd) y tipo impositivo (t)\n\n"
        + _table(
            [
                "Ejercicio",
                f"Deuda total ({unit})",
                f"Intereses ({unit})",
                "Kd",
                f"BAI ({unit})",
                f"Impuestos ({unit})",
                "t efectivo",
            ],
            kd_rows,
        )
        + "\n\n### 2.3 WACC\n\n"
        + _table(["Componente", "Importe / tasa", "Peso"], wacc_rows)
        + "\n"
        + _warnings("Avisos del WACC", w.warnings)
    )


# Sección 3: tabla de históricos con medias y tabla de proyecciones.
def _history_section(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
    r = result.ratios
    years = [h.fiscal_year for h in company.historicals]
    by_year = {h.fiscal_year: h for h in company.historicals}

    def row(label: str, values: list[str], mean: str = "") -> list[str]:
        return [label, *values, mean]

    hist_rows = [
        row(f"Ventas ({unit})", [_amount(by_year[y].revenue, scale) for y in years]),
        row(
            "Crecimiento de ventas",
            [_pct(r.revenue_growth_by_year.get(y)) for y in years],
            _pct(r.average_revenue_growth),
        ),
        row(f"Net Income ({unit})", [_amount(by_year[y].net_income, scale) for y in years]),
        row(
            "Margen neto",
            [_pct(r.net_margin_by_year.get(y)) for y in years],
            _pct(r.average_net_margin),
        ),
        row(f"CFO ({unit})", [_amount(by_year[y].operating_cash_flow, scale) for y in years]),
        row(f"Capex ({unit})", [_amount(by_year[y].capital_expenditure, scale) for y in years]),
        row(f"Intereses ({unit})", [_amount(by_year[y].interest_expense, scale) for y in years]),
        row("t efectivo", [_pct(r.tax_rate_by_year.get(y)) for y in years]),
        row(
            f"FCFF = CFO + Int.·(1−t) − Capex ({unit})",
            [_amount(r.fcff_by_year[y], scale) if y in r.fcff_by_year else "—" for y in years],
        ),
        row(
            "FCFF / Net Income",
            [
                _num(r.fcff_to_net_income_by_year[y], 3)
                if y in r.fcff_to_net_income_by_year
                else "—"
                for y in years
            ],
            _num(r.average_fcff_to_net_income, 3),
        ),
    ]
    source_label = {"analyst_estimate": "Analistas", "average_growth": "Crec. medio"}
    proj = result.projections
    proj_rows = [
        ["Origen de las ventas", *[source_label[str(p.revenue_source)] for p in proj]],
        [f"Ventas ({unit})", *[_amount(p.revenue, scale) for p in proj]],
        ["Crecimiento de ventas", *[_pct(p.revenue_growth) for p in proj]],
        [
            f"Net Income = Ventas × {_pct(r.average_net_margin)} ({unit})",
            *[_amount(p.net_income, scale) for p in proj],
        ],
        [
            f"FCFF = Net Income × {_num(r.average_fcff_to_net_income, 3)} ({unit})",
            *[_amount(p.fcff, scale) for p in proj],
        ],
        ["Factor de descuento", *[_num(p.discount_factor, 4) for p in proj]],
        [f"Valor actual del FCFF ({unit})", *[_amount(p.present_value, scale) for p in proj]],
    ]
    return (
        "## 3. Históricos y proyecciones\n\n"
        "### 3.1 Históricos\n\n"
        + _table(["Partida", *map(str, years), "Media"], hist_rows)
        + "\n"
        + _warnings("Años excluidos de alguna media", r.warnings)
        + "\n### 3.2 Proyecciones\n\n"
        + f"Crecimiento aplicado a los años sin estimación de analistas: "
        f"**{_pct(result.projection_growth)}**.\n\n"
        + _table(["Partida", *[f"{p.fiscal_year}e" for p in proj]], proj_rows)
        + "\n"
        + _warnings("Avisos de la proyección", result.warnings)
    )


# Sección 4: puente a valor por acción, escenarios y sensibilidad.
def _value_section(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
    b, price = company.balance, company.balance.share_price
    pv_flows = sum(p.present_value for p in result.projections)

    def vs_price(value: float | None) -> str:
        return "—" if value is None else _pct(value / price - 1)

    bridge = [
        [f"Valor actual de los FCFF ({unit})", _amount(pv_flows, scale)],
        [
            f"Valor terminal (Gordon, g = {_pct(result.assumptions.terminal_growth)}) ({unit})",
            _amount(result.terminal_value, scale),
        ],
        [
            f"Valor actual del valor terminal ({unit})",
            _amount(result.terminal_value_present, scale),
        ],
        ["Peso del valor terminal sobre el VE", _pct(result.terminal_value_weight)],
        [f"**Valor de empresa (VE)** ({unit})", f"**{_amount(result.enterprise_value, scale)}**"],
        [f"− Deuda total ({unit})", _amount(b.total_debt, scale)],
        [f"+ Caja ({unit})", _amount(b.cash, scale)],
        [f"− Minoritarios ({unit})", _amount(b.minority_interest, scale)],
        [f"**Fondos propios** ({unit})", f"**{_amount(result.equity_value, scale)}**"],
        ["÷ Acciones diluidas (millones)", _num(b.diluted_shares / 1e6, 2)],
        ["**Valor intrínseco por acción**", f"**{_eur(result.value_per_share)}**"],
        ["Cotización", _eur(price)],
        ["Diferencia valor intrínseco vs. cotización", vs_price(result.value_per_share)],
    ]
    text = (
        "## 4. Valor intrínseco\n\n"
        "### 4.1 Del valor de empresa al valor por acción\n\n"
        + _table(["Concepto", "Valor"], bridge)
        + "\n"
    )

    if result.scenarios:
        case_label = {
            "low": "Estimación baja",
            "avg": "Estimación media",
            "high": "Estimación alta",
        }
        rows = [
            [
                f"**{s.name.capitalize()}**",
                case_label[str(s.estimate_case)],
                _pct(s.wacc),
                _pct(s.terminal_growth),
                "—" if s.enterprise_value is None else _amount(s.enterprise_value, scale),
                _pct(s.terminal_value_weight),
                f"**{_eur(s.value_per_share)}**",
                vs_price(s.value_per_share),
            ]
            for s in result.scenarios
        ]
        errors = [f"{s.name}: {s.error}" for s in result.scenarios if s.error]
        notes = sorted({w for s in result.scenarios for w in s.warnings})
        text += (
            "\n### 4.2 Escenarios\n\n"
            + _table(
                [
                    "Escenario",
                    "Ventas +1/+2",
                    "WACC",
                    "g terminal",
                    f"VE ({unit})",
                    "Peso VT",
                    "Valor por acción",
                    "vs. cotización",
                ],
                rows,
            )
            + "\n"
            + _warnings("Escenarios no válidos", errors)
            + _warnings("Avisos de los escenarios", notes)
        )

    s = result.sensitivity
    sens_rows = [
        [_pct(float(w)), *[_eur(None if math.isnan(v) else float(v)) for v in s.loc[w]]]
        for w in s.index
    ]
    text += (
        "\n### 4.3 Sensibilidad del valor por acción (WACC × g terminal)\n\n"
        + _table(["WACC \\ g", *[_pct(float(g)) for g in s.columns]], sens_rows)
        + "\n\nCeldas con «—»: g ≥ WACC o g ≥ rf (no válidas).\n"
    )
    return text


# Genera el informe completo en Markdown.
def render_report(
    company: Company,
    result: ValuationResult,
    scale: float = MILLIONS,
    unit: str = "M€",
) -> str:
    """Genera el informe de valoración en Markdown.

    Args:
        company: Compañía valorada (datos de entrada).
        result: Resultado de :func:`dcf.valuation.dcf.value_company`.
        scale: Divisor de los importes para mostrarlos (1e6 = millones).
        unit: Etiqueta de la unidad de los importes.

    Returns:
        Texto Markdown con las cuatro secciones del informe.
    """
    a = result.assumptions
    header = (
        f"# Valoración DCF: {company.info.name} ({result.ticker})\n\n"
        f"> {DISCLAIMER}\n\n"
        f"- Fecha de valoración (UTC): {result.valuation_date:%Y-%m-%d %H:%M}\n"
        f"- Datos: {result.source}, {result.data_date:%Y-%m-%d %H:%M} UTC\n"
        f"- Versión del código: dcf {result.code_version}\n"
        f"- Supuestos: horizonte {a.projection_years} años, g terminal {_pct(a.terminal_growth)},"
        f" descuento a final de año\n"
        f"- Unidades: importes en {unit} (1 decimal); por acción en € (2 decimales)\n"
    )
    sections = [
        _company_section(company, result, scale, unit),
        _wacc_section(company, result, scale, unit),
        _history_section(company, result, scale, unit),
        _value_section(company, result, scale, unit),
    ]
    return header + "\n" + "\n".join(sections)
