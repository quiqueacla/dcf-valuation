"""Caso de referencia calculado a mano sobre el fixture sintético (tolerancia relativa 1e-9).

Ventas 1000, 1100, 1210, 1331 → crecimiento 10 % cada año. Margen neto 10 %.
t = 35 / 140 = 25 %. FCFF = 0,15·R + 10·(1 − 0,25) − 0,05·R = 0,10·R + 7,5.
FCFF/NI = 1 + 75/R → 1,075; 1,0681818; 1,0619835; 1,0563486 → mediana
(1,0681818 + 1,0619835) / 2 = 1 + 37,5 · (1/1100 + 1/1210) = 1,0650826.
"""

import dataclasses

import pytest

from dcf.company import Company
from dcf.model.fcff_cfo_ratios import compute_historical_ratios, historical_fcff
from dcf.model.tax import effective_tax_rate

REL = 1e-9


def test_caso_referencia(company: Company) -> None:
    r = compute_historical_ratios(company)
    assert r.revenue_growth_by_year == pytest.approx({2023: 0.10, 2024: 0.10, 2025: 0.10}, rel=REL)
    assert r.average_revenue_growth == pytest.approx(0.10, rel=REL)
    assert r.average_net_margin == pytest.approx(0.10, rel=REL)
    assert r.tax_rate_by_year == pytest.approx({y: 0.25 for y in range(2022, 2026)}, rel=REL)
    assert r.fcff_by_year[2022] == pytest.approx(107.5, rel=REL)
    assert r.fcff_by_year[2025] == pytest.approx(140.6, rel=REL)
    assert r.fcff_to_net_income_by_year[2022] == pytest.approx(1.075, rel=REL)
    assert r.average_fcff_to_net_income == pytest.approx(1 + 37.5 * (1 / 1100 + 1 / 1210), rel=REL)
    assert r.warnings == ()


def test_historical_fcff(company: Company) -> None:
    # CFO 150 + 10·(1 − 0,25) − Capex 50 = 107,5
    assert historical_fcff(company.historicals[0], 0.25) == pytest.approx(107.5, rel=REL)


@pytest.mark.parametrize(("pretax", "provision"), [(0.0, 0.0), (-100.0, 10.0)])
def test_tax_rate_bai_no_positivo(company: Company, pretax: float, provision: float) -> None:
    d = dataclasses.replace(
        company.debt_cost_data[0], pretax_income=pretax, tax_provision=provision
    )
    rate, reason = effective_tax_rate(d)
    assert rate is None
    assert reason is not None and "BAI" in reason


@pytest.mark.parametrize("provision", [-10.0, 150.0])
def test_tax_rate_fuera_de_rango(company: Company, provision: float) -> None:
    d = dataclasses.replace(company.debt_cost_data[0], pretax_income=100.0, tax_provision=provision)
    rate, reason = effective_tax_rate(d)
    assert rate is None
    assert reason is not None and "fuera" in reason


def test_excluye_ano_con_bai_negativo(company: Company) -> None:
    debt = list(company.debt_cost_data)
    debt[0] = dataclasses.replace(debt[0], pretax_income=-50.0, tax_provision=0.0)
    r = compute_historical_ratios(dataclasses.replace(company, debt_cost_data=tuple(debt)))
    assert 2022 not in r.fcff_to_net_income_by_year
    assert 2022 not in r.tax_rate_by_year
    expected = 1.06198347107438  # mediana de los tres años válidos
    assert r.average_fcff_to_net_income == pytest.approx(expected, rel=REL)
    assert len(r.warnings) == 1 and "2022" in r.warnings[0] and "BAI" in r.warnings[0]


def test_excluye_ano_con_perdidas_pero_lo_mantiene_en_margen(company: Company) -> None:
    hist = list(company.historicals)
    hist[1] = dataclasses.replace(hist[1], net_income=-55.0)
    r = compute_historical_ratios(dataclasses.replace(company, historicals=tuple(hist)))
    assert 2023 not in r.fcff_to_net_income_by_year
    assert 2023 in r.fcff_by_year
    assert r.net_margin_by_year[2023] == pytest.approx(-0.05, rel=REL)
    assert r.average_net_margin == pytest.approx(0.10, rel=REL)  # mediana: el −5 % no la mueve
    assert "Net Income" in r.warnings[0]


def test_error_si_ningun_ano_valido(company: Company) -> None:
    hist = tuple(dataclasses.replace(h, net_income=-1.0) for h in company.historicals)
    with pytest.raises(ValueError, match="Ningún ejercicio"):
        compute_historical_ratios(dataclasses.replace(company, historicals=hist))


def test_error_si_faltan_datos_de_impuestos(company: Company) -> None:
    with pytest.raises(ValueError, match="Faltan datos de impuestos"):
        compute_historical_ratios(
            dataclasses.replace(company, debt_cost_data=company.debt_cost_data[1:])
        )
