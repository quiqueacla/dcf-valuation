import math

import pytest

from dcf.defaults import DEFAULT_PROJECTION_YEARS
from dcf.model.assumptions import Assumptions


def test_assumptions_validas_con_horizonte_por_defecto() -> None:
    a = Assumptions(terminal_growth=0.02)
    assert a.projection_years == DEFAULT_PROJECTION_YEARS == 5


@pytest.mark.parametrize("g", [math.nan, math.inf])
def test_rechaza_crecimiento_no_finito(g: float) -> None:
    with pytest.raises(ValueError, match="terminal_growth"):
        Assumptions(terminal_growth=g)


def test_rechaza_horizonte_menor_que_anos_de_analistas() -> None:
    with pytest.raises(ValueError, match="projection_years"):
        Assumptions(terminal_growth=0.02, projection_years=1)
