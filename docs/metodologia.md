# Metodología DCF

Documento de referencia de las fórmulas del modelo. Se actualiza con cada cambio de fórmula.
Tasas en decimal (0.08 = 8 %). Importes en EUR, en unidades (no millones).

Hay cuatro modelos de flujo y tres métodos de valor terminal (VT), combinables. El modelo
y el VT se eligen por tipo de empresa en `config/company_types.toml` (claves `model` y `vt`,
con `[default]` para industriales) y se fuerzan con `dcf --model` y `dcf --vt`. Las fórmulas
de partida están en `docs/dcf_metodos.md`.

| Modelo | Para | Flujo | Tasa | Secciones |
|---|---|---|---|---|
| `fcff` | Industriales (por defecto) | FCFF = EBIT·(1−t) + D&A − Capex − ΔNWC | WACC | §11 (y §1-§9) |
| `fcff_cfo` | Industriales | FCFF desde el CFO: Net Income × FCFF/Net Income | WACC | §1-§9 |
| `fcfe` | Industriales, sobre todo con mucha deuda o deuda cambiante | FCFE = FCFF − Int·(1−t) + ΔDeuda neta | Ke | §13 |
| `fcfe_fin` | Bancos y aseguradoras | FCFE = Net Income − g · fondos propios | Ke | §10 |

| VT (`vt`) | Fórmula | Por defecto en |
|---|---|---|
| `gordon` | CF_N · (1 + g) / (r − g) | Bancos y aseguradoras |
| `gordon_value_driver` | Beneficio_N · (1 + g) · (1 − g / RONIC) / (r − g) | Industriales (`[default]`) |
| `vt_mult` | M × EBITDA_N (FCFF) o M × Net Income_N (FCFE) | — |

Detalle de los métodos de VT y de las comprobaciones de consistencia en §12.

Código: `model/fcff_projection.py`, `valuation/fcff*.py`, `reports/fcff_markdown.py` (fcff);
`model/fcff_cfo_*`, `valuation/fcff_cfo*.py`, `reports/fcff_cfo_markdown.py` (fcff_cfo);
`model/fcfe_projection.py`, `valuation/fcfe.py`, `valuation/fcfe_result.py`,
`reports/fcfe_markdown.py` (fcfe); `model/fcfe_fin_projection.py`, `valuation/fcfe_fin*.py`,
`reports/fcfe_fin_markdown.py` (fcfe_fin). Los dos FCFF comparten `model/wacc.py`,
`valuation/enterprise.py` (VE, puente, sensibilidad, escenarios) y
`reports/enterprise_markdown.py`; los dos FCFE, `valuation/equity.py`. Común a todos:
`model/revenue_projection.py` (ventas y Net Income), `model/cost_of_equity.py` (Ke y beta),
`model/tax.py` (t efectivo), `model/discount_rate.py`, `model/terminal_methods.py` (VT),
`model/checks.py` (avisos), `model/returns.py` (ROIC y ROE), `valuation/discounting.py`,
`valuation/run.py`, `reports/format.py`.

## 1. Datos históricos

Por cada ejercicio histórico (4 años anuales de Yahoo Finance):

| Dato | Significado |
|---|---|
| Revenues | Ventas |
| Net Income | Beneficio neto |
| CFO | Flujo de caja de operaciones |
| Capex | Inversión en activo fijo (importe positivo = salida de caja) |
| Intereses | Gasto financiero por intereses |
| Emisión de deuda | Deuda nueva obtenida en el año |
| Reembolso de deuda | Deuda devuelta en el año (importe positivo) |

### Correspondencia con Yahoo Finance

"Obligatorio" se refiere a los modelos `fcff`, `fcff_cfo` y `fcfe`, salvo que se indique.
Con `fcfe_fin` solo son obligatorios ventas, Net Income, fondos propios, acciones diluidas y
cotización; el resto se carga si está (`None` si no).

| Dato del modelo | Fila de Yahoo | Estado | Tratamiento |
|---|---|---|---|
| Ventas | Total Revenue | income_stmt | Obligatorio |
| Net Income | Net Income (atribuible a la dominante) | income_stmt | Obligatorio |
| Fondos propios | Stockholders Equity (atribuibles a la dominante) | balance_sheet | Obligatorio en FCFE (cada año); opcional en FCFF |
| Intereses | Interest Expense | income_stmt | Valor absoluto. Si falta: Kd por defecto × deuda total del año (ver abajo); sin Kd por defecto, error |
| EBIT | EBIT | income_stmt | Obligatorio |
| BAI | Pretax Income | income_stmt | Obligatorio |
| Provisión de impuestos | Tax Provision | income_stmt | Obligatorio |
| Acciones diluidas | Diluted Average Shares (último ejercicio) | income_stmt | Obligatorio |
| CFO | Operating Cash Flow | cashflow | Obligatorio solo en fcff_cfo |
| D&A | Depreciation And Amortization (cashflow; si no, income_stmt) | cashflow | Obligatorio en fcff y fcfe |
| Clientes | Accounts Receivable | balance_sheet | Obligatorio en fcff y fcfe |
| Existencias | Inventory | balance_sheet | 0 con aviso si falta (empresas sin existencias) |
| Proveedores | Accounts Payable | balance_sheet | Obligatorio en fcff y fcfe |
| Capex | Capital Expenditure | cashflow | Obligatorio, valor absoluto |
| Emisión de deuda | Issuance Of Debt | cashflow | 0 con aviso si falta |
| Reembolso de deuda | Repayment Of Debt | cashflow | 0 con aviso si falta, valor absoluto |
| Deuda total | Total Debt (incluye arrendamientos NIIF 16) | balance_sheet | Obligatorio |
| Caja | Cash Cash Equivalents And Short Term Investments | balance_sheet | Obligatorio |
| Minoritarios | Minority Interest | balance_sheet | 0 con aviso si falta |
| Cotización | info.currentPrice | info | Obligatorio |
| Beta | info.beta | info | Opcional en la carga; el modo de `[beta]` decide (§4) |
| Ventas estimadas +1, +2 | revenue_estimate "0y", "+1y" (avg) | revenue_estimate | Opcional, aviso si falta |

- **Años:** los 4 últimos ejercicios comunes a los tres estados; el ejercicio se identifica por el
  año de la fecha de cierre. Si falta un dato obligatorio en esos años, error.
- **Arrendamientos como deuda:** bajo NIIF 16 el CFO no resta los pagos de alquiler (van a
  financiación), así que se tratan como deuda en D, Kd y el puente a fondos propios.
- **Moneda:** importes de estados en `financialCurrency`; cotización en `currency` (las
  subunidades como GBp se pasan a la unidad principal); estimaciones en su columna `currency`.
  Cada moneda ≠ EUR se convierte con el cambio `{MONEDA}EUR=X` de Yahoo en el momento de la
  descarga, que queda registrado.
- **Intereses ausentes:** algunas empresas (p. ej. Apple desde 2024) no desglosan el gasto por
  intereses. Si `config/data/market_inputs.toml` incluye `[default_cost_of_debt]`, se estiman
  como Intereses_i = Kd_defecto · Deuda total_i, con aviso. Así el FCFF_i y el Kd_i de ese año
  son coherentes (Kd_i = Kd_defecto).
- **Acciones diluidas:** media diluida del último ejercicio (NIC 33). No recoge recompras ni
  emisiones posteriores al cierre.
- **Tipo de empresa:** se guardan `info.sector` e `info.industry` y se clasifica la empresa como
  `industrial`, `banco`, `aseguradora` o `inmobiliaria` con la tabla `config/company_types.toml`,
  que usa las claves `industryKey` (primero) y `sectorKey`. Lo que no encaja es `industrial`;
  sin sector ni industria queda sin clasificar, con aviso. La misma tabla fija el modelo de
  cada tipo (`model`): `fcfe` para bancos y aseguradoras, `fcff_cfo` para el resto. Modelos
  adecuados: industrial → fcff_cfo; banco y aseguradora → fcfe; inmobiliaria → ninguno de los dos
  (el valor está en los activos: NAV, FFO). Si el modelo aplicado no es adecuado para el tipo
  (o el tipo no se ha clasificado), se valora igual, pero el informe y el resumen de la línea
  de comandos lo avisan.

## 2. Ratios históricos

Para cada año histórico *i*:

- Crecimiento de ventas: g_i = Ventas_i / Ventas_{i−1} − 1 (con 4 años hay 3 crecimientos: −3, −2, −1)
- Margen neto: m_i = Net Income_i / Ventas_i
- Tipo impositivo efectivo: t_i = Provisión de impuestos_i / BAI_i
- FCFF histórico: FCFF_i = CFO_i + Intereses_i · (1 − t_i) − Capex_i
- Conversión a caja: c_i = FCFF_i / Net Income_i

Se suman los intereses después de impuestos porque el CFO ya los ha restado y el FCFF es el
flujo para todos los financiadores (accionistas y acreedores).

Se usan **medianas** de los años válidos: ḡ_hist, m̄, c̄. Con 4 años, la mediana es la
media de los dos valores centrales, así que un año atípico (p. ej. un circulante que
infla el CFO o un beneficio extraordinario) no arrastra el ratio que se proyecta. Lo
mismo se aplica a los ratios de §10, §11 y §13 y al ROIC / ROE de §12.

**Años excluidos** (se avisa en el resultado; si no queda ningún año válido, error):

- BAI_i ≤ 0, o t_i fuera de [0, 1]: no se puede calcular FCFF_i, el año no entra en c̄.
- Net Income_i ≤ 0: c_i no tiene sentido económico, el año no entra en c̄.
- El margen neto sí incluye años con pérdidas (un margen negativo es información válida).

## 3. Proyección (horizonte 5 años)

**Ventas:**

- Con estimaciones de analistas: Ventas_{+1} (ejercicio en curso) y Ventas_{+2} son las estimadas.
  Sus crecimientos g_{+1}, g_{+2} se calculan respecto al año anterior. Los años +3..+5 crecen a
  la mediana de {g_{−3}, g_{−2}, g_{−1}, g_{+1}, g_{+2}}.
- Sin estimaciones: todos los años crecen a ḡ_hist.

**Flujos:**

- Net Income_t = Ventas_t · m̄
- FCFF_t = Net Income_t · c̄

## 4. WACC

WACC = E/(D+E) · Ke + D/(D+E) · Kd · (1 − t)

| Componente | Cálculo | Fuente |
|---|---|---|
| rf | Rentabilidad libre de riesgo | `config/data/market_inputs.toml` (valor, fuente y fecha que introduce el usuario) |
| PRM | Prima de riesgo de mercado | `config/data/market_inputs.toml` |
| β | Beta de la acción | Según `[beta].mode` de `market_inputs.toml` (ver abajo). Por defecto bottom-up: beta sectorial reapalancada o, sin ella, la de Yahoo ajustada por Blume |
| Ke | máx(CAPM, suelo): CAPM = rf + β · PRM; suelo = rf + PRM + prima de riesgo país | Prima país en `[country_risk_premium."PAÍS"]` de `market_inputs.toml` |
| Kd | Media de los Kd_i = Intereses_i / Deuda total_i | Históricos. Se excluyen años con deuda 0. Años sin intereses publicados: Kd_i = `[default_cost_of_debt]` |
| t | **Mediana** de los t_i = Provisión_i / BAI_i válidos | Históricos (mismos criterios de exclusión que §2). La mediana evita que un año anómalo (SCYR.MC 2023: 91,6 %) distorsione el ahorro fiscal |
| E | Cotización × acciones diluidas (valor de mercado) | Último dato |
| D | Deuda financiera total (valor contable) | Último balance |

Los pesos E/(D+E) y D/(D+E) deben sumar 1. Si D = 0, WACC = Ke y no se necesita Kd.

**Selección de la beta** (`[beta]` en `config/data/market_inputs.toml`, opcional):

| Modo | Beta usada | Error |
|---|---|---|
| `bottom-up` (por defecto) | Beta sectorial desapalancada βu de `[sector_beta."CLAVE"]` (clave de industria de Yahoo y, si no está, la de sector), reapalancada: β = βu · (1 + (1 − t) · D / E). Sin beta sectorial: la de Yahoo ajustada por Blume, β = 0,67 · β_Yahoo + 0,33. Si Yahoo no la publica o es negativa, la del fichero (`[beta]`) | Si no hay beta sectorial, ni de Yahoo válida, ni del fichero |
| `yahoo` | La de Yahoo, sin ajustar | Si Yahoo no la publica o es negativa |
| `fichero` | La del fichero (override) | Si no hay beta en el fichero |
| `yahoo-fichero` | La de Yahoo; si no la publica o es negativa, la del fichero, con el motivo en el informe y en los avisos del WACC | Si hace falta la del fichero y no está |

- La beta del fichero lleva `value`, `source` y `date`. Puede ser general (`[beta]`) o por
  ticker (`[beta."REP.MC"]`); la del ticker prevalece campo a campo, también en `mode`.
- Una beta negativa no es válida: daría Ke < rf (p. ej. Repsol en Yahoo, β = −0,181, por la
  correlación negativa con el mercado en 2022). Una beta 0 se acepta (Ke = rf).
- **Bottom-up:** D es la deuda total contable, E la capitalización (cotización × acciones
  diluidas) y t la mediana de los tipos efectivos. La beta sectorial (p. ej. las
  desapalancadas de Damodaran por industria) la introduce el usuario con fuente y fecha.
  En `fcfe_fin` se usa sin reapalancar: la deuda de un banco o una aseguradora es su materia
  prima, y sus betas sectoriales ya se publican apalancadas.
- **Blume** (1971): la beta de regresión tiende a 1 con el tiempo; 0,67 · β + 0,33 es la
  beta ajustada que publica Bloomberg. Peso en `src/dcf/defaults.py` (`BLUME_WEIGHT`).
- El informe muestra la beta publicada por Yahoo y la utilizada, con fuente, fecha, modo y,
  si se usa una de respaldo, el motivo.

**Suelo de Ke por riesgo país.** Ke = máx(rf + β · PRM, rf + 1 · PRM + CRP), con CRP la
prima de riesgo país del país de la sede (`info.country` de Yahoo, p. ej. "Spain") en
`[country_risk_premium."Spain"]` de `market_inputs.toml` (value ≥ 0, source, date). Ninguna
acción se descuenta a menos que el mercado de su país. Si Yahoo no publica el país o falta
su prima, error (para un país sin prima, value = 0). Se aplica al Ke de los cuatro
modelos (en los FCFF, dentro del WACC); con tasa de descuento forzada no se aplica.

- **Cuidado con la doble cuenta:** si la PRM ya es la prima total de un país (p. ej. la
  «Total Equity Risk Premium» de Damodaran para España, que suma la madura y la del país),
  la prima país del fichero debe ser 0; si la PRM es la de un mercado maduro, la prima país
  es la «Country Risk Premium».

**Tasa de descuento forzada** (WACC en FCFF, Ke en FCFE). Precedencia:

1. Argumento `--set rate=8%` (o `discount_rate=`): todos los tickers de la ejecución.
2. `[discount_rate."TICKER"]` en `market_inputs.toml`, con `value`, `source` y `date`: solo
   ese ticker. No hay valor general en el fichero.
3. La calculada (§4 para el WACC, CAPM para Ke).

- Con tasa forzada, la calculada se muestra solo como información y, si no se puede calcular
  (p. ej. beta negativa o sin Kd), pasa a ser un aviso en lugar de un error.
- El descuento, el valor terminal, la sensibilidad y los escenarios (modo `coste`, desplazados
  desde la tasa forzada) usan la tasa forzada; se sigue validando g < tasa y g < rf.
- La tasa forzada debe ser positiva. El informe y el resumen del lote indican que está
  forzada, su fuente y fecha, y la tasa calculada.

## 5. Descuento y valor terminal

- Descuento a final de año: FD_k = 1 / (1 + WACC)^k, con k entero = 1, 2, …, N (el +1 es el ejercicio en curso).
- VA de los flujos = Σ FCFF_k · FD_k
- VT según el método elegido (§12); en todos, g < WACC y g < rf (error si no se cumple).
  Gordon clásico: VT = FCFF_N · (1 + g) / (WACC − g).
- VA del VT = VT · FD_N
- VE = VA de los flujos + VA del VT

Se informa siempre el peso del VT descontado sobre el VE.

## 6. Valor por acción

Fondos propios = VE − deuda total + caja − minoritarios

Valor por acción = Fondos propios / acciones diluidas

Es equivalente a (VE − deuda neta − minoritarios) / acciones diluidas, con deuda neta = deuda − caja.
Nunca se resta la deuda neta y se suma la caja a la vez.

**Limitaciones conocidas:**

- No se suman asociadas ni otros activos no operativos, ni se restan preferentes, pensiones o
  arrendamientos (NIIF 16).
- Se suma toda la caja, no solo la excedente.
- El FCFF sale del CFO, que puede incluir intereses cobrados por la caja y dividendos de
  asociadas. Ese rendimiento ya está en el VE, así que sumar la caja lo cuenta en parte dos veces.
  Suele ser un efecto pequeño.

## 7. Sensibilidad

Tabla de valor por acción con WACC (filas) × g terminal (columnas), centrada en los valores
de la valoración. Pasos en `src/dcf/defaults.py`. Las celdas con g ≥ WACC o g ≥ rf quedan vacías (NaN).
Los FCFF proyectados no dependen del WACC, así que solo cambian el descuento y el VT, que se
recalcula con el mismo método (§12). Con `vt_mult` el VT no depende de g ni de la tasa: solo
cambia el descuento.

## 8. Escenarios

Se configuran en `config/settings.toml` (`[scenarios]`). Hay dos modos combinables:

| Modo | Bajista | Neutro | Alcista |
|---|---|---|---|
| `ventas` | Ventas +1/+2 = estimación **baja** de analistas | Estimación media | Estimación **alta** |
| `coste` | WACC + `wacc_shift`, g − `growth_shift` | WACC y g centrales | WACC − `wacc_shift`, g + `growth_shift` |

- Con los dos modos, el bajista combina estimación baja con WACC↑ y g↓, y el alcista al revés.
- En el modo `ventas`, los años +3..+5 crecen a la media de los crecimientos históricos y de los
  +1/+2 de **ese** escenario. Si falta la estimación baja o alta, se usa la media (con aviso).
  Sin estimaciones de analistas, los tres escenarios usan el crecimiento histórico.
- Márgenes, conversión FCFF/Net Income y el puente a fondos propios son comunes a todos.
- Un escenario que incumple g < WACC o g < rf se marca como no válido en el informe; no detiene
  la valoración.
- **Exclusión por g implícito:** un escenario bajista o alcista cuyo g implícito en el VT
  (§12) difiere más de `scenario_growth_gap` (1 punto por defecto,
  `config/thresholds.toml`) de su g se excluye: se marca no válido, con el motivo, y queda
  vacío en el resumen. La valoración central (neutro) nunca se excluye; si la incumple, el
  aviso de g implícito de §12 lo indica. Con `gordon` el g implícito es el g y nunca se
  excluye.

## 9. Informe

`uv run python -m dcf <TICKER>` muestra el informe en consola y lo guarda en
`output/<TICKER>_<fecha UTC>.md`. Secciones: compañía, WACC, históricos y proyecciones, valor
intrínseco (puente, escenarios y sensibilidad). La columna resumen de la tabla de históricos
es la mediana (§2). Importes en millones de EUR con 1 decimal, valor
por acción con 2 decimales y tasas en % con 2 decimales, con redondeo comercial (mitad hacia
arriba) solo en la presentación.

En una terminal el informe se muestra formateado con `rich`; si la salida se redirige o se usa
`--raw`, se escribe el Markdown tal cual. El fichero `.md` guardado es siempre Markdown.

Con el modelo FCFE el informe cambia la sección 2 (solo Ke, sin WACC ni Kd), la 3 (fondos
propios, ROE y reinversión) y la 4 (sin puente deuda/caja; añade valor contable y P/VC).

En los modelos fcff, fcff_cfo y fcfe, la tabla de históricos (3.1) incluye EBIT_i y margen EBIT,
NOPAT_i = EBIT_i · (1 − t), con t la mediana de los tipos efectivos; capital invertido_i = deuda total + fondos
propios − caja al cierre; y ROIC_i = NOPAT_i / capital invertido_{i−1}, con su mediana (el RONIC
histórico del value driver, §12). El primer año no tiene ROIC (falta el capital inicial). En
fcfe_fin se muestra el ROE.
En fcfe, entre el FCFF y el capital invertido, se muestra el paso al FCFE histórico:
− intereses · (1 − t), deuda neta (deuda total − caja), + ΔDeuda neta y FCFE_i (§12).

La sección 4 incluye la subsección **Valor terminal** (método, fórmula, datos del año N, VT,
g implícito y múltiplo implícito) y **Comprobaciones de consistencia** con los avisos de §12.

**Resumen de un lote** (varios tickers): `output/resumen_<fecha UTC>.md` y `.csv`, una fila por
ticker con empresa, modelo, método de VT, cotización, valor bajista / neutro / alcista y su margen potencial
= valor / cotización − 1, tasa de descuento (WACC o Ke) y g con sus fuentes (rf, PRM, beta y,
en FCFF, Kd y t), y todos los avisos (carga, modelo, tasa, proyección, escenarios no válidos
y comprobaciones de consistencia).
Sin escenarios, bajista y alcista quedan vacíos y el neutro es la valoración central. Los
tickers que fallan se incluyen con su error. CSV con separador `;`, decimal `,` y UTF-8 con
BOM (Excel en español); números sin redondear, tasas y márgenes en decimal.

## 10. Modelo FCFE_FIN (bancos y aseguradoras)

Antes se llamaba `fcfe`; ese nombre es ahora el FCFE 1.2 para industriales (§13).

En una financiera la deuda (depósitos, reservas técnicas) es la materia prima del negocio, no
su financiación, y el CFO incluye la variación de préstamos y depósitos (SAN.MC: CFO 2025 de
−14.835 M€). Por eso no se usa FCFF ni WACC: se valora directamente el flujo del accionista.

**Datos:** ventas, Net Income y fondos propios (Stockholders Equity) de cada ejercicio (§1).

**Ratios históricos:** crecimiento de ventas y margen neto como en §2. Se informa el ROE de
cada año (Net Income_i / FP_{i−1}), que el modelo no usa para proyectar.
La tabla de históricos muestra también el FCFE_i = Net Income_i − (FP_i − FP_{i−1}): el
beneficio que no se retiene en fondos propios (dividendos y recompras netos de emisiones).

**Proyección:** ventas y Net Income exactamente como en §3 (analistas +1/+2, después el
crecimiento medio; Net Income = ventas × margen medio). Los fondos propios crecen al ritmo de
las ventas y ese crecimiento se financia reteniendo beneficio (capital regulatorio):

- FP_0 = fondos propios del último ejercicio (debe ser > 0).
- Reinversión_t = g_t · FP_{t−1}, con g_t el crecimiento de ventas del año t.
- FCFE_t = Net Income_t − g_t · FP_{t−1}
- FP_t = FP_{t−1} · (1 + g_t)

**Descuento y valor terminal:** a Ke (CAPM, §4, misma selección de beta), a final de año. El
VT sigue el método elegido (§12); por defecto, Gordon clásico.

- `gordon`: VT = FCFE_N · (1 + g) / (Ke − g).
- `gordon_value_driver`: VT = Net Income_N · (1 + g) · (1 − g / ROE) / (Ke − g), con ROE el
  histórico medio (Net Income_i / FP_{i−1}) o el forzado. Con ROE = Net Income_{N+1} / FP_N
  coincide con la fórmula anterior de este modelo, Net Income_N · (1 + g) − g · FP_N.
- `vt_mult`: VT = P/E × Net Income_N.
- En todos, g < Ke y g < rf (error si no se cumple).
- Fondos propios = Σ FCFE_k / (1 + Ke)^k + VT / (1 + Ke)^N (debe ser > 0).

**Valor por acción** = Fondos propios / acciones diluidas. No hay puente: el FCFE ya es del
accionista y el Net Income es el atribuible a la dominante, así que no se restan minoritarios
ni se suma caja. El informe añade el valor contable por acción (FP_0 / acciones) y el P/VC
implícito como control de coherencia.

**Sensibilidad y escenarios:** como en §7-§8, con Ke en lugar del WACC (el modo `coste`
desplaza Ke con `wacc_shift`).

**Limitaciones conocidas:**

- Supone un ratio fondos propios / ventas constante; no modela el capital regulatorio (CET1 ×
  activos ponderados por riesgo) ni el exceso de capital actual, que se reparte implícitamente
  solo a través del valor terminal.
- Con crecimientos de ventas altos la reinversión puede superar al beneficio y dar FCFE
  negativos en el horizonte.
- No resta dividendos preferentes ni cupones de instrumentos AT1, si Yahoo no los descuenta ya
  del Net Income.
- Las betas de Yahoo de algunas financieras son muy bajas (CABK.MC 0,12; MAP.MC 0,29 el
  2026-11-19): conviene revisarlas con `[beta]` en `market_inputs.toml`.

## 11. Modelo FCFF (desde el EBIT; por defecto en industriales)

Fórmula 1.1 de `docs/dcf_metodos.md`:

FCFF = EBIT · (1 − t) + D&A − Capex − ΔNWC

**Ratios históricos** (medianas de los 4 años, como t; §2):

- Margen EBIT = EBIT_i / Ventas_i; D&A / ventas; Capex / ventas.
- Circulante comercial NWC_i = clientes_i + existencias_i − proveedores_i; NWC / ventas.
- t = mediana de los tipos efectivos (§4).
- FCFF histórico_i = EBIT_i · (1 − t) + D&A_i − Capex_i − (NWC_i − NWC_{i−1}), desde el
  segundo año.

**Proyección:** ventas como en §3. Para cada año t:

- NOPAT_t = Ventas_t · margen EBIT · (1 − t)
- D&A_t = Ventas_t · D&A/ventas; Capex_t = Ventas_t · Capex/ventas
- NWC_t = Ventas_t · NWC/ventas; ΔNWC_t = NWC_t − NWC_{t−1}, con NWC_0 el último histórico.
  Un NWC negativo (proveedores > clientes + existencias) genera caja al crecer.
- FCFF_t = NOPAT_t + D&A_t − Capex_t − ΔNWC_t

**Descuento, VT y puente:** como en §5-§6 (WACC, final de año, VE − deuda + caja −
minoritarios), con el VT de §12.

## 12. Valor terminal y comprobaciones de consistencia

`r` es la tasa del modelo (WACC en fcff y fcff_cfo, Ke en fcfe y fcfe_fin) y `CF_N` el flujo
del último año proyectado (FCFF o FCFE).

| Método | Fórmula | Datos del año N |
|---|---|---|
| `gordon` | VT = CF_N · (1 + g) / (r − g) | CF_N |
| `gordon_value_driver` | VT = Beneficio_N · (1 + g) · (1 − g / RONIC) / (r − g) | NOPAT_N y RONIC (FCFF); Net Income_N y ROE (FCFE) |
| `vt_mult` | VT = M × métrica_N | EBITDA_N y EV/EBITDA (FCFF); Net Income_N y P/E (FCFE) |

- **Value driver:** g / RONIC es la parte del beneficio que hay que reinvertir para crecer a
  g. Con RONIC = r el crecimiento no crea valor (VT = Beneficio_N · (1 + g) / r).
  - NOPAT_N: en fcff, el de la proyección; en fcff_cfo, Ventas_N · margen EBIT medio · (1 − t).
  - RONIC por precedencia: `--set ronic=` > `[ronic."TICKER"]` de `market_inputs.toml` >
    ROIC histórico mediano, ROIC_i = NOPAT_i / capital invertido_{i−1}, con capital invertido
    = deuda total + fondos propios − caja. En los FCFE, el análogo es el ROE histórico
    mediano (Net Income_i / FP_{i−1}). Sin RONIC disponible, error.
- **Múltiplo de salida:** precedencia `--set exit_multiple=` > `[exit_multiple."TICKER"]` de
  `market_inputs.toml` (con fuente y fecha); sin múltiplo, error. EBITDA_N = EBIT_N + D&A_N
  (en fcff_cfo, ventas_N · (margen EBIT + D&A/ventas) medios; sin D&A, no disponible).
- **g implícito:** el g que, con Gordon clásico sobre CF_N, da el mismo VT:
  g_impl = (r · VT − CF_N) / (VT + CF_N). Se informa siempre, junto con el múltiplo implícito
  VT / métrica_N.

**Comprobaciones (avisos, no detienen la valoración).** Se muestran en el informe
(«Comprobaciones de consistencia») y en el resumen del lote:

| Aviso | Condición | Umbral (`config/thresholds.toml`, `[warnings]`) |
|---|---|---|
| Flujo histórico negativo | FCFF_i < 0 (o FCFE_i en los FCFE) | — |
| Último año atípico | \|CF_último − media de los anteriores\| / \|media\| > umbral; por encima, posible sobrevaloración si es puntual | `last_flow_deviation` = 0.33 |
| VT incoherente | \|g_impl − g\| > umbral (value driver y múltiplo) | `implied_growth_gap` = 0.0075 (0,75 puntos) |
| RONIC muy alto | RONIC (o ROE) > umbral × r: supone una ventaja competitiva duradera; un RONIC cercano a r es más prudente | `ronic_to_rate` = 2 |
| VT muy incoherente | \|g_impl − g\| > umbral: el aviso de «VT incoherente» añade que un escenario así se excluiría (§8) | `scenario_growth_gap` = 0.01 (1 punto) |

- Los flujos históricos comprobados: FCFF en fcff y fcff_cfo (el de cada modelo); FCFE
  (FCFF_i − Int_i·(1−t) + ΔDeuda neta_i) y FCFF en fcfe; Net Income_i − ΔFP_i en fcfe_fin.
- `config/thresholds.toml` es opcional (`dcf --thresholds` usa otro); sin él, los valores de
  `src/dcf/defaults.py`. Claves desconocidas o valores no positivos → error.

## 13. Modelo FCFE para industriales (fórmula 1.2)

Fórmula 1.2 de `docs/dcf_metodos.md`: FCFE = FCFF − Int · (1 − t) + ΔDeuda neta. Útil en
empresas con mucha deuda o con una deuda que cambia mucho, donde el WACC con pesos constantes
encaja peor.

**Supuestos de deuda:**

- FCFF_t como en §11.
- Kd = media de los Kd_i (§4); t = mediana de los tipos efectivos.
- D/(D+E) con D contable (deuda total) y E a mercado (cotización × acciones diluidas),
  constante: la deuda neta financia esa parte de la reinversión neta.
- DN_0 = deuda total − caja del último balance.

**Proyección:**

- Intereses_t = Kd · DN_{t−1}
- Reinversión neta_t = Capex_t − D&A_t + ΔNWC_t
- ΔDeuda neta_t = D/(D+E) · reinversión neta_t; DN_t = DN_{t−1} + ΔDeuda neta_t
- FCFE_t = FCFF_t − Intereses_t · (1 − t) + ΔDeuda neta_t
- Net Income_t = (EBIT_t − Intereses_t) · (1 − t) (base del value driver y del P/E)

**Descuento y valor:** a Ke (CAPM, §4), a final de año, con el VT de §12.
Valor descontado = Σ FCFE_k / (1 + Ke)^k + VT / (1 + Ke)^N. El FCFF es consolidado, así que
fondos propios = valor descontado − minoritarios. No se suma caja ni se resta deuda: ya están
en el flujo (intereses y variación de deuda neta).

**Limitaciones:** el apalancamiento D/(D+E) es constante y a valor de mercado del momento; el
Kd es el histórico medio; la caja inicial reduce la deuda neta y, con ella, los intereses.
