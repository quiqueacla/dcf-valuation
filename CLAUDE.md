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

- **Descuento:** FCFF descontado al WACC. Fórmula de referencia documentada en `docs/metodologia.md`.
- **Proyección (modelo por defecto):** horizonte de 5 años. Ventas +1 (ejercicio en curso) y +2 desde estimaciones de analistas; si no hay, crecimiento medio histórico. Años +3..+5 con la media de los crecimientos históricos y de +1/+2. Net Income = ventas × margen neto medio histórico; FCFF = Net Income × media histórica de FCFF/Net Income. Detalle en `docs/metodologia.md`.
- **WACC:** coste del capital con CAPM (rf, beta, prima de riesgo) y coste de la deuda neto de impuestos. Documenta cada fuente de rf y prima.
- **Valor terminal:** método de Gordon (crecimiento perpetuo) y, si se usa, múltiplo de salida. Siempre muestra el peso del valor terminal sobre el valor total.
- **Crecimiento terminal:** debe ser inferior al WACC y a la rentafija libre de riesgo. Valida esta condición y lanza error si no se cumple.
- **Valor por acción:** (VE − deuda total + caja − minoritarios) / acciones diluidas. Usa acciones diluidas, no básicas. No uses deuda neta y caja a la vez (contaría la caja dos veces).
- **Sensibilidad:** toda valoración incluye una tabla WACC × crecimiento terminal.
- **Salidas:** cada resultado registra fecha de datos, fuente, supuestos completos y versión del código.

## 6. Arquitectura del Proyecto

- **Clase base** Genera una clase Company donde se alamacenen todos los datos necesarios para el cálculo del DCF. Debe haber: informacion de la empresa, Lista con los históricos de los útlimos años, lista para el cálculo del coste de deuda con los datos de la empresa (Para cada año historico: Deuda total, gastos en intereses, EBIT, provision de impuestos, Y el Taxrate final)
- **Data** Almacenado en el data del repo los archivos .py para descargar los datos y rellenar la Clase Company en su caso. De momento habrá uno para yahoofinance
- **Model:** 
  - Implementación del modelo de proyecciones. De momento habrá uno. Pero podrían aparecer nuevos.
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
- [2026-11-18] Acciones diluidas = Diluted Average Shares del último ejercicio. Motivo: único dato diluido de Yahoo. Alternativas descartadas: sharesOutstanding (básicas).

## 10. Contexto adicional

Para detalles de un submódulo, crea un `CLAUDE.md` dentro de su carpeta (p. ej. `src/dcf/data/CLAUDE.md`).

@docs/metodologia.md
