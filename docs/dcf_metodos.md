# Valoración por DCF: modelos, valor terminal y combinación

## 0. Marco común

$$V_0=\sum_{t=1}^{N}\frac{CF_t}{(1+r)^t}+\frac{VT_N}{(1+r)^N}$$

El valor de un activo es el valor presente de sus flujos esperados, descontados a una tasa ajustada por riesgo. Esa tasa es el coste del capital si se valora la empresa, o el coste del equity si se valora el equity ([Damodaran, *Intrinsic Valuation*](https://pages.stern.nyu.edu/~adamodar/pdfiles/dcfallA.pdf)).

Una valoración se construye en tres piezas: **modelo** (qué flujo se descuenta y a qué tasa), **horizonte explícito** (cuántos años se proyectan) y **valor terminal** (cómo se recoge lo que pasa después).

---

## 1. Modelos

### 1.1 FCFF descontado a WACC

Es el método más usado en la práctica. Según el CFA Institute, los modelos basados en FCFF se usan aproximadamente el doble que los basados en FCFE ([CFA Institute](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2024/free-cash-flow-valuation)).

$$FCFF=EBIT\,(1-t)+D\&A-CAPEX-\Delta NWC$$

$$WACC=\frac{E}{D+E}\,K_e+\frac{D}{D+E}\,K_d\,(1-t),\qquad K_e=r_f+\beta\,(ERP)$$

$$EV=\sum_{t=1}^{N}\frac{FCFF_t}{(1+WACC)^t}+\frac{VT_N}{(1+WACC)^N},\qquad E=EV-\text{Deuda neta}$$

Descuenta flujos antes de deuda, así que no depende directamente de la financiación. Su coherencia exige que la estructura de capital se mantenga o se modele explícitamente.

### 1.2 FCFE descontado a Ke

$$FCFE=FCFF-Int\,(1-t)+\Delta\text{Deuda neta}$$

$$E_0=\sum_{t=1}^{N}\frac{FCFE_t}{(1+K_e)^t}+\frac{VT_N}{(1+K_e)^N}$$

Útil cuando la deuda cambia de forma significativa o cuando no se quiere estimar el WACC. Con apalancamiento constante debería dar el mismo resultado que el FCFF. Damodaran señala que FCFE y FCFF dan el mismo valor del equity si se hacen de forma consistente, y que el FCFE es más difícil de estimar cuando la deuda varía ([UNM, FCFF](https://www.unm.edu/~maj/Security%20Analysis/FCFF.pdf)).

### 1.3 Modelo de dividendos (DDM) y Gordon

$$P_0=\sum_{t=1}^{\infty}\frac{D_t}{(1+K_e)^t}\;\;\xrightarrow{\;g\text{ constante}\;}\;\;P_0=\frac{D_1}{K_e-g}$$

Solo es razonable para empresas que reparten dividendos de forma estable. Con recompras o sin dividendos, el FCFE es preferible. Aquí el valor terminal es el propio Gordon: todo el modelo es una perpetuidad.

### 1.4 APV (Adjusted Present Value)

$$V_L=V_U+VPN(\text{escudos fiscales})$$

$$V_U=\sum_{t=1}^{N}\frac{FCFF_t}{(1+K_u)^t}+\frac{VT_N}{(1+K_u)^N},\qquad K_u=r_f+\beta_u\,(ERP)$$

Para deuda constante y permanente, una aproximación habitual es $VPN(\text{escudos})\approx T_c\cdot D$. Si la deuda cambia, los escudos se descuentan año a año a $K_d$. El APV separa el valor de una empresa apalancada en sus componentes ([Fiveable, Business Valuation](https://fiveable.me/business-valuation/unit-3)). Según la literatura, con apalancamiento constante APV, WACC y FCFE dan el mismo resultado ([Valuation 7.ª ed., Apéndice B](https://www.oreilly.com/library/view/valuation-7th-edition/9781119610885/b02.xhtml)). Es el método preferido en LBO y en estructuras con deuda variable.

### 1.5 Residual income / EVA

$$V_0=BV_0+\sum_{t=1}^{N}\frac{(ROE_t-K_e)\,BV_{t-1}}{(1+K_e)^t}+\frac{VT^{RI}_N}{(1+K_e)^N}$$

Parte del valor contable y añade solo el beneficio por encima del coste del equity. Con supuestos consistentes es equivalente al DDM o al FCFE, y es útil cuando el FCF es negativo en los primeros años, porque no depende de la inversión de caja.

---

## 2. Estructura temporal

Se aplica sobre los modelos 1.1, 1.2 y 1.4 para dividir el horizonte en fases.

- **Dos etapas**: una fase explícita de $N$ años y una fase de crecimiento estable.

$$V_0=\sum_{t=1}^{N}\frac{FCF_t}{(1+r)^t}+\frac{FCF_N(1+g)}{(r-g)(1+r)^N}$$

- **Tres etapas**: añade una fase de transición con crecimiento que decrece linealmente, normalmente con $g_1 > g_2 > g_\infty$.

El crecimiento debe ser consistente con la reinversión. La referencia de la UNM expresa el crecimiento del EBIT como tasa de reinversión por ROC ([UNM, FCFF](https://www.unm.edu/~maj/Security%20Analysis/FCFF.pdf)):

$$g=RR\cdot ROIC,\qquad RR=\frac{CAPEX-D\&A+\Delta NWC}{EBIT\,(1-t)}$$

---

## 3. Valor terminal: tres vías

Damodaran enumera tres formas de estimar el VT: liquidación, múltiplo o empresa en marcha con crecimiento constante ([Damodaran, *Damodaran on Valuation*](https://www.oreilly.com/library/view/damodaran-on-valuation/9780471751212/9780471751212_terminal_value.html)).

### 3.1 Liquidación

Valor de los activos acumulados en el año terminal, estimado como lo pagaría un tercero. Se usa cuando la empresa no va a seguir en marcha.

$$VT_N=\text{Valor de liquidación de activos en }N$$

### 3.2 Múltiplo de salida

$$VT_N=M\times EBITDA_N\quad(\text{o beneficio, ventas, valor contable})$$

El múltiplo $M$ suele tomarse de comparables. Ojo: si el múltiplo se basa en valoraciones de mercado de hoy, la valoración se apoya en el mercado y deja de ser intrínseca.

### 3.3 Crecimiento constante

**Gordon clásico:**

$$VT_N=\frac{FCF_{N+1}}{WACC-g}$$

**Gordon con *value driver* (recomendado):** el FCF terminal depende de la reinversión necesaria para sostener $g$:

$$VT_N=\frac{NOPAT_{N+1}\left(1-\dfrac{g}{RONIC}\right)}{WACC-g}$$

Corrige el problema del Gordon clásico, donde se puede suponer un $g$ alto sin pagar la inversión que lo produce. Damodaran advierte que el valor terminal puede dominar la valoración, así que la sensibilidad a $g$ y al WACC es crítica ([Damodaran, *Terminal value*](https://pages.stern.nyu.edu/~adamodar/pdfiles/country/TerminalValue.pdf)).

**Comprobación de consistencia:** despejar el $g$ implícito en el múltiplo y compararlo con el $g$ de partida. Si difieren mucho, uno de los dos supuestos no encaja con el resto del modelo. Con RONIC alto, la reinversión necesaria es baja y el valor sube. Un RONIC cercano al WACC en el largo plazo es una opción prudente, porque la ventaja competitiva tiende a erosionarse.

**VT por modelo** (cuando el modelo no es FCFF):

- Residual income: $VT^{RI}_N=\dfrac{(ROE_{N+1}-K_e)\,BV_N}{K_e-g}$
- FCFE o APV: el mismo Gordon con el flujo y la tasa del modelo ($K_e$ o $K_u$).

---

## 4. Combinar modelo y valor terminal

| Modelo | Tasa | VT más habitual | Nota |
|---|---|---|---|
| 1.1 FCFF-WACC | WACC | Gordon *value driver* y múltiplo de EV/EBITDA | Caso general |
| 1.2 FCFE | $K_e$ | Gordon sobre FCFE o múltiplo de P/E | VT de equity, no de empresa |
| 1.3 DDM / Gordon | $K_e$ | El propio Gordon | Solo con dividendos estables |
| 1.4 APV | $K_u$ (escudos a $K_d$) | Gordon *value driver* a $K_u$ | Deuda variable, LBO |
| 1.5 Residual income | $K_e$ | Residual de Gordon o múltiplo de P/B | Útil con FCF negativo |

Cualquier combinación es técnicamente posible, pero algunas exigen supuestos coherentes entre sí. Por ejemplo, un FCFE con deuda que crece fuerte no puede usar un Gordon con deuda constante sin ajustar la tasa.

---

## 5. Cómo se hace una valoración

1. **Elegir el modelo** según la estructura de deuda y la política de dividendos.
2. **Proyectar** los flujos explícitos durante $N$ años (dos o tres etapas si hace falta).
3. **Elegir el VT** y comprobar la consistencia: $g$ frente a reinversión, $g$ implícito del múltiplo, RONIC razonable.
4. **Calcular** EV o E y pasar al equity:
   $E=EV-\text{Deuda neta}-\text{Minoritarios}-\text{Pensiones}+\text{Caja no operativa}\pm\dots$
5. **Dividir** entre acciones diluidas para obtener el valor por acción.
6. **Contrastar**: sensibilidad al WACC y a $g$, y comparación entre modelos. Si FCFF, FCFE y residual income dan valores muy distintos, casi siempre hay supuestos incompatibles entre ellos.

Una valoración, por tanto, es la elección de **modelo + VT + horizonte**, con las comprobaciones de coherencia entre las tres.

---

## 6. Nota sobre la simplicidad

En una presentación, Damodaran afirma que los modelos simples suelen funcionar mejor que los complejos ([Damodaran, *Valuation: Art, Science or Magic?*](https://pages.stern.nyu.edu/~adamodar/pdfiles/country/val2dayDubai2017.pdf)). La afirmación se refiere a la complejidad del modelo en general; la fuente no indica qué método concreto tiene en mente.

---

## Tabla resumen

| Método (título de sección) | Flujo descontado | Tasa | Cuándo usarlo |
|---|---|---|---|
| 1.1 FCFF descontado a WACC | FCFF (antes de deuda) | WACC | Caso general, estructura de capital estable |
| 1.2 FCFE descontado a Ke | FCFE (para accionistas) | $K_e$ | Deuda variable, valor directo del equity |
| 1.3 Modelo de dividendos (DDM) y Gordon | Dividendos | $K_e$ | Empresas maduras que reparten dividendos |
| 1.4 APV (Adjusted Present Value) | FCFF (antes de deuda) más escudos fiscales | $K_u$ (escudos a $K_d$) | Apalancamiento variable, LBO |
| 1.5 Residual income / EVA | Beneficio menos coste del capital | $K_e$ | FCF negativo o poco fiable en los primeros años |

---

## Referencias

- Damodaran, *Investment Valuation* (Wiley) y notas en pages.stern.nyu.edu
- McKinsey, *Valuation* (Koller, Goedhart, Wessels)
- Damodaran, *Damodaran on Valuation*
- CFA Institute, *Equity Valuation* (Level II)
