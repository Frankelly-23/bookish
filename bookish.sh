#!/bin/bash

set -e # exit on any error ( non-zero exit code )

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/python3" ]; then
    PYTHON_BIN=".venv/bin/python3"
else
  echo "Need a python venv installed in the current directory."
  exit 1 
fi

if [ -n "$BOOKISH_USERNAME" ] && [ -n "$BOOKISH_PASS" ]; then
    echo "====================================="
    echo " [1/4] Iniciando sesión en Moodle..."
    echo "====================================="
    $PYTHON_BIN src/scraper.py login "$BOOKISH_USERNAME" "$BOOKISH_PASS"
fi

echo "============================================"
echo " [2/4] Extrayendo asignaciones de Moodle..."
echo "============================================"
$PYTHON_BIN src/scraper.py scrape

echo "=============================================="
echo " [3/4] Cuestionario interactivo y generación..."
echo "=============================================="
$PYTHON_BIN src/generator.py

echo "========================================"
echo " [4/4] Convirtiendo borradores a PDF..."
echo "========================================"
$PYTHON_BIN src/converter.py

if cp -r /home/thegxnster/py/bookish/data/pdfs/* /mnt/c/Users/frank/Downloads/Homework; then  

  echo "=================================="
  echo " ✓ ¡Proceso completado con éxito!"
  echo "=================================="

else
  echo "=================================="
  echo " X Problema Copiando los archivos"
  echo "=================================="
fi
