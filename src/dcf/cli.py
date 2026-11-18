"""Línea de comandos: ``python -m dcf <TICKER>``.

Descarga (o lee de la caché) los datos, valora, muestra el informe en consola y lo
guarda en Markdown.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from dcf.company import Company
from dcf.data.market_inputs import DEFAULT_MARKET_INPUTS_PATH, load_market_inputs
from dcf.data.yahoo import DEFAULT_CACHE_DIR, build_company, fetch_company, load_raw
from dcf.model.assumptions import Assumptions
from dcf.model.wacc import MarketRate
from dcf.reports.markdown import render_report
from dcf.settings import DEFAULT_SETTINGS_PATH, load_settings
from dcf.valuation.dcf import value_company

DEFAULT_OUTPUT_DIR = Path("output")


# Define los argumentos de la línea de comandos.
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m dcf",
        description="Valoración DCF de una compañía (educativa, no es recomendación de inversión).",
    )
    p.add_argument("ticker", help="Símbolo de Yahoo Finance, p. ej. ITX.MC")
    p.add_argument("--g", type=float, help="Crecimiento terminal en decimal (0.02 = 2 %%)")
    p.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    p.add_argument("--market-inputs", type=Path, default=DEFAULT_MARKET_INPUTS_PATH)
    p.add_argument(
        "--from-cache", type=Path, help="Carpeta de data/cache con una descarga previa (sin red)"
    )
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return p


# Carga la compañía desde la caché indicada o descargándola de Yahoo.
def _load_company(
    ticker: str, from_cache: Path | None, cache_dir: Path, kd: MarketRate | None
) -> Company:
    if from_cache is None:
        return fetch_company(ticker, kd, cache_dir)  # pragma: no cover - requiere red
    raw = load_raw(from_cache)
    if raw.ticker != ticker:
        raise ValueError(f"La caché {from_cache} es de {raw.ticker}, no de {ticker}")
    return build_company(raw, kd)


# Ejecuta la valoración completa; devuelve el código de salida del proceso.
def main(argv: Sequence[str] | None = None, now: datetime | None = None) -> int:
    """Punto de entrada de ``python -m dcf``.

    Args:
        argv: Argumentos (sin el nombre del programa); ``None`` = ``sys.argv``.
        now: Momento de la valoración en UTC; ``None`` = ahora (inyectable en tests).

    Returns:
        0 si la valoración termina, 1 si hay un error de datos o de configuración.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    try:
        settings = load_settings(args.settings)
        growth = args.g if args.g is not None else settings.terminal_growth
        if growth is None:
            raise ValueError(
                f"Falta el crecimiento terminal: usa --g o fija terminal_growth en {args.settings}"
            )
        market = load_market_inputs(args.market_inputs)
        company = _load_company(
            args.ticker, args.from_cache, args.cache_dir, market.default_cost_of_debt
        )
        moment = now or datetime.now(UTC)
        result = value_company(
            company, market, Assumptions(terminal_growth=growth), moment, settings.scenarios
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    report = render_report(company, result)
    print(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"{args.ticker}_{moment:%Y%m%dT%H%M%SZ}.md"
    path.write_text(report, encoding="utf-8")
    print(f"\nInforme guardado en {path}")
    return 0
