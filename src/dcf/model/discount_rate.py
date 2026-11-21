"""Tasa de descuento usada: la calculada (WACC o Ke) o la forzada por el usuario.

Precedencia: argumento ``--set rate`` > ``[discount_rate]`` de ``market_inputs.toml``
(primero la del ticker, después la general) > calculada. Función pura, sin I/O.
Tasas en decimal (0.08 = 8 %). Ver ``docs/metodologia.md`` §4.
"""

from __future__ import annotations

from dataclasses import dataclass

from dcf.model.cost_of_equity import MarketRate


# Tasa en decimal como porcentaje con 2 decimales y coma decimal (0.0863 → "8,63 %").
def _pct(value: float) -> str:
    return f"{value * 100:.2f} %".replace(".", ",")


@dataclass(frozen=True, slots=True)
class DiscountRateChoice:
    """Tasa con la que se descuentan los flujos y de dónde sale.

    Attributes:
        name: Nombre de la tasa en el modelo: "WACC" (FCFF) o "Ke" (FCFE).
        value: Tasa usada para descontar, en decimal: la rentabilidad mínima que se
            exige a los flujos (de todos los financiadores en FCFF, del accionista en FCFE).
        calculated: Tasa calculada a partir de sus componentes; ``None`` si no se pudo
            calcular (solo posible si está forzada).
        override: Tasa forzada por el usuario con su fuente y fecha; ``None`` si se usa
            la calculada.
        calculation_error: Motivo por el que no se pudo calcular; ``None`` si se calculó.
    """

    name: str
    value: float
    calculated: float | None
    override: MarketRate | None = None
    calculation_error: str | None = None

    # Indica si la tasa usada es la forzada por el usuario.
    @property
    def is_forced(self) -> bool:
        """``True`` si se descuenta con la tasa forzada y no con la calculada."""
        return self.override is not None

    # Texto del origen de la tasa para informes y avisos.
    def describe(self) -> str:
        """Describe el origen de la tasa usada.

        Returns:
            Texto como «forzada (argumento --set rate, 2026-11-21); WACC calculado 8,63 %».
        """
        if self.override is None:
            return f"{self.name} calculado"
        calc = (
            f"no calculable: {self.calculation_error}"
            if self.calculated is None
            else _pct(self.calculated)
        )
        return (
            f"{self.name} forzado ({self.override.source}, {self.override.date:%Y-%m-%d}); "
            f"calculado: {calc}"
        )


# Elige la tasa de descuento: la forzada si existe; si no, la calculada (error si no hay).
def choose_discount_rate(
    name: str,
    calculated: float | None,
    calculation_error: str | None,
    override: MarketRate | None,
) -> DiscountRateChoice:
    """Decide con qué tasa se descuenta.

    Args:
        name: "WACC" o "Ke".
        calculated: Tasa calculada en decimal; ``None`` si el cálculo falló.
        calculation_error: Motivo del fallo del cálculo, si lo hubo.
        override: Tasa forzada (argumento o fichero), ya resuelta por precedencia.

    Returns:
        Tasa elegida con su origen.

    Raises:
        ValueError: Si la tasa forzada no es positiva, o si no hay tasa forzada y el
            cálculo falló (se repite el motivo).
    """
    if override is not None:
        if override.value <= 0:
            raise ValueError(
                f"La tasa de descuento forzada debe ser positiva, recibido {override.value}"
            )
        return DiscountRateChoice(name, override.value, calculated, override, calculation_error)
    if calculated is None:
        raise ValueError(calculation_error or f"No se pudo calcular el {name}")
    return DiscountRateChoice(name, calculated, calculated)


# Avisos de la tasa: que está forzada y, si no se pudo calcular, por qué.
def rate_warnings(choice: DiscountRateChoice) -> tuple[str, ...]:
    """Genera los avisos de la tasa de descuento.

    Args:
        choice: Tasa elegida.

    Returns:
        Avisos (vacío si se usa la calculada).
    """
    if not choice.is_forced:
        return ()
    return (f"Tasa de descuento forzada al {_pct(choice.value)}: {choice.describe()}",)
