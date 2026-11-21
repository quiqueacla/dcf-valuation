"""Informe Markdown del modelo FCFF_CFO (función pura: devuelve texto, no escribe).

Secciones: 1) compañía, 2) coste de la deuda y del capital → WACC, 3) históricos y
proyecciones, 4) valor intrínseco con escenarios y sensibilidad. Formato en
:mod:`dcf.reports.format`.
"""

from __future__ import annotations

from dcf.company import Company
from dcf.reports.enterprise_markdown import value_section, wacc_section
from dcf.reports.format import (
    SOURCE_LABEL,
    amount,
    company_section,
    num,
    pct,
    report_header,
    table,
    warnings_block,
)
from dcf.valuation.fcff_cfo_result import FcffCfoValuationResult


# Sección 3: tabla de históricos con medias y tabla de proyecciones.
def _history_section(
    company: Company, result: FcffCfoValuationResult, scale: float, unit: str
) -> str:
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


# Informe FCFF_CFO completo en Markdown.
def render_fcff_cfo_report(
    company: Company, result: FcffCfoValuationResult, scale: float, unit: str
) -> str:
    """Genera el informe de una valoración FCFF_CFO.

    Args:
        company: Compañía valorada (datos de entrada).
        result: Resultado de :func:`dcf.valuation.fcff_cfo.value_company`.
        scale: Divisor de los importes para mostrarlos (1e6 = millones).
        unit: Etiqueta de la unidad de los importes.

    Returns:
        Texto Markdown con las cuatro secciones del informe.
    """
    header = report_header(
        company,
        "FCFF_CFO",
        result.valuation_date,
        result.data_date,
        result.source,
        result.code_version,
        result.assumptions,
        unit,
    )
    sections = [
        company_section(company, scale, unit),
        wacc_section(company, result, scale, unit),
        _history_section(company, result, scale, unit),
        value_section(company, result, scale, unit),
    ]
    return header + "\n" + "\n".join(sections)
