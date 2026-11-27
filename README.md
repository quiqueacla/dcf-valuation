# dcf-valuation

Valoración de empresas por flujos de caja descontados (FCFF descontado al WACC) con datos de
Yahoo Finance, escenarios bajista / neutro / alcista e informe en Markdown.

> Herramienta educativa y analítica. Sus resultados no son recomendación de inversión.

## Instalación

Requiere Python ≥ 3.12. Se recomienda [uv](https://docs.astral.sh/uv/): instala él mismo la
versión de Python necesaria y no pide permisos de administrador. Dependencias: `yfinance`,
`pandas`, `numpy`, `rich`. Detalle en el [manual de usuario](docs/manual_usuario.md#2-instalación).

### Windows (PowerShell)

1. Instala uv (una sola vez) y abre una terminal nueva:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   O con winget: `winget install --id=astral-sh.uv -e`.

2. Descarga el proyecto e instala el entorno:

   ```powershell
   git clone https://github.com/quiqueacla/dcf-valuation.git
   cd dcf-valuation
   uv sync
   uv run dcf --help
   ```

   `uv sync` crea `.venv` con Python 3.12 o superior, las dependencias (también las de
   desarrollo) y el comando `dcf`. Antepón `uv run` a cada comando, o activa el entorno una
   vez por terminal con `.\.venv\Scripts\Activate.ps1` (si PowerShell bloquea el script:
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`).

No uses `python -m venv` si no tienes Python instalado: en Windows, `python` suele ser el
acceso directo de Microsoft Store y falla («No se encontró Python» o «No se pudo ejecutar el
programa python.exe»). uv no lo necesita.

### Red corporativa con inspección TLS (Windows)

Si la red de tu empresa inspecciona el tráfico HTTPS (Netskope, Zscaler…), pueden fallar:

- `uv sync`, con `invalid peer certificate: UnknownIssuer`;
- la descarga de Yahoo (`dcf TICKER`), con `curl: (60) SSL certificate … self signed
  certificate in certificate chain`.

La CA corporativa está instalada en Windows, pero uv y `curl_cffi` (lo usa yfinance) no leen
el almacén de Windows. Una variable `SSL_CERT_FILE` que apunte a un `.pem` antiguo o con solo
una CA también rompe uv. Solución: genera un `.pem` con los certificados de Windows y úsalo
en las dos variables:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows_ca_bundle.ps1 -SetUserEnv
```

Abre una terminal nueva y repite `uv sync`. El script guarda el fichero en
`%USERPROFILE%\.certs\ca_windows.pem` y las variables de usuario `SSL_CERT_FILE` (uv) y
`CURL_CA_BUNDLE` (yfinance). Sin `-SetUserEnv` no cambia nada persistente: ejecútalo con
`. .\scripts\windows_ca_bundle.ps1` para que valga solo en esa terminal. Vuelve a generarlo
si cambia la CA corporativa. Si ya tenías `SSL_CERT_FILE` para otra herramienta, comprueba que
siga funcionando con el nuevo fichero (incluye todas las CA de Windows).

### Linux, macOS y WSL

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # instala uv en ~/.local/bin
git clone https://github.com/quiqueacla/dcf-valuation.git
cd dcf-valuation
uv sync && source .venv/bin/activate                # o: uv run dcf ...
dcf --help
```

**WSL sobre una carpeta de Windows** (`/mnt/c/...`): un mismo `.venv` no sirve a la vez para
Windows y Linux. Usa otro entorno en WSL:

```bash
uv venv --python 3.12 .venv-wsl                     # uv descarga Python 3.12 si no lo tienes
source .venv-wsl/bin/activate
uv pip install -e ".[dev]"
```

**Sin uv, con Python 3.10 / 3.11 del sistema** (p. ej. Ubuntu 22.04): `pip install -e .`
falla con `requires a different Python: 3.10.x not in '>=3.12'`. Instala 3.12 sin tocar el
Python del sistema:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update && sudo apt install python3.12 python3.12-venv
python3.12 -m venv .venv-wsl && source .venv-wsl/bin/activate
pip install -e ".[dev]"
```

## Configuración (antes de la primera valoración)

1. Revisa `config/data/market_inputs.toml`: rentabilidad libre de riesgo, prima de riesgo de
   mercado, primas de riesgo país y coste de la deuda por defecto, cada uno con su fuente y su
   fecha. El repositorio trae los de enero de 2026; actualízalos antes de valorar.
   `config/data/market_inputs.example.toml` es la plantilla comentada.
2. Fija el crecimiento terminal en `config/settings.toml` (`terminal_growth`) o pásalo con
   `--set g=2%`. En el mismo fichero se eligen los modos de escenario (`ventas`, `coste`).
3. Opcional: revisa `config/company_types.toml`, la tabla que clasifica cada empresa como
   industrial, banco, aseguradora o inmobiliaria según su sector e industria de Yahoo y fija su
   modelo y su método de valor terminal (VT). Por defecto (`[default]`): **fcff** (FCFF desde
   el EBIT, al WACC) con **gordon_value_driver**; bancos y aseguradoras: **fcfe_fin** (flujo
   para el accionista, a Ke) con **gordon**. Las inmobiliarias usan `[default]` y el informe
   avisa de que el modelo puede no ser adecuado.
4. Opcional: ajusta los umbrales de los avisos de consistencia en `config/thresholds.toml`.

Las rutas por defecto son relativas a la carpeta del proyecto: ejecuta `dcf` desde ella o
indica los ficheros con `-c`, `-m` y `-t`.

## Uso rápido

```bash
dcf ITX.MC SAN.MC AAPL                          # informes en ./output
dcf -f tickers.example.txt -o informes          # lista desde fichero
dcf -c config/settings.toml -f tickers.example.txt
dcf ITX.MC --set g=2% --set modes=ventas,coste  # ajustar supuestos sin tocar el fichero
dcf ITX.MC --set wacc_shift=1.5% --set projection_years=7
python -m dcf ITX.MC --no-extras                # sin escenarios (más rápido)
dcf SAN.MC MAP.MC                               # financieras: fcfe_fin + gordon automático
dcf SAN.MC --model fcff_cfo                     # forzar un modelo (avisa si no es adecuado)
dcf IDR.MC --model fcfe --vt gordon             # combinar modelo y valor terminal
dcf IDR.MC --vt vt_mult --set exit_multiple=10  # VT por múltiplo de salida (EV/EBITDA)
dcf IDR.MC --set ronic=12%                      # RONIC del value driver (por defecto, ROIC histórico)
dcf ITX.MC --from-cache data/cache/ITX.MC/20261118T103000Z   # repetir sin red
```

Claves de `--set`: `terminal_growth` (o `g`), `projection_years`, `modes`, `wacc_shift`,
`growth_shift`, `rate` (o `discount_rate`), `exit_multiple` (o `multiple`) y `ronic`. Las
tasas admiten `2%` o `0.02`.

Modelos (`--model`): `fcff` (EBIT·(1−t) + D&A − Capex − ΔNWC), `fcff_cfo` (desde el CFO),
`fcfe` (FCFF − Int·(1−t) + ΔDeuda neta, para industriales con mucha deuda) y `fcfe_fin`
(financieras). Valor terminal (`--vt`): `gordon`, `gordon_value_driver` (con RONIC) y
`vt_mult` (EV/EBITDA en FCFF, P/E en FCFE). El múltiplo y el RONIC se pueden fijar por ticker
en `market_inputs.toml` (`[exit_multiple."TICKER"]`, `[ronic."TICKER"]`); el argumento
prevalece. Sin múltiplo, `vt_mult` da error; sin RONIC se usa el ROIC histórico (ROE en
FCFE).

Cada informe incluye **comprobaciones de consistencia**: FCFF históricos negativos, último
FCFF muy distinto de la media de los anteriores (posible sobrevaloración por un año puntual),
g implícito en el VT alejado del g supuesto y RONIC muy por encima de la tasa. Los umbrales
están en `config/thresholds.toml` (otro fichero con `--thresholds`).

`--set rate=8%` fuerza la tasa de descuento (WACC en FCFF, Ke en FCFE) de todos los tickers de
la ejecución. Para forzarla en un solo ticker, usa `[discount_rate."TICKER"]` en
`market_inputs.toml`. Precedencia: argumento > fichero > calculada. El informe muestra la tasa
calculada a título informativo y, si no se puede calcular, lo indica como aviso.

Con un ticker se muestra el informe completo en consola, formateado con
[rich](https://github.com/Textualize/rich) (títulos, tablas con bordes, negritas); con varios,
un resumen por ticker. Si la salida se redirige (`dcf ITX.MC > informe.md`) o se usa `--raw`,
se escribe el Markdown sin formatear.
Cada informe se guarda en `<carpeta>/<TICKER>_<fecha UTC>.md` y cada descarga en `data/cache/`.
La tabla de sensibilidad WACC × g se incluye siempre.

Con varios tickers se guarda además un resumen del lote en `<carpeta>/resumen_<fecha UTC>.md`
y `.csv`, con una fila por ticker: empresa, modelo, método de VT, cotización, valor bajista, neutro y alcista
con su margen potencial frente a la cotización, tasa de descuento (WACC o Ke) y g con sus
fuentes, y avisos. Los tickers que fallan aparecen con su error. El CSV usa el formato de Excel
en español (separador `;`, decimal `,`, UTF-8 con BOM); las tasas y los márgenes van en
decimal (0,10 = 10 %).

## Desarrollo

```powershell
uv run pytest -q
uv run ruff check . && uv run mypy src
```

Manual de usuario: [docs/manual_usuario.md](docs/manual_usuario.md).
Metodología y fórmulas: [docs/metodologia.md](docs/metodologia.md).
