from __future__ import annotations

from pathlib import Path


# Rutas resueltas a partir de la ubicación de este archivo, no del directorio
# desde el que se ejecuta Python. Así todos los scripts comparten una única
# fuente de datos crudos: Data/ en la raíz del repositorio.
SRC_DIR = Path(__file__).resolve().parent
CP_SAT_DIR = SRC_DIR.parent
PROJECT_ROOT = CP_SAT_DIR.parents[2]

DATA_DIR = PROJECT_ROOT / "Data"
INTERMEDIATE_DIR = CP_SAT_DIR / "intermedios"
REBUILT_INTERMEDIATE_DIR = CP_SAT_DIR / "intermedios_reconstruidos"
CERTIFICATES_DIR = CP_SAT_DIR / "certificados"
RESULTS_DIR = CP_SAT_DIR / "resultados"
REFERENCE_RESULTS_DIR = CP_SAT_DIR / "resultados_referencia"
