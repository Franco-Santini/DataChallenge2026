from pathlib import Path

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

GROSOR_GLOBAL = [3.0]

RUTA_INCUMBENTE = (
    OUTPUT_DIR / "runs" / "k40_4h" / "solucion_base.csv"
)

TIEMPO_SEGUNDOS = 8 * 60 * 60
SEMILLA = 17

# None: búsqueda global.
# 15, 30 o 60: búsqueda local, permitiendo cambiar como máximo esa cantidad de SKU.
MAX_CAMBIOS = None

DIMENSIONES_CAJA = [
    "caja_exterior_largo",
    "caja_exterior_ancho",
    "caja_exterior_alto",
]

DATA_PATH = Path("Datos modificados/catalogo_especificaciones_operaciones.csv")
OUTPUT_DIR = Path("outputs")

PLANTAS = [
    "buenos_aires",
    "curitiba",
    "santiago",
    "monterrey",
    "bakersfield",
]

COL_VOLUMEN = [
    f"volumen_producto_planta_{planta}"
    for planta in PLANTAS
]

# CP-SAT requiere coeficientes enteros.
# USD 0,715 por caja equivale a 715 milésimos de dólar.
ESCALA_COSTO = 1000

# Precio unitario en milésimos de USD, según grosor y tier:
# <20k, 20k–49.999, 50k–99.999, 100k–499.999, >=500k
PRECIOS_TIER_MIL = {
    3.0: [660, 600, 540, 480, 420],
    4.5: [715, 650, 585, 520, 455],
    5.0: [770, 700, 630, 560, 490],
}

# El límite inferior es inclusivo. El último tier no tiene techo.
TIERS = [
    ("tier_1", 1, 19_999),
    ("tier_2", 20_000, 49_999),
    ("tier_3", 50_000, 99_999),
    ("tier_4", 100_000, 499_999),
    ("tier_5", 500_000, None),
]

def indice_tier(volumen: int) -> int:
    """Devuelve el tier aplicable a un volumen anual positivo."""
    if volumen < 20_000:
        return 0
    if volumen < 50_000:
        return 1
    if volumen < 100_000:
        return 2
    if volumen < 500_000:
        return 3
    return 4


def calcular_packaging(
    solucion: pd.DataFrame,
    productos: pd.DataFrame,
    grosor: float,
) -> tuple[float, pd.DataFrame]:
    """
    Recalcula el costo de packaging a partir de la asignación elegida.

    El tier se determina por candidate_id y planta, consolidando los volúmenes
    de todos los SKU asignados a ese diseño de caja.
    """
    asignacion = solucion[["codigo_producto", "candidate_id"]].copy()

    largo = asignacion.merge(
        productos[["codigo_producto", *COL_VOLUMEN]],
        on="codigo_producto",
        how="left",
        validate="one_to_one",
    ).melt(
        id_vars=["codigo_producto", "candidate_id"],
        value_vars=COL_VOLUMEN,
        var_name="columna_planta",
        value_name="volumen",
    )

    largo["planta"] = largo["columna_planta"].str.replace(
        "volumen_producto_planta_",
        "",
        regex=False,
    )

    volumenes = (
        largo.groupby(["candidate_id", "planta"], as_index=False)["volumen"]
        .sum()
        .query("volumen > 0")
        .copy()
    )

    volumenes["volumen"] = volumenes["volumen"].astype(int)
    volumenes["indice_tier"] = volumenes["volumen"].map(indice_tier)
    volumenes["tier"] = volumenes["indice_tier"].map(
        lambda indice: TIERS[indice][0]
    )

    precios = PRECIOS_TIER_MIL[grosor]

    volumenes["costo_unitario_usd"] = volumenes["indice_tier"].map(
        lambda indice: precios[indice] / ESCALA_COSTO
    )

    volumenes["costo_packaging_usd"] = (
        volumenes["volumen"]
        * volumenes["costo_unitario_usd"]
    )

    return volumenes["costo_packaging_usd"].sum(), volumenes

def clave_caja(tabla: pd.DataFrame) -> pd.Series:
    return tabla[DIMENSIONES_CAJA].apply(
        lambda fila: "|".join(f"{float(x):.6f}" for x in fila),
        axis=1,
    )


def agregar_hint_incumbente(
    modelo,
    x,
    matriz: pd.DataFrame,
    candidatas: pd.DataFrame,
) -> list[int]:
    incumbente = pd.read_csv(
        RUTA_INCUMBENTE,
        dtype={"codigo_producto": "string"},
    )

    columnas = ["codigo_producto", *DIMENSIONES_CAJA]

    if not set(columnas).issubset(incumbente.columns):
        raise ValueError("El incumbente no contiene las dimensiones de caja.")

    incumbente = incumbente[columnas].copy()
    incumbente["codigo_producto"] = incumbente["codigo_producto"].astype(str)
    incumbente["clave"] = clave_caja(incumbente)

    cajas_actuales = candidatas[["candidate_id", *DIMENSIONES_CAJA]].copy()
    cajas_actuales["clave"] = clave_caja(cajas_actuales)

    if cajas_actuales["clave"].duplicated().any():
        raise ValueError("Hay diseños físicamente duplicados entre candidatas.")

    mapa_caja = cajas_actuales.set_index("clave")["candidate_id"]

    incumbente["candidate_id"] = incumbente["clave"].map(mapa_caja)

    if incumbente["candidate_id"].isna().any():
        faltantes = incumbente.loc[
            incumbente["candidate_id"].isna(),
            ["codigo_producto", "clave"],
        ]
        raise ValueError(
            "El universo actual no contiene todas las cajas del incumbente. "
            f"Ejemplo: {faltantes.head(3).to_dict('records')}"
        )

    if incumbente["codigo_producto"].duplicated().any():
        raise ValueError("El incumbente asigna más de una caja a algún SKU.")

    arista_por_par = {
        (str(fila.codigo_producto), str(fila.candidate_id)): int(e)
        for e, fila in matriz[
            ["codigo_producto", "candidate_id"]
        ].iterrows()
    }

    aristas_incumbente = []

    for fila in incumbente.itertuples(index=False):
        clave = (str(fila.codigo_producto), str(fila.candidate_id))

        if clave not in arista_por_par:
            raise ValueError(
                f"La asignación incumbente no es factible: {clave}"
            )

        aristas_incumbente.append(arista_por_par[clave])

    aristas_incumbente = set(aristas_incumbente)

    for e in matriz.index:
        modelo.add_hint(x[int(e)], int(e in aristas_incumbente))

    return list(aristas_incumbente)

def resolver_mip_flete_packaging(grosor: float) -> dict:
    etiqueta = str(grosor).replace(".", "_")

    ruta_cajas = OUTPUT_DIR / f"cajas_candidatas_t{etiqueta}.csv"
    ruta_matriz = OUTPUT_DIR / f"matriz_factibilidad_t{etiqueta}.csv"

    candidatas = pd.read_csv(ruta_cajas)
    matriz = pd.read_csv(ruta_matriz).reset_index(drop=True)

    productos = (
        pd.read_csv(DATA_PATH)
        .drop_duplicates("codigo_producto")
        .copy()
    )

    candidatas["candidate_id"] = candidatas["candidate_id"].astype(str)
    matriz["candidate_id"] = matriz["candidate_id"].astype(str)
    matriz["codigo_producto"] = matriz["codigo_producto"].astype(str)
    productos["codigo_producto"] = productos["codigo_producto"].astype(str)

    for columna in COL_VOLUMEN:
        productos[columna] = pd.to_numeric(
            productos[columna],
            errors="raise",
        )

    # Las demandas deben ser cantidades enteras de cajas.
    demanda = productos.set_index("codigo_producto")[COL_VOLUMEN].copy()

    if not np.allclose(demanda.to_numpy(), np.round(demanda.to_numpy())):
        raise ValueError("Se detectaron volúmenes no enteros.")

    demanda = demanda.round().astype(np.int64)

    candidatas_utiles = set(matriz["candidate_id"])

    candidatas = candidatas.loc[
        candidatas["candidate_id"].isin(candidatas_utiles)
    ].copy()

    print("\n" + "=" * 72)
    print(f"MIP — FLETE + PACKAGING — GROSOR {grosor:.1f} mm")
    print("=" * 72)
    print(f"SKU: {matriz['codigo_producto'].nunique():,}")
    print(f"Candidatas útiles: {len(candidatas):,}")
    print(f"Asignaciones factibles: {len(matriz):,}")

    modelo = cp_model.CpModel()

    # x[e] = 1 si el SKU de la fila e usa la caja candidata de esa fila.
    x = {
        e: modelo.new_bool_var(f"x_{e}")
        for e in matriz.index
    }

    # Cada SKU debe usar exactamente un diseño de caja factible.
    aristas_por_sku = matriz.groupby("codigo_producto").groups

    for _, indices in aristas_por_sku.items():
        modelo.add_exactly_one(x[int(e)] for e in indices)

    aristas_incumbente = agregar_hint_incumbente(
        modelo=modelo,
        x=x,
        matriz=matriz,
        candidatas=candidatas,
    )

    if MAX_CAMBIOS is not None:
        modelo.add(
            sum(x[e] for e in aristas_incumbente)
            >= len(aristas_incumbente) - MAX_CAMBIOS
        )
    costo_packaging_mil = []
    aristas_por_caja = matriz.groupby("candidate_id").groups

    for candidate_id, indices in aristas_por_caja.items():
        for planta, columna_volumen in zip(PLANTAS, COL_VOLUMEN):
            # Q_cp = volumen anual total de la caja c en la planta p.
            # Se expresa como suma de las demandas de los SKU que elijan c.
            terminos_volumen = []

            for e in indices:
                sku = matriz.at[int(e), "codigo_producto"]
                volumen_sku = int(demanda.at[sku, columna_volumen])

                if volumen_sku > 0:
                    terminos_volumen.append(volumen_sku * x[int(e)])

            # Si ningún SKU compatible se produce en esta planta, Q_cp = 0
            # y no hay costo de packaging que modelar.
            if not terminos_volumen:
                continue

            volumen_maximo = sum(
                int(demanda.at[
                    matriz.at[int(e), "codigo_producto"],
                    columna_volumen,
                ])
                for e in indices
            )

            volumen_por_tier = []
            selector_tier = []

            for indice, (nombre_tier, minimo, maximo) in enumerate(TIERS):
                maximo_efectivo = (
                    volumen_maximo
                    if maximo is None
                    else min(maximo, volumen_maximo)
                )

                # Ese tier es imposible para esta combinación caja–planta.
                if minimo > maximo_efectivo:
                    continue

                z = modelo.new_bool_var(
                    f"z_{candidate_id}_{planta}_{nombre_tier}"
                )

                q_tier = modelo.new_int_var(
                    0,
                    maximo_efectivo,
                    f"q_{candidate_id}_{planta}_{nombre_tier}",
                )

                # Si z=0, q_tier debe ser 0.
                # Si z=1, q_tier debe quedar dentro del intervalo del tier.
                modelo.add(q_tier >= minimo * z)
                modelo.add(q_tier <= maximo_efectivo * z)

                selector_tier.append(z)
                volumen_por_tier.append(q_tier)

                costo_unitario_mil = PRECIOS_TIER_MIL[grosor][indice]

                costo_packaging_mil.append(
                    costo_unitario_mil * q_tier
                )

            # Una caja en una planta puede usar, como máximo, un tier.
            modelo.add_at_most_one(selector_tier)

            # Todo el volumen de esa caja–planta debe estar imputado a su tier.
            modelo.add(
                sum(volumen_por_tier) == sum(terminos_volumen)
            )

    costo_flete_mil = [
        int(round(matriz.at[e, "costo_flete_usd"] * ESCALA_COSTO)) * x[e]
        for e in matriz.index
    ]

    modelo.minimize(
        sum(costo_flete_mil) + sum(costo_packaging_mil)
    )

    solver = cp_model.CpSolver()

    # En este modelo sí vale la pena darle más tiempo que al MIP de flete.
    solver.parameters.max_time_in_seconds = TIEMPO_SEGUNDOS
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = SEMILLA
    solver.parameters.log_search_progress = False
    
    estado = solver.solve(modelo)

    if estado not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(
            f"No se obtuvo solución para grosor {grosor}. "
            f"Estado: {solver.status_name(estado)}"
        )

    indices_elegidos = [
        e for e in matriz.index
        if solver.value(x[e]) == 1
    ]

    solucion = matriz.loc[indices_elegidos].merge(
        candidatas,
        on="candidate_id",
        how="left",
        validate="many_to_one",
    )

    costo_flete = solucion["costo_flete_usd"].sum()

    costo_packaging, detalle_packaging = calcular_packaging(
        solucion=solucion,
        productos=productos,
        grosor=grosor,
    )

    costo_total_recalculado = costo_flete + costo_packaging
    costo_total_solver = solver.objective_value / ESCALA_COSTO

    if not np.isclose(
        costo_total_recalculado,
        costo_total_solver,
        atol=0.01,
    ):
        raise ValueError(
            "El costo recalculado no coincide con el objetivo del solver. "
            f"Recalculado: {costo_total_recalculado:,.3f}; "
            f"solver: {costo_total_solver:,.3f}"
        )

    cantidad_tipos = solucion["candidate_id"].nunique()

    solucion.to_csv(
        OUTPUT_DIR / f"solucion_mip_completa_t{etiqueta}.csv",
        index=False,
    )

    detalle_packaging.to_csv(
        OUTPUT_DIR / f"detalle_packaging_mip_t{etiqueta}.csv",
        index=False,
    )

    print(f"Estado: {solver.status_name(estado)}")
    print(f"Tipos de caja usados: {cantidad_tipos:,}")
    print(f"Packaging: USD {costo_packaging:,.2f}")
    print(f"Flete: USD {costo_flete:,.2f}")
    print(f"Costo total: USD {costo_total_recalculado:,.2f}")
    print(f"Mejor cota del solver: USD {solver.best_objective_bound / ESCALA_COSTO:,.2f}")

    return {
        "grosor": grosor,
        "estado": solver.status_name(estado),
        "tipos_caja": cantidad_tipos,
        "costo_packaging_usd": costo_packaging,
        "costo_flete_usd": costo_flete,
        "costo_total_usd": costo_total_recalculado,
        "cota_solver_usd": solver.best_objective_bound / ESCALA_COSTO,
    }

resultados = [
    resolver_mip_flete_packaging(grosor)
    for grosor in GROSOR_GLOBAL
]

resumen = (
    pd.DataFrame(resultados)
    .sort_values("costo_total_usd")
    .reset_index(drop=True)
)

print("\n" + "=" * 72)
print("RESUMEN — MIP CON FLETE Y PACKAGING")
print("=" * 72)

print(
    resumen.to_string(
        index=False,
        formatters={
            "costo_packaging_usd": "USD {:,.2f}".format,
            "costo_flete_usd": "USD {:,.2f}".format,
            "costo_total_usd": "USD {:,.2f}".format,
            "cota_solver_usd": "USD {:,.2f}".format,
        },
    )
)

resumen.to_csv(
    OUTPUT_DIR / "resumen_mip_flete_packaging.csv",
    index=False,
)
