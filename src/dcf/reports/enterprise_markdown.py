"""Secciones del informe FCFF (fcff_cfo): WACC y puente a fondos propios.

Funciones puras: devuelven texto. Formato en :mod:`dcf.reports.format`.
"""

from __future__ import annotations

from dcf.company import Company
from dcf.model.cost_of_equity import CostOfEquityResult
from dcf.reports.format import (
    amount,
    cost_of_equity_rows,
    discount_rate_note,
    eur,
    num,
    pct,
    scenarios_block,
    sensitivity_block,
    table,
    vs_price,
    warnings_block,
)
from dcf.valuation.fcff_cfo_result import FcffCfoValuationResult

AnyFcffResult = FcffCfoValuationResult
"""Resultado del modelo FCFF (fcff_cfo)."""


# Sección 2: Ke por CAPM, Kd y t por año, pesos y WACC.
def wacc_section(company: Company, result: AnyFcffResult, scale: float, unit: str) -> str:
    """Construye la sección 2 (Ke, Kd, t mediano, pesos y WACC) de un informe FCFF.

    Args:
        company: Compañía valorada.
        result: Resultado fcff o fcff_cfo.
        scale: Divisor de los importes.
        unit: Etiqueta de la unidad.

    Returns:
        Sección Markdown.
    """
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
        [
            "**Kd medio · t mediano**",
            "",
            "",
            f"**{pct(w.cost_of_debt)}**",
            "",
            "",
            f"**{pct(w.tax_rate)}**",
        ]
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


# Sección 4: puente a valor por acción, escenarios y sensibilidad.
def value_section(company: Company, result: AnyFcffResult, scale: float, unit: str) -> str:
    """Construye la sección 4 (puente VE → valor por acción, escenarios, sensibilidad).

    Args:
        company: Compañía valorada.
        result: Resultado fcff o fcff_cfo.
        scale: Divisor de los importes.
        unit: Etiqueta de la unidad.

    Returns:
        Sección Markdown.
    """
    b, price = company.balance, company.balance.share_price
    pv_flows = sum(p.present_value for p in result.projections)
    g = pct(result.assumptions.terminal_growth)
    terminal = [
        [
            f"Valor terminal (Gordon, g = {g}) = FCFF_N · (1 + g) / (WACC − g) ({unit})",
            amount(result.terminal_value, scale),
        ]
    ]
    bridge = [
        [f"Valor actual de los FCFF ({unit})", amount(pv_flows, scale)],
        *terminal,
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
