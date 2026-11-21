# dcf-valuation

Valoración de empresas por flujos de caja descontados (FCFF descontado al WACC) con datos de
Yahoo Finance, escenarios bajista / neutro / alcista e informe en Markdown.

> Herramienta educativa y analítica. Sus resultados no son recomendación de inversión.

## Instalación

```bash
git clone https://github.com/quiqueacla/dcf-valuation.git
cd dcf-valuation
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                                          # con tests: pip install -e ".[dev]"
```

Requiere Python ≥ 3.12. Dependencias: `yfinance`, `pandas`, `numpy`, `rich`.

Con [uv](https://docs.astral.sh/uv/) basta con `uv sync` y anteponer `uv run` a los comandos.

### Desde WSL o con Python 3.10 / 3.11

El proyecto necesita **Python ≥ 3.12** (usa `tomllib`, `StrEnum` y `datetime.UTC`). Si tu
sistema trae una versión anterior, como el Python 3.10 de Ubuntu 22.04 en WSL, `pip install -e .`
falla con `requires a different Python: 3.10.x not in '>=3.12'`. No hace falta cambiar el Python
del sistema: crea un entorno con 3.12 de una de estas dos formas.

**Opción 1: con uv (recomendada, no necesita permisos de administrador)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # instala uv en ~/.local/bin
source ~/.bashrc                                    # o abre una terminal nueva
cd dcf-valuation
uv venv --python 3.12 .venv-wsl                     # uv descarga Python 3.12 si no lo tienes
source .venv-wsl/bin/activate
uv pip install -e .                                 # con tests: uv pip install -e ".[dev]"
dcf --help
```

**Opción 2: con apt (Ubuntu, PPA deadsnakes)**

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv
cd dcf-valuation
python3.12 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -e .                                    # con tests: pip install -e ".[dev]"
dcf --help
```

Notas:

- Si la carpeta del proyecto también se usa desde Windows (p. ej. `/mnt/c/...`), usa un nombre
  de entorno distinto de `.venv` (aquí `.venv-wsl`): un mismo `.venv` no sirve a la vez para
  Windows y Linux, y uno sobrescribiría al otro.
- Cada vez que abras una terminal nueva, activa el entorno con `source .venv-wsl/bin/activate`
  antes de ejecutar `dcf`.
- En redes corporativas con inspección TLS, si la descarga falla con un error de certificado
  (`invalid peer certificate` / `CERTIFICATE_VERIFY_FAILED`), revisa las variables
  `SSL_CERT_FILE` y `REQUESTS_CA_BUNDLE` o consulta con tu departamento de sistemas.

## Configuración (antes de la primera valoración)

1. Copia `config/data/market_inputs.example.toml` a `config/data/market_inputs.toml` y rellena
   la rentabilidad libre de riesgo, la prima de riesgo de mercado (con su fuente y su fecha) y,
   si alguna empresa no publica sus intereses, el coste de la deuda por defecto.
2. Fija el crecimiento terminal en `config/settings.toml` (`terminal_growth`) o pásalo con
   `--set g=2%`. En el mismo fichero se eligen los modos de escenario (`ventas`, `coste`).
3. Opcional: revisa `config/company_types.toml`, la tabla que clasifica cada empresa como
   industrial, banco, aseguradora o inmobiliaria según su sector e industria de Yahoo y fija su
   modelo: **FCFF** (flujo para la empresa, descontado al WACC) para industriales y
   **FCFE** (flujo para el accionista, descontado a Ke) para bancos y aseguradoras. Las
   inmobiliarias se valoran con FCFF y el informe avisa de que el modelo puede no ser adecuado.

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
dcf SAN.MC MAP.MC                               # financieras: modelo FCFE automático
dcf SAN.MC --model fcff                         # forzar un modelo (avisa si no es adecuado)
dcf ITX.MC --from-cache data/cache/ITX.MC/20261118T103000Z   # repetir sin red
```

Claves de `--set`: `terminal_growth` (o `g`), `projection_years`, `modes`, `wacc_shift`,
`growth_shift` y `rate` (o `discount_rate`). Las tasas admiten `2%` o `0.02`.

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
y `.csv`, con una fila por ticker: empresa, modelo, cotización, valor bajista, neutro y alcista
con su margen potencial frente a la cotización, tasa de descuento (WACC o Ke) y g con sus
fuentes, y avisos. Los tickers que fallan aparecen con su error. El CSV usa el formato de Excel
en español (separador `;`, decimal `,`, UTF-8 con BOM); las tasas y los márgenes van en
decimal (0,10 = 10 %).

## Desarrollo

```bash
pytest -q
ruff check . && mypy src
```

Metodología y fórmulas: [docs/metodologia.md](docs/metodologia.md).
