from pathlib import Path

import numpy as np
import pandas as pd

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

DATA_PATH = Path("Datos modificados/catalogo_especificaciones_operaciones.csv")
OUTPUT_DIR = Path("outputs")

GROSOR_GLOBAL = [3.0, 4.5, 5.0]


# =============================================================================
# CARGA DE SKU: se usa para saber cuántos productos deberían estar cubiertos
# =============================================================================

productos = (
    pd.read_csv(DATA_PATH)
    .drop_duplicates("codigo_producto")
    .assign(codigo_producto=lambda x: x["codigo_producto"].astype(str))
)

sku_esperados = set(productos["codigo_producto"])

print(f"SKU esperados: {len(sku_esperados):,}\n")


# =============================================================================
# AUDITORÍA POR GROSOR
# =============================================================================

for grosor in GROSOR_GLOBAL:
    etiqueta = str(grosor).replace(".", "_")

    ruta_cajas = OUTPUT_DIR / f"cajas_candidatas_t{etiqueta}.csv"
    ruta_matriz = OUTPUT_DIR / f"matriz_factibilidad_t{etiqueta}.csv"

    candidatas = pd.read_csv(ruta_cajas)
    matriz = pd.read_csv(ruta_matriz)

    matriz["codigo_producto"] = matriz["codigo_producto"].astype(str)
    matriz["candidate_id"] = matriz["candidate_id"].astype(str)
    candidatas["candidate_id"] = candidatas["candidate_id"].astype(str)

    # -------------------------------------------------------------------------
    # 1. Cobertura: cada SKU necesita al menos una caja factible
    # -------------------------------------------------------------------------
    alternativas_sku = matriz.groupby("codigo_producto").size()

    sku_sin_caja = sku_esperados - set(alternativas_sku.index)

    # -------------------------------------------------------------------------
    # 2. Utilidad de cada candidata: cuántos SKU podría cubrir
    # -------------------------------------------------------------------------
    cobertura_caja = matriz.groupby("candidate_id")["codigo_producto"].nunique()

    candidatas_auditadas = candidatas.merge(
        cobertura_caja.rename("sku_compatibles"),
        on="candidate_id",
        how="left",
    )

    candidatas_auditadas["sku_compatibles"] = (
        candidatas_auditadas["sku_compatibles"]
        .fillna(0)
        .astype(int)
    )

    candidatas_sin_uso = candidatas_auditadas.query("sku_compatibles == 0")

    # -------------------------------------------------------------------------
    # 3. Control de costos de flete precalculados
    # -------------------------------------------------------------------------
    if matriz["costo_flete_usd"].isna().any():
        raise ValueError(f"Hay fletes faltantes para grosor {grosor}.")

    if (matriz["costo_flete_usd"] < 0).any():
        raise ValueError(f"Hay fletes negativos para grosor {grosor}.")

    # Es una cota optimista: para cada SKU toma su caja de menor flete, aunque
    # luego esa combinación no necesariamente minimice packaging.
    cota_flete = (
        matriz.groupby("codigo_producto")["costo_flete_usd"]
        .min()
        .sum()
    )

    # -------------------------------------------------------------------------
    # 4. Resumen en consola
    # -------------------------------------------------------------------------
    print("=" * 72)
    print(f"GROSOR GLOBAL: {grosor:.1f} mm")
    print("=" * 72)

    print(f"Cajas candidatas: {len(candidatas):,}")
    print(f"Asignaciones SKU-caja factibles: {len(matriz):,}")

    print(
        "\nAlternativas factibles por SKU:\n"
        f"  mínimo:  {alternativas_sku.min():,}\n"
        f"  p25:     {alternativas_sku.quantile(0.25):,.0f}\n"
        f"  mediana: {alternativas_sku.median():,.0f}\n"
        f"  p75:     {alternativas_sku.quantile(0.75):,.0f}\n"
        f"  máximo:  {alternativas_sku.max():,}"
    )

    print(
        "\nSKU compatibles por caja candidata:\n"
        f"  mediana: {candidatas_auditadas['sku_compatibles'].median():,.0f}\n"
        f"  máximo:  {candidatas_auditadas['sku_compatibles'].max():,}"
    )

    print(f"\nCandidatas sin ningún SKU compatible: {len(candidatas_sin_uso):,}")
    print(f"Cota inferior de flete solamente: USD {cota_flete:,.2f}")

    if sku_sin_caja:
        print("\nERROR — SKU sin candidata factible:")
        print(sorted(sku_sin_caja))
    else:
        print("\nOK — todos los SKU tienen al menos una candidata factible.")

    # -------------------------------------------------------------------------
    # 5. Archivos de diagnóstico
    # -------------------------------------------------------------------------
    candidatas_auditadas.sort_values(
        ["sku_compatibles", "capacidad_pallet"],
        ascending=[False, False],
    ).to_csv(
        OUTPUT_DIR / f"auditoria_candidatas_t{etiqueta}.csv",
        index=False,
    )

    resumen_sku = (
        alternativas_sku
        .rename("alternativas_factibles")
        .reset_index()
        .sort_values("alternativas_factibles")
    )

    resumen_sku.to_csv(
        OUTPUT_DIR / f"auditoria_sku_t{etiqueta}.csv",
        index=False,
    )
