"""Informe Markdown del modelo FCFF (función pura: devuelve texto, no escribe).

Secciones: 1) compañía, 2) coste de la deuda y del capital → WACC, 3) históricos y
proyecciones, 4) valor intrínseco con escenarios y sensibilidad. Formato en
:mod:`dcf.reports.format`.
"""

from __future__ import annotations

from dcf.company import Company
from dcf.model.cost_of_equity import CostOfEquityResult
from dcf.reports.format import (
    SOURCE_LABEL,
    amount,
    company_section,
    cost_of_equity_rows,
    discount_rate_note,
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
from dcf.valuation.fcff_result import ValuationResult


# Sección 2: Ke por CAPM, Kd y t por año, pesos y WACC.
def _wacc_section(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
    title = "## 2. Coste de la deuda y del capital (WACC)\n"
    note = discount_rate_note(result.discount_rate)
    w = result.wacc
    if w is None:
        return title + note
    ke = CostOfEquityResult(w.market_inputs, w.beta_choice, w.cost_of_equity)
    kd_rows = [
        [
            str(d.fiscal_year),
            amount(d.total_debt, scale),
            amount(d.interest_expense, scale),
            pct(w.cost_of_debt_by_year.get(d.fiscal_year)),
            amount(d.pretax_income, scale),
            amount(d.tax_provision, scale),
            pct(w.tax_rate_by_year.get(d.fiscal_year)),
        ]
        for d in company.debt_cost_data
    ]
    kd_rows.append(
        ["**Media**", "", "", f"**{pct(w.cost_of_debt)}**", "", "", f"**{pct(w.tax_rate)}**"]
    )
    after_tax = None if w.cost_of_debt is None else w.cost_of_debt * (1 - w.tax_rate)
    wacc_rows = [
        [
            f"Fondos propios E (mercado, {unit})",
            amount(w.equity_value, scale),
            pct(w.equity_weight),
        ],
        [f"Deuda D (contable, {unit})", amount(w.debt_value, scale), pct(w.debt_weight)],
        ["Coste del capital Ke", pct(w.cost_of_equity), ""],
        ["Coste de la deuda después de impuestos Kd · (1 − t)", pct(after_tax), ""],
        ["**WACC = We · Ke + Wd · Kd · (1 − t)**", f"**{pct(w.wacc)}**", ""],
    ]
    kd_headers = [
        "Ejercicio",
        f"Deuda total ({unit})",
        f"Intereses ({unit})",
        "Kd",
        f"BAI ({unit})",
        f"Impuestos ({unit})",
        "t efectivo",
    ]
    return (
        title
        + note
        + "\n### 2.1 Coste del capital (Ke)\n\n"
        + table(["Componente", "Valor", "Fuente"], cost_of_equity_rows(ke))
        + "\n\n### 2.2 Coste de la deuda (Kd) y tipo impositivo (t)\n\n"
        + table(kd_headers, kd_rows)
        + "\n\n### 2.3 WACC\n\n"
        + table(["Componente", "Importe / tasa", "Peso"], wacc_rows)
        + "\n"
        + warnings_block("Avisos del WACC", w.warnings)
    )


# Sección 3: tabla de históricos con medias y tabla de proyecciones.
def _history_section(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
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
        row(f"CFO ({unit})", [amount(by_year[y].operating_cash_flow, scale) for y in years]),
        row(f"Capex ({unit})", [amount(by_year[y].capital_expenditure, scale) for y in years]),
        row(f"Intereses ({unit})", [amount(by_year[y].interest_expense, scale) for y in years]),
        row("t efectivo", [pct(r.tax_rate_by_year.get(y)) for y in years]),
        row(
            f"FCFF = CFO + Int.·(1−t) − Capex ({unit})",
            [amount(r.fcff_by_year.get(y), scale) for y in years],
        ),
        row(
            "FCFF / Net Income",
            [num(r.fcff_to_net_income_by_year.get(y), 3) for y in years],
            num(r.average_fcff_to_net_income, 3),
        ),
    ]
    proj = result.projections
    proj_rows = [
        ["Origen de las ventas", *[SOURCE_LABEL[str(p.revenue_source)] for p in proj]],
        [f"Ventas ({unit})", *[amount(p.revenue, scale) for p in proj]],
        ["Crecimiento de ventas", *[pct(p.revenue_growth) for p in proj]],
        [
            f"Net Income = Ventas × {pct(r.average_net_margin)} ({unit})",
            *[amount(p.net_income, scale) for p in proj],
        ],
        [
            f"FCFF = Net Income × {num(r.average_fcff_to_net_income, 3)} ({unit})",
            *[amount(p.fcff, scale) for p in proj],
        ],
        ["Factor de descuento", *[num(p.discount_factor, 4) for p in proj]],
        [f"Valor actual del FCFF ({unit})", *[amount(p.present_value, scale) for p in proj]],
    ]
    return (
        "## 3. Históricos y proyecciones\n\n"
        "### 3.1 Históricos\n\n"
        + table(["Partida", *map(str, years), "Media"], hist_rows)
        + "\n"
        + warnings_block("Años excluidos de alguna media", r.warnings)
        + "\n### 3.2 Proyecciones\n\n"
        + f"Crecimiento aplicado a los años sin estimación de analistas: "
        f"**{pct(result.projection_growth)}**.\n\n"
        + table(["Partida", *[f"{p.fiscal_year}e" for p in proj]], proj_rows)
        + "\n"
        + warnings_block("Avisos de la proyección", result.warnings)
    )


# Sección 4: puente a valor por acción, escenarios y sensibilidad.
def _value_section(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
    b, price = company.balance, company.balance.share_price
    pv_flows = sum(p.present_value for p in result.projections)
    bridge = [
        [f"Valor actual de los FCFF ({unit})", amount(pv_flows, scale)],
        [
            f"Valor terminal (Gordon, g = {pct(result.assumptions.terminal_growth)}) ({unit})",
            amount(result.terminal_value, scale),
        ],
        [f"Valor actual del valor terminal ({unit})", amount(result.terminal_value_present, scale)],
        ["Peso del valor terminal sobre el VE", pct(result.terminal_value_weight)],
        [f"**Valor de empresa (VE)** ({unit})", f"**{amount(result.enterprise_value, scale)}**"],
        [f"− Deuda total ({unit})", amount(b.total_debt, scale)],
        [f"+ Caja ({unit})", amount(b.cash, scale)],
        [f"− Minoritarios ({unit})", amount(b.minority_interest, scale)],
        [f"**Fondos propios** ({unit})", f"**{amount(result.equity_value, scale)}**"],
        ["÷ Acciones diluidas (millones)", num(b.diluted_shares / 1e6, 2)],
        ["**Valor intrínseco por acción**", f"**{eur(result.value_per_share)}**"],
        ["Cotización", eur(price)],
        ["Diferencia valor intrínseco vs. cotización", vs_price(result.value_per_share, price)],
    ]
    return (
        "## 4. Valor intrínseco\n\n"
        "### 4.1 Del valor de empresa al valor por acción\n\n"
        + table(["Concepto", "Valor"], bridge)
        + "\n"
        + scenarios_block(result.scenarios, "WACC", "VE", price, scale, unit)
        + sensitivity_block(result.sensitivity, "WACC")
    )


# Informe FCFF completo en Markdown.
def render_fcff_report(company: Company, result: ValuationResult, scale: float, unit: str) -> str:
    """Genera el informe de una valoración FCFF.

    Args:
        company: Compañía valorada (datos de entrada).
        result: Resultado de :func:`dcf.valuation.fcff.value_company`.
        scale: Divisor de los importes para mostrarlos (1e6 = millones).
        unit: Etiqueta de la unidad de los importes.

    Returns:
        Texto Markdown con las cuatro secciones del informe.
    """
    header = report_header(
        company,
        "FCFF",
        result.valuation_date,
        result.data_date,
        result.source,
        result.code_version,
        result.assumptions,
        unit,
    )
    sections = [
        company_section(company, scale, unit),
        _wacc_section(company, result, scale, unit),
        _history_section(company, result, scale, unit),
        _value_section(company, result, scale, unit),
    ]
    return header + "\n" + "\n".join(sections)
