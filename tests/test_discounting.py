"""Comprobación del valor descontado positivo (VE o fondos propios)."""

import pytest

from dcf.valuation.discounting import require_positive_value


def test_valor_positivo_no_falla() -> None:
    require_positive_value("Valor de empresa", 1.0, -5.0, 6.0, "FCFF")


# El mensaje lleva el desglose en millones y la sugerencia.
def test_valor_negativo_con_desglose_y_sugerencia() -> None:
    with pytest.raises(ValueError) as exc:
        require_positive_value("Valor de empresa", -3e6, -1e6, -2e6, "FCFF", "prueba --model x")
    message = str(exc.value)
    assert message.startswith("Valor de empresa negativo o nulo (-3.0 M EUR)")
    assert "FCFF proyectados -1.0 M EUR y del valor terminal -2.0 M EUR" in message
    assert message.endswith("; prueba --model x")


def test_valor_nulo_sin_sugerencia() -> None:
    with pytest.raises(ValueError, match="con este modelo$"):
        require_positive_value("Fondos propios", 0.0, 0.0, 0.0, "FCFE")
