"""Informe Markdown del modelo FCFF desde el EBIT (función pura: devuelve texto, no escribe).

Secciones: 1) compañía, 2) WACC, 3) históricos (márgenes, circulante, FCFF) y proyecciones,
4) valor intrínseco con escenarios y sensibilidad. Formato en :mod:`dcf.reports.format`.
"""

from __future__ import annotations

from dcf.company import Company
from dcf.model.fcff_projection import FcffRatios
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
from dcf.valuation.fcff_result import FcffValuationResult


# Filas de la tabla de históricos del FCFF desde el EBIT (comunes a fcff y fcfe).
def fcff_history_rows(
    company: Company, r: FcffRatios, scale: float, unit: str
) -> tuple[list[int], list[list[str]]]:
    """Construye la tabla de históricos de los modelos fcff y fcfe.

    Args:
        company: Compañía valorada.
        r: Ratios FCFF.
        scale: Divisor de los importes.
        unit: Etiqueta de la unidad.

    Returns:
        Ejercicios y filas de la tabla.
    """
    years = [h.fiscal_year for h in company.historicals]
    by_year = {h.fiscal_year: h for h in company.historicals}
    ebit = {d.fiscal_year: d.ebit for d in company.debt_cost_data}

    def row(label: str, values: list[str], mean: str = "") -> list[str]:
        return [label, *values, mean]

    hist_rows = [
        row(f"Ventas ({unit})", [amount(by_year[y].revenue, scale) for y in years]),
        row(
            "Crecimiento de ventas",
            [pct(r.revenue_growth_by_year.get(y)) for y in years],
            pct(r.average_revenue_growth),
        ),
        row(f"EBIT ({unit})", [amount(ebit.get(y), scale) for y in years]),
        row(
            "Margen EBIT",
            [pct(r.ebit_margin_by_year.get(y)) for y in years],
            pct(r.average_ebit_margin),
        ),
        row(
            "t efectivo (columna Media: mediana)",
            [pct(r.taxes.by_year.get(y)) for y in years],
            pct(r.tax_rate),
        ),
        row(
            "D&A / ventas",
            [pct(r.da_to_revenue_by_year.get(y)) for y in years],
            pct(r.average_da_to_revenue),
        ),
        row(
            "Capex / ventas",
            [pct(r.capex_to_revenue_by_year.get(y)) for y in years],
            pct(r.average_capex_to_revenue),
        ),
        row(
            f"Circulante comercial = clientes + existencias − proveedores ({unit})",
            [amount(r.nwc_by_year.get(y), scale) for y in years],
        ),
        row(
            "Circulante / ventas",
            [pct(r.nwc_to_revenue_by_year.get(y)) for y in years],
            pct(r.average_nwc_to_revenue),
        ),
        row(
            f"FCFF = EBIT·(1−t) + D&A − Capex − ΔNWC ({unit})",
            [amount(r.fcff_by_year.get(y), scale) for y in years],
        ),
    ]
    return years, hist_rows


# Sección 3: históricos con medias y proyección FCFF desde el EBIT.
def _history_section(company: Company, result: FcffValuationResult, scale: float, unit: str) -> str:
    r = result.ratios
    years, hist_rows = fcff_history_rows(company, r, scale, unit)
    proj = result.projections
    flows = [p.flow for p in proj]
    proj_rows = [
        ["Origen de las ventas", *[SOURCE_LABEL[str(f.revenue_source)] for f in flows]],
        [f"Ventas ({unit})", *[amount(f.revenue, scale) for f in flows]],
        ["Crecimiento de ventas", *[pct(f.revenue_growth) for f in flows]],
        [
            f"EBIT = Ventas × {pct(r.average_ebit_margin)} ({unit})",
            *[amount(f.ebit, scale) for f in flows],
        ],
        [
            f"NOPAT = EBIT × (1 − {pct(r.tax_rate)}) ({unit})",
            *[amount(f.nopat, scale) for f in flows],
        ],
        [
            f"+ D&A = Ventas × {pct(r.average_da_to_revenue)} ({unit})",
            *[amount(f.depreciation_amortization, scale) for f in flows],
        ],
        [
            f"− Capex = Ventas × {pct(r.average_capex_to_revenue)} ({unit})",
            *[amount(f.capital_expenditure, scale) for f in flows],
        ],
        [
            f"− ΔNWC (NWC = Ventas × {pct(r.average_nwc_to_revenue)}) ({unit})",
            *[amount(f.nwc_change, scale) for f in flows],
        ],
        [f"**FCFF** ({unit})", *[f"**{amount(f.fcff, scale)}**" for f in flows]],
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
        + "El circulante se proyecta como porcentaje medio de las ventas, así que ΔNWC solo "
        "recoge el crecimiento de las ventas y no los saltos históricos (p. ej. anticipos).\n\n"
        + f"Crecimiento aplicado a los años sin estimación de analistas: "
        f"**{pct(result.projection_growth)}**.\n\n"
        + table(["Partida", *[f"{f.fiscal_year}e" for f in flows]], proj_rows)
        + "\n"
        + warnings_block("Avisos de la proyección", result.warnings)
    )


# Informe FCFF completo en Markdown.
def render_fcff_report(
    company: Company, result: FcffValuationResult, scale: float, unit: str
) -> str:
    """Genera el informe de una valoración FCFF (desde el EBIT).

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
        wacc_section(company, result, scale, unit),
        _history_section(company, result, scale, unit),
        value_section(company, result, scale, unit),
    ]
    return header + "\n" + "\n".join(sections)
