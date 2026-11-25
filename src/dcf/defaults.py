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

DEFAULT_VALUATION_MODEL = "fcff"
"""Modelo por defecto (industriales y tipos sin ``model`` ni sección ``[default]``).

Motivo: FCFF desde el EBIT (``docs/dcf_metodos.md`` §1.1), caso general; elección del
usuario (2026-11-21).
"""

DEFAULT_TERMINAL_METHOD = "gordon_value_driver"
"""Valor terminal por defecto: Gordon con value driver (``docs/dcf_metodos.md`` §3.3).

Motivo: obliga a pagar la reinversión que sostiene g; elección del usuario (2026-11-21).
"""

LAST_FLOW_DEVIATION = 0.33
"""Aviso si el último flujo histórico se desvía más de un 33 % de la media de los anteriores.

Motivo: alertar de una valoración apoyada en un año puntual; elección del usuario
(2026-11-21). Se puede cambiar en ``config/thresholds.toml``.
"""

IMPLIED_GROWTH_GAP = 0.0075
"""Aviso si el g implícito en el valor terminal difiere más de 0,75 puntos del g supuesto.

Motivo: comprobación de consistencia del VT; elección del usuario (2026-11-21).
"""

RONIC_TO_RATE = 2.0
"""Aviso si el RONIC (o ROE) del value driver supera 2 veces la tasa de descuento.

Motivo: la ventaja competitiva tiende a erosionarse; un RONIC muy superior a la tasa
infla el VT. Elección del usuario (2026-11-21).
"""

DEFAULT_BETA_MODE = "bottom-up"
"""Modo de beta si ``market_inputs.toml`` no indica ``[beta].mode``.

Motivo: la beta de regresión de Yahoo es ruidosa (p. ej. REP.MC −0,181, CABK.MC 0,12);
una beta sectorial reapalancada es más estable. Elección del usuario (2026-11-24).
"""

BLUME_WEIGHT = 0.67
"""Peso de la beta de regresión en el ajuste de Blume: β_aj = 0,67 · β + 0,33 · 1.

Fuente: Blume (1971), «On the assessment of risk»; es la beta ajustada que publica
Bloomberg. Se usa cuando no hay beta sectorial para la industria de la empresa.
"""

KE_FLOOR_BETA = 1.0
"""Beta del suelo de Ke: Ke ≥ rf + 1 · PRM + prima de riesgo país.

Motivo: ninguna acción debería exigir menos que el mercado de su país; elección del
usuario (2026-11-24).
"""

SCENARIO_GROWTH_GAP = 0.01
"""Un escenario bajista o alcista se excluye si su g implícito difiere más de 1 punto del g.

Motivo: elección del usuario (2026-11-24). La valoración central no se excluye: solo avisa.
Se puede cambiar en ``config/thresholds.toml`` (``scenario_growth_gap``).
"""
