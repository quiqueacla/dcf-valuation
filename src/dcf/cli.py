"""Línea de comandos: ``dcf <TICKER> [<TICKER> ...]`` o ``python -m dcf ...``.

Para cada ticker descarga (o lee de la caché) los datos, valora y guarda el informe en
Markdown. Con un solo ticker muestra el informe completo en consola; con varios, un
resumen por ticker. Un ticker con error no detiene al resto.
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
from dcf.model.wacc import MarketInputs, MarketRate
from dcf.reports.console import print_report
from dcf.reports.markdown import render_report
from dcf.settings import DEFAULT_SETTINGS_PATH, AppSettings, apply_overrides, load_settings
from dcf.valuation.dcf import value_company
from dcf.valuation.result import ValuationResult

DEFAULT_OUTPUT_DIR = Path("output")


# Define los argumentos de la línea de comandos.
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dcf",
        description="Valoración DCF de compañías (educativa, no es recomendación de inversión).",
        epilog=(
            "Ejemplos:\n"
            "  dcf ITX.MC SAN.MC AAPL\n"
            "  dcf -f tickers.example.txt -o informes\n"
            "  dcf -c config/settings.toml ITX.MC --set g=2%% --set modes=ventas,coste\n"
            "  dcf ITX.MC --no-extras\n"
            "  dcf ITX.MC --from-cache data/cache/ITX.MC/20261118T103000Z"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("tickers", nargs="*", help="Símbolos de Yahoo Finance, p. ej. ITX.MC")
    p.add_argument(
        "-f", "--file", type=Path, help="Fichero con un ticker por línea (# = comentario)"
    )
    p.add_argument(
        "-c",
        "--config",
        "--settings",
        dest="settings",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help=f"Configuración TOML (por defecto {DEFAULT_SETTINGS_PATH})",
    )
    p.add_argument(
        "-m",
        "--market-inputs",
        type=Path,
        default=DEFAULT_MARKET_INPUTS_PATH,
        help=f"rf, PRM y Kd por defecto (por defecto {DEFAULT_MARKET_INPUTS_PATH})",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Carpeta de los informes (por defecto {DEFAULT_OUTPUT_DIR})",
    )
    p.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="CLAVE=VALOR",
        help="Ajusta la configuración: terminal_growth (g), projection_years, modes, "
        "wacc_shift, growth_shift. Tasas como 2%% o 0.02. Repetible.",
    )
    p.add_argument("--g", type=float, help="Crecimiento terminal en decimal (atajo de --set g=)")
    p.add_argument(
        "--no-extras",
        action="store_true",
        help="Sin escenarios (la tabla de sensibilidad se mantiene siempre)",
    )
    p.add_argument(
        "--raw",
        action="store_true",
        help="Muestra el informe en Markdown sin formatear (útil para copiarlo o redirigirlo)",
    )
    p.add_argument(
        "--from-cache", type=Path, help="Carpeta de data/cache con una descarga previa (sin red)"
    )
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    return p


# Lee tickers de un fichero: uno o varios por línea, separados por espacios o comas.
def read_tickers(path: Path) -> list[str]:
    """Lee la lista de tickers de un fichero de texto.

    Args:
        path: Fichero con tickers; las líneas en blanco y lo que sigue a ``#`` se ignoran.

    Returns:
        Tickers en el orden del fichero.

    Raises:
        FileNotFoundError: Si el fichero no existe.
    """
    tickers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        content = line.split("#", 1)[0].replace(",", " ")
        tickers.extend(t for t in content.split() if t)
    return tickers


# Une tickers de argumentos y fichero, sin duplicados y conservando el orden.
def _all_tickers(args: argparse.Namespace) -> list[str]:
    tickers = list(args.tickers)
    if args.file is not None:
        tickers += read_tickers(args.file)
    return list(dict.fromkeys(tickers))


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


# Valora un ticker y guarda su informe; devuelve compañía, resultado y ruta del informe.
def _value_one(
    ticker: str,
    args: argparse.Namespace,
    settings: AppSettings,
    growth: float,
    market: MarketInputs,
    moment: datetime,
) -> tuple[Company, ValuationResult, Path]:
    company = _load_company(ticker, args.from_cache, args.cache_dir, market.default_cost_of_debt)
    assumptions = Assumptions(terminal_growth=growth, projection_years=settings.projection_years)
    scenarios = None if args.no_extras else settings.scenarios
    result = value_company(company, market, assumptions, moment, scenarios)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"{ticker}_{moment:%Y%m%dT%H%M%SZ}.md"
    path.write_text(render_report(company, result), encoding="utf-8")
    return company, result, path


# Línea de resumen de un ticker valorado (para ejecuciones con varios tickers).
def _summary(company: Company, result: ValuationResult, path: Path) -> str:
    price = company.balance.share_price
    parts = [
        f"{result.ticker}: {result.value_per_share:,.2f} € por acción "
        f"(cotización {price:,.2f} €, WACC {result.wacc.wacc:.2%})"
    ]
    for s in result.scenarios:
        value = "no válido" if s.value_per_share is None else f"{s.value_per_share:,.2f} €"
        parts.append(f"{s.name}: {value}")
    return " | ".join(parts) + f"\n    informe: {path}"


# Ejecuta la valoración de todos los tickers; devuelve el código de salida del proceso.
def main(argv: Sequence[str] | None = None, now: datetime | None = None) -> int:
    """Punto de entrada de ``dcf`` y ``python -m dcf``.

    Args:
        argv: Argumentos (sin el nombre del programa); ``None`` = ``sys.argv``.
        now: Momento de la valoración en UTC; ``None`` = ahora (inyectable en tests).

    Returns:
        0 si todos los tickers se valoran, 1 si alguno falla o hay un error de
        configuración, 2 si no se indica ningún ticker.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        tickers = _all_tickers(args)
        if not tickers:
            parser.print_usage(sys.stderr)
            print("Error: indica al menos un ticker o un fichero con -f", file=sys.stderr)
            return 2
        if args.from_cache is not None and len(tickers) > 1:
            raise ValueError("--from-cache solo admite un ticker")
        settings = apply_overrides(load_settings(args.settings), args.overrides)
        growth = args.g if args.g is not None else settings.terminal_growth
        if growth is None:
            raise ValueError(
                "Falta el crecimiento terminal: usa --set g=2%, --g 0.02 "
                f"o fija terminal_growth en {args.settings}"
            )
        market = load_market_inputs(args.market_inputs)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    moment = now or datetime.now(UTC)
    failures = 0
    for ticker in tickers:
        try:
            company, result, path = _value_one(ticker, args, settings, growth, market, moment)
        except (ValueError, FileNotFoundError) as exc:
            failures += 1
            print(f"Error en {ticker}: {exc}", file=sys.stderr)
            continue
        if len(tickers) == 1:
            print_report(render_report(company, result), raw=args.raw)
            print(f"\nInforme guardado en {path}")
        else:
            print(_summary(company, result, path))

    if len(tickers) > 1:
        print(f"\n{len(tickers) - failures} de {len(tickers)} tickers valorados.")
    return 1 if failures else 0
