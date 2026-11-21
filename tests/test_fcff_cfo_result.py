import dataclasses
from datetime import UTC, datetime

import pandas as pd
import pytest

from dcf.company import Company
from dcf.model.assumptions import Assumptions
from dcf.model.cost_of_equity import MarketInputs
from dcf.model.discount_rate import choose_discount_rate
from dcf.model.fcff_cfo_ratios import HistoricalRatios
from dcf.model.revenue_projection import RevenueSource
from dcf.model.wacc import compute_wacc
from dcf.valuation.fcff_cfo_result import FcffCfoProjectedYear, FcffCfoValuationResult

NOW = datetime(2026, 11, 18, tzinfo=UTC)


@pytest.fixture
def base(company: Company, market_inputs: MarketInputs) -> dict[str, object]:
    projections = (
        FcffCfoProjectedYear(
            2026, 1100.0, 0.10, RevenueSource.ANALYST_ESTIMATE, 110.0, 100.0, 1 / 1.1, 100 / 1.1
        ),
        FcffCfoProjectedYear(
            2027, 1210.0, 0.10, RevenueSource.AVERAGE_GROWTH, 121.0, 110.0, 1 / 1.21, 110 / 1.21
        ),
    )
    return {
        "ticker": "TEST",
        "source": "fixture",
        "data_date": NOW,
        "valuation_date": NOW,
        "code_version": "0.1.0",
        "assumptions": Assumptions(terminal_growth=0.02, projection_years=2),
        "ratios": HistoricalRatios({}, {}, {}, {}, {}, 0.10, 0.10, 0.9, ()),
        "wacc": compute_wacc(company, market_inputs),  # WACC 8,125 %, rf 3 %
        "discount_rate": choose_discount_rate("WACC", 0.08125, None, None),
        "market_inputs": market_inputs,
        "projections": projections,
        "projection_growth": 0.10,
        "terminal_value": 1402.5,
        "terminal_value_present": 1402.5 / 1.21,
        "enterprise_value": 200.0 + 1402.5 / 1.21,
        "equity_value": 1000.0,
        "value_per_share": 10.0,
        "sensitivity": pd.DataFrame(),
    }


def _result(base: dict[str, object], **overrides: object) -> FcffCfoValuationResult:
    return FcffCfoValuationResult(**{**base, **overrides})  # type: ignore[arg-type]


def test_peso_valor_terminal(base: dict[str, object]) -> None:
    r = _result(base)
    assert r.terminal_value_weight == pytest.approx((1402.5 / 1.21) / (200.0 + 1402.5 / 1.21))


def test_rechaza_horizonte_incoherente(base: dict[str, object]) -> None:
    r = _result(base)
    with pytest.raises(ValueError, match="años proyectados"):
        dataclasses.replace(r, projections=r.projections[:1])


def test_rechaza_fecha_sin_zona(base: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="valuation_date"):
        _result(base, valuation_date=datetime(2026, 11, 18))


def test_rechaza_valor_empresa_no_positivo(base: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="enterprise_value"):
        _result(base, enterprise_value=0.0)


@pytest.mark.parametrize("g", [0.08125, 0.09])
def test_rechaza_g_mayor_o_igual_que_wacc(base: dict[str, object], g: float) -> None:
    with pytest.raises(ValueError, match="WACC"):
        _result(base, assumptions=Assumptions(terminal_growth=g, projection_years=2))


@pytest.mark.parametrize("g", [0.03, 0.05])
def test_rechaza_g_mayor_o_igual_que_rf(base: dict[str, object], g: float) -> None:
    with pytest.raises(ValueError, match="rf"):
        _result(base, assumptions=Assumptions(terminal_growth=g, projection_years=2))
