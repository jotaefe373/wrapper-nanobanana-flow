"""
recorder.py — Graba interacciones del usuario en Flow como macro reutilizable.

Usa playwright codegen con la sesion autenticada para capturar selectores reales.
El script generado se guarda en flow/recordings/ y se parametriza para replay.

Para el recorder, exportamos las cookies del perfil persistente a un JSON temporal
que playwright codegen puede cargar con --load-storage.
"""

import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core.config import settings
from core.logger import get_logger

log = get_logger("recorder")

RECORDINGS_DIR = Path(__file__).parent / "recordings"
TEMP_STORAGE = Path(settings.session_dir) / "_codegen_state.json"

WRAPPER_TEMPLATE = '''"""
Macro grabado para Google Labs Flow.
Generado: {timestamp}
Nombre: {name}

Ejecutar via replay:
    make replay MACRO={module_name} IMAGE=foto.jpg PROMPT="mi prompt"
"""

from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("output")


async def recorded_flow(page, image_path: str, prompt: str):
    """Flujo grabado — los selectores fueron capturados del DOM real."""
{body}
'''


async def _export_storage_state(account: str) -> Path | None:
    """Exporta cookies del perfil persistente de la cuenta a JSON para que codegen las use."""
    from core.accounts import profile_dir

    profile = profile_dir(account)
    if not profile.exists():
        return None

    from playwright.async_api import async_playwright

    log.info("Exportando cookies del perfil para codegen...")
    async with async_playwright() as p:
        # Lanzar con perfil persistente para leer cookies
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=True,
            channel="chrome",
            args=["--no-first-run", "--no-default-browser-check"],
        )
        await context.storage_state(path=str(TEMP_STORAGE))
        await context.close()

    log.info("Cookies exportadas a %s", TEMP_STORAGE)
    return TEMP_STORAGE


def _build_codegen_cmd(storage_path: Path | None = None) -> list[str]:
    """Construye el comando playwright codegen."""
    cmd = [
        sys.executable, "-m", "playwright", "codegen",
        "--target", "python-async",
        "--browser", "chromium",
    ]

    if storage_path and storage_path.exists():
        cmd.extend(["--load-storage", str(storage_path)])

    cmd.append(settings.base_url)
    return cmd


def record(name: str | None = None, account: str | None = None) -> Path:
    """Abre playwright codegen para grabar un macro.

    El usuario interactua con Flow manualmente.
    Al cerrar el browser, el script se guarda en recordings/.
    """
    from core.accounts import resolve_account

    # Exportar cookies del perfil persistente a JSON
    storage_path = asyncio.run(_export_storage_state(resolve_account(account)))
    if not storage_path:
        log.warning("No hay perfil guardado. Ejecuta: make login ACCOUNT=<nombre>")
        log.info("Continuando sin sesion (tendras que hacer login en la grabacion)...")

    # Nombre del recording
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    recording_name = name or f"macro_{ts}"
    module_name = recording_name.replace("-", "_").replace(" ", "_")

    # Archivo de salida
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RECORDINGS_DIR / f"{module_name}.py"
    temp_file = RECORDINGS_DIR / f"_temp_{module_name}.py"

    cmd = _build_codegen_cmd(storage_path)
    cmd.extend(["--output", str(temp_file)])

    log.info("=" * 60)
    log.info("MODO GRABACION")
    log.info("=" * 60)
    log.info("Se abrira el browser con el inspector de Playwright.")
    log.info("")
    log.info("Instrucciones:")
    log.info("  1. Realiza el flujo completo en Flow (subir imagen, prompt, generar)")
    log.info("  2. Playwright grabara cada accion automaticamente")
    log.info("  3. Al cerrar el browser, el macro se guardara")
    log.info("")
    log.info("El macro quedara en: %s", output_file)
    log.info("=" * 60)

    # Ejecutar codegen (bloqueante — espera a que el usuario cierre el browser)
    result = subprocess.run(cmd)

    # Limpiar storage temporal
    if TEMP_STORAGE.exists():
        TEMP_STORAGE.unlink()

    if result.returncode != 0:
        log.error("playwright codegen termino con error (code %d)", result.returncode)
        return output_file

    if not temp_file.exists():
        log.error("No se genero el script. Asegurate de cerrar el browser para guardar.")
        return output_file

    # Leer script crudo y envolverlo en el template parametrizable
    raw_script = temp_file.read_text(encoding="utf-8")
    _wrap_recording(raw_script, output_file, recording_name, module_name)
    temp_file.unlink()

    log.info("Macro guardado exitosamente: %s", output_file)
    return output_file


def _is_setup_or_cleanup(line: str) -> bool:
    """Detecta lineas de boilerplate que codegen genera pero el replayer ya maneja."""
    s = line.strip()
    skip_patterns = [
        "playwright.chromium.launch",
        "browser.new_context",
        "context.new_page",
        "context.close",
        "browser.close",
        "page.close()",
        "storage_state=",
    ]
    return any(p in s for p in skip_patterns)


def _transform_downloads(line: str, download_counter: list) -> str:
    """Transforma lineas de download para que guarden en output/."""
    s = line.strip()

    # "download = await download_info.value" → guardar a disco
    if "= await download" in s and "_info.value" in s:
        var = s.split("=")[0].strip()
        download_counter.append(var)
        idx = len(download_counter)
        save_line = (
            f'    {var} = await {var}_info.value\n'
            f'    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)\n'
            f'    ts = datetime.now().strftime("%Y%m%d_%H%M%S")\n'
            f'    save_path = OUTPUT_DIR / f"flow_{{ts}}_{idx}.png"\n'
            f'    await {var}.save_as(str(save_path))\n'
            f'    print(f"Descarga {idx} guardada en: {{save_path}}")'
        )
        return save_line

    return None


def _wrap_recording(raw_script: str, output_file: Path, name: str, module_name: str) -> None:
    """Envuelve el script de codegen en un template parametrizable."""
    timestamp = datetime.now().isoformat()

    lines = raw_script.splitlines()
    body_lines = []
    inside_run = False
    indent_level = 0
    download_counter = []

    for line in lines:
        # Saltar imports
        if line.strip().startswith(("import ", "from ")):
            continue
        # Entrar a la funcion run()
        if line.strip().startswith("async def run("):
            inside_run = True
            indent_level = len(line) - len(line.lstrip()) + 4
            continue
        # Salir en main()
        if line.strip().startswith("async def main()"):
            break
        if not inside_run:
            continue

        # Extraer contenido sin el indent original
        if len(line) > indent_level:
            content = line[indent_level:]
        else:
            content = line.lstrip()

        # Saltar boilerplate de setup/cleanup
        if _is_setup_or_cleanup(line):
            continue

        # Transformar downloads para que guarden a disco
        transformed = _transform_downloads(line, download_counter)
        if transformed is not None:
            body_lines.append(transformed)
            continue

        body_lines.append(f"    {content}")

    body = "\n".join(body_lines)

    content = WRAPPER_TEMPLATE.format(
        timestamp=timestamp,
        name=name,
        module_name=module_name,
        body=body,
    )

    output_file.write_text(content, encoding="utf-8")


def list_recordings() -> list[dict]:
    """Lista todos los macros grabados."""
    recordings = []
    for f in sorted(RECORDINGS_DIR.glob("*.py")):
        if f.name.startswith("_") or f.name == "__init__.py" or f.name == ".gitkeep":
            continue
        recordings.append({
            "name": f.stem,
            "path": f,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return recordings
