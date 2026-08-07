from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

DATA_PATH = Path("Datos modificados/catalogo_especificaciones_operaciones.csv")
HEURISTIC_PATH = Path("resultado_optimo_pallet.csv")  # opcional
OUTPUT_DIR = Path("outputs")

GROSOR_GLOBAL = [3.0, 4.5, 5.0]

# Para no generar ~90.000 pares, cada SKU aporta sólo sus K vecinos factibles
# más parecidos. Para una primera corrida, 12 es un valor razonable.
K_VECINOS = 12

PLANTAS = [
    "buenos_aires",
    "curitiba",
    "santiago",
    "monterrey",
    "bakersfield",
]

COL_VOLUMEN = [f"volumen_producto_planta_{p}" for p in PLANTAS]

# El largo de la caja debe ubicarse sobre el lado corto del pallet.
PALLET = np.array([800.0, 1200.0, 1800.0])  # largo, ancho, alto
EPS = 1e-7
G = 9.81

ECT = {3.0: 1000.0, 4.5: 1400.0, 5.0: 1650.0}


# =============================================================================
# FUNCIONES DE FACTIBILIDAD
# =============================================================================

def headspace_pct(grosor: float) -> float:
    """Porcentaje máximo de headspace permitido según el grosor."""
    if grosor <= 3.0:
        return 0.06
    if grosor <= 4.5:
        return 0.08
    return 0.10


def limites_dimension(d0: np.ndarray, grosor: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Para las dimensiones internas originales d0 = (L0, W0, H0), devuelve
    el intervalo admisible de una caja nueva.

    Límite inferior: se puede reducir hasta 10%.
    Límite superior: mínimo entre +10%, headspace y tope de 40 mm.
    """
    h = headspace_pct(grosor)

    inferior = 0.90 * d0
    superior = np.minimum.reduce([
        1.10 * d0,
        d0 / (1.0 - h),
        d0 + 40.0,
    ])

    return inferior, superior


def caja_desde_dimensiones(
    dimensiones_internas: np.ndarray,
    grosor: float,
    fuente: str,
    sku_semilla: str,
) -> dict | None:
    """
    Calcula dimensiones externas, patrón real de pallet y resistencia
    de una caja cuyas dimensiones internas ya fueron elegidas.
    """
    exterior = dimensiones_internas + 2.0 * grosor
    cajas_eje = np.floor(PALLET / exterior + EPS).astype(int)

    if np.any(cajas_eje < 1):
        return None

    capacidad = int(np.prod(cajas_eje))

    perimetro_m = 2.0 * (exterior[0] + exterior[1]) / 1000.0
    carga_maxima = ECT[grosor] * perimetro_m / G

    return {
        "fuente": fuente,
        "sku_semilla": sku_semilla,
        "caja_grosor_mm": grosor,
        "L_int": dimensiones_internas[0],
        "W_int": dimensiones_internas[1],
        "H_int": dimensiones_internas[2],
        "caja_exterior_largo": exterior[0],
        "caja_exterior_ancho": exterior[1],
        "caja_exterior_alto": exterior[2],
        "cajas_L": cajas_eje[0],
        "cajas_W": cajas_eje[1],
        "cajas_H": cajas_eje[2],
        "capacidad_pallet": capacidad,
        "carga_maxima_kg": carga_maxima,
    }


def mejor_caja_para_grupo(
    limite_inferior: np.ndarray,
    limite_superior: np.ndarray,
    volumen_minimo: float,
    peso_maximo: float,
    grosor: float,
    fuente: str,
    sku_semilla: str,
) -> dict | None:
    """
    Busca, para un SKU o grupo de SKU, una caja factible con la mayor capacidad
    de pallet posible.

    Se enumeran patrones discretos de pallet, por ejemplo 2 x 4 x 6.
    Para cada patrón se verifica que exista una caja dentro de los intervalos
    dimensionales y con volumen suficiente.
    """
    max_cajas_eje = np.floor(
        PALLET / (limite_inferior + 2.0 * grosor)
    ).astype(int)

    if np.any(max_cajas_eje < 1):
        return None

    mejor = None

    for n_largo in range(1, max_cajas_eje[0] + 1):
        for n_ancho in range(1, max_cajas_eje[1] + 1):
            for n_alto in range(1, max_cajas_eje[2] + 1):

                patron = np.array([n_largo, n_ancho, n_alto])

                # Máximo interior que permite conservar ese patrón de pallet.
                maximo_por_pallet = PALLET / patron - 2.0 * grosor - EPS

                superior = np.minimum(limite_superior, maximo_por_pallet)

                if np.any(superior + EPS < limite_inferior):
                    continue

                if np.prod(superior) + EPS < volumen_minimo:
                    continue

                # Se parte desde la caja mínima y se expande proporcionalmente
                # hasta llegar al volumen mínimo requerido.
                if np.prod(limite_inferior) >= volumen_minimo:
                    dimensiones = limite_inferior.copy()
                else:
                    bajo, alto = 0.0, 1.0

                    for _ in range(80):
                        alpha = (bajo + alto) / 2.0
                        prueba = limite_inferior + alpha * (
                            superior - limite_inferior
                        )

                        if np.prod(prueba) >= volumen_minimo:
                            alto = alpha
                        else:
                            bajo = alpha

                    dimensiones = limite_inferior + alto * (
                        superior - limite_inferior
                    )

                candidata = caja_desde_dimensiones(
                    dimensiones, grosor, fuente, sku_semilla
                )

                if candidata is None:
                    continue

                # Chequeo de resistencia para el SKU más pesado del grupo.
                peso_encima = (candidata["cajas_H"] - 1) * peso_maximo

                if candidata["carga_maxima_kg"] + EPS < peso_encima:
                    continue

                if (
                    mejor is None
                    or candidata["capacidad_pallet"] > mejor["capacidad_pallet"]
                    or (
                        candidata["capacidad_pallet"] == mejor["capacidad_pallet"]
                        and dimensiones.prod()
                        < np.array([mejor["L_int"], mejor["W_int"], mejor["H_int"]]).prod()
                    )
                ):
                    mejor = candidata

    return mejor


def pares_vecinos_factibles(productos: pd.DataFrame, grosor: float) -> set[tuple[int, int]]:
    """
    Obtiene los pares de SKU que vale la pena probar.

    Primero descarta pares sin intersección dimensional o sin volumen posible.
    Entre los restantes, conserva los K vecinos geométricamente más cercanos
    de cada SKU.
    """
    n = len(productos)
    vecinos = [[] for _ in range(n)]

    dimensiones = productos[["L0", "W0", "H0"]].to_numpy(float)
    volumenes = np.prod(dimensiones, axis=1)

    limites = [limites_dimension(d, grosor) for d in dimensiones]

    for i, j in combinations(range(n), 2):
        li, ui = limites[i]
        lj, uj = limites[j]

        inferior = np.maximum(li, lj)
        superior = np.minimum(ui, uj)

        if np.any(inferior > superior + EPS):
            continue

        if np.prod(superior) + EPS < max(volumenes[i], volumenes[j]):
            continue

        # Medida simple de similitud geométrica: menor es más parecido.
        distancia = np.abs(np.log(dimensiones[i] / dimensiones[j])).sum()

        vecinos[i].append((distancia, j))
        vecinos[j].append((distancia, i))

    pares = set()

    for i, lista in enumerate(vecinos):
        lista_ordenada = sorted(lista, key=lambda x: x[0])

        for _, j in lista_ordenada[:K_VECINOS]:
            pares.add(tuple(sorted((i, j))))

    return pares


# =============================================================================
# CARGA Y PREPARACIÓN DE PRODUCTOS
# =============================================================================

OUTPUT_DIR.mkdir(exist_ok=True)

productos = pd.read_csv(DATA_PATH).drop_duplicates("codigo_producto").copy()

columnas_necesarias = [
    "codigo_producto",
    "peso_neto_caja",
    "caja_interior_largo",
    "caja_interior_ancho",
    "caja_interior_alto",
    *COL_VOLUMEN,
]

faltantes = set(columnas_necesarias) - set(productos.columns)

if faltantes:
    raise ValueError(
        "Faltan columnas. Corré antes 01 data_prep.R. "
        f"Columnas faltantes: {sorted(faltantes)}"
    )

productos = productos.rename(
    columns={
        "caja_interior_largo": "L0",
        "caja_interior_ancho": "W0",
        "caja_interior_alto": "H0",
    }
)

columnas_numericas = ["L0", "W0", "H0", "peso_neto_caja", *COL_VOLUMEN]

for col in columnas_numericas:
    productos[col] = pd.to_numeric(productos[col], errors="raise")

if (productos[["L0", "W0", "H0", "peso_neto_caja"]] <= 0).any().any():
    raise ValueError("Hay dimensiones o pesos no positivos.")

print(f"SKU cargados: {len(productos):,}")


# =============================================================================
# GENERACIÓN DE CANDIDATAS
# =============================================================================

for grosor in GROSOR_GLOBAL:
    candidatas = []

    # -------------------------------------------------------------------------
    # A. Cajas de referencia y cajas individualmente eficientes
    # -------------------------------------------------------------------------
    for _, fila in productos.iterrows():
        sku = fila["codigo_producto"]
        d0 = fila[["L0", "W0", "H0"]].to_numpy(float)
        peso = float(fila["peso_neto_caja"])

        # Caja de referencia: mismas dimensiones internas actuales, pero con el
        # grosor externo del escenario que estamos evaluando.
        referencia = caja_desde_dimensiones(
            dimensiones_internas=d0,
            grosor=grosor,
            fuente="referencia_individual",
            sku_semilla=sku,
        )

        if referencia is not None:
            candidatas.append(referencia)

        # Caja eficiente para ese SKU: maximiza cajas por pallet.
        inferior, superior = limites_dimension(d0, grosor)

        individual = mejor_caja_para_grupo(
            limite_inferior=inferior,
            limite_superior=superior,
            volumen_minimo=float(np.prod(d0)),
            peso_maximo=peso,
            grosor=grosor,
            fuente="optima_individual",
            sku_semilla=sku,
        )

        if individual is None:
            raise ValueError(
                f"El SKU {sku} no tiene una caja factible para grosor {grosor}."
            )

        candidatas.append(individual)

    # -------------------------------------------------------------------------
    # B. Cajas obtenidas de pares de SKU similares y compatibles
    # -------------------------------------------------------------------------
    pares = pares_vecinos_factibles(productos, grosor)

    print(
        f"Grosor {grosor}: se evaluarán {len(pares):,} pares de SKU "
        f"(K_VECINOS = {K_VECINOS})."
    )

    for i, j in pares:
        fila_i = productos.iloc[i]
        fila_j = productos.iloc[j]

        d_i = fila_i[["L0", "W0", "H0"]].to_numpy(float)
        d_j = fila_j[["L0", "W0", "H0"]].to_numpy(float)

        li, ui = limites_dimension(d_i, grosor)
        lj, uj = limites_dimension(d_j, grosor)

        inferior = np.maximum(li, lj)
        superior = np.minimum(ui, uj)

        candidata = mejor_caja_para_grupo(
            limite_inferior=inferior,
            limite_superior=superior,
            volumen_minimo=max(np.prod(d_i), np.prod(d_j)),
            peso_maximo=max(
                float(fila_i["peso_neto_caja"]),
                float(fila_j["peso_neto_caja"]),
            ),
            grosor=grosor,
            fuente="par_factible",
            sku_semilla=f"{fila_i['codigo_producto']}|{fila_j['codigo_producto']}",
        )

        if candidata is not None:
            candidatas.append(candidata)

    # -------------------------------------------------------------------------
    # C. Incorporar las cajas de la heurística que obtuvo 9,29, si existe.
    # -------------------------------------------------------------------------
    if HEURISTIC_PATH.exists():
        solucion_greedy = pd.read_csv(HEURISTIC_PATH)

        requeridas = {
            "caja_grosor_mm",
            "caja_exterior_largo",
            "caja_exterior_ancho",
            "caja_exterior_alto",
        }

        if requeridas.issubset(solucion_greedy.columns):
            solucion_greedy = solucion_greedy.loc[
                np.isclose(solucion_greedy["caja_grosor_mm"], grosor)
            ]

            for _, fila in solucion_greedy.iterrows():
                dimensiones_internas = np.array([
                    fila["caja_exterior_largo"] - 2.0 * grosor,
                    fila["caja_exterior_ancho"] - 2.0 * grosor,
                    fila["caja_exterior_alto"] - 2.0 * grosor,
                ])

                candidata = caja_desde_dimensiones(
                    dimensiones_internas=dimensiones_internas,
                    grosor=grosor,
                    fuente="heuristica_9_29",
                    sku_semilla="solucion_greedy",
                )

                if candidata is not None:
                    candidatas.append(candidata)

    # -------------------------------------------------------------------------
    # D. Eliminar duplicados físicos: dos cajas con las mismas dimensiones son
    # el mismo diseño, aun si fueron encontradas a partir de SKU distintos.
    # -------------------------------------------------------------------------
    candidatas = pd.DataFrame(candidatas)

    columnas_dimension = ["L_int", "W_int", "H_int"]

    candidatas[columnas_dimension] = candidatas[columnas_dimension].round(6)

    candidatas = (
        candidatas
        .drop_duplicates(
            subset=["caja_grosor_mm", "L_int", "W_int", "H_int"]
        )
        .reset_index(drop=True)
    )

    etiqueta = str(grosor).replace(".", "_")

    candidatas.insert(
        0,
        "candidate_id",
        [f"t{etiqueta}_c{i:05d}" for i in range(1, len(candidatas) + 1)],
    )

    ruta_salida = OUTPUT_DIR / f"cajas_candidatas_t{etiqueta}.csv"

    candidatas.to_csv(ruta_salida, index=False)

    print(
        f"Grosor {grosor}: {len(candidatas):,} diseños candidatos guardados en "
        f"{ruta_salida}"
    )
