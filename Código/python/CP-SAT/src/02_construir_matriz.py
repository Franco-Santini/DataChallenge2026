from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from repo_paths import DATA_DIR, REBUILT_INTERMEDIATE_DIR


THICKNESS = 3.0
HEADSPACE = 0.06
PALLET_COST = 150
EPS = 1e-7

PLANTS = [
    "buenos_aires",
    "curitiba",
    "santiago",
    "monterrey",
    "bakersfield",
]
VOLUME_COLUMNS = [f"volumen_producto_planta_{plant}" for plant in PLANTS]


def load_products(data_dir: Path) -> pd.DataFrame:
    catalog = pd.read_csv(
        data_dir / "catalogo_productos.csv",
        dtype={"codigo_producto": str, "caja_tipo_id": str},
    )
    specifications = pd.read_csv(
        data_dir / "especificaciones_cajas.csv",
        dtype={"caja_tipo_id": str},
    )
    operations = pd.read_csv(
        data_dir / "operaciones_planta.csv",
        dtype={"codigo_producto": str},
    )
    products = (
        catalog.merge(
            specifications[
                [
                    "caja_tipo_id",
                    "caja_interior_largo",
                    "caja_interior_ancho",
                    "caja_interior_alto",
                ]
            ],
            on="caja_tipo_id",
            how="left",
            validate="many_to_one",
        )
        .merge(
            operations[["codigo_producto", *VOLUME_COLUMNS]],
            on="codigo_producto",
            how="left",
            validate="one_to_one",
        )
        .rename(
            columns={
                "caja_interior_largo": "L0",
                "caja_interior_ancho": "W0",
                "caja_interior_alto": "H0",
            }
        )
    )
    for column in ["L0", "W0", "H0", "peso_neto_caja", *VOLUME_COLUMNS]:
        products[column] = pd.to_numeric(products[column], errors="raise")
    return products


def feasible_mask(product: pd.Series, candidates: pd.DataFrame) -> np.ndarray:
    original = product[["L0", "W0", "H0"]].to_numpy(float)
    internal = candidates[["L_int", "W_int", "H_int"]].to_numpy(float)

    fit = np.all(
        (internal >= 0.90 * original - EPS)
        & (internal <= 1.10 * original + EPS),
        axis=1,
    )
    volume = np.prod(internal, axis=1) >= np.prod(original) - EPS
    headspace = np.all(
        (internal <= original + EPS)
        | (
            internal - original
            <= np.minimum(HEADSPACE * internal, 40.0) + EPS
        ),
        axis=1,
    )
    weight_above = (
        candidates["cajas_H"].to_numpy(dtype=float) - 1.0
    ) * float(product["peso_neto_caja"])
    compression = (
        candidates["carga_maxima_kg"].to_numpy(dtype=float) + EPS
        >= weight_above
    )
    return fit & volume & headspace & compression


def build(data_dir: Path, candidates_dir: Path, output_dir: Path) -> Path:
    products = load_products(data_dir)
    candidates = pd.read_csv(
        candidates_dir / "cajas_candidatas_t3_0.csv",
        dtype={"candidate_id": str},
    )
    if len(candidates) != 5_894:
        raise ValueError("La reconstrucción espera 5.894 cajas candidatas.")

    edges: list[pd.DataFrame] = []
    for row_number, (_, product) in enumerate(products.iterrows(), start=1):
        mask = feasible_mask(product, candidates)
        feasible = candidates.loc[mask]
        if feasible.empty:
            raise ValueError(
                f"El SKU {product['codigo_producto']} no tiene una caja factible."
            )

        plant_demand = product[VOLUME_COLUMNS].to_numpy(dtype=np.int64)
        capacity = feasible["capacidad_pallet"].to_numpy(dtype=np.int64)
        pallets = np.ceil(plant_demand[None, :] / capacity[:, None]).sum(axis=1)
        edges.append(
            pd.DataFrame(
                {
                    "codigo_producto": product["codigo_producto"],
                    "candidate_id": feasible["candidate_id"].to_numpy(),
                    "costo_flete_usd": (pallets * PALLET_COST).astype(np.int64),
                }
            )
        )
        if row_number % 50 == 0:
            print(f"SKU procesados: {row_number}/427", flush=True)

    matrix = pd.concat(edges, ignore_index=True)
    if matrix["codigo_producto"].nunique() != 427:
        raise ValueError("La matriz no cubre los 427 SKU.")
    if matrix["candidate_id"].nunique() != 5_894:
        raise ValueError("Alguna candidata quedó sin cobertura.")
    if len(matrix) != 184_457:
        raise ValueError(
            f"Se obtuvieron {len(matrix):,} aristas; se esperan 184.457."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "matriz_factibilidad_t3_0.csv"
    matrix.to_csv(path, index=False)
    alternatives = matrix.groupby("codigo_producto").size()
    print(f"Asignaciones factibles: {len(matrix):,}")
    print(
        "Alternativas por SKU: "
        f"mínimo={alternatives.min()}, "
        f"mediana={alternatives.median():.0f}, "
        f"máximo={alternatives.max()}"
    )
    print(f"Archivo: {path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--candidates-dir",
        type=Path,
        default=REBUILT_INTERMEDIATE_DIR,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("intermedios_reconstruidos"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build(args.data_dir, args.candidates_dir, args.output_dir)
