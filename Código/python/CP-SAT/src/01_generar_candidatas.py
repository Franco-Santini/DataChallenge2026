from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from repo_paths import (
    CERTIFICATES_DIR,
    DATA_DIR,
    REBUILT_INTERMEDIATE_DIR,
)


THICKNESS = 3.0
PALLET = np.array([800.0, 1200.0, 1800.0], dtype=float)
ECT = 1000.0
G = 9.81
EPS = 1e-7


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
            operations,
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

    needed = ["codigo_producto", "peso_neto_caja", "L0", "W0", "H0"]
    if products[needed].isna().any().any():
        raise ValueError("Hay productos sin dimensiones o peso.")
    if products["codigo_producto"].nunique() != 427:
        raise ValueError("Se esperaban exactamente 427 SKU.")
    if (products[["peso_neto_caja", "L0", "W0", "H0"]] <= 0).any().any():
        raise ValueError("Se encontraron dimensiones o pesos no positivos.")
    return products.reset_index(drop=True)


def dimension_limits(original: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lower = 0.90 * original
    upper = np.minimum.reduce(
        [
            1.10 * original,
            original / 0.94,
            original + 40.0,
        ]
    )
    return lower, upper


def box_from_internal(
    internal: np.ndarray,
    source: str,
    seed_sku: str,
) -> dict | None:
    external = internal + 2.0 * THICKNESS
    counts = np.floor(PALLET / external + EPS).astype(int)
    if np.any(counts < 1):
        return None

    perimeter_m = 2.0 * (external[0] + external[1]) / 1000.0
    maximum_load = ECT * perimeter_m / G
    return {
        "fuente": source,
        "sku_semilla": seed_sku,
        "caja_grosor_mm": THICKNESS,
        "L_int": float(internal[0]),
        "W_int": float(internal[1]),
        "H_int": float(internal[2]),
        "caja_exterior_largo": float(external[0]),
        "caja_exterior_ancho": float(external[1]),
        "caja_exterior_alto": float(external[2]),
        "cajas_L": int(counts[0]),
        "cajas_W": int(counts[1]),
        "cajas_H": int(counts[2]),
        "capacidad_pallet": int(np.prod(counts)),
        "carga_maxima_kg": float(maximum_load),
    }


def best_box_for_group(
    lower: np.ndarray,
    upper: np.ndarray,
    minimum_volume: float,
    maximum_weight: float,
    source: str,
    seed_sku: str,
) -> dict | None:
    maximum_counts = np.floor(PALLET / (lower + 2.0 * THICKNESS)).astype(int)
    if np.any(maximum_counts < 1):
        return None

    best: dict | None = None
    best_internal_volume = np.inf

    for count_l in range(1, maximum_counts[0] + 1):
        for count_w in range(1, maximum_counts[1] + 1):
            for count_h in range(1, maximum_counts[2] + 1):
                pattern = np.array([count_l, count_w, count_h], dtype=float)
                maximum_by_pallet = PALLET / pattern - 2.0 * THICKNESS - EPS
                feasible_upper = np.minimum(upper, maximum_by_pallet)

                if np.any(feasible_upper + EPS < lower):
                    continue
                if np.prod(feasible_upper) + EPS < minimum_volume:
                    continue

                if np.prod(lower) >= minimum_volume:
                    internal = lower.copy()
                else:
                    low_alpha, high_alpha = 0.0, 1.0
                    for _ in range(80):
                        alpha = (low_alpha + high_alpha) / 2.0
                        trial = lower + alpha * (feasible_upper - lower)
                        if np.prod(trial) >= minimum_volume:
                            high_alpha = alpha
                        else:
                            low_alpha = alpha
                    internal = lower + high_alpha * (feasible_upper - lower)

                candidate = box_from_internal(internal, source, seed_sku)
                if candidate is None:
                    continue

                weight_above = (candidate["cajas_H"] - 1) * maximum_weight
                if candidate["carga_maxima_kg"] + EPS < weight_above:
                    continue

                internal_volume = float(np.prod(internal))
                if (
                    best is None
                    or candidate["capacidad_pallet"] > best["capacidad_pallet"]
                    or (
                        candidate["capacidad_pallet"] == best["capacidad_pallet"]
                        and internal_volume < best_internal_volume
                    )
                ):
                    best = candidate
                    best_internal_volume = internal_volume

    return best


def feasible_pair_indices(products: pd.DataFrame) -> list[tuple[int, int]]:
    dimensions = products[["L0", "W0", "H0"]].to_numpy(float)
    volumes = np.prod(dimensions, axis=1)
    limits = [dimension_limits(row) for row in dimensions]
    feasible: list[tuple[int, int]] = []

    for i, j in combinations(range(len(products)), 2):
        lower = np.maximum(limits[i][0], limits[j][0])
        upper = np.minimum(limits[i][1], limits[j][1])
        if np.any(lower > upper + EPS):
            continue
        if np.prod(upper) + EPS < max(volumes[i], volumes[j]):
            continue
        feasible.append((i, j))
    return feasible


def generate(
    data_dir: Path,
    output_dir: Path,
    group_boxes_path: Path | None,
) -> Path:
    products = load_products(data_dir)
    candidates: list[dict] = []

    for row in products.itertuples(index=False):
        original = np.array([row.L0, row.W0, row.H0], dtype=float)
        reference = box_from_internal(
            original,
            "referencia_individual",
            row.codigo_producto,
        )
        if reference is not None:
            candidates.append(reference)

        lower, upper = dimension_limits(original)
        individual = best_box_for_group(
            lower,
            upper,
            float(np.prod(original)),
            float(row.peso_neto_caja),
            "optima_individual",
            row.codigo_producto,
        )
        if individual is None:
            raise ValueError(f"El SKU {row.codigo_producto} no tiene una caja factible.")
        candidates.append(individual)

    pairs = feasible_pair_indices(products)
    print(f"Pares geométricamente compatibles: {len(pairs):,}", flush=True)

    for pair_number, (i, j) in enumerate(pairs, start=1):
        row_i = products.iloc[i]
        row_j = products.iloc[j]
        dimensions_i = row_i[["L0", "W0", "H0"]].to_numpy(float)
        dimensions_j = row_j[["L0", "W0", "H0"]].to_numpy(float)
        lower_i, upper_i = dimension_limits(dimensions_i)
        lower_j, upper_j = dimension_limits(dimensions_j)

        candidate = best_box_for_group(
            np.maximum(lower_i, lower_j),
            np.minimum(upper_i, upper_j),
            max(float(np.prod(dimensions_i)), float(np.prod(dimensions_j))),
            max(float(row_i["peso_neto_caja"]), float(row_j["peso_neto_caja"])),
            "par_factible",
            f"{row_i['codigo_producto']}|{row_j['codigo_producto']}",
        )
        if candidate is not None:
            candidates.append(candidate)
        if pair_number % 5_000 == 0:
            print(f"Pares procesados: {pair_number:,}/{len(pairs):,}", flush=True)

    frame = pd.DataFrame(candidates)
    # La corrida original identificó duplicados a seis decimales. Se usa una
    # clave temporal, pero se conservan las dimensiones sin redondear.
    key_columns = []
    for column in ["L_int", "W_int", "H_int"]:
        key = f"_key_{column}"
        frame[key] = frame[column].round(6)
        key_columns.append(key)
    frame = (
        frame.drop_duplicates(
            subset=["caja_grosor_mm", *key_columns],
            keep="first",
        )
        .drop(columns=key_columns)
        .reset_index(drop=True)
    )
    if len(frame) != 5_838:
        raise ValueError(
            f"La etapa individual+pares generó {len(frame):,} diseños; "
            "con los datos oficiales se esperan 5.838."
        )

    # La búsqueda original también exploró particiones de tres o más SKU por
    # descenso aglomerativo. Sus 56 diseños físicos se preservan para poder
    # reconstruir exactamente el universo que recibió el solver. Ninguno de
    # estos diseños fue usado por la asignación óptima final.
    if group_boxes_path is not None:
        group_boxes = pd.read_csv(group_boxes_path)
        if len(group_boxes) != 56:
            raise ValueError("El certificado de cajas directas debe contener 56 filas.")
        group_boxes = group_boxes.drop(columns=["candidate_id"], errors="ignore")
        missing = set(frame.columns) - set(group_boxes.columns)
        if missing:
            raise ValueError(
                f"A las cajas directas les faltan columnas: {sorted(missing)}"
            )
        group_boxes = group_boxes[frame.columns]
        frame = pd.concat([frame, group_boxes], ignore_index=True)

    frame.insert(
        0,
        "candidate_id",
        [f"t3_0_c{index:05d}" for index in range(1, len(frame) + 1)],
    )

    if len(frame) != 5_894:
        raise ValueError(
            f"Se generaron {len(frame):,} candidatas; con los datos oficiales se esperan 5.894."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "cajas_candidatas_t3_0.csv"
    frame.to_csv(path, index=False)
    print(f"Candidatas físicas: {len(frame):,}")
    print(f"Archivo: {path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=REBUILT_INTERMEDIATE_DIR)
    parser.add_argument(
        "--group-boxes",
        type=Path,
        default=CERTIFICATES_DIR / "cajas_directas_grupos.csv",
        help="56 diseños provenientes de la búsqueda directa de grupos.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate(args.data_dir, args.output_dir, args.group_boxes)
