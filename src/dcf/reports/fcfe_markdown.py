"""Informe Markdown del modelo FCFE (función pura: devuelve texto, no escribe).

Secciones: 1) compañía, 2) coste de los fondos propios (Ke), 3) históricos y
proyecciones, 4) valor intrínseco con escenarios y sensibilidad. Formato en
:mod:`dcf.reports.format`.
"""

from __future__ import annotations

from dcf.company import Company
from dcf.reports.format import (
    SOURCE_LABEL,
    amount,
    company_section,
    cost_of_equity_rows,
    eur,
    num,
    pct,
    report_header,
    scenarios_block,
    sensitivity_block,
    table,
    vs_price,
    warnings_block,
)
from dcf.valuation.fcfe_result import FcfeValuationResult


# Sección 2: Ke por CAPM (tasa de descuento del FCFE).
def _cost_section(result: FcfeValuationResult) -> str:
    ke = result.cost_of_equity
    return (
        "## 2. Coste de los fondos propios (Ke)\n\n"
        "En el modelo FCFE los flujos son del accionista y se descuentan a Ke; no hay WACC "
        "ni coste de la deuda.\n\n"
        + table(["Componente", "Valor", "Fuente"], cost_of_equity_rows(ke))
        + "\n"
        + warnings_block("Avisos del coste de los fondos propios", ke.warnings)
    )


# Sección 3: históricos (ventas, margen, fondos propios, ROE) y proyección FCFE.
def _history_section(company: Company, result: FcfeValuationResult, scale: float, unit: str) -> str:
    r = result.ratios
    years = [h.fiscal_year for h in company.historicals]
    by_year = {h.fiscal_year: h for h in company.historicals}

    def row(label: str, values: list[str], mean: str = "") -> list[str]:
        return [label, *values, mean]

    hist_rows = [
        row(f"Ventas ({unit})", [amount(by_year[y].revenue, scale) for y in years]),
        row(
            "Crecimiento de ventas",
            [pct(r.revenue_growth_by_year.get(y)) for y in years],
            pct(r.average_revenue_growth),
        ),
        row(f"Net Income ({unit})", [amount(by_year[y].net_income, scale) for y in years]),
        row(
            "Margen neto",
            [pct(r.net_margin_by_year.get(y)) for y in years],
            pct(r.average_net_margin),
        ),
        row(f"Fondos propios ({unit})", [amount(r.equity_by_year.get(y), scale) for y in years]),
        row(
            "ROE = Net Income / FP inicial", [pct(r.return_on_equity_by_year.get(y)) for y in years]
        ),
    ]
    proj = result.projections
    flows = [p.flow for p in proj]
    proj_rows = [
        ["Origen de las ventas", *[SOURCE_LABEL[str(f.revenue_source)] for f in flows]],
        [f"Ventas ({unit})", *[amount(f.revenue, scale) for f in flows]],
        ["Crecimiento de ventas (g_t)", *[pct(f.revenue_growth) for f in flows]],
        [
            f"Net Income = Ventas × {pct(r.average_net_margin)} ({unit})",
            *[amount(f.net_income, scale) for f in flows],
        ],
        [
            f"Fondos propios iniciales FP_t−1 ({unit})",
            *[amount(f.equity_begin, scale) for f in flows],
        ],
        [
            f"− Reinversión = g_t · FP_t−1 ({unit})",
            *[amount(f.equity_reinvestment, scale) for f in flows],
        ],
        [f"**FCFE** ({unit})", *[f"**{amount(f.fcfe, scale)}**" for f in flows]],
        ["ROE implícito = Net Income / FP_t−1", *[pct(f.implied_roe) for f in flows]],
        ["Factor de descuento (Ke)", *[num(p.discount_factor, 4) for p in proj]],
        [f"Valor actual del FCFE ({unit})", *[amount(p.present_value, scale) for p in proj]],
    ]
    return (
        "## 3. Históricos y proyecciones\n\n"
        "### 3.1 Históricos\n\n"
        + table(["Partida", *map(str, years), "Media"], hist_rows)
        + "\n\n### 3.2 Proyecciones\n\n"
        + "FCFE_t = Net Income_t − g_t · FP_t−1: se retiene el beneficio necesario para que "
        "los fondos propios crezcan al ritmo de las ventas.\n\n"
        + f"Crecimiento aplicado a los años sin estimación de analistas: "
        f"**{pct(result.projection_growth)}**.\n\n"
        + table(["Partida", *[f"{f.fiscal_year}e" for f in flows]], proj_rows)
        + "\n"
        + warnings_block("Avisos de la proyección", result.warnings)
    )


# Sección 4: valor de los fondos propios, por acción, escenarios y sensibilidad.
def _value_section(company: Company, result: FcfeValuationResult, scale: float, unit: str) -> str:
    b, price = company.balance, company.balance.share_price
    g = result.assumptions.terminal_growth
    pv_flows = sum(p.present_value for p in result.projections)
    book_per_share = result.ratios.last_equity / b.diluted_shares
    rows = [
        [f"Valor actual de los FCFE ({unit})", amount(pv_flows, scale)],
        [
            f"FCFE del año N+1 = NI_N · (1 + g) − g · FP_N ({unit})",
            amount(result.terminal_fcfe, scale),
        ],
        [
            f"Valor terminal (Gordon, g = {pct(g)}) = FCFE_N+1 / (Ke − g) ({unit})",
            amount(result.terminal_value, scale),
        ],
        [f"Valor actual del valor terminal ({unit})", amount(result.terminal_value_present, scale)],
        ["Peso del valor terminal sobre los fondos propios", pct(result.terminal_value_weight)],
        [f"**Valor de los fondos propios** ({unit})", f"**{amount(result.equity_value, scale)}**"],
        ["÷ Acciones diluidas (millones)", num(b.diluted_shares / 1e6, 2)],
        ["**Valor intrínseco por acción**", f"**{eur(result.value_per_share)}**"],
        ["Cotización", eur(price)],
        ["Diferencia valor intrínseco vs. cotización", vs_price(result.value_per_share, price)],
        ["Valor contable por acción (FP_0 / acciones)", eur(book_per_share)],
        [
            "P/VC implícito (valor intrínseco / valor contable)",
            num(result.value_per_share / book_per_share, 2),
        ],
    ]
    return (
        "## 4. Valor intrínseco\n\n"
        "### 4.1 Del FCFE al valor por acción\n\n"
        "No hay puente deuda/caja: el FCFE ya es el flujo del accionista y el Net Income es "
        "el atribuible a la dominante (sin minoritarios).\n\n"
        + table(["Concepto", "Valor"], rows)
        + "\n"
        + scenarios_block(result.scenarios, "Ke", "Fondos propios", price, scale, unit)
        + sensitivity_block(result.sensitivity, "Ke")
    )


# Informe FCFE completo en Markdown.
def render_fcfe_report(
    company: Company, result: FcfeValuationResult, scale: float, unit: str
) -> str:
    """Genera el informe de una valoración FCFE.

    Args:
        company: Compañía valorada (datos de entrada).
        result: Resultado de :func:`dcf.valuation.fcfe.value_company`.
        scale: Divisor de los importes para mostrarlos (1e6 = millones).
        unit: Etiqueta de la unidad de los importes.

    Returns:
        Texto Markdown con las cuatro secciones del informe.
    """
    header = report_header(
        company,
        "FCFE",
        result.valuation_date,
        result.data_date,
        result.source,
        result.code_version,
        result.assumptions,
        unit,
    )
    sections = [
        company_section(company, scale, unit),
        _cost_section(result),
        _history_section(company, result, scale, unit),
        _value_section(company, result, scale, unit),
    ]
    return header + "\n" + "\n".join(sections)
