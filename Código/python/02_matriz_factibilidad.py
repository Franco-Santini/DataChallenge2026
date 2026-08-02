from pathlib import Path

import numpy as np
import pandas as pd

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

DATA_PATH = Path("Datos modificados/catalogo_especificaciones_operaciones.csv")
CANDIDATES_DIR = Path("outputs")
OUTPUT_DIR = Path("outputs")

GROSOR_GLOBAL = [3.0, 4.5, 5.0]

PLANTAS = [
    "buenos_aires",
    "curitiba",
    "santiago",
    "monterrey",
    "bakersfield",
]

COL_VOLUMEN = [f"volumen_producto_planta_{p}" for p in PLANTAS]

COSTO_PALLET = 150
EPS = 1e-7
G = 9.81


# =============================================================================
# FUNCIONES DE FACTIBILIDAD
# =============================================================================

def headspace_pct(grosor: float) -> float:
    if grosor <= 3.0:
        return 0.06
    if grosor <= 4.5:
        return 0.08
    return 0.10


def caja_es_factible_para_sku(
    producto: pd.Series,
    candidatas: pd.DataFrame,
    grosor: float,
) -> np.ndarray:
    """
    Devuelve un vector booleano: True para cada candidata que puede usar
    el SKU indicado.
    """
    d0 = producto[["L0", "W0", "H0"]].to_numpy(float)
    peso = float(producto["peso_neto_caja"])

    dimensiones = candidatas[["L_int", "W_int", "H_int"]].to_numpy(float)

    h = headspace_pct(grosor)

    # Restricción de +/- 10%.
    ajuste_ok = np.all(
        (dimensiones >= 0.90 * d0 - EPS)
        & (dimensiones <= 1.10 * d0 + EPS),
        axis=1,
    )

    # La caja debe conservar, como mínimo, el volumen original.
    volumen_ok = (
        np.prod(dimensiones, axis=1) >= np.prod(d0) - EPS
    )

    # Si una dimensión crece, debe respetar headspace y el máximo de 40 mm.
    headspace_ok = np.all(
        (dimensiones <= d0 + EPS)
        | (
            dimensiones - d0
            <= np.minimum(h * dimensiones, 40.0) + EPS
        ),
        axis=1,
    )

    # Aunque la resistencia no venía siendo vinculante, se mantiene el chequeo.
    peso_encima = (candidatas["cajas_H"].to_numpy() - 1) * peso

    resistencia_ok = (
        candidatas["carga_maxima_kg"].to_numpy() + EPS >= peso_encima
    )

    return ajuste_ok & volumen_ok & headspace_ok & resistencia_ok


# =============================================================================
# CARGA DE PRODUCTOS
# =============================================================================

productos = pd.read_csv(DATA_PATH).drop_duplicates("codigo_producto").copy()

productos = productos.rename(
    columns={
        "caja_interior_largo": "L0",
        "caja_interior_ancho": "W0",
        "caja_interior_alto": "H0",
    }
)

for col in ["L0", "W0", "H0", "peso_neto_caja", *COL_VOLUMEN]:
    productos[col] = pd.to_numeric(productos[col], errors="raise")

OUTPUT_DIR.mkdir(exist_ok=True)


# =============================================================================
# MATRIZ DE FACTIBILIDAD Y COSTO DE FLETE
# =============================================================================

for grosor in GROSOR_GLOBAL:
    etiqueta = str(grosor).replace(".", "_")

    ruta_candidatas = CANDIDATES_DIR / f"cajas_candidatas_t{etiqueta}.csv"
    candidatas = pd.read_csv(ruta_candidatas)

    aristas = []

    for _, producto in productos.iterrows():
        mascara = caja_es_factible_para_sku(
            producto=producto,
            candidatas=candidatas,
            grosor=grosor,
        )

        candidatas_factibles = candidatas.loc[mascara].copy()

        if candidatas_factibles.empty:
            raise ValueError(
                f"El SKU {producto['codigo_producto']} no tiene ninguna "
                f"caja candidata factible para grosor {grosor}."
            )

        # Pallets y flete se pueden calcular antes de resolver el MIP:
        # la capacidad del pallet ya está fijada para cada caja candidata.
        demanda_planta = producto[COL_VOLUMEN].to_numpy(float)

        capacidad = candidatas_factibles["capacidad_pallet"].to_numpy(float)

        pallets_totales = np.ceil(
            demanda_planta[None, :] / capacidad[:, None]
        ).sum(axis=1)

        costo_flete = pallets_totales * COSTO_PALLET

        aristas.append(
            pd.DataFrame(
                {
                    "codigo_producto": producto["codigo_producto"],
                    "candidate_id": candidatas_factibles["candidate_id"].to_numpy(),
                    "costo_flete_usd": costo_flete,
                }
            )
        )

    matriz = pd.concat(aristas, ignore_index=True)

    # Verificación: todo SKU debe tener al menos una alternativa.
    cobertura = matriz.groupby("codigo_producto").size()

    sku_sin_caja = set(productos["codigo_producto"]) - set(cobertura.index)

    if sku_sin_caja:
        raise ValueError(
            f"Hay SKU sin caja factible: {sorted(sku_sin_caja)}"
        )

    ruta_salida = OUTPUT_DIR / f"matriz_factibilidad_t{etiqueta}.csv"
    matriz.to_csv(ruta_salida, index=False)

    print(
        f"Grosor {grosor}: "
        f"{len(candidatas):,} candidatas, "
        f"{len(matriz):,} asignaciones SKU-caja factibles."
    )

    print(
        "Alternativas por SKU — "
        f"mínimo: {cobertura.min():,}, "
        f"mediana: {cobertura.median():,.0f}, "
        f"máximo: {cobertura.max():,}"
    )
