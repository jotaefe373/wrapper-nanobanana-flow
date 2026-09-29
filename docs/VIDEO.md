# Video (Veo / Omni) en Flow

Actualizado el 2026-09-29 con exploración **en vivo** (cuenta `smithmonsterr`, plan
PLUS) y una prueba real de punta a punta. Las secciones 1–8 de más abajo son el mapa
original (hecho sin sesión); lo confirmado y lo que cambió está en esta sección 0.

## 0. Estado confirmado (2026-09-29, en vivo)

### Flujo objetivo (el que quiere la persona)
Para mantener consistencia, **todo pasa en UN proyecto de Flow**, en la pantalla del
proyecto (igual que las imágenes):
1. Primero se crean los **personajes, lugares y objetos** (imágenes Nano Banana) en el proyecto.
2. En ese **mismo proyecto** se generan los clips **citando lo ya creado** con `@`
   (Flow lo adjunta como *ingrediente*/referencia).
3. Un video = **2 a 3 clips de 8 s** (Veo 3.1 Lite: 8 s con ingredientes), mismo proyecto.

### Flujo de video completo
1. Un proyecto de Flow por video. Primero **personajes, lugares y objetos** como imágenes
   (`make ingredientes`, Nano Banana 2 = 0 puntos en Plus).
2. **Un video = 2 a 3 clips de 8–10 s** en ese mismo proyecto (`make clip PROYECTO=<url>`),
   cada uno citando los recursos con `@{...}`. Veo 3.1 Lite/Fast: **máx. 8 s** (con
   ingredientes, solo 8 s); **10 s solo con Omni 1.1 Flash**.
3. Cada clip lleva **tramos internos** (cortes de plano dentro del mismo clip), ver plantilla.
4. Se descargan (720p original) y se **unen con ffmpeg** (concat), fuera de Flow.

### Plantilla oficial de prompt de un clip (guion por tramos)
Va en un archivo (`PROMPT_FILE=guion.txt`); cada salto de línea se escribe con
Shift+Enter, así que el guion llega entero en un solo mensaje.

```
Genera 1 solo video de 8 segundos (sin variantes). Personaje: @{yellow jacket} (rasgos que no deben cambiar). Lugar: @{coffee shop}.
0–3 s: <encuadre/cámara> ; <acción>. Sonido: <efecto puntual>.
3–6 s: corte a <encuadre> ; <acción>. Sonido: <efecto>.
6–8 s: corte a <encuadre> ; <acción>. Sonido: <efecto>.
Audio: música <sí/no, estilo>, <diálogo sí/no>, sin narración. Vertical 9:16, <estilo visual>, sin texto en pantalla.
```

Por qué así:
- **Tramos con tiempo**: Veo respeta mejor los cortes cuando cada tramo trae su encuadre
  y su acción; sin tiempos tiende a un solo plano continuo o a ordenar mal la acción.
  Además hace que 2–3 clips encadenen (el último tramo de uno prepara el primero del siguiente).
- **Audio explícito**: Veo 3.1 genera audio nativo; si no se pide, inventa música o
  voces. Pedir sonidos puntuales por tramo (campanita, espresso, taza) los sincroniza con
  la acción, y "sin diálogo" evita voces que después no se pueden sacar.
- **"1 solo video … sin variantes"**: el agente decide la cantidad; esto más x1 en Ajustes
  y el chequeo de la confirmación (`n == 1`) evitan pagar variantes.
- **`@{...}` + rasgos**: la referencia ancla la identidad; repetir los rasgos clave en
  texto la refuerza. Usar palabras que estén en el nombre que Flow le puso al recurso.

### Prueba real (Veo 3.1 Lite, x1, 8 s, 9:16)
- Proyecto: `https://flow.google.com/project/cc89e6c1-e0b9-4cf6-b106-22addd099896`
- Saldo antes **93** puntos → después **83**. Imágenes Nano Banana 2: **0 puntos** (no
  preguntan). Clip Veo 3.1 Lite: **10 puntos** (lo dijo el agente antes de aprobar).
- Clip: `output/video-prueba/flow_video_20260929_051501_1.mp4` — H.264 720×1280, 24 fps,
  **8,0 s**, audio AAC, 4,4 MB. Tardó ~1 min desde la aprobación.
- Imágenes: `output/video-prueba/personaje_mujer.jpg`, `output/video-prueba/flow_image_20260929_051218_1.jpg` (cafetería).
- **Referencia**: el lugar salió igual a la imagen (ventanal, mesas, plantas, pizarra).
  El personaje **no**: la búsqueda `@yellow jacket` eligió por error el primer recurso
  (la cafetería, dos veces) y la mujer salió de beige. Corregido en el código
  (`pick_option`: todas las palabras, y si no hay coincidencia falla **antes** de enviar).
- Tropiezo con imágenes: un `\n` tipeado en el editor **envía el mensaje** (Enter). Se
  mandó la mitad del prompt y el agente hizo 2 imágenes de la mujer (costo 0). Corregido:
  los saltos van con Shift+Enter.

### Clip 2 (guion por tramos, mismo proyecto) — `make clip` con `PROMPT_FILE`
- Saldo 83 → **73** (10 puntos, confirmado por el agente; x1). Aprobado a los 10 s y listo en ~40 s.
- `output/video/flow_video_20260929_052208_1.mp4` — 720×1280, 24 fps, 8,0 s, AAC.
- **Personaje correcto** (`@yellow jacket` → "Woman standing in yellow jacket"): misma cara,
  chaqueta amarilla, camiseta blanca, jeans. Arreglo de `pick_option` validado en vivo.
- **Cortes**: salieron 3 planos en orden (exterior con la puerta · mostrador con barista ·
  primer plano en la ventana con taza y plato), pero con otros tiempos: ~0–2,5 s, ~2,5–3,5 s,
  ~3,5–8 s. Veo respeta el orden de los tramos, no la duración exacta.
- **Audio**: hay pista con música tonal de fondo y transitorios hacia el final (taza); no
  hay voz evidente. No verificado a oído.
- Nuevo tropiezo: `@coffee shop` eligió el **clip anterior** ("Woman entering coffee shop
  sitting", un video) en vez de la imagen del lugar → la cafetería de adentro no es la de
  la referencia. Corregido: `pick_option` prefiere recursos "Imagen" (test incluido).

### UI confirmada (selectores)
| Qué | Selector | Nota |
|---|---|---|
| Saldo | `button "Información de la cuenta"` → texto `93 puntos de Google Flow` | Ahora son **"puntos"**, no créditos. Banner "Te quedan pocos puntos…" |
| Cerrar menús | clic en `.cdk-overlay-backdrop` | **Escape no cierra** los menús (el explorador fallaba por eso) |
| Ajustes | `button "Ajustes"` → panel "Configuración del agente" → `Guardar` | |
| Confirmar antes de generar | texto `Siempre` / `Nunca` | Se deja **Siempre**: es el gate de costo |
| Grupos del panel | `[aria-label="Relación de aspecto predeterminada de generación de vídeo"]`, `"Número de salidas predeterminado de generación de vídeo"`, `"… de generación de imágenes"` (aspecto / "Número de resultados") → `radio` con `aria-checked` | Video: solo 16:9 / 9:16; x1–x4 |
| Modelo de video | `button "Modelo predeterminado de generación de vídeo"` → `menuitem` | Menú: `Omni 1.1 Flash`, `Veo 3.1 - Lite`, `Veo 3.1 - Fast`, `Veo 3.1 - Quality` (**sin costo** en el menú) |
| Confirmación del agente | texto `¿Quieres que empiece a generar 1 vídeo, que cuesta 10 puntos?` + `radio` `Aprobar` / `Aprobar siempre` / `Rechazar` | Nunca "Aprobar siempre" (deja la sesión en auto-aprobar) |
| Referencia a algo del proyecto | tipear `@palabra` en el editor → `option` (nombre auto de Flow, p. ej. "Woman standing in yellow jacket") → queda `span.mention-chip[data-reference-type=media]` + miniatura "Ingrediente" | El filtro se corta con el espacio |
| "+" de la barra | `button "Añadir ingredientes a ventana para peticiones"` → selector de recursos (tabs Todo/Imágenes/Vídeos/Voces/Caracteres/Avatares/Subidas, `Buscar recursos`, `Subir archivo multimedia`) → `button "Añadir a petición"` | Equivale al `@` |
| Limpiar prompt | `button "Borrar petición"` | |
| Resultado en el chat | `button "Abrir vídeo en el editor"` / `"Abrir imagen en el editor"`; mientras genera, tarjetas con `NN %` | En la grilla los videos son `<img>` con ícono play (no hay `<video>` en el DOM) |
| Descarga del clip | editor → `button "Descargar contenido multimedia"` → `menuitem` `270p GIF animado` / `720p Tamaño original` / `1080p Resolución mejorada` / `4K` (deshabilitado en Plus, "Actualizar") | Se usa 720p con `expect_download` |
| Red | la respuesta de red volvió a traer URLs `flow-content.google/...` (1 de imagen, 2 de video en la prueba) | Queda como dato; se descarga por el menú |
| No existe (hoy) | `Activador de ajustes` está en el DOM pero con tamaño 0; "Menú para añadir contenido multimedia" es el `+` de arriba | |

Costos: Plus = Lite 10, y la ayuda dice Fast 20, Quality 100, Omni 8 s 720p 12 (en un
proyecto viejo el agente pidió 12 puntos por un clip Omni). Nano Banana 2 = 0.

### Código y comandos (`flow/video.py`)
```
make creditos ACCOUNT=smithmonsterr                                  # saldo, sin gastar
make ingredientes ACCOUNT=smithmonsterr PROMPT="retrato ... mujer con chaqueta amarilla"   # crea proyecto (o PROYECTO=url)
make clip ACCOUNT=smithmonsterr PROYECTO=<url> MAX=10 \
     PROMPT="@{yellow jacket} entra a @{coffee shop} y se sienta junto a la ventana"
```
Todo devuelve JSON por stdout (`proyecto`, `archivos`, `confirmacion.cost`,
`saldo_antes/despues`); exit 3 = tope, 4 = sin créditos/rechazo. Cada llamada es un
mensaje; se sigue en el mismo proyecto pasando `PROYECTO=<url>` (clip 2, clip 3…).

Seguridad de créditos, en capas: (1) estimación por tabla antes de abrir el navegador
(`FLOW_VIDEO_MAX_CREDITS`, default 10); (2) Ajustes fijados y verificados (modelo,
aspecto, x1) antes de enviar; (3) el costo **real** que pregunta el agente: si supera el
tope, o si quiere generar otra cantidad/tipo, se aprieta **Rechazar**; (4) nunca se
reintenta una generación. Variables: `FLOW_VIDEO_MODEL` (default Lite),
`FLOW_VIDEO_ASPECT` (9:16), `FLOW_VIDEO_MAX_CREDITS`, `FLOW_VIDEO_TIMEOUT` (900 s).
`make t2v`/`t2vh` (`generate.generate_video`, por red y sin tope) quedan como legado.

### Pendiente
- Validar en vivo que `@` prefiera la imagen del lugar (arreglo posterior al clip 2).
- Si hace falta tiempo exacto por tramo, probar clips más cortos por plano (4/6 s) y unir con ffmpeg.
- Clip 2 y 3 en el mismo proyecto y unirlos (ffmpeg o "Añadir a escena"/Extend de Flow).
- Nombres de recursos: Flow los pone en inglés y solos; pedir al agente que los
  renombre (hay sugerencia "Cambia el nombre de mis recursos") daría `@` estables.
- Frames (primer/último cuadro) y subir imagen propia (`Subir archivo multimedia`): sin probar.
- Health-check: sumar `Añadir ingredientes a ventana para peticiones` y el botón de modelo de video.
- Lock del perfil: una generación deja el perfil tomado ~2–5 min; serializar con Estudio.

---

## Mapa original (exploración sin sesión, 2026-09-29 temprano)

Escrito el 2026-09-29. Es **exploración, no el feature**. Objetivo: que el wrapper
genere video igual que imágenes (y después lo use Estudio/atelier), con la
suscripción y sin API paga.

> **Límite de esta exploración:** la sesión de `smithmonsterr` estaba **vencida**
> (Flow redirige a `/about` y "Crear con Google Flow" pide login desde cero). No se
> pudo recorrer la UI autenticada ni ver proyectos con video. Lo de abajo sale de
> los snapshots versionados en `history/` (UI del 21 y 26 de sept), del código
> actual y de la ayuda oficial de Google. Lo que falta confirmar en vivo está
> marcado **[confirmar]** y lo levanta `tools/explorar_video.py` (sin créditos).

## 1. Qué hay hoy en el código

Ya existe un **scaffolding de text-to-video sin verificar end-to-end** (commits
`5730eb5`, `41540bd`):

- `flow/generate.py::generate_video` — proyecto nuevo → `set_video_defaults`
  (elige el modelo en Ajustes) → prompt → `verify_ready_to_generate` → "Iniciar
  generación" → espera una URL `flow-content.google/video/...` por red (hybrid)
  → `download_url` (.mp4). Si el agente responde con una pregunta, contesta "Sí,
  procede…" y vuelve a disparar.
- `flow/recordings/text-to-video.py` + `make t2v` / `make t2vh`.
- `FLOW_VIDEO_MODEL` (default `"Veo 3.1 - Fast"`), `FLOW_VIDEO_TIMEOUT` (480 s).
- `flow/results.py` ya reconoce `/video/` (test `test_extrae_video`).

Problemas conocidos de ese scaffolding:
1. **Depende de hybrid**, y desde el 2026-09-26 la red **ya no trae** la URL
   `flow-content.google/...` para imágenes (se sirven por `flow.google.com/asb/<id>`
   y se bajan del DOM). Es muy probable que al video le pase lo mismo → hace falta
   un respaldo por DOM (`<video src>` / `/asb/`) **[confirmar]**.
2. No fija **aspecto ni cantidad** de video (el panel los tiene, ver §2).
3. La "confirmación" del agente es una heurística de texto; si la cuenta tiene
   **"Confirmar antes de generar: Siempre"**, el agente siempre pregunta.
4. No hay **tope de créditos** ni estimación previa del costo.
5. Rotación de cuentas: si falla *después* del clic (timeout), el replayer solo
   rota con `NoCreditsError`/`SessionExpiredError`, bien; pero hay que garantizar
   que nunca se re-dispare una generación ya pagada.

## 2. La UI (lo observado en snapshots)

Flow es hoy un **editor tipo chat con un agente** (`flow.google.com/u/<n>/`). El
agente decide imagen vs video según el prompt; los defaults se fijan en Ajustes.

| Qué | Selector (semántico, nivel 2) | Fuente |
|---|---|---|
| Proyecto nuevo | texto `Proyecto nuevo\|New project` | `NEW_PROJECT_RE` |
| Panel de ajustes | `button` `Configuración\|Ajustes` | `SETTINGS_RE` |
| Modelo de video | `button` `Modelo predeterminado de (la )?generación de v[ií]deo` → `menuitem` con el nombre | snapshot 09-21 / `set_video_defaults` |
| Aspecto de video | `radio` `crop_16_9 16:9` / `crop_9_16 9:16` (**solo 16:9 y 9:16**) | config 09-21 |
| Cantidad de video | `radio` `x1`…`x4` (segundo grupo; el primero es de imagen) | config 09-21 |
| Confirmar antes de generar | `Siempre` / `Nunca` ("Nunca: generará y gastará créditos de forma automática") | config 09-21 |
| Guardar ajustes | `button` `Guardar` | |
| Editor del prompt | `[contenteditable=true]` | |
| Adjuntar archivo | `button` `Añadir archivo multimedia` (antes `Agregar contenido multimedia`), ícono `+` | project 09-26 |
| Ingredientes | `button` `Añadir ingredientes a ventana para peticiones` | project 09-26 |
| Ajustes de la barra | `button` `Activador de ajustes` / `Ver ajustes` (ícono `tune`) | project 09-26 |
| Instrucciones del agente | `button` `Instrucciones del agente` | project 09-26 |
| Disparar | `button` `Iniciar generación` (**gasta créditos**) | |
| Secciones laterales | `Todo el contenido multimedia`, `Caracteres` (Personajes), `Escenas`, `Herramientas` | project 09-26 |

Detalle: los dos grupos de radios de aspecto/cantidad (imagen y video) tienen los
mismos nombres; `set_image_defaults` usa `.first` y por eso siempre toca el de
imagen. Para video hay que acotar al contenedor "Configuración predeterminada de
generación de video" (p. ej. `page.get_by_text(re.compile("generación de v[ií]deo")).locator("xpath=..")`) **[confirmar estructura]**.

Modelo por defecto visto: `Veo 3.1 - Lite` (09-21). Nombres esperables en el menú
**[confirmar]**: `Veo 3.1 - Lite`, `Veo 3.1 - Fast`, `Veo 3.1 - Quality`,
`Gemini Omni Flash` (360p/720p). Veo 2 ya no figura en la ayuda.

### Modos de video (ayuda oficial, Flow Help 16352836 / 16353334)

| Modo | Lite | Fast | Quality | Omni Flash 1.1 |
|---|---|---|---|---|
| Text-to-video | sí | sí | sí | sí |
| Frames-to-video: primer cuadro | sí | sí | sí | sí |
| Frames-to-video: primero y último | sí | sí | sí | sí |
| Ingredients/referencias → video | sí (solo 8 s) | sí (solo 8 s) | no | sí |
| Extender clip | **sí (solo Lite)** | no | no | ? |
| Video-to-video (edición) | — | — | — | sí (40 créditos) |
| Duración | 4/6/8 s | 4/6/8 s | 8 s | 4/6/8/10 s |
| Aspecto | 16:9, 9:16 | ídem | ídem | ídem |
| Audio | nativo (Veo 3.1) | | | |

En el modo **manual** que describe la ayuda: nombre del modelo → **Video** →
**Frames** (arrastrar a "+ Add start frame" / "+ Add end frame") o
**Ingredients** (arrastrar o **Add**). En la UI con **agente** eso se traduce en
adjuntar la imagen con `+` / ingredientes y pedirlo en el prompt ("animá esta
imagen…"); cómo decide el agente entre frame inicial e ingrediente **[confirmar]**.
Extender / Insert / Remove / cámara / Scenebuilder se hacen sobre un clip ya
generado (botón **Extend** abajo del clip; "More → Add to Scene").

## 3. Costo en créditos (ayuda oficial "Manage your Google Flow credits", 16526234)

**Por generación, no por pedido**: x2 o un agente que hace variantes = 2×.

| Modelo | No-Ultra | Ultra |
|---|---|---|
| Veo 3.1 Lite (lower priority) | no disponible | 0 |
| Veo 3.1 Lite | 10 | 5 |
| Veo 3.1 Fast | 20 | 10 |
| Veo 3.1 Quality | 100 | 100 |
| Omni Flash 720p (4/6/8/10 s) | 7 / 10 / 12 / 15 | ídem |
| Omni Flash 360p (4/6/8/10 s) | 4 / 5 / 6 / 7 | ídem |
| Omni edición video-to-video | 40 | 40 |
| Upscale 1080p | gratis (Plus/Pro/Ultra) | gratis |
| Upscale 4K | no disponible | 50 |

Créditos: **50 por día** para todos (se "arman" con la primera generación del día,
no se acumulan) + mensual por plan (Plus 200, Pro 1.000, Ultra 10.000/25.000).
Se ven en el menú del avatar (arriba a la derecha) **[confirmar selector y el costo
que muestra la UI antes de generar]**. `flow/credits.py` hoy **no lee el saldo**:
solo detecta el aviso de "sin créditos".

## 4. Tiempo, fin y descarga

- Tiempo: minutos (el scaffolding espera hasta 480 s). Fast/Lite más rápidos que
  Quality **[medir en la prueba real]**.
- Progreso: la tarjeta del clip muestra avance en el DOM; el fin se detecta por
  (a) URL `flow-content.google/video/...` en la respuesta de `as29s` (lo que hace
  hybrid) o (b) aparición de un `<video>` con `src` en la grilla **[confirmar cuál
  sigue vigente]**. Errores: `check_blockers` (sin créditos / filtro de seguridad).
- Descarga: MP4. Hybrid baja el original (720p) por request autenticada. 1080p
  (gratis con plan) y 4K (Ultra, 50) son **upscales** del menú "Descargar" del clip
  → vía classic, análogo a 2K/4K de imagen **[confirmar items del menú; también GIF]**.

## 5. Imagen de entrada (lo más útil para atelier)

- Botón `+` (`Añadir archivo multimedia`) o ingredientes; además el lienzo acepta
  **arrastrar y soltar** ("Empieza a crear o arrastra y suelta contenido multimedia").
- Implementación sugerida, en orden: `page.expect_file_chooser()` + clic en `+` →
  `set_files(path)`; si no, `input[type=file]` oculto con `set_input_files`
  (ya existe `flow/actions.upload_image` con esa lógica, del Flow viejo); último
  recurso, drag & drop sintético con `DataTransfer`. Subir **no gasta créditos**.
- La imagen queda en la galería del proyecto; también se puede elegir una ya
  subida/generada ("Todo el contenido multimedia") **[confirmar]**.

## 6. Propuesta de diseño

Módulo nuevo `flow/video.py` (sacar lo de video de `generate.py`, sin tocar imagen):

```
generate_video(page, prompt, *, image=None, end_image=None, refs=(),
               model="Veo 3.1 - Lite", aspect="16:9", count="x1",
               max_credits=None, timeout_s=600) -> list[Path]
```

1. `new_project` (reuso) → `set_video_defaults(model, aspect, count)` acotado al
   bloque de video; fijar **Confirmar antes de generar = Nunca** solo si se pasó
   `max_credits` (así el costo es explícito del lado del wrapper).
2. Subir `image`/`end_image`/`refs` (§5), luego `enter_prompt` (reuso).
3. **Estimar costo** = tabla §3 × count; si supera `max_credits` o
   `FLOW_VIDEO_MAX_CREDITS`, abortar **antes** del clic.
4. `verify_ready_to_generate` (reuso) → `click_generate` (reuso).
5. Esperar: `ResultCapture.wait_new(kind="video")` **o** `<video src>` en DOM
   (lo que llegue primero) + `check_blockers`. Nunca re-disparar tras el clic.
6. Descargar: hybrid (`download_url`, reuso) o `src` del DOM; `QUALITY=1080p` →
   menú Descargar del clip.

CLI / make (contrato JSON como el resto de atelier):

```
make t2v  PROMPT_FILE=clip.txt [MODEL=lite|fast|quality|omni] [ASPECT=9:16] [COUNT=1] [DUR=8]
make i2v  IMAGE=foto.png PROMPT_FILE=mov.txt [END_IMAGE=fin.png] [MODEL=…] [ASPECT=…]
make ref2v REFS="a.png b.png" PROMPT_FILE=…      # ingredients (8 s)
make creditos [ACCOUNT=x]                        # leer saldo (sin gastar)
```

Variables nuevas: `FLOW_VIDEO_ASPECT`, `FLOW_VIDEO_COUNT`, `FLOW_VIDEO_MAX_CREDITS`,
`FLOW_VIDEO_QUALITY` (720p/1080p). Health-check: sumar al `CRITICAL_SELECTORS` el
botón de modelo de video y `Añadir archivo multimedia`.

Reuso: rotación de cuentas y `NoCreditsError`/`SessionExpiredError` (replayer),
`new_project`, `enter_prompt`, `verify_ready_to_generate` + auto-snapshot,
`check_blockers`, `ResultCapture`, `download_url`, `results.py`, stealth.

## 7. Riesgos

- **Créditos**: un video cuesta 10–100× una imagen; el agente puede generar más de
  una variante por pedido. Tope obligatorio y x1 por defecto.
- **Tiempos largos** (minutos): headless abierto mucho rato; Estudio corre `make
  health` sobre el mismo perfil → conflicto de lock. Serializar por cuenta.
- **Selectores**: la UI cambió 3 veces en septiembre (09-13, 09-21, 09-26: textos
  "Configuración"→"Ajustes", "Agregar"→"Añadir"). Grupos de radios duplicados
  imagen/video.
- **Agente**: puede preguntar (duración/modelo), elegir imagen en vez de video o
  rechazar por el filtro de seguridad.
- **Hybrid roto** para imágenes desde 09-26; probablemente también para video.
- **Límite diario**: 50 créditos/día sin plan = 5 Lite o 2 Fast.
- **Sesiones que vencen** (`__Secure-1PSIDTS` rota): justo lo que frenó esta exploración.

## 8. Cómo completar el mapa (sin créditos)

```
make importar CHROME=<correo> ACCOUNT=smithmonsterr    # renovar la sesión (la persona)
.venv/bin/python tools/explorar_video.py --account smithmonsterr --out /tmp/explorar-video \
    [--proyecto <URL de un proyecto con videos>]
```

Aborta cualquier `StreamChat` (la request que genera), no aprieta Guardar ni
descargas, no sube archivos y redacta firmas/correos. Deja `informe.json` (superficie
por pantalla, menú de modelos con costos, radios, inputs de archivo, RPCs que traen
URLs de video) y capturas por paso.
