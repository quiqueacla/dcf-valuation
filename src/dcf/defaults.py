"""Supuestos por defecto del modelo. Único lugar para constantes del modelo.

Cada valor indica su fuente o el motivo de la elección.
"""

DEFAULT_PROJECTION_YEARS = 5
"""Horizonte de proyección en años. Motivo: decisión del usuario (2026-11-18)."""

ANALYST_ESTIMATE_YEARS = 2
"""Años proyectados (+1 ejercicio en curso, +2) que usan estimaciones de analistas.

Motivo: decisión del usuario (2026-11-18); Yahoo Finance publica consenso para el
ejercicio en curso y el siguiente.
"""

HISTORICAL_YEARS = 4
"""Ejercicios históricos que se toman de la fuente. Motivo: decisión del usuario (2026-11-18)."""

SENSITIVITY_WACC_STEP = 0.005
"""Paso del WACC en la tabla de sensibilidad (0,5 puntos). Motivo: granularidad habitual."""

SENSITIVITY_GROWTH_STEP = 0.005
"""Paso del g terminal en la tabla de sensibilidad (0,5 puntos). Motivo: granularidad habitual."""

SENSITIVITY_STEPS_EACH_SIDE = 2
"""Pasos a cada lado del valor central: tabla 5 × 5. Motivo: legible en un informe."""
