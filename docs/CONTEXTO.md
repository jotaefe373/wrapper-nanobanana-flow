# Contexto — wrapper-nanobanana-flow

Briefing para retomar o para pegar en una conversación futura y poder preguntar
sobre estos temas. Escrito el 2026-09-13. Cubre el trabajo de esta sesión.

## Objetivo

Wrapper para automatizar **Google Flow** (modelos Nano Banana para imagen, Veo
para video) **exprimiendo la suscripción** del usuario, no la API que se paga
aparte. Con **varias cuentas** para repartir los créditos.

## Qué se construyó

### Multi-cuenta (repartir créditos)
- Cada cuenta tiene su perfil de Chrome en `session/accounts/<nombre>/`.
- **Rotación**: cada generación arranca por la cuenta siguiente a la última que
  funcionó (`session/accounts/_rotation.json`). Si una no tiene créditos o su
  sesión venció, **salta a la otra**. `ACCOUNT=x` fuerza una sola.
- `make cuentas` lista; `make login ACCOUNT=x` crea/renueva a mano.
- Cuentas actuales: `zerossse` (en `flow.google.com/u/1/`) y `smithmonsterr`.
  Cada cuenta guarda su URL de Flow en `account.json` (con varias cuentas en un
  mismo navegador, cada una vive en `/u/<n>/`).

### Clonar la sesión desde Chrome — solo 6 cookies
`make importar CHROME=<correo> ACCOUNT=<nombre>` lee la sesión del Chrome del
usuario (perfil más reciente con ese correo) y copia **solo 6 cookies de
autenticación**: `SID`, `APISID`, `SAPISID`, `LSID`, `__Secure-1PSIDTS`,
`__Secure-1PSID`.

Historia de la ablación (probado con perfiles efímeros, sin leer valores):
- El perfil trae ~70 cookies de Google; casi todas son de otros servicios.
- **2 cookies NO alcanzan** (`__Secure-1PSID` + `__Secure-1PSIDTS` falla).
- Piso real confirmado: **6**. Imprescindibles (sacar una rompe): `SID`,
  `APISID`, `SAPISID`, `LSID`, `__Secure-1PSIDTS`. La 6ta es `__Secure-1PSID`.
- Por qué 2 no bastan: las llamadas de datos se firman con **`SAPISIDHASH`**
  (desde `SAPISID`), y elegir cuenta pasa por `accounts.google.com` que necesita
  `LSID`.
- Existe un conjunto de **11** (solo-auth, con redundancia) documentado en
  `core/chrome_import.py` como alternativa robusta si Google endurece requisitos.
- En macOS las cookies se cifran con la clave del llavero (`Chrome Safe Storage`);
  para leerlas desencriptadas se lanza el Chrome real (`--use-mock-keychain`
  deshabilitado) y después se usan por HTTP/inyección.

### Migración de Flow y macros nuevos
Flow migró de `labs.google/fx/es/tools/flow` a **`flow.google.com`** y cambió toda
la UI (editor tipo chat). Se reescribieron los macros text-to-image al flujo nuevo:
**Proyecto nuevo → Configuración (aspecto/cantidad) → prompt en editor
contenteditable → "Iniciar generación" → resultado → descarga**.
Los pasos comunes viven en `flow/generate.py`.

### Estrategias de descarga (`FLOW_STRATEGY`)
Cómo se obtiene el archivo tras generar:
- **`hybrid`**: lee la URL del resultado directo de la **respuesta de red** de Flow
  (RPC `as29s`, URL firmada en `flow-content.google/image|video/...`) y la descarga
  con la sesión. No abre editor ni menú: menos dependencia del DOM. Solo 1K.
- **`classic`**: la vía por el editor → "Descargar contenido multimedia" → 1K/2K/4K.
  Necesaria para 2K/4K (reescalados). Es el **respaldo**.
- **`auto`** (default): intenta hybrid; si no capta la URL, cae a classic sin
  re-generar. Pedir 2K/4K fuerza classic.

El extractor de URLs (`flow/results.py`) desescapa el JSON doble-escapado
(`\\u003d` → `=`) y sirve igual para imagen y video.

### Otros
- Limpieza automática (`core/housekeeping.py`): borra temporales y screenshots
  legacy al arrancar; imágenes solo si `FLOW_OUTPUT_RETENTION_DAYS>0`.
- `FLOW_IMAGE_QUALITY` = 1K (original) / 2K / 4K (reescalados por Flow).
- Modo stealth (`t2ish`): clicks con curva bezier + delays gaussianos.
- Tests en `tests/` (rotación, cookies, extractor, estrategias) — sin gastar créditos.

## El spike de Nivel 3 (llamar el backend directo) — cerrado

**Pregunta**: ¿se puede generar sin manejar la UI, llamando el backend, para usar
los créditos de la suscripción de forma robusta?

Hallazgos (capturando el tráfico de una generación):
- Flow usa el framework RPC de Google **`batchexecute`** y, para generar, el
  endpoint de agente **`FlowCreationAgentService/StreamChat`** sobre **XHR**
  (no `fetch`).
- **Auth de los endpoints de Flow**: cookies + token **`at`** (anti-XSRF, se raspa
  de la página, clave WIZ `SNlM0e`) + header `x-same-domain: 1`. El `SAPISIDHASH`
  aparece **solo** en llamadas cross-origin a `-pa.googleapis.com` (barra OneGoogle).
- Cadena de RPCs: `jHPbke` (crea proyecto → project-id) → `csbIsb` (sesión →
  session-uuid) → `StreamChat` (genera) → `as29s` (trae la URL en flow-content).
- El cuerpo del `StreamChat` es un array posicional anidado con un **token de turno
  de ~2489 chars** que **no viene de ninguna respuesta**: lo genera el JS de la
  página en cada acción. Es casi seguro un token **anti-abuso tipo botguard**.
- Al reintentar la request (HTTP puro headless, o `fetch`/XHR desde la propia
  página con el prompt cambiado) Google responde **`PUBLIC_ERROR_UNUSUAL_ACTIVITY`**.
- El clasificador de seguridad de Claude Code además bloqueó el intento de HTTP
  puro headless como "Third-Party Attack".

**Conclusión**: Nivel 3 **no es viable** y **no se intenta evadir** el anti-abuso.
El único paso irreducible por UI es *disparar la generación* (ahí el JS de la
página fabrica el token válido). Todo lo demás (leer el resultado, descargar) sí
se hace por red directa → es lo que hace la estrategia **hybrid** ("Nivel 2.5").

## Marco de niveles de scraping/automatización

| Nivel | Qué es | Robustez UI | Notas |
|---|---|---|---|
| 0 | Coordenadas (clic en x,y) | nula | evitar |
| 1 | Selectores estructurales (CSS/XPath) | frágil | lo que escupe `playwright codegen` |
| 2 | Selectores semánticos (rol/texto) | buena | lo que usan los macros |
| 3 | API interna reverse-engineered | alta a la UI | **bloqueado acá por anti-abuso** |
| 4 | API oficial (Gemini/Imagen) | máxima | **factura aparte, no usa la suscripción** |

El proyecto vive en **Nivel 2 / 2.5**: UI para el paso blindado + red directa para
leer el resultado.

## Observaciones de seguridad
- **reCAPTCHA Enterprise** activo en el sitio (fingerprinting).
- Prefijos de cookies `__Secure-` (exige `Secure`) y `__Host-` (host-only, `Path=/`).
- `__Secure-1PSIDTS` **rota** del lado servidor (anti-robo de sesión): una copia
  estática caduca sola. Por eso a veces hay que reimportar.
- Robo de sesión / *pass-the-cookie*: las 6 cookies son, en la práctica, el token
  portador de la sesión (saltan el MFA, que valida el login, no cada request).
- **DBSC** (Device Bound Session Credentials): mitigación futura de Google que liga
  la sesión al TPM del equipo; volvería la cookie no-portable.

## Sesión 2026-09-26 — Flow cambió la UI, multi-imagen

**Síntoma**: todo fallaba sin gastar créditos (health-check en rojo).

**Cambios de Flow detectados** (snapshots en `history/20260926_*`):
- "Proyecto nuevo" quedó **sin traducir**: "New project" (el resto de la UI sigue
  en español). Se acepta cualquiera de los dos (`NEW_PROJECT_RE`).
- "Configuración" pasó a llamarse **"Ajustes"** (`SETTINGS_RE`). El panel es el
  mismo: aspecto 16:9/4:3/1:1/3:4/9:16, cantidad x1–x4, "Guardar".
- Los radios de aspecto traen el ícono en el nombre accesible
  (`crop_16_9 16:9`): se matchea por sufijo.
- "Modelo predeterminado de generación de **vídeo**" (con tilde).
- Los resultados se sirven en `flow.google.com/asb/<id>=s512-rw?authuser=N`.
  Original: `=s0` conservando `?authuser` (sin ella, 403).
- La captura por red (hybrid) **ya no trae la URL** del resultado; queda el
  respaldo por DOM. Pendiente revisar el RPC (tarea en el hub).
- El health-check de rol ahora admite alternativas (`"Configuración|Ajustes"`).

**Nuevo**:
- `FLOW_IMAGE_ASPECT` (antes el aspecto estaba fijo en 1:1).
- `FLOW_MULTI`: un mensaje → varias imágenes (el agente las genera en tanda,
  ~45 s). Solo en cuentas que lo permiten (`smithmonsterr` sí, `zerossse` no).
  Primera versión esperaba 7 min por la red rota; ahora vigila red + DOM.
- `GenerationRejectedError`: si el filtro de seguridad de Flow rechaza el prompt,
  se corta al instante (antes ~5 min de timeout) y no se rota de cuenta.

**Aprendido**:
- Las sesiones importadas se vencen rápido si Chrome sigue usando la cuenta
  (rota `__Secure-1PSIDTS`). Con varias cuentas en un mismo perfil de Chrome,
  verificar que `account.json` quede en el `/u/<n>/` correcto: `smithmonsterr`
  había quedado en la raíz y "vencía" enseguida; reimportada quedó en `/u/1/`.
- El filtro de seguridad de Flow rechaza personajes menores de edad descritos con
  detalle físico/de vestimenta. Diseñar personajes originales adultos.

## Preguntas abiertas / ideas futuras
- **Video**: funcionando (2026-09-29) en `flow/video.py` — flujo por proyecto:
  personajes/lugares como imágenes y clips que los citan con `@`; tope de puntos por
  la confirmación del agente. Prueba real Veo 3.1 Lite 9:16 8 s = 10 puntos. Detalle y
  pendientes en `docs/VIDEO.md` §0.
- **API oficial de Gemini** (Nivel 4): opción para escala, pero paga por imagen a
  parte de la suscripción — solo si se acepta ese costo.
- **Recorder configurable** (aparcado): flujos-como-datos + depurador paso a paso,
  para reconfigurar cuando la UI cambie sin tocar código.

## Glosario
- **batchexecute**: framework RPC de Google (`/_/<App>/data/batchexecute`).
- **StreamChat**: endpoint de agente de Flow que dispara la generación.
- **SAPISIDHASH**: `Authorization` = hash de `timestamp + SAPISID + origin`; firma
  las llamadas XHR autenticadas de Google.
- **token `at` / `SNlM0e`**: token anti-XSRF embebido en la página (WIZ_global_data).
- **botguard / token de turno**: token anti-abuso de ~2489 chars por-acción.
- **DBSC**: Device Bound Session Credentials.
- **PUBLIC_ERROR_UNUSUAL_ACTIVITY**: rechazo del anti-abuso al replicar la request.

## Cómo retomar
- Estado (2026-09-26): imágenes funcionando end-to-end por DOM (classic); hybrid
  no capta la URL tras el cambio de Flow. Multi-imagen funcionando. Video
  funcionando (`make clip`, ver docs/VIDEO.md). Recorder configurable aparcado.
- Comandos clave:
  - `make cuentas` — ver cuentas y la próxima en rotar.
  - `make importar CHROME=<correo> ACCOUNT=<nombre>` — renovar/clonar sesión.
  - `make t2ih PROMPT="..."` — generar imagen (estrategia auto).
  - `FLOW_STRATEGY=classic make t2ih PROMPT="..."` — forzar el respaldo.
  - `FLOW_MULTI=true ACCOUNT=smithmonsterr make t2ih PROMPT_FILE=...` — varias
    imágenes de un mensaje.
  - `make health` — ¿cambió la UI? (sin créditos).
  - `.venv/bin/python -m pytest -q tests` — tests sin créditos.
- Proyecto en el hub (`hub-harness`) con el slug `wrapper-nanobanana-flow`
  (hitos y decisiones registrados).
