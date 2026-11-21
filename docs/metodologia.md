# Metodología DCF

Documento de referencia de las fórmulas del modelo. Se actualiza con cada cambio de fórmula.
Tasas en decimal (0.08 = 8 %). Importes en EUR, en unidades (no millones).

Hay dos modelos de valoración. El modelo se elige por tipo de empresa en
`config/company_types.toml` (clave `model`) o se fuerza con `dcf --model`:

| Modelo | Para | Flujo | Tasa | Secciones |
|---|---|---|---|---|
| `fcff_cfo` | Industriales (por defecto) | FCFF desde el CFO: Net Income × FCFF/Net Income | WACC | §1-§9 |
| `fcfe` | Bancos y aseguradoras | FCFE, flujo para el accionista | Ke | §10 (y las comunes de §1-§9) |

Código: `model/fcff_cfo_*`, `model/wacc.py`, `valuation/fcff_cfo*.py`, `valuation/enterprise.py`
(VE, puente, sensibilidad, escenarios), `reports/fcff_cfo_markdown.py` y
`reports/enterprise_markdown.py` para fcff_cfo; `model/fcfe_projection.py`, `valuation/fcfe*.py`
y `reports/fcfe_markdown.py` para fcfe. Común a los dos: `model/revenue_projection.py` (ventas
y Net Income), `model/cost_of_equity.py` (Ke y beta), `model/tax.py` (t efectivo),
`model/discount_rate.py`, `valuation/discounting.py`, `valuation/run.py`, `reports/format.py`.

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

"Obligatorio" se refiere al modelo `fcff_cfo`. Con FCFE solo son obligatorios ventas, Net
Income, fondos propios, acciones diluidas y cotización; el resto se carga si está (`None` si
no).

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
| CFO | Operating Cash Flow | cashflow | Obligatorio |
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

Se usan medias aritméticas simples: ḡ_hist, m̄, c̄.

**Años excluidos** (se avisa en el resultado; si no queda ningún año válido, error):

- BAI_i ≤ 0, o t_i fuera de [0, 1]: no se puede calcular FCFF_i, el año no entra en c̄.
- Net Income_i ≤ 0: c_i no tiene sentido económico, el año no entra en c̄.
- El margen neto sí incluye años con pérdidas (un margen negativo es información válida).

## 3. Proyección (horizonte 5 años)

**Ventas:**

- Con estimaciones de analistas: Ventas_{+1} (ejercicio en curso) y Ventas_{+2} son las estimadas.
  Sus crecimientos g_{+1}, g_{+2} se calculan respecto al año anterior. Los años +3..+5 crecen a
  la media de {g_{−3}, g_{−2}, g_{−1}, g_{+1}, g_{+2}}.
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
| β | Beta de la acción | Según `[beta].mode` de `market_inputs.toml` (ver abajo). Por defecto Yahoo Finance (5 años, datos mensuales) |
| Ke | CAPM: rf + β · PRM | — |
| Kd | Media de los Kd_i = Intereses_i / Deuda total_i | Históricos. Se excluyen años con deuda 0. Años sin intereses publicados: Kd_i = `[default_cost_of_debt]` |
| t | **Mediana** de los t_i = Provisión_i / BAI_i válidos | Históricos (mismos criterios de exclusión que §2). La mediana evita que un año anómalo (SCYR.MC 2023: 91,6 %) distorsione el ahorro fiscal |
| E | Cotización × acciones diluidas (valor de mercado) | Último dato |
| D | Deuda financiera total (valor contable) | Último balance |

Los pesos E/(D+E) y D/(D+E) deben sumar 1. Si D = 0, WACC = Ke y no se necesita Kd.

**Selección de la beta** (`[beta]` en `config/data/market_inputs.toml`, opcional):

| Modo | Beta usada | Error |
|---|---|---|
| `yahoo` (por defecto) | La de Yahoo | Si Yahoo no la publica o es negativa |
| `fichero` | La del fichero (override) | Si no hay beta en el fichero |
| `yahoo-fichero` | La de Yahoo; si no la publica o es negativa, la del fichero, con el motivo en el informe y en los avisos del WACC | Si hace falta la del fichero y no está |

- La beta del fichero lleva `value`, `source` y `date`. Puede ser general (`[beta]`) o por
  ticker (`[beta."REP.MC"]`); la del ticker prevalece campo a campo, también en `mode`.
- Una beta negativa no es válida: daría Ke < rf (p. ej. Repsol en Yahoo, β = −0,181, por la
  correlación negativa con el mercado en 2022). Una beta 0 se acepta (Ke = rf).
- El informe muestra la beta publicada por Yahoo y la utilizada, con fuente, fecha y modo.

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
- Gordon: VT = FCFF_N · (1 + g) / (WACC − g), con g < WACC y g < rf (error si no se cumple).
- VA del VT = VT · FD_N
- VE = VA de los flujos + VA del VT
- Múltiplo de salida: no implementado.

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
Los FCFF proyectados no dependen del WACC, así que solo cambian el descuento y el VT.

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

## 9. Informe

`uv run python -m dcf <TICKER>` muestra el informe en consola y lo guarda en
`output/<TICKER>_<fecha UTC>.md`. Secciones: compañía, WACC, históricos y proyecciones, valor
intrínseco (puente, escenarios y sensibilidad). Importes en millones de EUR con 1 decimal, valor
por acción con 2 decimales y tasas en % con 2 decimales, con redondeo comercial (mitad hacia
arriba) solo en la presentación.

En una terminal el informe se muestra formateado con `rich`; si la salida se redirige o se usa
`--raw`, se escribe el Markdown tal cual. El fichero `.md` guardado es siempre Markdown.

Con el modelo FCFE el informe cambia la sección 2 (solo Ke, sin WACC ni Kd), la 3 (fondos
propios, ROE y reinversión) y la 4 (sin puente deuda/caja; añade valor contable y P/VC).

**Resumen de un lote** (varios tickers): `output/resumen_<fecha UTC>.md` y `.csv`, una fila por
ticker con empresa, modelo, cotización, valor bajista / neutro / alcista y su margen potencial
= valor / cotización − 1, tasa de descuento (WACC o Ke) y g con sus fuentes (rf, PRM, beta y,
en FCFF, Kd y t), y todos los avisos (carga, modelo, tasa, proyección, escenarios no válidos).
Sin escenarios, bajista y alcista quedan vacíos y el neutro es la valoración central. Los
tickers que fallan se incluyen con su error. CSV con separador `;`, decimal `,` y UTF-8 con
BOM (Excel en español); números sin redondear, tasas y márgenes en decimal.

## 10. Modelo FCFE (bancos y aseguradoras)

En una financiera la deuda (depósitos, reservas técnicas) es la materia prima del negocio, no
su financiación, y el CFO incluye la variación de préstamos y depósitos (SAN.MC: CFO 2025 de
−14.835 M€). Por eso no se usa FCFF ni WACC: se valora directamente el flujo del accionista.

**Datos:** ventas, Net Income y fondos propios (Stockholders Equity) de cada ejercicio (§1).

**Ratios históricos:** crecimiento de ventas y margen neto como en §2. Se informa el ROE de
cada año (Net Income_i / FP_{i−1}), que el modelo no usa para proyectar.

**Proyección:** ventas y Net Income exactamente como en §3 (analistas +1/+2, después el
crecimiento medio; Net Income = ventas × margen medio). Los fondos propios crecen al ritmo de
las ventas y ese crecimiento se financia reteniendo beneficio (capital regulatorio):

- FP_0 = fondos propios del último ejercicio (debe ser > 0).
- Reinversión_t = g_t · FP_{t−1}, con g_t el crecimiento de ventas del año t.
- FCFE_t = Net Income_t − g_t · FP_{t−1}
- FP_t = FP_{t−1} · (1 + g_t)

**Descuento y valor terminal:** a Ke (CAPM, §4, misma selección de beta), a final de año.

- FCFE_{N+1} = Net Income_N · (1 + g) − g · FP_N: el beneficio crece a g y solo se retiene lo
  necesario para que los fondos propios crezcan a g. No se usa FCFE_N · (1 + g), porque la
  reinversión del año N corresponde a g_N y no al g terminal.
- VT = FCFE_{N+1} / (Ke − g), con g < Ke y g < rf (error si no se cumple).
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

