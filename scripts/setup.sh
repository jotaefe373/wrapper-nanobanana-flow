#!/usr/bin/env bash
# setup.sh — Configura el entorno virtual e instala dependencias para flow-nanobanana
set -e

VENV_DIR=".venv"

# Buscar Python >= 3.11 (requerido por el proyecto)
PYTHON=""
for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Error: Se requiere Python >= 3.11"
    echo "Instala con: brew install python@3.12"
    exit 1
fi

echo "=== flow-nanobanana setup ==="
echo "Usando: $PYTHON ($($PYTHON --version))"

# Crear venv si no existe
if [ ! -d "$VENV_DIR" ]; then
    echo "Creando entorno virtual en $VENV_DIR..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "Entorno virtual ya existe en $VENV_DIR"
fi

# Activar
source "$VENV_DIR/bin/activate"

# Instalar dependencias
echo "Instalando dependencias..."
pip install --upgrade pip -q
pip install -e "." -q

# Instalar Playwright + Chromium
echo "Instalando Playwright Chromium..."
playwright install chromium

echo ""
echo "=== Setup completo ==="
echo ""
echo "Para activar el entorno:"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "Siguiente paso — login:"
echo "  python cli.py --login"
