"""Clasificación del tipo de empresa y elección de modelo + valor terminal por tipo.

La tabla de correspondencia está en ``config/company_types.toml``.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dcf.company import CompanyType, TerminalMethod, ValuationModel
from dcf.defaults import DEFAULT_TERMINAL_METHOD, DEFAULT_VALUATION_MODEL

DEFAULT_COMPANY_TYPES_PATH = Path("config/company_types.toml")
"""Ubicación por defecto de la tabla de tipos (relativa a la raíz del repo)."""

DEFAULT_SECTION = "default"
"""Sección con el modelo y el VT de los tipos que no los indican (industriales incluidos)."""


@dataclass(frozen=True, slots=True)
class CompanyTypeRules:
    """Reglas para pasar de sector e industria a tipo de empresa, modelo y VT.

    Attributes:
        by_industry: Clave de industria (``industryKey`` de Yahoo) → tipo de empresa.
        by_sector: Clave de sector (``sectorKey`` de Yahoo) → tipo de empresa. Solo se
            usa si la industria no está en ``by_industry``.
        models: Modelo de valoración de cada tipo (clave ``model`` de su sección).
        terminal_methods: Método de VT de cada tipo (clave ``vt`` de su sección).
        default_model: Modelo de los tipos sin ``model`` (sección ``[default]`` o
            ``DEFAULT_VALUATION_MODEL``).
        default_terminal: VT de los tipos sin ``vt`` (sección ``[default]`` o
            ``DEFAULT_TERMINAL_METHOD``).
    """

    by_industry: Mapping[str, CompanyType] = field(default_factory=dict)
    by_sector: Mapping[str, CompanyType] = field(default_factory=dict)
    models: Mapping[CompanyType, ValuationModel] = field(default_factory=dict)
    terminal_methods: Mapping[CompanyType, TerminalMethod] = field(default_factory=dict)
    default_model: ValuationModel = ValuationModel(DEFAULT_VALUATION_MODEL)
    default_terminal: TerminalMethod = TerminalMethod(DEFAULT_TERMINAL_METHOD)

    # Modelo de valoración para un tipo de empresa (o sin clasificar).
    def model_for(self, company_type: CompanyType | None) -> ValuationModel:
        """Devuelve el modelo de valoración que se aplica a un tipo de empresa.

        Args:
            company_type: Tipo de empresa; ``None`` si no se ha clasificado.

        Returns:
            El modelo de la tabla, o el de ``[default]`` si no lo indica.
        """
        if company_type is None:
            return self.default_model
        return self.models.get(company_type, self.default_model)

    # Método de valor terminal para un tipo de empresa (o sin clasificar).
    def terminal_for(self, company_type: CompanyType | None) -> TerminalMethod:
        """Devuelve el método de valor terminal que se aplica a un tipo de empresa.

        Args:
            company_type: Tipo de empresa; ``None`` si no se ha clasificado.

        Returns:
            El VT de la tabla, o el de ``[default]`` si no lo indica.
        """
        if company_type is None:
            return self.default_terminal
        return self.terminal_methods.get(company_type, self.default_terminal)


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


# Valor de un enum leído del TOML, con error claro si no es válido.
def _enum_value[E: (ValuationModel, TerminalMethod)](
    enum: type[E], table: dict[str, Any], key: str, label: str, path: Path
) -> E | None:
    if key not in table:
        return None
    valid = sorted(m.value for m in enum)
    if table[key] not in valid:
        raise ValueError(f"{path}: [{label}].{key} = {table[key]!r} no válido; usa {valid}")
    return enum(table[key])


# Lee config/company_types.toml y valida tipos, modelos, VT y claves repetidas.
def load_company_type_rules(path: Path = DEFAULT_COMPANY_TYPES_PATH) -> CompanyTypeRules:
    """Carga la tabla de tipos de empresa.

    Args:
        path: Fichero TOML con una sección por tipo (``[banco]``, ``[aseguradora]``,
            ``[inmobiliaria]``), listas ``industries`` y ``sectors`` y, opcionales, el
            modelo ``model`` (fcff, fcff_cfo, fcfe, fcfe_fin) y el VT ``vt`` (gordon,
            gordon_value_driver, vt_mult). La sección ``[default]`` (solo ``model`` y
            ``vt``) aplica a industriales y a los tipos que no los indican.

    Returns:
        Reglas de clasificación y de elección de modelo y VT.

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
    by_industry: dict[str, CompanyType] = {}
    by_sector: dict[str, CompanyType] = {}
    models: dict[CompanyType, ValuationModel] = {}
    terminals: dict[CompanyType, TerminalMethod] = {}
    default_model = ValuationModel(DEFAULT_VALUATION_MODEL)
    default_terminal = TerminalMethod(DEFAULT_TERMINAL_METHOD)
    for name, table in data.items():
        if not isinstance(table, dict) or name not in valid | {DEFAULT_SECTION}:
            raise ValueError(
                f"{path}: sección [{name}] no válida; usa {sorted(valid | {DEFAULT_SECTION})}"
            )
        if name == DEFAULT_SECTION:
            unknown = sorted(set(table) - {"model", "vt"})
            if unknown:
                raise ValueError(f"{path}: claves desconocidas {unknown} en [{name}]")
            default_model = _enum_value(ValuationModel, table, "model", name, path) or default_model
            default_terminal = (
                _enum_value(TerminalMethod, table, "vt", name, path) or default_terminal
            )
            continue
        unknown = sorted(set(table) - {"industries", "sectors", "model", "vt"})
        if unknown:
            raise ValueError(f"{path}: claves desconocidas {unknown} en [{name}]")
        company_type = CompanyType(name)
        model = _enum_value(ValuationModel, table, "model", name, path)
        if model is not None:
            models[company_type] = model
        terminal = _enum_value(TerminalMethod, table, "vt", name, path)
        if terminal is not None:
            terminals[company_type] = terminal
        for key, target in (("industries", by_industry), ("sectors", by_sector)):
            for item in _keys(table, key, name, path):
                if item in target and target[item] is not company_type:
                    raise ValueError(
                        f"{path}: '{item}' aparece en [{target[item].value}] y en [{name}]"
                    )
                target[item] = company_type
    return CompanyTypeRules(
        by_industry=by_industry,
        by_sector=by_sector,
        models=models,
        terminal_methods=terminals,
        default_model=default_model,
        default_terminal=default_terminal,
    )
