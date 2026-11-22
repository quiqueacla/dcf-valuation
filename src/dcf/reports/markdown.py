"""Informe de valoración en Markdown: elige el informe del modelo aplicado.

Función pura: devuelve texto, no escribe. Formato en :mod:`dcf.reports.format`.
"""

from __future__ import annotations

from dcf.company import Company
from dcf.reports.fcfe_fin_markdown import render_fcfe_fin_report
from dcf.reports.fcfe_markdown import render_fcfe_report
from dcf.reports.fcff_cfo_markdown import render_fcff_cfo_report
from dcf.reports.fcff_markdown import render_fcff_report
from dcf.reports.format import MILLIONS
from dcf.valuation.fcfe_fin_result import FcfeFinValuationResult
from dcf.valuation.fcfe_result import FcfeValuationResult
from dcf.valuation.fcff_result import FcffValuationResult
from dcf.valuation.run import AnyValuationResult


# Genera el informe completo en Markdown con las secciones del modelo aplicado.
def render_report(
    company: Company,
    result: AnyValuationResult,
    scale: float = MILLIONS,
    unit: str = "M€",
) -> str:
    """Genera el informe de valoración en Markdown.

    Args:
        company: Compañía valorada (datos de entrada).
        result: Resultado de :func:`dcf.valuation.run.run_valuation`.
        scale: Divisor de los importes para mostrarlos (1e6 = millones).
        unit: Etiqueta de la unidad de los importes.

    Returns:
        Texto Markdown con las cuatro secciones del informe.
    """
    if isinstance(result, FcfeFinValuationResult):
        return render_fcfe_fin_report(company, result, scale, unit)
    if isinstance(result, FcfeValuationResult):
        return render_fcfe_report(company, result, scale, unit)
    if isinstance(result, FcffValuationResult):
        return render_fcff_report(company, result, scale, unit)
    return render_fcff_cfo_report(company, result, scale, unit)
