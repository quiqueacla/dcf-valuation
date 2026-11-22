"""Informe Markdown del modelo FCFE 1.2 para industriales (función pura: devuelve texto).

Secciones: 1) compañía, 2) Ke y deuda, 3) históricos y proyección (FCFF → FCFE),
4) valor intrínseco con VT, comprobaciones, escenarios y sensibilidad.
"""

from __future__ import annotations

from dcf.company import Company
from dcf.model.fcfe_projection import historical_fcfe, historical_net_debt
from dcf.reports.fcff_markdown import fcff_history_rows
from dcf.reports.format import (
    SOURCE_LABEL,
    TERMINAL_LABEL,
    amount,
    checks_block,
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
    terminal_block,
    vs_price,
    warnings_block,
)
from dcf.valuation.fcfe_result import FcfeValuationResult


# Sección 2: Ke (tasa de descuento) y supuestos de deuda.
def _cost_section(result: FcfeValuationResult, scale: float, unit: str) -> str:
    lev = result.leverage
    debt_rows = [
        ["Kd medio histórico (antes de impuestos)", pct(lev.cost_of_debt)],
        ["t (mediana de los tipos efectivos)", pct(lev.tax_rate)],
        ["D / (D + E): parte de la reinversión financiada con deuda", pct(lev.debt_ratio)],
        [f"Deuda neta inicial = deuda total − caja ({unit})", amount(lev.net_debt_0, scale)],
    ]
    text = (
        "## 2. Coste de los fondos propios (Ke) y deuda\n\n"
        "FCFE = FCFF − Int·(1−t) + ΔDeuda neta, descontado a Ke. La deuda neta financia "
        "D/(D+E) de la reinversión neta (apalancamiento constante).\n"
        + discount_rate_note(result.discount_rate)
    )
    ke = result.cost_of_equity
    if ke is not None:
        text += (
            "\n### 2.1 Coste del capital (Ke)\n\n"
            + table(["Componente", "Valor", "Fuente"], cost_of_equity_rows(ke))
            + "\n"
            + warnings_block("Avisos del coste de los fondos propios", ke.warnings)
        )
    return text + "\n### 2.2 Deuda\n\n" + table(["Supuesto", "Valor"], debt_rows) + "\n"


# Filas del paso FCFF → FCFE histórico, tras el FCFF y antes del capital invertido y el ROIC.
def _fcfe_history_rows(
    company: Company, result: FcfeValuationResult, years: list[int], scale: float, unit: str
) -> list[list[str]]:
    t = result.ratios.tax_rate
    interest = {d.fiscal_year: d.interest_expense for d in company.debt_cost_data}
    net_debt = historical_net_debt(company)
    change = {
        y: net_debt[y] - net_debt[prev]
        for prev, y in zip(years, years[1:], strict=False)
        if y in net_debt and prev in net_debt
    }
    fcfe = historical_fcfe(company, result.ratios)
    return [
        [
            f"− Intereses · (1 − {pct(t)}) ({unit})",
            *[amount(interest[y] * (1 - t) if y in interest else None, scale) for y in years],
            "",
        ],
        [
            f"Deuda neta = deuda total − caja ({unit})",
            *[amount(net_debt.get(y), scale) for y in years],
            "",
        ],
        [f"+ ΔDeuda neta ({unit})", *[amount(change.get(y), scale) for y in years], ""],
        [
            f"**FCFE = FCFF − Int.·(1−t) + ΔDeuda neta** ({unit})",
            *[f"**{amount(fcfe[y], scale)}**" if y in fcfe else "—" for y in years],
            "",
        ],
    ]


# Sección 3: históricos del FCFF y proyección FCFF → FCFE.
def _history_section(company: Company, result: FcfeValuationResult, scale: float, unit: str) -> str:
    years, hist_rows = fcff_history_rows(company, result.ratios, scale, unit)
    flows = [p.flow for p in result.projections]
    t = result.leverage.tax_rate
    hist_rows = (
        hist_rows[:-2] + _fcfe_history_rows(company, result, years, scale, unit) + hist_rows[-2:]
    )
    proj_rows = [
        ["Origen de las ventas", *[SOURCE_LABEL[str(f.operating.revenue_source)] for f in flows]],
        [f"Ventas ({unit})", *[amount(f.operating.revenue, scale) for f in flows]],
        [
            f"FCFF = EBIT·(1−t) + D&A − Capex − ΔNWC ({unit})",
            *[amount(f.operating.fcff, scale) for f in flows],
        ],
        [f"Deuda neta inicial ({unit})", *[amount(f.net_debt_begin, scale) for f in flows]],
        [
            f"− Intereses · (1 − {pct(t)}) = Kd · DN_t−1 · (1 − t) ({unit})",
            *[amount(f.interest * (1 - t), scale) for f in flows],
        ],
        [
            f"Reinversión neta = Capex − D&A + ΔNWC ({unit})",
            *[amount(f.reinvestment, scale) for f in flows],
        ],
        [
            f"+ ΔDeuda neta = {pct(result.leverage.debt_ratio)} × reinversión ({unit})",
            *[amount(f.net_debt_change, scale) for f in flows],
        ],
        [f"**FCFE** ({unit})", *[f"**{amount(f.fcfe, scale)}**" for f in flows]],
        [
            f"Net Income = (EBIT − Int) · (1 − t) ({unit})",
            *[amount(f.net_income, scale) for f in flows],
        ],
        ["Factor de descuento (Ke)", *[num(p.discount_factor, 4) for p in result.projections]],
        [
            f"Valor actual del FCFE ({unit})",
            *[amount(p.present_value, scale) for p in result.projections],
        ],
    ]
    return (
        "## 3. Históricos y proyecciones\n\n"
        "### 3.1 Históricos\n\n"
        + table(["Partida", *map(str, years), "Media"], hist_rows)
        + "\n"
        + warnings_block("Años excluidos de alguna media", result.ratios.warnings)
        + "\n### 3.2 Proyecciones\n\n"
        + f"Crecimiento aplicado a los años sin estimación de analistas: "
        f"**{pct(result.projection_growth)}**.\n\n"
        + table(["Partida", *[f"{f.fiscal_year}e" for f in flows]], proj_rows)
        + "\n"
        + warnings_block("Avisos de la proyección", result.warnings)
    )


# Sección 4: valor de los fondos propios, por acción, VT, comprobaciones y escenarios.
def _value_section(company: Company, result: FcfeValuationResult, scale: float, unit: str) -> str:
    b, price = company.balance, company.balance.share_price
    pv_flows = sum(p.present_value for p in result.projections)
    method = "" if result.terminal is None else f", {TERMINAL_LABEL[result.terminal.method.value]}"
    rows = [
        [f"Valor actual de los FCFE ({unit})", amount(pv_flows, scale)],
        [f"Valor terminal{method} ({unit})", amount(result.terminal_value, scale)],
        [f"Valor actual del valor terminal ({unit})", amount(result.terminal_value_present, scale)],
        ["Peso del valor terminal", pct(result.terminal_value_weight)],
        [f"Valor descontado (consolidado) ({unit})", amount(result.present_value_total, scale)],
        [f"− Minoritarios ({unit})", amount(result.minority_interest, scale)],
        [f"**Valor de los fondos propios** ({unit})", f"**{amount(result.equity_value, scale)}**"],
        ["÷ Acciones diluidas (millones)", num(b.diluted_shares / 1e6, 2)],
        ["**Valor intrínseco por acción**", f"**{eur(result.value_per_share)}**"],
        ["Cotización", eur(price)],
        ["Diferencia valor intrínseco vs. cotización", vs_price(result.value_per_share, price)],
    ]
    return (
        "## 4. Valor intrínseco\n\n"
        "### 4.1 Del FCFE al valor por acción\n\n"
        "El FCFE parte del FCFF consolidado, así que se restan los minoritarios; no hay "
        "puente de deuda ni caja (la deuda ya está en el flujo).\n\n"
        + table(["Concepto", "Valor"], rows)
        + "\n"
        + terminal_block(result.terminal, "Ke", result.assumptions.terminal_growth, scale, unit)
        + checks_block(result.checks)
        + scenarios_block(result.scenarios, "Ke", "Fondos propios", price, scale, unit)
        + sensitivity_block(result.sensitivity, "Ke")
    )


# Informe FCFE 1.2 completo en Markdown.
def render_fcfe_report(
    company: Company, result: FcfeValuationResult, scale: float, unit: str
) -> str:
    """Genera el informe de una valoración FCFE 1.2.

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
        _cost_section(result, scale, unit),
        _history_section(company, result, scale, unit),
        _value_section(company, result, scale, unit),
    ]
    return header + "\n" + "\n".join(sections)
