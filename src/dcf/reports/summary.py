"""Resumen de una valoración de varios tickers en Markdown y en tabla (para CSV).

Funciones puras: construyen las filas, el texto Markdown y el DataFrame; la escritura de
los ficheros la hace la línea de comandos. Importes en EUR; tasas en decimal (0.08 = 8 %).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from dcf.company import Company, model_suitability_warning
from dcf.model.cost_of_equity import CostOfEquityResult, MarketRate
from dcf.reports.format import DISCLAIMER, eur, num, pct, table
from dcf.valuation.fcfe_fin_result import FcfeFinValuationResult
from dcf.valuation.fcfe_result import FcfeValuationResult
from dcf.valuation.run import AnyValuationResult
from dcf.valuation.scenarios import ScenarioName


@dataclass(frozen=True, slots=True)
class SummaryRow:
    """Resultado final de un ticker en el resumen del lote.

    Attributes:
        ticker: Símbolo valorado.
        name: Nombre de la empresa; ``None`` si la valoración falló antes de cargarla.
        model: Modelo usado (fcff, fcff_cfo, fcfe, fcfe_fin); ``None`` si falló.
        terminal_method: Método de valor terminal (gordon, gordon_value_driver, vt_mult).
        share_price: Cotización en EUR.
        bearish: Valor por acción del escenario bajista, en EUR; ``None`` si no hay
            escenarios o el escenario no es válido.
        neutral: Valor por acción del escenario neutro (la valoración central), en EUR.
        bullish: Valor por acción del escenario alcista, en EUR.
        rate_name: Tasa de descuento del modelo: "WACC" (FCFF) o "Ke" (FCFE).
        discount_rate: Tasa de descuento central, en decimal.
        terminal_growth: g terminal usado, en decimal.
        rate_sources: Fuentes de la tasa: rf, PRM, beta y, en FCFF, Kd y t.
        growth_source: De dónde sale el g terminal (fichero de configuración o argumento).
        warnings: Avisos de la carga, el modelo, la tasa, la proyección y los escenarios.
        error: Motivo por el que el ticker no se pudo valorar; ``None`` si se valoró.
    """

    ticker: str
    name: str | None = None
    model: str | None = None
    terminal_method: str | None = None
    share_price: float | None = None
    bearish: float | None = None
    neutral: float | None = None
    bullish: float | None = None
    rate_name: str | None = None
    discount_rate: float | None = None
    terminal_growth: float | None = None
    rate_sources: str | None = None
    growth_source: str | None = None
    warnings: tuple[str, ...] = ()
    error: str | None = None

    # Margen potencial de un valor respecto a la cotización (valor / cotización − 1).
    def upside(self, value: float | None) -> float | None:
        """Calcula el margen potencial de un valor por acción frente a la cotización.

        Args:
            value: Valor por acción en EUR; ``None`` si no existe.

        Returns:
            Margen en decimal (0.10 = valor un 10 % por encima de la cotización), o
            ``None`` si falta el valor o la cotización.
        """
        if value is None or self.share_price is None:
            return None
        return value / self.share_price - 1.0


# Texto de una tasa de mercado con su fuente y fecha.
def _rate_label(name: str, rate: MarketRate) -> str:
    return f"{name} {pct(rate.value)} ({rate.source}, {rate.date:%Y-%m-%d})"


# Fuentes de la tasa de descuento: rf, PRM, beta y, en FCFF, Kd y t históricos.
def _rate_sources(equity: CostOfEquityResult, fcff_extra: str | None) -> str:
    beta = equity.beta_choice
    parts = [
        _rate_label("rf", equity.market_inputs.risk_free_rate),
        _rate_label("PRM", equity.market_inputs.market_risk_premium),
        f"β {num(beta.value, 3)} ({beta.source}, {beta.date:%Y-%m-%d}, modo {beta.mode.value})",
    ]
    floor = equity.floor
    if floor is not None:
        crp = floor.country_risk_premium
        applied = "aplicado" if equity.floor_applied else "no aplicado"
        parts.append(
            f"suelo Ke {pct(floor.value)} {applied} (prima país {floor.country} "
            f"{pct(crp.value)}, {crp.source}, {crp.date:%Y-%m-%d})"
        )
    if fcff_extra:
        parts.append(fcff_extra)
    return "; ".join(parts)


# Lista sin duplicados conservando el orden.
def _unique(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(i for i in items if i))


# Fila del resumen de un ticker valorado.
def summary_row(company: Company, result: AnyValuationResult, growth_source: str) -> SummaryRow:
    """Construye la fila del resumen de un ticker valorado.

    Args:
        company: Compañía valorada.
        result: Resultado de la valoración (FCFF o FCFE).
        growth_source: Origen del g terminal (p. ej. "config/settings.toml").

    Returns:
        Fila con valores de los escenarios, tasas, fuentes y avisos.
    """
    info = company.info
    warnings: list[str] = list(info.data_warnings)
    suitability = model_suitability_warning(info.company_type, info.valuation_model)
    if suitability is not None:
        warnings.insert(0, suitability)

    choice = result.discount_rate
    sources: str | None = None
    if isinstance(result, FcfeFinValuationResult | FcfeValuationResult):
        if result.cost_of_equity is not None:
            sources = _rate_sources(result.cost_of_equity, None)
    else:
        w = result.wacc
        if w is not None:
            equity = w.equity or CostOfEquityResult(
                w.market_inputs, w.beta_choice, w.cost_of_equity
            )
            kd = "sin deuda" if w.cost_of_debt is None else pct(w.cost_of_debt)
            sources = _rate_sources(
                equity, f"Kd {kd} y t {pct(w.tax_rate)} (medias históricas, {result.source})"
            )
            warnings += list(w.warnings)
        warnings += list(result.ratios.warnings)
    if choice.override is not None:
        forced = f"forzado ({choice.override.source}, {choice.override.date:%Y-%m-%d})"
        calculated = (
            f"calculado: no se pudo calcular ({choice.calculation_error})"
            if choice.calculated is None
            else f"calculado {pct(choice.calculated)}: {sources}"
        )
        sources = f"{forced}; {calculated}"
    warnings += list(result.warnings) + list(result.checks)

    by_name = {s.name: s for s in result.scenarios}
    for s in result.scenarios:
        if s.error:
            warnings.append(f"Escenario {s.name} no válido: {s.error}")
        warnings += list(s.warnings)

    def scenario(name: ScenarioName) -> float | None:
        s = by_name.get(name)
        return None if s is None else s.value_per_share

    return SummaryRow(
        ticker=info.ticker,
        name=info.name,
        model=info.valuation_model.value,
        terminal_method=None if result.terminal is None else result.terminal.method.value,
        share_price=company.balance.share_price,
        bearish=scenario(ScenarioName.BEARISH),
        neutral=result.value_per_share,
        bullish=scenario(ScenarioName.BULLISH),
        rate_name=choice.name,
        discount_rate=choice.value,
        terminal_growth=result.assumptions.terminal_growth,
        rate_sources=sources,
        growth_source=growth_source,
        warnings=_unique(warnings),
    )


# Fila del resumen de un ticker que no se pudo valorar.
def error_row(ticker: str, error: str) -> SummaryRow:
    """Construye la fila de un ticker cuya valoración falló.

    Args:
        ticker: Símbolo.
        error: Mensaje de error.

    Returns:
        Fila con solo el ticker y el error.
    """
    return SummaryRow(ticker=ticker, error=error)


# Resumen en Markdown: tabla de resultados, supuestos con fuentes y avisos por ticker.
def render_summary(rows: Sequence[SummaryRow], valuation_date: datetime, code_version: str) -> str:
    """Genera el resumen del lote en Markdown.

    Args:
        rows: Filas del resumen, en el orden de valoración.
        valuation_date: Momento de la valoración, en UTC.
        code_version: Versión del paquete ``dcf``.

    Returns:
        Texto Markdown.
    """
    valued = [r for r in rows if r.error is None]
    results = [
        [
            f"**{r.ticker}**",
            r.name or "",
            r.model or "",
            r.terminal_method or "",
            eur(r.share_price),
            eur(r.bearish),
            pct(r.upside(r.bearish)),
            f"**{eur(r.neutral)}**",
            pct(r.upside(r.neutral)),
            eur(r.bullish),
            pct(r.upside(r.bullish)),
            str(len(r.warnings)),
        ]
        for r in valued
    ]
    assumptions = [
        [
            f"**{r.ticker}**",
            f"{r.rate_name} {pct(r.discount_rate)}",
            pct(r.terminal_growth),
            r.rate_sources or "",
            r.growth_source or "",
        ]
        for r in valued
    ]
    text = (
        "# Resumen de valoraciones DCF\n\n"
        f"> {DISCLAIMER}\n\n"
        f"- Fecha de valoración (UTC): {valuation_date:%Y-%m-%d %H:%M}\n"
        f"- Versión del código: dcf {code_version}\n"
        f"- Tickers valorados: {len(valued)} de {len(rows)}\n"
        "- Margen potencial = valor intrínseco / cotización − 1. Importes por acción en €.\n\n"
        "## Resultados\n\n"
        + table(
            [
                "Ticker",
                "Empresa",
                "Modelo",
                "VT",
                "Cotización",
                "Bajista",
                "Margen",
                "Neutro",
                "Margen",
                "Alcista",
                "Margen",
                "Avisos",
            ],
            results,
            text_columns=frozenset({0, 1, 2, 3}),
        )
        + "\n\n## Supuestos y fuentes\n\n"
        + table(
            ["Ticker", "Tasa", "g terminal", "Fuentes de la tasa", "Fuente de g"],
            assumptions,
            text_columns=frozenset({0, 3, 4}),
        )
        + "\n"
    )
    errors = [r for r in rows if r.error is not None]
    if errors:
        text += (
            "\n## Tickers no valorados\n\n"
            + "\n".join(f"- **{r.ticker}**: {r.error}" for r in errors)
            + "\n"
        )
    with_warnings = [r for r in valued if r.warnings]
    if with_warnings:
        text += "\n## Avisos\n"
        for r in with_warnings:
            text += f"\n### {r.ticker}\n\n" + "\n".join(f"- {w}" for w in r.warnings) + "\n"
    return text


# Tabla del resumen para CSV: una fila por ticker, tasas y márgenes en decimal.
def summary_frame(rows: Sequence[SummaryRow]) -> pd.DataFrame:
    """Construye la tabla del resumen para exportarla a CSV.

    Args:
        rows: Filas del resumen.

    Returns:
        DataFrame con una fila por ticker. Importes por acción en EUR; tasas y márgenes
        en decimal (0.10 = 10 %); avisos unidos con " | ". Sin redondeo.
    """
    return pd.DataFrame(
        [
            {
                "ticker": r.ticker,
                "empresa": r.name,
                "modelo": r.model,
                "vt": r.terminal_method,
                "cotizacion_eur": r.share_price,
                "bajista_eur": r.bearish,
                "margen_bajista": r.upside(r.bearish),
                "neutro_eur": r.neutral,
                "margen_neutro": r.upside(r.neutral),
                "alcista_eur": r.bullish,
                "margen_alcista": r.upside(r.bullish),
                "tasa": r.rate_name,
                "tasa_descuento": r.discount_rate,
                "g_terminal": r.terminal_growth,
                "fuentes_tasa": r.rate_sources,
                "fuente_g": r.growth_source,
                "avisos": " | ".join(r.warnings),
                "error": r.error,
            }
            for r in rows
        ]
    )


CSV_SEPARATOR = ";"
"""Separador del CSV. Motivo: Excel en español abre así el fichero con doble clic (2026-11-19)."""

CSV_DECIMAL = ","
"""Separador decimal del CSV (Excel en español)."""

CSV_ENCODING = "utf-8-sig"
"""UTF-8 con BOM: Excel detecta así las tildes y la «ñ»."""


# CSV del resumen con el formato de Excel en español.
def summary_csv(rows: Sequence[SummaryRow]) -> str:
    """Genera el CSV del resumen como texto.

    Args:
        rows: Filas del resumen.

    Returns:
        Texto CSV con separador «;» y decimal «,» (escribirlo con ``CSV_ENCODING``).
    """
    text: str = summary_frame(rows).to_csv(sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, index=False)
    return text
