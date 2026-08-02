from pathlib import Path

import pandas as pd
from ortools.sat.python import cp_model

OUTPUT_DIR = Path("outputs")
GROSOR_GLOBAL = [3.0, 4.5, 5.0]

# CP-SAT trabaja con coeficientes enteros.
# Expresamos USD en centavos para conservar precisión.
ESCALA_COSTO = 100

def resolver_mip_solo_flete(grosor: float) -> dict:
    etiqueta = str(grosor).replace(".", "_")

    ruta_cajas = OUTPUT_DIR / f"cajas_candidatas_t{etiqueta}.csv"
    ruta_matriz = OUTPUT_DIR / f"matriz_factibilidad_t{etiqueta}.csv"

    candidatas = pd.read_csv(ruta_cajas)
    matriz = pd.read_csv(ruta_matriz)

    matriz["codigo_producto"] = matriz["codigo_producto"].astype(str)
    matriz["candidate_id"] = matriz["candidate_id"].astype(str)
    candidatas["candidate_id"] = candidatas["candidate_id"].astype(str)

    # Eliminar candidatas sin ninguna arista factible.
    # No modifica el resultado: simplemente achica el modelo.
    candidatas_utiles = set(matriz["candidate_id"])
    candidatas = candidatas.loc[
        candidatas["candidate_id"].isin(candidatas_utiles)
    ].copy()

    print("\n" + "=" * 72)
    print(f"MODELO MIP — FLETE SOLAMENTE — GROSOR {grosor:.1f} mm")
    print("=" * 72)
    print(f"SKU: {matriz['codigo_producto'].nunique():,}")
    print(f"Cajas candidatas útiles: {len(candidatas):,}")
    print(f"Variables de asignación: {len(matriz):,}")

    modelo = cp_model.CpModel()

    # x[e] = 1 si se selecciona la asignación de la fila e de matriz:
    #        SKU i -> caja candidata c.
    x = {}

    for e, fila in matriz.iterrows():
        x[e] = modelo.new_bool_var(
            f"x_sku_{fila['codigo_producto']}_caja_{fila['candidate_id']}"
        )

    aristas_por_sku = matriz.groupby("codigo_producto").groups

    for sku, indices in aristas_por_sku.items():
        modelo.add_exactly_one(x[e] for e in indices)

    costo_flete_centavos = {
        e: int(round(fila["costo_flete_usd"] * ESCALA_COSTO))
        for e, fila in matriz.iterrows()
    }

    modelo.minimize(
        sum(costo_flete_centavos[e] * x[e] for e in matriz.index)
    )

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = 60
    solver.parameters.num_search_workers = 8
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

    costo_flete = solver.objective_value / ESCALA_COSTO

    if solucion["codigo_producto"].nunique() != matriz["codigo_producto"].nunique():
        raise ValueError("La solución no asignó exactamente una caja a cada SKU.")

    ruta_salida = OUTPUT_DIR / f"solucion_mip_flete_t{etiqueta}.csv"
    solucion.to_csv(ruta_salida, index=False)

    print(f"Estado: {solver.status_name(estado)}")
    print(f"Flete mínimo: USD {costo_flete:,.2f}")
    print(f"Asignaciones elegidas: {len(solucion):,}")
    print(f"Archivo guardado: {ruta_salida}")

    return {
        "grosor": grosor,
        "estado": solver.status_name(estado),
        "costo_flete_usd": costo_flete,
    }

resultados = [
    resolver_mip_solo_flete(grosor)
    for grosor in GROSOR_GLOBAL
]

resumen = (
    pd.DataFrame(resultados)
    .sort_values("costo_flete_usd")
    .reset_index(drop=True)
)

print("\n" + "=" * 72)
print("RESUMEN — MIP DE FLETE")
print("=" * 72)
print(
    resumen.to_string(
        index=False,
        formatters={"costo_flete_usd": "USD {:,.2f}".format},
    )
)

resumen.to_csv(OUTPUT_DIR / "resumen_mip_flete.csv", index=False)
