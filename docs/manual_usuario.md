# Manual de usuario de `dcf`

Guía práctica para instalar, configurar y usar la aplicación de valoración por flujos de caja
descontados (DCF). Lo que hace cada cálculo a nivel económico (fórmulas, supuestos y
limitaciones) está en [metodologia.md](metodologia.md); aquí se indica la sección (§) que
corresponde en cada caso.

> Herramienta educativa y analítica. Sus resultados no son recomendación de inversión.

**Contenido**

1. [Qué hace la aplicación](#1-qué-hace-la-aplicación)
2. [Instalación](#2-instalación)
3. [Configuración inicial](#3-configuración-inicial)
4. [Primera valoración](#4-primera-valoración)
5. [Línea de comandos](#5-línea-de-comandos)
6. [Modelos y métodos de valor terminal](#6-modelos-y-métodos-de-valor-terminal)
7. [Ficheros de configuración](#7-ficheros-de-configuración)
8. [Resultados: informe, resumen y caché](#8-resultados-informe-resumen-y-caché)
9. [Cómo leer el informe y los avisos](#9-cómo-leer-el-informe-y-los-avisos)
10. [Casos de uso](#10-casos-de-uso)
11. [Solución de problemas](#11-solución-de-problemas)
12. [Referencia rápida](#12-referencia-rápida)

---

## 1. Qué hace la aplicación

Para cada ticker de Yahoo Finance (p. ej. `ITX.MC`, `SAN.MC`, `AAPL`):

1. **Descarga** los 4 últimos ejercicios anuales (cuenta de resultados, balance y flujos), la
   cotización, la beta y las estimaciones de ventas de los analistas, y los guarda en caché.
   Convierte a EUR lo que venga en otra moneda (metodología §1).
2. **Clasifica** la empresa (industrial, banco, aseguradora, inmobiliaria) y elige el modelo y
   el método de valor terminal adecuados (§1, «Tipo de empresa»).
3. **Proyecta** ventas y flujos de caja 5 años (§3, §11, §13, §10).
4. **Descuenta** los flujos al WACC o al coste de los fondos propios Ke (§4, §5), calcula el
   valor terminal (§12) y llega al **valor intrínseco por acción** (§6).
5. Calcula **escenarios** bajista / neutro / alcista y una **tabla de sensibilidad** (§7, §8).
6. Revisa la **consistencia** de la valoración y avisa de lo que no encaja (§12).
7. Genera un **informe** en consola y en Markdown y, con varios tickers, un **resumen** en
   Markdown y CSV (§9).

La aplicación no inventa datos: si falta una cifra imprescindible o un supuesto (rf, prima de
riesgo, g…), se detiene con un error que dice qué falta y dónde indicarlo.

---

## 2. Instalación

Requisitos: Python ≥ 3.12 y conexión a internet para descargar datos (no hace falta para
repetir una valoración desde la caché). Se recomienda [uv](https://docs.astral.sh/uv/), que
instala él mismo la versión de Python necesaria.

### Windows (PowerShell)

```powershell
git clone https://github.com/quiqueacla/dcf-valuation.git
cd dcf-valuation
uv sync
```

`uv sync` crea el entorno `.venv` con Python 3.12 e instala las dependencias y el comando
`dcf`. Para usarlo hay dos formas:

- **Sin activar el entorno**, anteponiendo `uv run`:

  ```powershell
  uv run dcf --help
  ```

- **Activando el entorno** una vez por terminal (el prompt pasa a empezar por `(dcf)`):

  ```powershell
  .\.venv\Scripts\Activate.ps1
  dcf --help
  ```

  Si PowerShell bloquea el script, permítelo solo para esa sesión con
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y vuelve a activarlo. En
  VS Code, elige `.venv\Scripts\python.exe` como intérprete («Python: Select Interpreter») y
  las terminales nuevas se abrirán con el entorno activado.

Sin uv: `python -m venv .venv`, `.\.venv\Scripts\Activate.ps1` y `pip install -e .`.

### Linux, macOS y WSL

```bash
uv sync && source .venv/bin/activate      # o: uv run dcf ...
```

Si tu sistema tiene Python 3.10 / 3.11 (p. ej. Ubuntu 22.04 en WSL), el README explica cómo
crear un entorno con 3.12 sin tocar el Python del sistema.

### Comprobación

```powershell
dcf --help
```

Debe mostrar la ayuda con las opciones `--model`, `--vt`, `--set`, etc.

---

## 3. Configuración inicial

Antes de la primera valoración hay que dar dos supuestos de mercado que la aplicación **no
descarga** y un crecimiento terminal.

### 3.1 Datos de mercado (obligatorio)

Copia la plantilla y rellénala:

```powershell
Copy-Item config\data\market_inputs.example.toml config\data\market_inputs.toml
```

En `config/data/market_inputs.toml`, como mínimo:

```toml
[risk_free_rate]          # rentabilidad libre de riesgo, p. ej. Bund alemán a 10 años
value = 0.027             # en decimal: 0.027 = 2,7 %
source = "BCE, curva de tipos AAA a 10 años"
date = 2026-11-20

[market_risk_premium]     # prima de un mercado MADURO (p. ej. Damodaran, país Aaa)
value = 0.0423
source = "Damodaran, ctryprem: Equity Risk Premium de un país Aaa"
date = 2026-01-05
```

Y la **prima de riesgo país** de cada país de las empresas que valores (el país de la sede
según Yahoo, en inglés). Se suma al CAPM y fija el suelo de Ke:
Ke = máx(rf + β · PRM + prima país, rf + PRM + prima país).

```toml
[country_risk_premium."Spain"]
value = 0.0155            # «Country Risk Premium» de Damodaran
source = "Damodaran, ctryprem: Country Risk Premium, rating Moody's A3"
date = 2026-01-05
```

Las primas de todos los países están en la tabla de Damodaran (ctryprem). No uses como PRM la
prima total de un país («Total Equity Risk Premium»): contarías su prima país dos veces.

Las cifras de este ejemplo son ilustrativas: pon las tuyas con su fuente y su fecha, que
aparecerán en el informe. Sin la prima del país de una empresa, su valoración da error.
El resto de secciones del fichero son opcionales (ver §7.2).
Este fichero es tuyo: no se sube al repositorio.

### 3.2 Crecimiento terminal

El crecimiento perpetuo g se fija en `config/settings.toml` (`terminal_growth`, por defecto
0.025 = 2,5 %) o en cada ejecución con `--set g=2%`. Debe ser menor que la tasa de descuento
y que la rentabilidad libre de riesgo; si no, la valoración se detiene (§5).

### 3.3 Opcional

- `config/company_types.toml`: qué modelo y valor terminal se aplica a cada tipo de empresa
  (§7.3).
- `config/thresholds.toml`: umbrales de los avisos de consistencia (§7.4).
- `config/settings.toml`: escenarios y años de proyección (§7.1).

---

## 4. Primera valoración

```powershell
dcf ITX.MC
```

La aplicación:

1. descarga los datos de Yahoo y los guarda en `data/cache/ITX.MC/<fecha UTC>/`;
2. muestra el informe completo en la consola;
3. lo guarda en `output/ITX.MC_<fecha UTC>.md`.

Con varios tickers solo muestra una línea por empresa y guarda además un resumen del lote:

```powershell
dcf ITX.MC SAN.MC IDR.MC
```

```
ITX.MC: 41,20 € por acción (cotización 52,10 €, fcff + gordon_value_driver, WACC 7,80 %) | Bajista: … | Neutro: … | Alcista: …
    informe: output\ITX.MC_20261122T180000Z.md
…
3 de 3 tickers valorados.
Resumen guardado en output\resumen_20261122T180000Z.md y output\resumen_20261122T180000Z.csv
```

(Las cifras de este ejemplo son ilustrativas.)

---

## 5. Línea de comandos

```
dcf [TICKER ...] [-f FICHERO] [opciones]
```

También funciona como `python -m dcf ...`.

### 5.1 Opciones

| Opción | Qué hace | Por defecto |
|---|---|---|
| `TICKER ...` | Símbolos de Yahoo Finance (p. ej. `ITX.MC`, `SAN.MC`, `AAPL`) | — |
| `-f`, `--file FICHERO` | Lee tickers de un fichero, uno o varios por línea (separados por espacios o comas); lo que va tras `#` es comentario. Se puede combinar con tickers sueltos; los repetidos se valoran una vez | — |
| `-c`, `--config`, `--settings FICHERO` | Configuración de la aplicación (g, horizonte, escenarios) | `config/settings.toml` |
| `-m`, `--market-inputs FICHERO` | Datos de mercado (rf, prima de riesgo, beta, tasas, múltiplos…) | `config/data/market_inputs.toml` |
| `-t`, `--company-types FICHERO` | Tabla de tipos de empresa con su modelo y valor terminal | `config/company_types.toml` |
| `--model MODELO` | Fuerza el modelo: `fcff`, `fcff_cfo`, `fcfe`, `fcfe_fin` (§6) | El de la tabla de tipos |
| `--vt MÉTODO` | Fuerza el valor terminal: `gordon`, `gordon_value_driver`, `vt_mult` (§6) | El de la tabla de tipos |
| `--thresholds FICHERO` | Umbrales de los avisos de consistencia | `config/thresholds.toml` |
| `-o`, `--output-dir CARPETA` | Carpeta de los informes y del resumen | `output` |
| `--set CLAVE=VALOR` | Cambia un supuesto solo en esta ejecución (repetible, ver 5.2) | — |
| `--g G` | Atajo de `--set g=`, en decimal (`--g 0.02`) | — |
| `--no-extras` | Sin escenarios (más rápido); la sensibilidad se mantiene | Con escenarios |
| `--raw` | Muestra el informe en Markdown sin formato | Formateado en terminal |
| `--from-cache CARPETA` | Valora desde una descarga guardada, sin red (un solo ticker) | Descarga de Yahoo |
| `--cache-dir CARPETA` | Dónde se guardan las descargas | `data/cache` |

Las rutas por defecto son relativas a la carpeta del proyecto: ejecuta `dcf` desde ella o
indica los ficheros con `-c`, `-m`, `-t` y `--thresholds`.

### 5.2 Claves de `--set`

Las tasas se pueden escribir como `2%`, `2 %`, `0.02` o `0,02`. Los ajustes solo valen para
esa ejecución y prevalecen sobre los ficheros.

| Clave (alias) | Qué cambia | Ejemplo | Metodología |
|---|---|---|---|
| `terminal_growth` (`g`) | Crecimiento perpetuo del valor terminal | `--set g=2%` | §5, §12 |
| `projection_years` | Años de proyección explícita (entero) | `--set projection_years=7` | §3 |
| `modes` | Modos de escenario, separados por comas; vacío = solo neutro | `--set modes=ventas,coste` | §8 |
| `wacc_shift` | Desplazamiento de la tasa en el modo `coste` | `--set wacc_shift=1.5%` | §8 |
| `growth_shift` | Desplazamiento de g en el modo `coste` | `--set growth_shift=0.25%` | §8 |
| `rate` (`discount_rate`) | Fuerza la tasa de descuento (WACC o Ke) de todos los tickers | `--set rate=8%` | §4 |
| `exit_multiple` (`multiple`) | Múltiplo de salida del VT (EV/EBITDA o P/E), número sin % | `--set exit_multiple=10` | §12 |
| `ronic` | RONIC (ROE en FCFE) del value driver | `--set ronic=10%` | §12 |

### 5.3 Códigos de salida

| Código | Significado |
|---|---|
| 0 | Todos los tickers se han valorado |
| 1 | Algún ticker ha fallado, o hay un error de configuración |
| 2 | No se ha indicado ningún ticker |

Útil para scripts: un lote con un ticker erróneo valora los demás, los incluye en el resumen
con su error y termina con código 1.

---

## 6. Modelos y métodos de valor terminal

Cada valoración combina un **modelo de flujos** y un **método de valor terminal (VT)**. Por
defecto los elige la tabla `config/company_types.toml` según el tipo de empresa; `--model` y
`--vt` los fuerzan.

### 6.1 Modelos (`--model`)

| Modelo | Cuándo usarlo | Flujo y tasa | Metodología |
|---|---|---|---|
| `fcff` | **Por defecto en industriales.** Empresas no financieras en general | FCFF desde el EBIT (EBIT·(1−t) + D&A − Capex − ΔNWC), al WACC | §11 |
| `fcff_cfo` | Industriales con circulante muy volátil que distorsiona el EBIT → FCFF; alternativa para comparar | FCFF desde el flujo de operaciones (Net Income × conversión histórica FCFF/Net Income), al WACC | §1-§9 |
| `fcfe` | Industriales con mucha deuda o con una deuda que cambia mucho | FCFE = FCFF − intereses·(1−t) + ΔDeuda neta, a Ke | §13 |
| `fcfe_fin` | **Por defecto en bancos y aseguradoras** | FCFE = Net Income − crecimiento de los fondos propios, a Ke | §10 |

Si fuerzas un modelo que no es adecuado para el tipo de empresa (p. ej. `fcff_cfo` en un
banco), se valora igual pero el informe y la línea del resumen lo avisan. Para inmobiliarias
ninguno es adecuado (su valor está en los activos) y siempre se avisa.

### 6.2 Valor terminal (`--vt`)

El valor terminal suele pesar entre el 70 % y el 90 % del valor, así que su método importa.

| Método | Idea | Necesita | Por defecto en |
|---|---|---|---|
| `gordon` | El último flujo crece a g para siempre | g | Bancos y aseguradoras |
| `gordon_value_driver` | El beneficio crece a g, pero hay que reinvertir g / RONIC para conseguirlo | g y RONIC (el ROIC histórico si no lo indicas; ROE en FCFE) | Industriales |
| `vt_mult` | Múltiplo de salida sobre el último año | El múltiplo: EV/EBITDA en FCFF, P/E en FCFE (**no hay valor por defecto**) | — |

- **RONIC** (rentabilidad de las nuevas inversiones): `--set ronic=10%` para todos los tickers,
  o `[ronic."TICKER"]` en `market_inputs.toml`. Sin ninguno se usa el ROIC histórico medio
  (ROE en FCFE), que suele ser optimista; un RONIC cercano a la tasa de descuento es la opción
  prudente a largo plazo (§12).
- **Múltiplo:** `--set exit_multiple=9` o `[exit_multiple."TICKER"]`. Sin él, `vt_mult` da
  error: la aplicación no busca múltiplos de mercado.

### 6.3 Combinaciones

Cualquier modelo admite cualquier método:

```powershell
dcf IDR.MC --model fcff --vt gordon_value_driver --set ronic=10%
dcf IDR.MC --model fcfe --vt gordon
dcf IDR.MC --vt vt_mult --set exit_multiple=9
dcf SAN.MC --vt gordon_value_driver --set ronic=11%
```

Comparar varias combinaciones sobre la misma descarga (con `--from-cache`, §8.3) es una buena
forma de ver qué supuestos mueven el valor.

---

## 7. Ficheros de configuración

Todos son TOML (texto, `clave = valor`). Tasas siempre en decimal: `0.03` = 3 %.

### 7.1 `config/settings.toml`: supuestos de la valoración

```toml
[valuation]
terminal_growth = 0.025     # g del valor terminal (o --set g=)
# projection_years = 5      # años de proyección (o --set projection_years=)

[scenarios]
modes = ["coste"]           # [], ["ventas"], ["coste"] o ["ventas", "coste"]
wacc_shift = 0.01           # ± 1 punto de tasa en el modo coste
growth_shift = 0.005        # ∓ 0,5 puntos de g en el modo coste
```

Modos de escenario (§8):

- `ventas`: el bajista usa la estimación **baja** de ventas de los analistas para los dos
  próximos años y el alcista la **alta**.
- `coste`: el bajista sube la tasa y baja g; el alcista al revés.
- Combinados, el bajista junta lo peor de los dos y el alcista lo mejor.

### 7.2 `config/data/market_inputs.toml`: datos de mercado

Cada dato lleva `value`, `source` y `date`, que se muestran en el informe. Secciones:

| Sección | Obligatoria | Para qué | Metodología |
|---|---|---|---|
| `[risk_free_rate]` | Sí | Rentabilidad libre de riesgo (CAPM y límite de g) | §4 |
| `[market_risk_premium]` | Sí | Prima de riesgo de mercado (CAPM) | §4 |
| `[default_cost_of_debt]` | No | Coste de la deuda para estimar los intereses cuando Yahoo no los publica | §1 |
| `[country_risk_premium."PAÍS"]` | Sí, por país | Prima de riesgo país: se suma al CAPM y fija el suelo de Ke | §4 |
| `[sector_beta."CLAVE"]` | No | Beta desapalancada por industria o sector (modo `bottom-up`) | §4 |
| `[beta]` y `[beta."TICKER"]` | No | Cómo se elige la beta (`mode`) y beta propia general o por ticker | §4 |
| `[discount_rate."TICKER"]` | No | Fuerza el WACC o Ke de un ticker | §4 |
| `[exit_multiple."TICKER"]` | No | Múltiplo de salida de un ticker (`vt_mult`) | §12 |
| `[ronic."TICKER"]` | No | RONIC / ROE de un ticker (`gordon_value_driver`) | §12 |

**Beta** (`[beta]`, campo `mode`):

| `mode` | Beta que se usa |
|---|---|
| `bottom-up` (defecto) | La beta sectorial desapalancada de `[sector_beta]`, reapalancada con la deuda de la empresa; si no hay para su industria ni su sector, la de Yahoo ajustada por Blume (0,67 · β + 0,33); si Yahoo no la publica o es negativa, la de `[beta]` |
| `yahoo` | La de Yahoo sin ajustar; error si no la publica o es negativa |
| `fichero` | Siempre la del fichero |
| `yahoo-fichero` | La de Yahoo; si falta o es negativa, la del fichero (el informe dice por qué) |

Ejemplo con beta propia para un ticker y RONIC prudente:

```toml
[beta]
mode = "yahoo-fichero"

[beta."REP.MC"]
value = 0.95
source = "Beta sectorial petróleo integrado (Damodaran)"
date = 2026-11-01

[ronic."IDR.MC"]
value = 0.10
source = "RONIC ≈ WACC a largo plazo (supuesto prudente)"
date = 2026-11-21
```

Beta sectorial desapalancada (modo `bottom-up`), por clave de industria o de sector de
Yahoo (se ven en la sección 1 del informe o en `meta.json` de la caché):

```toml
[sector_beta."engineering-construction"]
value = 0.85
source = "Damodaran, Unlevered beta, Engineering/Construction (Europa)"
date = 2026-01-05
```

Ke = rf + β · PRM + prima país y nunca baja del **suelo** rf + PRM + prima país del país de
la empresa (metodología §4).

Las cifras son ilustrativas. **Precedencia** de los datos forzables (tasa, múltiplo, RONIC):
argumento `--set` (todos los tickers) > sección del ticker en este fichero > calculado
(o error, en el múltiplo).

### 7.3 `config/company_types.toml`: tipo de empresa, modelo y VT

Clasifica cada empresa con las claves de sector e industria de Yahoo (`industryKey`, luego
`sectorKey`) y fija su modelo (`model`) y valor terminal (`vt`):

```toml
[default]                       # industriales y tipos sin modelo propio
model = "fcff"
vt = "gordon_value_driver"

[banco]
model = "fcfe_fin"
vt = "gordon"
industries = ["banks-diversified", "banks-regional"]
```

Para que una industria se trate como banco, aseguradora o inmobiliaria, añade su clave a la
lista del tipo. Las claves se ven en el informe (sección 1) o en la caché (`meta.json`).
Lo que no encaja con ninguna regla es industrial (metodología §1, «Tipo de empresa»).

### 7.4 `config/thresholds.toml`: umbrales de los avisos

```toml
[warnings]
last_flow_deviation = 0.33    # último flujo histórico a más de un 33 % de la media anterior
implied_growth_gap = 0.0075   # g implícito del VT a más de 0,75 puntos del g supuesto
ronic_to_rate = 2.0           # RONIC (o ROE) mayor que 2 veces la tasa de descuento
scenario_growth_gap = 0.01    # excluye bajista/alcista con g implícito a más de 1 punto
```

Es opcional: sin él se usan esos mismos valores. Con `--thresholds otro.toml` se usa otro
fichero. Qué mide cada aviso: §9.2 de este manual y metodología §12.

### 7.5 Listas de tickers

Ficheros de texto para `-f`: un ticker (o varios separados por espacios o comas) por línea,
`#` para comentarios. Ejemplos incluidos: `tickers.example.txt` y `config/tickers/ibex35.txt`.

```powershell
dcf -f config\tickers\ibex35.txt -o informes\ibex
```

---

## 8. Resultados: informe, resumen y caché

### 8.1 Informe por ticker

Se muestra en la consola (formateado con colores y tablas; `--raw` o redirigir la salida da el
Markdown sin formato) y se guarda en `<carpeta de salida>/<TICKER>_<fecha UTC>.md`. Importes
en millones de EUR. Secciones:

| Sección | Contenido | Metodología |
|---|---|---|
| Cabecera | Modelo, fechas de datos y de valoración, fuente, versión del código y supuestos | §9 |
| 1. Información de la compañía | Nombre, sector, industria, tipo, moneda y tipo de cambio, balance y cotización; aviso si el modelo no es adecuado | §1 |
| 2. Tasa de descuento | WACC (Ke, Kd, t, pesos) en los FCFF o solo Ke en los FCFE, con la beta usada y su origen; tasa forzada si la hay | §4 |
| 3.1 Históricos | Tabla en cascada: ventas → EBIT → impuestos → NOPAT → flujo de caja (FCFF o FCFE) → capital invertido y ROIC (ROE en fcfe_fin), con medias | §2, §9, §11, §13, §10 |
| 3.2 Proyecciones | Ventas (analistas o crecimiento medio), flujos de cada año, factor de descuento y valor actual | §3 |
| 4.1 Valor intrínseco | Del valor de empresa (o de los fondos propios) al valor por acción, peso del VT y diferencia con la cotización | §5, §6 |
| Valor terminal | Método, fórmula, datos del año N, VT, g implícito y múltiplo implícito | §12 |
| Comprobaciones de consistencia | Avisos sobre los históricos y el VT | §12 |
| 4.2 Escenarios | Bajista / neutro / alcista | §8 |
| 4.3 Sensibilidad | Valor por acción para tasa × g (±1 punto en pasos de 0,5) | §7 |

### 8.2 Resumen de un lote

Con dos o más tickers, además de un informe por empresa se guardan:

- `resumen_<fecha UTC>.md`: tabla con una fila por ticker y los avisos de cada uno.
- `resumen_<fecha UTC>.csv`: lo mismo para Excel en español (separador `;`, decimal `,`,
  UTF-8 con BOM). Números sin redondear; tasas y márgenes en decimal (0,10 = 10 %).

Columnas: ticker, empresa, modelo, método de VT, cotización, valor bajista / neutro / alcista
y su margen frente a la cotización, tasa de descuento y g con sus fuentes, avisos y, si
falló, el error (metodología §9).

### 8.3 Caché y repetición sin red

Cada descarga se guarda en `data/cache/<TICKER>/<fecha UTC>/` (no la edites a mano). Para
repetir la valoración con otros supuestos sin volver a descargar:

```powershell
dcf IDR.MC --from-cache data\cache\IDR.MC\20261122T171254Z --set g=2% --vt gordon
```

`--from-cache` admite un solo ticker y comprueba que la caché es de ese ticker. Así puedes
comparar modelos y supuestos sobre exactamente los mismos datos.

---

## 9. Cómo leer el informe y los avisos

### 9.1 Lo primero que conviene mirar

1. **Valor por acción frente a cotización** (4.1) y el rango de escenarios (4.2): un único
   número es engañoso; el rango y la sensibilidad (4.3) dicen cuánto depende de los supuestos.
2. **Peso del valor terminal**: si supera el 80-90 %, casi todo el valor está en el VT y su
   método, g y RONIC son decisivos.
3. **Tasa de descuento y beta** (sección 2): una beta muy baja o muy alta de Yahoo cambia
   mucho el resultado; revísala con `[beta]` si no tiene sentido económico.
4. **Comprobaciones de consistencia** y avisos de cada sección.

### 9.2 Avisos de consistencia

No detienen la valoración; señalan supuestos que conviene revisar (umbrales en
`config/thresholds.toml`, metodología §12).

| Aviso | Qué significa | Qué revisar |
|---|---|---|
| **Flujo histórico negativo** en un año | Ese año la empresa consumió caja (FCFF o FCFE < 0) | Si fue puntual (inversión, circulante) o estructural. En la tabla 3.1, Capex y circulante de ese año |
| **El flujo de AAAA está un X % por encima de la media** | El último año es mucho mejor que los anteriores: posible **sobrevaloración** si fue puntual | Si la mejora es sostenible. En `gordon` el VT parte de él |
| **… por debajo de la media** | El último año es mucho peor: posible **infravaloración** si fue puntual | Igual que el anterior |
| **RONIC (o ROE) > 2 × tasa** | El value driver supone que la empresa invertirá siempre con una rentabilidad muy superior a su coste: ventaja competitiva muy duradera | Un RONIC más prudente: `--set ronic=` cercano a la tasa |
| **g implícito difiere X puntos del g supuesto** | El VT no encaja con el flujo del último año proyectado | Ver abajo |

**g implícito.** Es el crecimiento que tendría que suponer un Gordon clásico sobre el último
flujo para dar el mismo VT. Si se aleja del g supuesto:

- **g implícito > g**: el VT es alto para el flujo del año N. Con `gordon_value_driver`, suele
  ser porque el RONIC es alto o porque el año N aún crece mucho y reinvierte mucho (el flujo
  es bajo, pero el VT solo exige la reinversión de crecer a g). Con `vt_mult`, el múltiplo es
  alto para ese flujo.
- **g implícito < g**: el flujo del año N es alto frente al beneficio, es decir, reinvierte
  poco o libera caja. Es frecuente en `fcff_cfo` cuando la conversión histórica FCFF / Net
  Income es mayor que 1. Revisa D&A, Capex y circulante proyectados.

Con `gordon` no se comprueba ni el g implícito (coincide con g por definición) ni el RONIC.

**«Sin avisos»** significa solo que ninguna de estas señales ha saltado con los umbrales
configurados, no que la valoración sea correcta.

### 9.3 Otros avisos

| Aviso | Significado |
|---|---|
| Aviso de modelo (sección 1 y línea del resumen) | El modelo aplicado no es adecuado para el tipo de empresa, o no se ha podido clasificar |
| Datos ausentes puestos a 0 (minoritarios, emisión o reembolso de deuda, existencias) | Yahoo no publica la fila; se toma 0 (metodología §1) |
| Intereses estimados | Yahoo no publica los intereses; se estiman con `[default_cost_of_debt]` |
| Años excluidos de alguna media | Años con pérdidas o un tipo impositivo sin sentido no entran en la media (§2) |
| Estimación de analistas ausente | Se proyecta con el crecimiento histórico medio (§3) |
| Escenario no válido | En ese escenario g ≥ tasa o g ≥ rf; el resto de la valoración sigue (§8) |
| Escenario excluido por g implícito | El VT del bajista o el alcista no encaja con su flujo del año N (g implícito a más de 1 punto de su g); se deja vacío (§8) |
| Beta de respaldo | No hay beta sectorial para la industria: se usa la de Yahoo ajustada por Blume (§4) |
| Ke por CAPM por debajo del suelo | Se descuenta al suelo rf + PRM + prima país (§4) |

---

## 10. Casos de uso

**Valorar el IBEX 35 y abrir el resumen en Excel**

```powershell
dcf -f config\tickers\ibex35.txt -o informes\ibex
```

Abre `informes\ibex\resumen_<fecha>.csv` con Excel.

**Probar un supuesto sin tocar los ficheros**

```powershell
dcf ITX.MC --set g=2% --set modes=ventas,coste --set wacc_shift=1.5%
```

**Fijar un RONIC prudente**

```powershell
dcf IDR.MC --set ronic=10%
```

**Valor terminal por múltiplo de comparables**

```powershell
dcf IDR.MC --vt vt_mult --set exit_multiple=9
```

**Banco con valor terminal value driver y ROE propio**

```powershell
dcf SAN.MC --vt gordon_value_driver --set ronic=11%
```

**Tasa de descuento propia para un ticker**: en `market_inputs.toml`

```toml
[discount_rate."REP.MC"]
value = 0.085
source = "WACC propio: beta sectorial y prima país"
date = 2026-11-21
```

o para todos los tickers de una ejecución: `--set rate=8.5%`.

**Comparar modelos sobre la misma descarga**

```powershell
dcf IDR.MC --from-cache data\cache\IDR.MC\20261122T171254Z --model fcff
dcf IDR.MC --from-cache data\cache\IDR.MC\20261122T171254Z --model fcff_cfo
dcf IDR.MC --from-cache data\cache\IDR.MC\20261122T171254Z --model fcfe
```

**Copiar el informe en Markdown**

```powershell
dcf ITX.MC --raw > informe.md
```

**Valoración rápida sin escenarios**

```powershell
dcf ITX.MC SAN.MC --no-extras
```

---

## 11. Solución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| `dcf: El término "dcf" no se reconoce…` | El entorno `.venv` no está activado | `uv run dcf …` o `.\.venv\Scripts\Activate.ps1` (§2) |
| `python` no se encuentra o apunta a `WindowsApps\python.exe` | Alias de la Microsoft Store en el PATH | Usa `uv sync` / `uv run`, que no necesitan `python` en el PATH; o desactiva los alias en Configuración → Aplicaciones → Opciones avanzadas → Alias de ejecución de aplicaciones |
| `CertificateVerifyError` / `self signed certificate in certificate chain` al descargar | Red corporativa que inspecciona el tráfico HTTPS (proxy o cliente como Netskope) con un certificado que Python no reconoce | Apunta `SSL_CERT_FILE` y `CURL_CA_BUNDLE` a un fichero `.pem` que contenga las raíces públicas y las de tu empresa (pídelo a sistemas). Si funciona con VPN y no sin ella, faltan las raíces de uno de los dos caminos en ese fichero |
| `invalid peer certificate: UnknownIssuer` en `uv sync` | El mismo problema, en la descarga de paquetes | Igual que el anterior; o ejecuta `uv sync` en una sesión sin esas variables |
| `No existe … market_inputs.toml` o faltan claves | No has creado o completado el fichero de datos de mercado | §3.1 |
| `Falta el crecimiento terminal` | No hay `terminal_growth` en `settings.toml` ni `--set g=` | §3.2 |
| `terminal_growth (…) debe ser menor que el WACC` (o Ke, o rf) | g ≥ tasa de descuento o g ≥ rf | Baja g o revisa rf y la tasa |
| Beta negativa o ausente | Yahoo publica una beta negativa o ninguna | Una beta sectorial en `[sector_beta]` o una propia en `[beta."TICKER"]` (§7.2) |
| `falta la prima de riesgo país de "…"` | No hay `[country_risk_premium]` para el país de la empresa | Añádela en `market_inputs.toml` (0 si no tiene prima) |
| `Falta el múltiplo de salida para vt_mult` | `vt_mult` sin múltiplo | `--set exit_multiple=` o `[exit_multiple."TICKER"]` |
| `Falta el RONIC para gordon_value_driver` | No se puede calcular el ROIC histórico (faltan fondos propios o caja) | `--set ronic=` o `[ronic."TICKER"]` |
| `Yahoo: falta la fila '…'` | Yahoo no publica un dato obligatorio para ese modelo | Prueba otro modelo (p. ej. `fcff_cfo` no necesita D&A ni circulante) o revisa el ticker |
| `--from-cache solo admite un ticker` | `--from-cache` con varios tickers | Una ejecución por ticker |
| Un ticker falla dentro de un lote | Error de datos de esa empresa | Se valora el resto; el error aparece en la consola y en el resumen |

---

## 12. Referencia rápida

```powershell
dcf TICKER                                   # valorar una empresa
dcf T1 T2 T3                                 # varias, con resumen md + csv
dcf -f lista.txt -o carpeta                  # desde fichero, a otra carpeta
dcf TICKER --model fcff|fcff_cfo|fcfe|fcfe_fin
dcf TICKER --vt gordon|gordon_value_driver|vt_mult
dcf TICKER --set g=2% --set rate=8% --set ronic=10% --set exit_multiple=9
dcf TICKER --set modes=ventas,coste --set projection_years=7
dcf TICKER --from-cache data\cache\TICKER\<fecha>   # sin red
dcf TICKER --raw > informe.md                # Markdown sin formato
dcf TICKER --no-extras                       # sin escenarios
dcf --help                                   # ayuda
```

| Fichero | Para qué |
|---|---|
| `config/settings.toml` | g, años de proyección, escenarios |
| `config/data/market_inputs.toml` | rf, prima de riesgo, beta, Kd por defecto, tasa / múltiplo / RONIC por ticker |
| `config/company_types.toml` | Tipo de empresa → modelo y valor terminal |
| `config/thresholds.toml` | Umbrales de los avisos |
| `config/tickers/*.txt`, `tickers.example.txt` | Listas de tickers |
| `output/` | Informes y resúmenes |
| `data/cache/` | Descargas de Yahoo |
| [docs/metodologia.md](metodologia.md) | Fórmulas, supuestos y limitaciones |
