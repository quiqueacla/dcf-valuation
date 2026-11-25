# CLAUDE.md

Instrucciones persistentes para Claude Code en este repositorio. Mantén este archivo corto y concreto: solo lo que el agente no puede deducir del código.

## 1. Proyecto

- **Nombre:** dcf_valuation (paquete `dcf`)
- **Qué hace:** valoración de empresas por flujos de caja descontados (DCF) a partir de datos de mercado y de estados financieros.
- **Python:** 3.12, gestionado con uv.
- **Idioma de comentarios y documentación:** español
- **Moneda de trabajo:** EUR. Todos los importes se expresan en esta moneda; convierte y documenta cualquier otra.

## 2. Estructura del repositorio

```
src/dcf/
  data/        # Descarga y normalización de datos (Yahoo Finance, CSV, etc.)
  model/       # Proyección de flujos, WACC, valor terminal
  valuation/   # Cálculo del valor intrínseco por acción y sensibilidades
  reports/     # Salidas: tablas, gráficos, informes
config/        # Para configuraciones del modo de la aplicación (fuentes de datos defecto, modelo aplicado por defecto)
config/data    # Para datos que no se descarguen de internet (seria otra fuente de datos)
tests/         # pytest; fixtures con datos congelados, sin llamadas de red
notebooks/     # Exploración. No contiene lógica que no esté también en src/
data/cache/    # Respuestas descargadas. No editar a mano
```

## 3. Comandos clave

| Acción | Comando |
|---|---|
| Instalar dependencias | `uv sync` |
| Ejecutar tests | `uv run pytest -q` |
| Valorar un ticker | `uv run python -m dcf <TICKER> [--g 0.02] [--from-cache data/cache/<TICKER>/<fecha>]` |
| Lint y tipos | `uv run ruff check . && uv run mypy src` |
| Formato | `uv run ruff format .` |

## 4. Reglas de trabajo del agente

1. **Lee antes de editar.** Revisa el módulo y sus tests antes de proponer cambios.
2. **Cambios mínimos.** No reorganices módulos ni cambies nombres públicos sin pedirlo.
3. **Tests sin red.** Los tests usan fixtures congelados. Nunca llames a Yahoo Finance ni a otra API desde `tests/`.
4. **No inventes datos financieros.** Cifras de balances, tasas o betas se obtienen de la fuente o de un fichero de entrada, nunca de memoria. Si falta un dato, falla con un error claro en lugar de usar un valor por defecto silencioso.
5. **Secretos fuera del código.** Claves de API en variables de entorno o `.env` (que está en `.gitignore`). Nunca las imprimas en logs ni en respuestas.
6. **Pregunta antes de actuar** si hay ambigüedad en supuestos del modelo (crecimiento, WACC, horizonte) o en cambios que afecten a resultados ya publicados.
7. **Git:** no hagas commit ni push salvo que se pida. Trabaja en ramas.
8. **Respuestas:** concisas y técnicamente precisas. Indica qué archivos cambiaste y qué resultado tienen los tests.

## 5. Convenciones de código

- Python con type hints en todas las funciones públicas. `mypy --strict` sobre `src/`.
- Funciones puras para el modelo: entrada explícita, sin efectos secundarios, sin I/O dentro de `model/` ni `valuation/`.
- Dataclasses para supuestos (`Assumptions`),  resultados (`ValuationResult`) y datos compañia (`Company`)
- Nada de números mágicos: supuestos por defecto en un único módulo de configuración, con comentario de fuente o motivo.
- Fechas en UTC y con `datetime` con zona. Importes en `Decimal` o `float` documentado; sé explícito con el redondeo.
- Docstrings en formato Google con unidades explícitas (p. ej. "tasas en decimal, 0.08 = 8 %").
- Usa comentarios # dencima de cada funcion
- En la clases documenta los difernetes atributos, definiendo que es la variable desde un punto económico.
- Librerias:
  - Usa pandas para procesado de tablas, reordencion, filtrados
  - Usa numpy para las operaciones matemáticas
  - Usa YAhoo finance para la descarga de datos de Yahoo

## 6. Reglas del modelo DCF

- **Modelos:** `fcff` (por defecto: EBIT·(1−t) + D&A − Capex − ΔNWC, al WACC), `fcff_cfo` (Net Income × FCFF/Net Income con FCFF desde el CFO, al WACC), `fcfe` (industriales: FCFF − Int·(1−t) + ΔDeuda neta, a Ke) y `fcfe_fin` (bancos y aseguradoras: NI − g·FP, a Ke, sin puente deuda/caja). **VT:** `gordon`, `gordon_value_driver` (por defecto) y `vt_mult`, combinables con cualquier modelo. Modelo y VT de cada tipo de empresa en `config/company_types.toml` (`[default]` y por tipo); `dcf --model` y `dcf --vt` los fuerzan. Fórmulas en `docs/metodologia.md` (§1-§9 fcff_cfo, §10 fcfe_fin, §11 fcff, §12 VT y avisos, §13 fcfe). Las reglas siguientes de WACC y puente son de los FCFF; en FCFE la tasa es Ke y g < Ke.
- **Descuento:** FCFF descontado al WACC. Fórmula de referencia documentada en `docs/metodologia.md`.
- **Proyección (modelo por defecto):** horizonte de 5 años. Ventas +1 (ejercicio en curso) y +2 desde estimaciones de analistas; si no hay, crecimiento medio histórico. Años +3..+5 con la mediana de los crecimientos históricos y de +1/+2. Ratios históricos por mediana (ver decisiones). Detalle en `docs/metodologia.md`.
- **WACC:** coste del capital con CAPM (rf, beta bottom-up o Blume, prima de riesgo) con suelo por riesgo país, y coste de la deuda neto de impuestos. Documenta cada fuente de rf, prima, prima país y beta sectorial.
- **Valor terminal:** método de Gordon (crecimiento perpetuo) y, si se usa, múltiplo de salida. Siempre muestra el peso del valor terminal sobre el valor total.
- **Crecimiento terminal:** debe ser inferior al WACC y a la rentafija libre de riesgo. Valida esta condición y lanza error si no se cumple.
- **Valor por acción:** (VE − deuda total + caja − minoritarios) / acciones diluidas. Usa acciones diluidas, no básicas. No uses deuda neta y caja a la vez (contaría la caja dos veces).
- **Sensibilidad:** toda valoración incluye una tabla WACC × crecimiento terminal.
- **Salidas:** cada resultado registra fecha de datos, fuente, supuestos completos y versión del código.

## 6. Arquitectura del Proyecto

- **Clase base** Genera una clase Company donde se alamacenen todos los datos necesarios para el cálculo del DCF. Debe haber: informacion de la empresa, Lista con los históricos de los útlimos años, lista para el cálculo del coste de deuda con los datos de la empresa (Para cada año historico: Deuda total, gastos en intereses, EBIT, provision de impuestos, Y el Taxrate final)
- **Data** Almacenado en el data del repo los archivos .py para descargar los datos y rellenar la Clase Company en su caso. De momento habrá uno para yahoofinance
- **Model:** 
  - Implementación del modelo de proyecciones. Hay cuatro: fcff (`model/fcff_projection.py`, `valuation/fcff*.py`, `reports/fcff_markdown.py`), fcff_cfo (`model/fcff_cfo_*.py`, `valuation/fcff_cfo*.py`, `reports/fcff_cfo_markdown.py`), fcfe (`model/fcfe_projection.py`, `valuation/fcfe.py`, `valuation/fcfe_result.py`, `reports/fcfe_markdown.py`) y fcfe_fin (`model/fcfe_fin_projection.py`, `valuation/fcfe_fin*.py`, `reports/fcfe_fin_markdown.py`). Los FCFF comparten `valuation/enterprise.py` y `reports/enterprise_markdown.py`; los FCFE, `valuation/equity.py`. Común: `model/revenue_projection.py`, `model/cost_of_equity.py`, `model/tax.py`, `model/discount_rate.py`, `model/terminal_methods.py` (VT), `model/checks.py` (avisos), `model/returns.py` (ROIC/ROE), `valuation/discounting.py`, `valuation/run.py` (elige modelo y VT) y `reports/format.py`. Un modelo nuevo sigue el mismo patrón de nombres.
  - Implementacion del modelo para el calulo del WACC
- **Presentacion resultados** Almacenado en reports, presentará los resultados intermedios y finales de la valuation.


## 8. Verificación (definición de "terminado")

Una tarea no está terminada hasta que:

- [ ] `pytest` pasa y hay tests nuevos para el cambio.
- [ ] `ruff`, `mypy` sin errores nuevos.
- [ ] Un caso de referencia (empresa con cifras conocidas, o un ejemplo de libro de texto con resultado calculado a mano) reproduce el resultado esperado con tolerancia documentada.
- [ ] Las funciones de valor terminal y WACC rechazan entradas inválidas (g ≥ WACC, pesos que no suman 1, acciones ≤ 0).
- [ ] La documentación de `docs/metodologia.md` refleja cualquier cambio en la fórmula.

## 9. Advertencias

- Esta herramienta es educativa y analítica. Sus resultados no son recomendación de inversión. No añadas funciones de ejecución de órdenes ni de asesoramiento personalizado.
- Yahoo Finance no es una API oficial y puede cambiar o devolver datos incompletos. Valida cada respuesta antes de usarla.

## 10. Decisiones y notas

Registra decisiones de modelado no obvias, con fecha y motivo.

- [AAAA-MM-DD] [Decisión]. Motivo: [motivo]. Alternativas descartadas: [alternativas].
- [2026-11-18] Moneda de trabajo EUR. Motivo: elección del usuario. Los datos de Yahoo en otra moneda se convierten y se documenta el tipo de cambio y su fecha. Alternativas descartadas: USD.
- [2026-11-18] Proyección por margen neto y ratio FCFF/Net Income (medias históricas), no por drivers sobre ventas. Motivo: elección del usuario, modelo simple con datos de Yahoo. Alternativas descartadas: drivers (margen EBIT, D&A, CapEx, NOF % ventas); crecer el último FCFF.
- [2026-11-18] FCFF histórico = CFO + intereses·(1−t) − Capex, con t = provisión/BAI de cada año. Años con BAI ≤ 0 o Net Income ≤ 0 se excluyen de la media FCFF/Net Income con aviso. Motivo: elección del usuario. Alternativas descartadas: FCFF = CFO − Capex; t medio o legal; error ante pérdidas.
- [2026-11-18] WACC: rf y PRM desde `config/data/market_inputs.toml` (con fuente y fecha); beta de Yahoo; Kd y t como medias históricas; E a mercado (precio × acciones diluidas), D contable. Motivo: elección del usuario. Alternativas descartadas: rf de Yahoo (^TNX es EE. UU.), beta por regresión o manual, Kd/t del último año, pesos contables.
- [2026-11-18] Beta configurable en `[beta]` de `market_inputs.toml` con `mode` = `yahoo` (defecto; error si falta o es negativa), `fichero` (override) o `yahoo-fichero` (la del fichero solo si Yahoo no la publica o es negativa, indicando el motivo); valor general o por ticker `[beta."TICKER"]`, con fuente y fecha. Motivo: Yahoo da β = −0,181 a REP.MC (WACC 2,46 % < g); elección del usuario. Sustituye "beta de Yahoo" de la decisión anterior. Alternativas descartadas: solo error; suelo de beta.
- [2026-11-18] Valor por acción = (VE − deuda total + caja − minoritarios) / acciones diluidas. Motivo: la fórmula anterior (VE − deuda neta − minoritarios + caja) contaba la caja dos veces. Alternativas descartadas: la fórmula anterior.
- [2026-11-18] Descuento a final de año: el año +k se descuenta con (1 + WACC)^k, con k entero = 1, 2, 3, 4, 5. Motivo: convención estándar y simple. Alternativas descartadas: mid-year, fracción del ejercicio en curso.
- [2026-11-18] Se usan los 4 años anuales que da Yahoo (3 crecimientos históricos), aunque haya 5 en flujos y balance. Motivo: elección del usuario. Alternativas descartadas: completar con CSV; usar todos los disponibles.
- [2026-11-18] Deuda = Total Debt de Yahoo, que incluye arrendamientos NIIF 16. Motivo: coherencia con el FCFF basado en CFO. Alternativas descartadas: excluir arrendamientos.
- [2026-11-18] Minority Interest, Issuance Of Debt y Repayment Of Debt ausentes → 0 con aviso registrado; cualquier otro dato ausente → error. Motivo: Yahoo omite esas filas cuando valen 0. Alternativas descartadas: error siempre.
- [2026-11-18] Interest Expense ausente → intereses = Kd por defecto × deuda total del año, con Kd de la sección opcional `[default_cost_of_debt]` de `market_inputs.toml` (con fuente y fecha) y aviso; sin esa sección, error. Motivo: propuesta del usuario; Yahoo no publica intereses de algunas empresas (p. ej. AAPL desde 2024). Alternativas descartadas: error siempre; 0 y excluir del Kd.
- [2026-11-18] Escenarios configurables en `config/settings.toml`: modo `ventas` (estimaciones baja/media/alta de analistas; media si falta) y modo `coste` (WACC ± 1 punto, g ∓ 0,5 puntos), combinables. Motivo: elección del usuario; desplazamientos por defecto propuestos por el agente. Alternativas descartadas: solo desplazar WACC y g; desplazar el crecimiento.
- [2026-11-18] Informe en consola + Markdown (`output/`), importes en M€; redondeo comercial solo en presentación. Motivo: elección del usuario. Alternativas descartadas: Excel, HTML.
- [2026-11-19] Company guarda sector e industria de Yahoo y un tipo de empresa (`industrial`, `banco`, `aseguradora`, `inmobiliaria`) según la tabla `config/company_types.toml` (industryKey, luego sectorKey; sin regla = industrial; sin datos = sin clasificar con aviso). Los no industriales se valoran con el modelo FCFF actual pero con aviso en el informe y el resumen. Motivo: el modelo está pensado para industriales; base para modelos por tipo. Alternativas descartadas: solo sector/industria; error para no industriales.
- [2026-11-19] Modelo FCFE para bancos y aseguradoras (`model = "fcfe"` en `company_types.toml`): ventas y Net Income como en FCFF; FCFE_t = NI_t − g_t · FP_{t−1} con FP (Stockholders Equity) creciendo al ritmo de las ventas; descuento a Ke; VT con FCFE_{N+1} = NI_N·(1+g) − g·FP_N; valor por acción = fondos propios / acciones diluidas, sin puente. El modelo actual pasa a llamarse FCFF y sus módulos llevan prefijo `fcff_`. Motivo: elección del usuario (enfoque de Damodaran para bancos). Alternativas descartadas: FCFE = NI × payout histórico; FCFE clásico (CFO − Capex + deuda neta), sin sentido en bancos; NI = ROE × FP; FCFE solo para bancos.
- [2026-11-19] El valor terminal FCFE usa FCFE_{N+1} = NI_N·(1+g) − g·FP_N y no FCFE_N·(1+g). Motivo: la reinversión del año N corresponde al crecimiento g_N, no al g terminal; propuesta del agente por coherencia. Alternativas descartadas: FCFE_N·(1+g).
- [2026-11-21] Tasa de descuento forzable (WACC en FCFF, Ke en FCFE) con precedencia argumento `--set rate` (todos los tickers) > `[discount_rate."TICKER"]` de `market_inputs.toml` (solo por ticker) > calculada. Con tasa forzada, la calculada es informativa y sus errores (beta negativa, sin Kd) pasan a avisos. Motivo: elección del usuario. Alternativas descartadas: valor general en el fichero; error aunque la tasa esté forzada; claves separadas wacc/ke.
- [2026-11-21] Modelos `fcff` (FCFF desde el EBIT: EBIT·(1−t) + D&A − Capex − ΔNWC con circulante comercial y VT sobre el año N+1) probado y eliminado; el modelo FCFF original pasa a llamarse `fcff_cfo` y es el de los industriales. Motivo: elección del usuario tras compararlo (SCYR.MC, IDR.MC). Alternativas descartadas: mantener los dos modelos FCFF.
- [2026-11-21] El t del WACC es la mediana de los tipos efectivos, no la media. Motivo: un año anómalo (SCYR.MC 2023: 91,6 %) subía el t medio al 51,8 % y bajaba el WACC; elección del usuario. Alternativas descartadas: tipo legal del fichero; media.
- [2026-11-21] Modelo `fcff` (1.1 de `docs/dcf_metodos.md`: EBIT·(1−t) + D&A − Capex − ΔNWC con circulante comercial) recuperado como modelo por defecto de los industriales, con VT `gordon_value_driver`; `fcff_cfo` se mantiene. Motivo: elección del usuario. Sustituye la eliminación del `fcff` de la decisión anterior (el VT N+1 de entonces se retira: el value driver cubre la reinversión terminal).
- [2026-11-21] Nuevo `fcfe` = FCFF − Kd·DN_{t−1}·(1−t) + D/(D+E)·(Capex − D&A + ΔNWC), con D/(D+E) constante (D contable, E a mercado) y fondos propios = valor descontado − minoritarios; el FCFE de financieras pasa a llamarse `fcfe_fin`. Motivo: elección del usuario (fórmula 1.2 literal para industriales con mucha deuda). Alternativas descartadas: un único FCFE; ΔDeuda = emisión − reembolso histórico.
- [2026-11-21] VT configurable (`gordon`, `gordon_value_driver`, `vt_mult`) por tipo en `company_types.toml` y con `--vt`. Value driver: Beneficio_N·(1+g)·(1−g/RONIC)/(r−g), con NOPAT y ROIC histórico (deuda + FP − caja) en FCFF y Net Income y ROE en FCFE; RONIC forzable (`--set ronic=` > `[ronic."TICKER"]`). Múltiplo EV/EBITDA (FCFF) o P/E (FCFE) solo desde `--set exit_multiple=` > `[exit_multiple."TICKER"]`; sin él, error. fcfe_fin pasa a Gordon clásico por defecto. Motivo: elección del usuario. Alternativas descartadas: múltiplo de mercado de Yahoo; RONIC = WACC fijo.
- [2026-11-21] Avisos de consistencia con umbrales en `config/thresholds.toml` (`[warnings]`): flujo histórico < 0; último flujo histórico a más de 33 % de la media de los anteriores; |g implícito − g| > 0,75 puntos (value driver y múltiplo); RONIC > 2 × tasa. Motivo: elección del usuario. Alternativas descartadas: umbrales fijos en el código; error en lugar de aviso.
- [2026-11-24] Beta por defecto `bottom-up`: beta sectorial desapalancada de `[sector_beta."CLAVE"]` (industryKey, luego sectorKey) reapalancada con D/E (D contable, E mercado) y t mediano; sin ella, Yahoo ajustada por Blume (0,67·β + 0,33); en `fcfe_fin` sin reapalancar. Motivo: elección del usuario; las betas de regresión de Yahoo son ruidosas. Alternativas descartadas: solo Blume; solo bottom-up.
- [2026-11-24] Suelo de Ke = rf + 1·PRM + prima de riesgo país (`[country_risk_premium."PAÍS"]`, por `info.country`); Ke = máx(CAPM, suelo) en los cuatro modelos; sin país o sin su prima, error. Motivo: elección del usuario. Alternativas descartadas: suelo fijo por país; sumar siempre la prima país.
- [2026-11-24] Medianas en lugar de medias en los ratios que se proyectan (crecimiento, márgenes, D&A/Capex/NWC sobre ventas, FCFF/NI) y en el ROIC/ROE histórico del value driver. Motivo: normalizar años atípicos; elección del usuario. Alternativas descartadas: excluir el año atípico; sustituirlo por la media de los demás. Kd sigue siendo la media.
- [2026-11-24] Los escenarios bajista y alcista con |g implícito − g| > 1 punto (`scenario_growth_gap`) se excluyen (no válidos); el central solo avisa. Motivo: elección del usuario. Alternativas descartadas: excluir también el central.
- [2026-11-18] Acciones diluidas = Diluted Average Shares del último ejercicio. Motivo: único dato diluido de Yahoo. Alternativas descartadas: sharesOutstanding (básicas).

## 10. Contexto adicional

Para detalles de un submódulo, crea un `CLAUDE.md` dentro de su carpeta (p. ej. `src/dcf/data/CLAUDE.md`).

@docs/metodologia.md
