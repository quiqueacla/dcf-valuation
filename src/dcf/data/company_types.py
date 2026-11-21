"""Clasificación del tipo de empresa a partir del sector y la industria de la fuente.

La tabla de correspondencia está en ``config/company_types.toml``.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dcf.company import CompanyType, ValuationModel
from dcf.defaults import DEFAULT_VALUATION_MODEL

DEFAULT_COMPANY_TYPES_PATH = Path("config/company_types.toml")
"""Ubicación por defecto de la tabla de tipos (relativa a la raíz del repo)."""


@dataclass(frozen=True, slots=True)
class CompanyTypeRules:
    """Reglas para pasar de sector e industria de la fuente a tipo de empresa.

    Attributes:
        by_industry: Clave de industria (``industryKey`` de Yahoo) → tipo de empresa.
        by_sector: Clave de sector (``sectorKey`` de Yahoo) → tipo de empresa. Solo se
            usa si la industria no está en ``by_industry``.
        models: Modelo de valoración de cada tipo (clave ``model`` de su sección). Los
            tipos que no aparecen usan ``DEFAULT_VALUATION_MODEL`` (fcff_cfo).
    """

    by_industry: Mapping[str, CompanyType] = field(default_factory=dict)
    by_sector: Mapping[str, CompanyType] = field(default_factory=dict)
    models: Mapping[CompanyType, ValuationModel] = field(default_factory=dict)

    # Modelo de valoración para un tipo de empresa (o sin clasificar).
    def model_for(self, company_type: CompanyType | None) -> ValuationModel:
        """Devuelve el modelo de valoración que se aplica a un tipo de empresa.

        Args:
            company_type: Tipo de empresa; ``None`` si no se ha clasificado.

        Returns:
            El modelo de la tabla, o ``DEFAULT_VALUATION_MODEL`` si no lo indica.
        """
        default = ValuationModel(DEFAULT_VALUATION_MODEL)
        return default if company_type is None else self.models.get(company_type, default)


# Tipo de empresa: primero por industria, luego por sector; si no encaja, industrial.
def classify_company(
    sector_key: str | None, industry_key: str | None, rules: CompanyTypeRules
) -> CompanyType | None:
    """Clasifica la empresa según su sector e industria.

    Args:
        sector_key: Clave del sector de la fuente (p. ej. ``"financial-services"``).
        industry_key: Clave de la industria (p. ej. ``"banks-diversified"``).
        rules: Tabla de correspondencia.

    Returns:
        Tipo de empresa; ``industrial`` si no encaja con ninguna regla, o ``None`` si
        la fuente no publica ni sector ni industria (no se puede clasificar).
    """
    if not sector_key and not industry_key:
        return None
    if industry_key and industry_key in rules.by_industry:
        return rules.by_industry[industry_key]
    if sector_key and sector_key in rules.by_sector:
        return rules.by_sector[sector_key]
    return CompanyType.INDUSTRIAL


# Lee una lista de claves de texto de una sección; error claro si el tipo no es válido.
def _keys(table: dict[str, object], key: str, label: str, path: Path) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{path}: [{label}].{key} debe ser una lista de textos")
    return [v.strip().lower() for v in value]


# Lee config/company_types.toml y valida tipos y claves repetidas.
def load_company_type_rules(path: Path = DEFAULT_COMPANY_TYPES_PATH) -> CompanyTypeRules:
    """Carga la tabla de tipos de empresa.

    Args:
        path: Fichero TOML con una sección por tipo (``[banco]``, ``[aseguradora]``,
            ``[inmobiliaria]``), listas ``industries`` y ``sectors`` y, opcional, el
            modelo de valoración ``model`` (``fcff_cfo`` o ``fcfe``).

    Returns:
        Reglas de clasificación.

    Raises:
        FileNotFoundError: Si el fichero no existe.
        ValueError: Si hay un tipo desconocido, claves no válidas o una misma
            industria o sector en dos tipos.
    """
    if not path.is_file():
        raise FileNotFoundError(f"No existe la tabla de tipos de empresa {path}")
    with path.open("rb") as f:
        data = tomllib.load(f)

    valid = {t.value for t in CompanyType if t is not CompanyType.INDUSTRIAL}
    valid_models = sorted(m.value for m in ValuationModel)
    by_industry: dict[str, CompanyType] = {}
    by_sector: dict[str, CompanyType] = {}
    models: dict[CompanyType, ValuationModel] = {}
    for name, table in data.items():
        if name not in valid or not isinstance(table, dict):
            raise ValueError(f"{path}: sección [{name}] no válida; usa {sorted(valid)}")
        unknown = sorted(set(table) - {"industries", "sectors", "model"})
        if unknown:
            raise ValueError(f"{path}: claves desconocidas {unknown} en [{name}]")
        company_type = CompanyType(name)
        if "model" in table:
            if table["model"] not in valid_models:
                raise ValueError(
                    f"{path}: [{name}].model = {table['model']!r} no válido; usa {valid_models}"
                )
            models[company_type] = ValuationModel(table["model"])
        for key, target in (("industries", by_industry), ("sectors", by_sector)):
            for item in _keys(table, key, name, path):
                if item in target and target[item] is not company_type:
                    raise ValueError(
                        f"{path}: '{item}' aparece en [{target[item].value}] y en [{name}]"
                    )
                target[item] = company_type
    return CompanyTypeRules(by_industry=by_industry, by_sector=by_sector, models=models)
