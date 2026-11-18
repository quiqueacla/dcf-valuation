# Metodología DCF

Documento de referencia de las fórmulas del modelo. Se actualiza con cada cambio de fórmula.
Tasas en decimal (0.08 = 8 %). Importes en EUR, en unidades (no millones).

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

| Dato del modelo | Fila de Yahoo | Estado | Tratamiento |
|---|---|---|---|
| Ventas | Total Revenue | income_stmt | Obligatorio |
| Net Income | Net Income (atribuible a la dominante) | income_stmt | Obligatorio |
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
| Beta | info.beta | info | Obligatorio |
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
| β | Beta de la acción | Yahoo Finance (5 años, datos mensuales). Si falta, error |
| Ke | CAPM: rf + β · PRM | — |
| Kd | Media de los Kd_i = Intereses_i / Deuda total_i | Históricos. Se excluyen años con deuda 0. Años sin intereses publicados: Kd_i = `[default_cost_of_debt]` |
| t | Media de los t_i = Provisión_i / BAI_i válidos | Históricos (mismos criterios de exclusión que §2) |
| E | Cotización × acciones diluidas (valor de mercado) | Último dato |
| D | Deuda financiera total (valor contable) | Último balance |

Los pesos E/(D+E) y D/(D+E) deben sumar 1. Si D = 0, WACC = Ke y no se necesita Kd.

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
