from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path("outputs")

RUTA_SOLUCION = OUTPUT_DIR / "solucion_mip_completa_t3_0.csv"
RUTA_ENTREGA = OUTPUT_DIR / "entrega_kaggle_mip_t3_0.csv"

COLUMNAS_KAGGLE = [
    "codigo_producto",
    "caja_grosor_mm",
    "caja_exterior_largo",
    "caja_exterior_ancho",
    "caja_exterior_alto",
]

# 1. Leer la solución ganadora del MIP.
solucion = pd.read_csv(RUTA_SOLUCION)

# 2. Verificar que tenga todo lo necesario para Kaggle.
faltantes = set(COLUMNAS_KAGGLE) - set(solucion.columns)

if faltantes:
    raise ValueError(
        "Faltan columnas necesarias para generar la entrega: "
        f"{sorted(faltantes)}"
    )

# 3. Conservar sólo el formato exigido por la consigna.
entrega = (
    solucion[COLUMNAS_KAGGLE]
    .copy()
    .sort_values("codigo_producto")
    .reset_index(drop=True)
)

# 4. Controles de integridad.
if entrega["codigo_producto"].duplicated().any():
    raise ValueError("Hay códigos de producto duplicados.")

if len(entrega) != 427:
    raise ValueError(
        f"Se esperaban 427 SKU y hay {len(entrega)}. No generar la entrega."
    )

if entrega.isna().any().any():
    raise ValueError("Hay valores faltantes en la entrega.")

if entrega["caja_grosor_mm"].nunique() != 1:
    raise ValueError("La entrega mezcla grosores, lo que invalida la solución.")

if entrega["caja_grosor_mm"].iloc[0] != 3.0:
    raise ValueError("Esta entrega debía corresponder al escenario ganador de 3,0 mm.")

# 5. Guardar CSV final.
entrega.to_csv(RUTA_ENTREGA, index=False)

print("Entrega creada correctamente.")
print(f"Archivo: {RUTA_ENTREGA}")
print(f"SKU: {len(entrega)}")
print(f"Grosor global: {entrega['caja_grosor_mm'].iloc[0]:.1f} mm")
print(f"Tipos de caja: {entrega.drop_duplicates(COLUMNAS_KAGGLE[1:]).shape[0]}")
print("\nPrimeras filas:")
print(entrega.head().to_string(index=False))