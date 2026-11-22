"""Tipo de empresa: tabla de config/company_types.toml y clasificación (sin red)."""

import dataclasses
from pathlib import Path

import pytest

from dcf.company import CompanyType, TerminalMethod, ValuationModel, model_suitability_warning
from dcf.data.company_types import (
    CompanyTypeRules,
    classify_company,
    load_company_type_rules,
)
from dcf.data.yahoo import YahooRawData, build_company
from tests.test_yahoo import _raw

REPO_TABLE = Path(__file__).parents[1] / "config/company_types.toml"


@pytest.fixture
def rules() -> CompanyTypeRules:
    return load_company_type_rules(REPO_TABLE)


# Claves reales de Yahoo comprobadas el 2026-11-19 (ver config/company_types.toml).
@pytest.mark.parametrize(
    ("sector", "industry", "expected"),
    [
        ("financial-services", "banks-diversified", CompanyType.BANK),  # SAN.MC, JPM
        ("financial-services", "banks-regional", CompanyType.BANK),  # CABK.MC
        ("financial-services", "insurance-diversified", CompanyType.INSURANCE),  # MAP.MC
        ("real-estate", "reit-office", CompanyType.REAL_ESTATE),  # MRL.MC
        ("real-estate", "reit-retail", CompanyType.REAL_ESTATE),  # O
        ("energy", "oil-gas-integrated", CompanyType.INDUSTRIAL),  # REP.MC
        ("technology", "consumer-electronics", CompanyType.INDUSTRIAL),  # AAPL
        ("financial-services", "insurance-brokers", CompanyType.INDUSTRIAL),  # corredores
        ("financial-services", "asset-management", CompanyType.INDUSTRIAL),
        (None, "banks-regional", CompanyType.BANK),
        ("real-estate", None, CompanyType.REAL_ESTATE),
    ],
)
def test_clasificacion_con_la_tabla_del_repo(
    rules: CompanyTypeRules, sector: str | None, industry: str | None, expected: CompanyType
) -> None:
    assert classify_company(sector, industry, rules) is expected


def test_sin_sector_ni_industria_no_se_clasifica(rules: CompanyTypeRules) -> None:
    assert classify_company(None, None, rules) is None


def test_industria_prevalece_sobre_sector() -> None:
    r = CompanyTypeRules(
        by_industry={"x-ind": CompanyType.BANK}, by_sector={"x-sec": CompanyType.REAL_ESTATE}
    )
    assert classify_company("x-sec", "x-ind", r) is CompanyType.BANK


def _table(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "types.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ('[industrial]\nsectors = ["energy"]\n', "industrial"),
        ('[fondo]\nsectors = ["x"]\n', "fondo"),
        ('[banco]\nindustrias = ["x"]\n', "desconocidas"),
        ('[banco]\nindustries = "banks-regional"\n', "lista"),
        ('[banco]\nsectors = ["x"]\n[aseguradora]\nsectors = ["x"]\n', "aparece en"),
    ],
)
def test_tabla_invalida(tmp_path: Path, text: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        load_company_type_rules(_table(tmp_path, text))


def test_tabla_inexistente(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_company_type_rules(tmp_path / "no.toml")


def test_claves_en_minusculas(tmp_path: Path) -> None:
    r = load_company_type_rules(_table(tmp_path, '[banco]\nindustries = [" Banks-Regional "]\n'))
    assert r.by_industry == {"banks-regional": CompanyType.BANK}


def test_build_company_guarda_sector_industria_y_tipo(rules: CompanyTypeRules) -> None:
    c = build_company(_raw(), type_rules=rules)
    assert c.info.sector == "Technology"
    assert c.info.industry == "Consumer Electronics"
    assert c.info.company_type is CompanyType.INDUSTRIAL


def test_build_company_banco(rules: CompanyTypeRules) -> None:
    raw = _raw()
    info = {
        **raw.info,
        "sector": "Financial Services",
        "sectorKey": "financial-services",
        "industry": "Banks - Diversified",
        "industryKey": "banks-diversified",
    }
    c = build_company(dataclasses.replace(raw, info=info), type_rules=rules)
    assert c.info.company_type is CompanyType.BANK
    assert c.info.valuation_model is ValuationModel.FCFE_FIN
    assert c.debt_cost_data == ()  # FCFE no usa coste de la deuda
    assert c.historicals[-1].stockholders_equity == pytest.approx(610.0 * 0.9)


def test_tabla_del_repo_asigna_modelos(rules: CompanyTypeRules) -> None:
    assert rules.model_for(CompanyType.BANK) is ValuationModel.FCFE_FIN
    assert rules.model_for(CompanyType.INSURANCE) is ValuationModel.FCFE_FIN
    assert rules.model_for(CompanyType.REAL_ESTATE) is ValuationModel.FCFF
    assert rules.model_for(CompanyType.INDUSTRIAL) is ValuationModel.FCFF
    assert rules.model_for(None) is ValuationModel.FCFF
    assert rules.terminal_for(CompanyType.BANK) is TerminalMethod.GORDON
    assert rules.terminal_for(CompanyType.INSURANCE) is TerminalMethod.GORDON
    assert rules.terminal_for(CompanyType.INDUSTRIAL) is TerminalMethod.VALUE_DRIVER
    assert rules.terminal_for(CompanyType.REAL_ESTATE) is TerminalMethod.VALUE_DRIVER
    assert rules.terminal_for(None) is TerminalMethod.VALUE_DRIVER


def test_modelo_forzado_prevalece_sobre_la_tabla(rules: CompanyTypeRules) -> None:
    c = build_company(_raw(), type_rules=rules, model=ValuationModel.FCFE_FIN)
    assert c.info.company_type is CompanyType.INDUSTRIAL
    assert c.info.valuation_model is ValuationModel.FCFE_FIN


def test_modelo_invalido_en_la_tabla(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model"):
        load_company_type_rules(_table(tmp_path, '[banco]\nmodel = "ddm"\n'))


def test_build_company_sin_sector_avisa(rules: CompanyTypeRules) -> None:
    raw = _raw()
    info = {k: v for k, v in raw.info.items() if not k.startswith(("sector", "industry"))}
    c = build_company(dataclasses.replace(raw, info=info), type_rules=rules)
    assert c.info.company_type is None and c.info.sector is None
    assert any("sin clasificar" in w for w in c.info.data_warnings)


def test_build_company_sin_tabla_no_clasifica() -> None:
    c = build_company(_raw())
    assert c.info.company_type is None
    assert c.info.sector == "Technology"
    assert not any("sin clasificar" in w for w in c.info.data_warnings)


@pytest.mark.parametrize(
    ("kind", "model"),
    [
        (CompanyType.INDUSTRIAL, ValuationModel.FCFF_CFO),
        (CompanyType.BANK, ValuationModel.FCFE_FIN),
        (CompanyType.INSURANCE, ValuationModel.FCFE_FIN),
    ],
)
def test_sin_aviso_si_el_modelo_es_adecuado(kind: CompanyType, model: ValuationModel) -> None:
    assert model_suitability_warning(kind, model) is None


@pytest.mark.parametrize(
    ("kind", "model", "text"),
    [
        (CompanyType.BANK, ValuationModel.FCFF_CFO, "usa el modelo fcfe"),
        (CompanyType.INSURANCE, ValuationModel.FCFF_CFO, "usa el modelo fcfe"),
        (CompanyType.INDUSTRIAL, ValuationModel.FCFE_FIN, "usa fcff o fcfe"),
        (CompanyType.REAL_ESTATE, ValuationModel.FCFF_CFO, "NAV"),
        (CompanyType.REAL_ESTATE, ValuationModel.FCFE_FIN, "NAV"),
    ],
)
def test_aviso_si_el_modelo_no_es_adecuado(
    kind: CompanyType, model: ValuationModel, text: str
) -> None:
    warning = model_suitability_warning(kind, model)
    assert warning is not None and kind.value in warning and model.value in warning
    assert text in warning


def test_aviso_sin_clasificar() -> None:
    warning = model_suitability_warning(None, ValuationModel.FCFF_CFO)
    assert warning is not None and "sin clasificar" in warning


def _bank(raw: YahooRawData) -> YahooRawData:
    info = {**raw.info, "sectorKey": "financial-services", "industryKey": "banks-diversified"}
    return dataclasses.replace(raw, info=info)


def test_banco_sin_ebit_se_carga_con_fcfe(rules: CompanyTypeRules) -> None:
    raw = _bank(_raw())
    income = raw.income_stmt.drop(index="EBIT")  # los bancos no publican EBIT
    cash_row = "Cash Cash Equivalents And Short Term Investments"
    balance = raw.balance_sheet.drop(index=cash_row)
    c = build_company(
        dataclasses.replace(raw, income_stmt=income, balance_sheet=balance), type_rules=rules
    )
    assert c.info.valuation_model is ValuationModel.FCFE_FIN
    assert c.balance.cash is None


def test_banco_sin_fondos_propios_es_error(rules: CompanyTypeRules) -> None:
    raw = _bank(_raw())
    balance = raw.balance_sheet.drop(index="Stockholders Equity")
    with pytest.raises(ValueError, match="Stockholders Equity"):
        build_company(dataclasses.replace(raw, balance_sheet=balance), type_rules=rules)


def test_error_de_carga_indica_si_el_modelo_no_es_adecuado(rules: CompanyTypeRules) -> None:
    raw = _bank(_raw())
    income = raw.income_stmt.drop(index="EBIT")
    with pytest.raises(ValueError, match="EBIT.*Empresa de tipo banco.*fcff"):
        build_company(
            dataclasses.replace(raw, income_stmt=income),
            type_rules=rules,
            model=ValuationModel.FCFF_CFO,
        )


def test_error_de_carga_industrial_sin_cambios(rules: CompanyTypeRules) -> None:
    raw = _raw()
    income = raw.income_stmt.drop(index="EBIT")
    with pytest.raises(ValueError) as exc:
        build_company(dataclasses.replace(raw, income_stmt=income), type_rules=rules)
    assert "tipo" not in str(exc.value)
