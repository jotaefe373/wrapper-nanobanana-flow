"""
housekeeping.py — Limpieza automatica de basura vieja.

Corre al inicio de cada replay/record. Borra siempre los archivos temporales y
los residuos del flujo viejo; las imagenes generadas solo se borran si se define
una retencion (FLOW_OUTPUT_RETENTION_DAYS > 0), para no perder tu trabajo sin querer.
"""

import shutil
import time
from pathlib import Path

from core.config import settings
from core.logger import get_logger

log = get_logger("housekeeping")

# Temporales y residuos que nunca son "operativos" — se borran siempre
_TEMP_PATHS = ["_codegen_state.json", "_chrome_import", "_chrome-profile-bak"]
# Screenshots redundantes que producia el replayer viejo (ya no se generan)
_LEGACY_OUTPUT_GLOB = "flow_result_*.png"


def prune() -> None:
    """Borra temporales, residuos legacy y, si hay retencion, imagenes viejas."""
    removed = 0
    session = Path(settings.session_dir)
    for name in _TEMP_PATHS:
        p = session / name
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True); removed += 1
        elif p.exists():
            p.unlink(); removed += 1

    out = settings.output_path
    if out.exists():
        for f in out.glob(_LEGACY_OUTPUT_GLOB):
            f.unlink(missing_ok=True); removed += 1
        removed += _prune_old_images(out)

    if removed:
        log.info("Limpieza: %d archivo(s) viejo(s) eliminado(s)", removed)


def _prune_old_images(out: Path) -> int:
    """Borra imagenes generadas mas viejas que la retencion configurada (0 = nunca)."""
    days = settings.output_retention_days
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for f in out.glob("flow_*"):
        if f.name.startswith("flow_result_"):
            continue  # ya cubierto arriba
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True); n += 1
    return n
