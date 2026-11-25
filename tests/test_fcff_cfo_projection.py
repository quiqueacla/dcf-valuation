"""Proyección sobre el fixture sintético, valores calculados a mano (tolerancia relativa 1e-9).

Con analistas (1450, 1550): g+1 = 1450/1331 − 1 = 8,94065 %, g+2 = 1550/1450 − 1 = 6,89655 %.
Crecimiento +3..+5 = mediana de {10 %, 10 %, 10 %, g+1, g+2} = 10 %.
FCFF/NI = mediana 1,0650826 (ver test_fcff_cfo_ratios).
"""

import dataclasses

import pytest

from dcf.company import Company, RevenueEstimate
from dcf.model.fcff_cfo_projection import project_cash_flows
from dcf.model.fcff_cfo_ratios import compute_historical_ratios
from dcf.model.revenue_projection import RevenueSource

REL = 1e-9
AVG_C = 1.0650826446280992
G1 = 0.0894064613072878
G2 = 0.06896551724137923
AVG_G = 0.10


def test_con_estimaciones_de_analistas(company: Company) -> None:
    p = project_cash_flows(company, compute_historical_ratios(company), 5)
    assert [f.fiscal_year for f in p.flows] == [2026, 2027, 2028, 2029, 2030]
    assert [f.revenue_source for f in p.flows] == [RevenueSource.ANALYST_ESTIMATE] * 2 + [
        RevenueSource.AVERAGE_GROWTH
    ] * 3
    assert p.projection_growth == pytest.approx(AVG_G, rel=REL)
    assert [f.revenue_growth for f in p.flows] == pytest.approx(
        [G1, G2, AVG_G, AVG_G, AVG_G], rel=REL
    )
    assert [f.revenue for f in p.flows] == pytest.approx(
        [1450.0, 1550.0, 1550 * 1.1, 1550 * 1.1**2, 1550 * 1.1**3], rel=REL
    )
    assert p.flows[0].net_income == pytest.approx(145.0, rel=REL)
    assert p.flows[0].fcff == pytest.approx(145.0 * AVG_C, rel=REL)
    assert p.flows[-1].fcff == pytest.approx(155.0 * 1.1**3 * AVG_C, rel=REL)


def test_sin_estimaciones_usa_crecimiento_historico(company: Company) -> None:
    c = dataclasses.replace(company, revenue_estimates=())
    p = project_cash_flows(c, compute_historical_ratios(c), 5)
    assert p.projection_growth == pytest.approx(0.10, rel=REL)
    assert all(f.revenue_source is RevenueSource.AVERAGE_GROWTH for f in p.flows)
    assert [f.revenue for f in p.flows] == pytest.approx(
        [1331.0 * 1.1**k for k in range(1, 6)], rel=REL
    )


def test_con_una_sola_estimacion(company: Company) -> None:
    c = dataclasses.replace(company, revenue_estimates=(RevenueEstimate(2026, 1450.0),))
    p = project_cash_flows(c, compute_historical_ratios(c), 5)
    assert p.projection_growth == pytest.approx(0.10, rel=REL)  # mediana de {10 % × 3, g+1}
    assert p.flows[0].revenue_source is RevenueSource.ANALYST_ESTIMATE
    assert p.flows[1].revenue == pytest.approx(1450.0 * 1.1, rel=REL)


def test_rechaza_horizonte_no_positivo(company: Company) -> None:
    with pytest.raises(ValueError, match="projection_years"):
        project_cash_flows(company, compute_historical_ratios(company), 0)
