# flow-nanobanana

Wrapper ligero para automatizar flujos en [Google Flow](https://flow.google.com/) — generacion de imagenes con IA.

Graba tus interacciones como macros reutilizables y ejecuitalos con diferentes imagenes y prompts.

## Requisitos

- Python >= 3.11
- Google Chrome instalado
- Cuenta de Google con acceso a Flow

## Inicio rapido

```bash
# 1. Instalar
make setup

# 2. Login en Google (una vez por cuenta; cierra la ventana al terminar)
make login ACCOUNT=principal
make login ACCOUNT=otra          # opcional: mas cuentas para repartir creditos

# 3. Grabar un macro
make rec NAME=mi-flujo

# 4. Ejecutar el macro
make r MACRO=mi_flujo IMAGE=foto.jpg PROMPT_FILE=prompt.txt
```

## Comandos

| Comando | Descripcion |
|---------|-------------|
| `make setup` | Instalar venv, dependencias y Playwright |
| `make login ACCOUNT=x` | Login manual en Google (crea o renueva la cuenta `x`) |
| `make cuentas` | Listar cuentas y la proxima en la rotacion |
| `make importar CHROME=correo ACCOUNT=x` | Clonar la sesion de esa cuenta desde tu Chrome, solo cookies de autenticacion (sin `CHROME` lista cuentas) |

## Cookies clonadas

`make importar` copia solo **6 cookies de autenticacion** de Google (`SID`, `APISID`,
`SAPISID`, `LSID`, `__Secure-1PSIDTS`, `__Secure-1PSID`) — el minimo confirmado por
ablacion para sostener una sesion de Flow. No copia cookies de otros servicios
(Drive, Calendar, etc.) ni de preferencias.

Es el minimo sin margen: si Google endurece requisitos o una rotacion de sesion
desincroniza, la cuenta puede caducar antes y hay que reimportar. Para mas robustez
a costa de exponer mas cookies, se puede volver al conjunto de 11 (las 6 + `HSID`,
`SSID`, `__Secure-1PAPISID`, `__Host-1PLSID`, `__Host-3PLSID`) en `core/chrome_import.py`.
| `make rec` | Grabar macro. Opcional: `NAME=x` |
| `make r` | Replay visible |
| `make rh` | Replay headless |
| `make rc` | Replay visible con credenciales `.enc` |
| `make rch` | Replay headless con credenciales `.enc` |
| `make ls` | Listar macros grabados |
| `make key` | Generar clave de encriptacion |
| `make creds` | Exportar credenciales encriptadas |
| `make clean` | Limpiar venv, cache y outputs |

### Parametros de replay

| Parametro | Descripcion |
|-----------|-------------|
| `IMAGE=ruta.png` | Imagen de entrada (requerido) |
| `PROMPT="texto"` | Prompt inline |
| `PROMPT_FILE=archivo.txt` | Prompt desde archivo (recomendado para textos largos) |
| `MACRO=nombre` | Macro especifico (default: el mas reciente) |
| `ACCOUNT=nombre` | Forzar una cuenta (default: rotar entre todas) |

La calidad de descarga se controla con `FLOW_IMAGE_QUALITY` en `.env`: `1K` (original, por defecto), `2K` o `4K` (reescalados por Flow).

## Varias cuentas

Cada cuenta de Google tiene su propio perfil en `session/accounts/<nombre>/`.
Las generaciones rotan: cada ejecucion parte por la cuenta siguiente a la ultima
que genero con exito, asi los creditos se gastan parejo.

Si una cuenta se queda sin creditos o su sesion vencio, el replay salta a la
siguiente automaticamente. Si ninguna puede, el error dice cual renovar con
`make login ACCOUNT=<nombre>`. Con `ACCOUNT=x` se usa solo esa cuenta, sin saltar.

La deteccion de "sin creditos" busca el aviso en la pagina (`flow/credits.py`);
si Flow cambia el texto, hay que ajustar `NO_CREDITS_RE`.

## Como funciona

### 1. Grabar

```bash
make rec NAME=upscale
```

Se abre Playwright Inspector con tu sesion de Google. Realizas el flujo completo en Flow (subir imagen, escribir prompt, generar, descargar). Al cerrar el browser, se guarda el macro en `flow/recordings/`.

### 2. Replay

```bash
make r MACRO=upscale IMAGE=foto.jpg PROMPT_FILE=prompt.txt
```

Ejecuta el macro grabado inyectando la imagen y el prompt como parametros dinamicos. El resultado se guarda en `output/`.

### 3. Credenciales para deploy

Para usar en un servidor sin perfil de Chrome:

```bash
# Generar clave
make key
# Guardar en .env: FLOW_CREDENTIALS_KEY=<clave>

# Exportar cookies encriptadas (una vez por cuenta)
make creds ACCOUNT=principal

# En el servidor, solo necesitas:
# - .env con FLOW_CREDENTIALS_KEY
# - session/accounts/<nombre>/credentials.enc
# - Los macros en flow/recordings/
```

## Estructura

```
flow-nanobanana/
├── cli.py                  # Entry point CLI
├── Makefile                # Comandos make
├── pyproject.toml          # Dependencias
├── scripts/
│   └── setup.sh            # Setup automatizado
├── core/
│   ├── accounts.py         # Cuentas y rotacion
│   ├── config.py           # Settings (prefijo FLOW_)
│   ├── credentials.py      # Export/import credenciales encriptadas
│   ├── logger.py           # Logger centralizado
│   └── stealth.py          # Anti-deteccion Playwright
├── flow/
│   ├── auth.py             # Login Google + perfil persistente
│   ├── actions.py          # Acciones DOM (upload, prompt, download)
│   ├── client.py           # FlowClient orquestador
│   ├── credits.py          # Deteccion de creditos agotados / sesion vencida
│   ├── recorder.py         # Graba macros con playwright codegen
│   ├── replayer.py         # Ejecuta macros con params dinamicos
│   └── recordings/         # Macros grabados (.py)
├── tests/                  # pytest (rotacion de cuentas)
├── session/accounts/       # Perfil Chrome + credenciales por cuenta (gitignored)
└── output/                 # Imagenes generadas (gitignored)
```

## Configuracion

Variables de entorno con prefijo `FLOW_` (en `.env`):

```env
FLOW_HEADLESS=true
FLOW_DELAY_MS=1500
FLOW_OUTPUT_DIR=output
FLOW_SESSION_DIR=session
FLOW_BASE_URL=https://flow.google.com/
FLOW_ACCOUNT=                  # Forzar una cuenta (sin rotar)
FLOW_USE_CREDENTIALS=false     # Usar credentials.enc aunque haya perfil
FLOW_CREDENTIALS_KEY=          # Para export/import de credenciales
```

## Tech Stack

- **Python 3.11+**
- **Playwright** — automatizacion de browser
- **Pydantic** — configuracion y validacion
- **cryptography** — encriptacion de credenciales (Fernet/AES)
