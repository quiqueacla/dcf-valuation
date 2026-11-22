"""Valor terminal: Gordon clásico, Gordon con value driver y múltiplo de salida.

Común a todos los modelos: cada uno aporta su :class:`TerminalBasis` (flujo del año N,
beneficio, métrica del múltiplo y rentabilidad de las nuevas inversiones) y la tasa con
la que descuenta. Funciones puras, sin I/O. Ver ``docs/dcf_metodos.md`` §3 y
``docs/metodologia.md`` §12. Tasas en decimal, importes en EUR.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass

from dcf.company import TerminalMethod
from dcf.model.checks import WarningThresholds
from dcf.model.cost_of_equity import MarketRate
from dcf.model.terminal_value import validate_terminal_growth


@dataclass(frozen=True, slots=True)
class TerminalBasis:
    """Datos del año N que el modelo aporta para calcular el valor terminal.

    Attributes:
        last_flow: Flujo del último año proyectado (CF_N: FCFF o FCFE), en EUR.
        profit_last: Beneficio del año N sobre el que reinvierte el value driver: NOPAT
            en los modelos FCFF y Net Income en los FCFE, en EUR.
        profit_name: "NOPAT" o "Net Income", para el informe.
        metric_last: Métrica del múltiplo en el año N: EBITDA (FCFF) o Net Income
            (FCFE), en EUR; ``None`` si el modelo no la puede calcular.
        metric_name: "EBITDA" o "Net Income" (múltiplo EV/EBITDA o P/E).
        return_name: "RONIC" (FCFF) o "ROE" (FCFE): rentabilidad de las nuevas
            inversiones que se reinvierten para crecer a g.
        ronic: RONIC o ROE con su origen (fichero, argumento o histórico); ``None`` si no
            se pudo obtener.
        multiple: Múltiplo de salida con su origen; ``None`` si no se indicó.
    """

    last_flow: float
    profit_last: float
    profit_name: str
    metric_last: float | None
    metric_name: str
    return_name: str
    ronic: MarketRate | None = None
    multiple: MarketRate | None = None


@dataclass(frozen=True, slots=True)
class TerminalValueResult:
    """Valor terminal calculado con su método, entradas y chequeos de consistencia.

    Attributes:
        method: Método aplicado (gordon, gordon_value_driver o vt_mult).
        value: Valor terminal al final del año N, sin descontar, en EUR.
        next_flow: Flujo del año N+1 que entra en Gordon (``None`` con múltiplo).
        basis: Datos del año N aportados por el modelo.
        implied_growth: g implícito: el que, con Gordon clásico sobre CF_N, daría este
            VT: g = (r · VT − CF_N) / (VT + CF_N).
        implied_multiple: VT / métrica del múltiplo (EV/EBITDA o P/E implícito); ``None``
            si la métrica no está disponible o no es positiva.
        warnings: Avisos de consistencia (g implícito, RONIC alto).
    """

    method: TerminalMethod
    value: float
    next_flow: float | None
    basis: TerminalBasis
    implied_growth: float
    implied_multiple: float | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TerminalOptions:
    """Cómo se calcula el valor terminal en una valoración.

    Attributes:
        method: Método de VT.
        multiple: Múltiplo de salida forzado (argumento o fichero); obligatorio con
            ``vt_mult``.
        ronic: RONIC / ROE forzado (argumento o fichero); ``None`` = el histórico.
        thresholds: Umbrales de los avisos de consistencia.
    """

    method: TerminalMethod
    multiple: MarketRate | None = None
    ronic: MarketRate | None = None
    thresholds: WarningThresholds = WarningThresholds()


# Elige el valor por precedencia: argumento > fichero > calculado.
def pick_override(
    argument: MarketRate | None, from_file: MarketRate | None, computed: MarketRate | None
) -> MarketRate | None:
    """Aplica la precedencia de los datos forzables del valor terminal.

    Args:
        argument: Valor del argumento ``--set``.
        from_file: Valor por ticker de ``market_inputs.toml``.
        computed: Valor calculado a partir de los históricos.

    Returns:
        El primero que exista, o ``None``.
    """
    return argument or from_file or computed


# g que, con Gordon clásico sobre CF_N, reproduce el VT: (r · VT − CF_N) / (VT + CF_N).
def implied_growth(terminal_value: float, last_flow: float, rate: float) -> float:
    """Despeja el crecimiento perpetuo implícito en un valor terminal.

    Args:
        terminal_value: VT al final del año N, en EUR.
        last_flow: Flujo del año N, en EUR.
        rate: Tasa de descuento en decimal.

    Returns:
        g implícito en decimal (``nan`` si VT + CF_N = 0).
    """
    denominator = terminal_value + last_flow
    if denominator == 0:
        return float("nan")
    return (rate * terminal_value - last_flow) / denominator


# Valor terminal según el método, con sus chequeos de consistencia.
def terminal_value(
    options: TerminalOptions,
    basis: TerminalBasis,
    rate: float,
    terminal_growth: float,
    risk_free_rate: float,
    rate_name: str,
) -> TerminalValueResult:
    """Calcula el valor terminal con el método elegido.

    - ``gordon``: VT = CF_N · (1 + g) / (r − g).
    - ``gordon_value_driver``: VT = Beneficio_N · (1 + g) · (1 − g / RONIC) / (r − g).
    - ``vt_mult``: VT = M × métrica_N (EBITDA en FCFF, Net Income en FCFE).

    Args:
        options: Método, múltiplo, RONIC y umbrales.
        basis: Datos del año N aportados por el modelo.
        rate: Tasa de descuento (WACC o Ke) en decimal.
        terminal_growth: g terminal en decimal.
        risk_free_rate: rf en decimal.
        rate_name: "WACC" o "Ke", para los mensajes.

    Returns:
        Valor terminal y chequeos.

    Raises:
        ValueError: Si g ≥ tasa o g ≥ rf, o si falta el RONIC / múltiplo / métrica que
            exige el método, o no son positivos.
    """
    g = terminal_growth
    validate_terminal_growth(g, rate, risk_free_rate, rate_name)
    warnings: list[str] = []
    method = options.method
    next_flow: float | None = None
    if method is TerminalMethod.GORDON:
        next_flow = basis.last_flow * (1.0 + g)
        value = next_flow / (rate - g)
    elif method is TerminalMethod.VALUE_DRIVER:
        ronic = basis.ronic
        if ronic is None:
            raise ValueError(
                f"Falta el {basis.return_name} para gordon_value_driver: no se pudo calcular "
                f'el histórico; indícalo con --set ronic= o [ronic."TICKER"] en '
                "market_inputs.toml"
            )
        if ronic.value <= 0:
            raise ValueError(f"El {basis.return_name} debe ser positivo, recibido {ronic.value}")
        next_flow = basis.profit_last * (1.0 + g) * (1.0 - g / ronic.value)
        value = next_flow / (rate - g)
        if ronic.value > options.thresholds.ronic_to_rate * rate:
            warnings.append(
                f"{basis.return_name} {ronic.value:.2%} > {options.thresholds.ronic_to_rate:g} × "
                f"{rate_name} ({rate:.2%}): supone una ventaja competitiva duradera; un "
                f"{basis.return_name} cercano al {rate_name} es más prudente a largo plazo"
            )
    else:
        multiple = options.multiple
        if multiple is None:
            raise ValueError(
                "Falta el múltiplo de salida para vt_mult: indícalo con --set exit_multiple= "
                'o [exit_multiple."TICKER"] en market_inputs.toml'
            )
        if multiple.value <= 0:
            raise ValueError(f"El múltiplo de salida debe ser positivo, recibido {multiple.value}")
        if basis.metric_last is None:
            raise ValueError(
                f"El modelo no dispone del {basis.metric_name} del año N para el múltiplo"
            )
        value = multiple.value * basis.metric_last

    implied = implied_growth(value, basis.last_flow, rate)
    if (
        method is not TerminalMethod.GORDON
        and abs(implied - g) > options.thresholds.implied_growth_gap
    ):
        warnings.append(
            f"El g implícito en el VT ({implied:.2%}) difiere {abs(implied - g) * 100:.2f} puntos "
            f"del g supuesto ({g:.2%}): el VT no encaja con el flujo del año N; revisa "
            f"{'el múltiplo' if method is TerminalMethod.MULTIPLE else f'el {basis.return_name}'}"
        )
    metric = basis.metric_last
    implied_multiple = value / metric if metric is not None and metric > 0 else None
    return TerminalValueResult(
        method=method,
        value=value,
        next_flow=next_flow,
        basis=dataclasses.replace(basis, multiple=options.multiple),
        implied_growth=implied,
        implied_multiple=implied_multiple,
        warnings=tuple(warnings),
    )


# VT como función de (tasa, g), para la sensibilidad y los escenarios.
def terminal_function(
    options: TerminalOptions, basis: TerminalBasis, risk_free_rate: float, rate_name: str
) -> Callable[[float, float], float]:
    """Devuelve el cálculo del VT con tasa y g variables.

    Args:
        options: Método, múltiplo, RONIC y umbrales.
        basis: Datos del año N del modelo.
        risk_free_rate: rf en decimal.
        rate_name: "WACC" o "Ke".

    Returns:
        Función (tasa, g) → VT en EUR.
    """

    def value(rate: float, growth: float) -> float:
        return terminal_value(options, basis, rate, growth, risk_free_rate, rate_name).value

    return value
