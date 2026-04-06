# flow-nanobanana

Wrapper ligero para automatizar flujos en [Google Labs Flow](https://labs.google/fx/es/tools/flow) — generacion de imagenes con IA.

Graba tus interacciones como macros reutilizables y ejecuitalos con diferentes imagenes y prompts.

## Requisitos

- Python >= 3.11
- Google Chrome instalado
- Cuenta de Google con acceso a Flow

## Inicio rapido

```bash
# 1. Instalar
make setup

# 2. Login en Google (una sola vez)
make login

# 3. Grabar un macro
make rec NAME=mi-flujo

# 4. Ejecutar el macro
make r MACRO=mi_flujo IMAGE=foto.jpg PROMPT_FILE=prompt.txt
```

## Comandos

| Comando | Descripcion |
|---------|-------------|
| `make setup` | Instalar venv, dependencias y Playwright |
| `make login` | Login manual en Google (abre Chrome) |
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

# Exportar cookies encriptadas
make creds

# En el servidor, solo necesitas:
# - .env con FLOW_CREDENTIALS_KEY
# - session/credentials.enc
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
│   ├── config.py           # Settings (prefijo FLOW_)
│   ├── credentials.py      # Export/import credenciales encriptadas
│   ├── logger.py           # Logger centralizado
│   └── stealth.py          # Anti-deteccion Playwright
├── flow/
│   ├── auth.py             # Login Google + perfil persistente
│   ├── actions.py          # Acciones DOM (upload, prompt, download)
│   ├── client.py           # FlowClient orquestador
│   ├── recorder.py         # Graba macros con playwright codegen
│   ├── replayer.py         # Ejecuta macros con params dinamicos
│   └── recordings/         # Macros grabados (.py)
├── session/                # Perfil Chrome + credenciales (gitignored)
└── output/                 # Imagenes generadas (gitignored)
```

## Configuracion

Variables de entorno con prefijo `FLOW_` (en `.env`):

```env
FLOW_HEADLESS=true
FLOW_DELAY_MS=1500
FLOW_OUTPUT_DIR=output
FLOW_SESSION_DIR=session
FLOW_BASE_URL=https://labs.google/fx/es/tools/flow
FLOW_CREDENTIALS_KEY=          # Para export/import de credenciales
FLOW_CREDENTIALS_FILE=session/credentials.enc
```

## Tech Stack

- **Python 3.11+**
- **Playwright** — automatizacion de browser
- **Pydantic** — configuracion y validacion
- **cryptography** — encriptacion de credenciales (Fernet/AES)
