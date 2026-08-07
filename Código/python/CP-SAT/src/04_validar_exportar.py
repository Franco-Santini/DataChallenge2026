from __future__ import annotations

import argparse
import hashlib
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

import numpy as np
import pandas as pd

from repo_paths import (
    CERTIFICATES_DIR,
    DATA_DIR,
    REFERENCE_RESULTS_DIR,
    RESULTS_DIR,
)


THICKNESS = 3.0
PALLET = np.array([800.0, 1200.0, 1800.0], dtype=np.longdouble)
ECT = np.longdouble(1000.0)
G = np.longdouble("9.81")
SAFETY_SCALE = np.longdouble("1.00000001")
BASE_TOTAL = Decimal("209235093.94")

PLANTS = [
    "buenos_aires",
    "curitiba",
    "santiago",
    "monterrey",
    "bakersfield",
]
VOLUME_COLUMNS = [f"volumen_producto_planta_{plant}" for plant in PLANTS]
EXTERNAL_COLUMNS = [
    "caja_exterior_largo",
    "caja_exterior_ancho",
    "caja_exterior_alto",
]
INTERNAL_COLUMNS = ["L_int", "W_int", "H_int"]


def unit_price(volume: int) -> Decimal:
    if volume < 20_000:
        return Decimal("0.660")
    if volume < 50_000:
        return Decimal("0.600")
    if volume < 100_000:
        return Decimal("0.540")
    if volume < 500_000:
        return Decimal("0.480")
    return Decimal("0.420")


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    products = catalog.merge(
        specifications,
        on="caja_tipo_id",
        how="left",
        validate="many_to_one",
    )
    return products, operations


def repair_dimensions(solution: pd.DataFrame) -> pd.DataFrame:
    """Agrega un margen microscópico sin cambiar el patrón de pallet."""
    repaired = solution.copy()
    for candidate_id, indices in repaired.groupby("candidate_id").groups.items():
        rows = repaired.loc[indices]
        if rows[INTERNAL_COLUMNS].drop_duplicates().shape[0] != 1:
            raise ValueError(
                f"La caja {candidate_id} tiene dimensiones internas inconsistentes."
            )
        internal = rows.iloc[0][INTERNAL_COLUMNS].to_numpy(dtype=np.longdouble)
        safe_internal = internal * SAFETY_SCALE
        safe_external = safe_internal + np.longdouble(2.0 * THICKNESS)
        safe_external = np.round(safe_external, 12).astype(float)
        safe_internal = safe_external - 2.0 * THICKNESS
        repaired.loc[indices, INTERNAL_COLUMNS] = safe_internal
        repaired.loc[indices, EXTERNAL_COLUMNS] = safe_external
    return repaired


def strict_validation(
    solution: pd.DataFrame,
    products: pd.DataFrame,
    operations: pd.DataFrame,
) -> tuple[Decimal, Decimal, Decimal, Decimal, np.ndarray, np.ndarray]:
    if len(solution) != 427 or solution["codigo_producto"].nunique() != 427:
        raise ValueError("La solución no contiene exactamente los 427 SKU únicos.")
    if (
        solution["caja_grosor_mm"].nunique() != 1
        or float(solution["caja_grosor_mm"].iloc[0]) != THICKNESS
    ):
        raise ValueError("La solución no usa uniformemente el grosor de 3,0 mm.")

    joined = (
        solution.merge(
            products[
                [
                    "codigo_producto",
                    "peso_neto_caja",
                    "caja_interior_largo",
                    "caja_interior_ancho",
                    "caja_interior_alto",
                ]
            ],
            on="codigo_producto",
            how="left",
            validate="one_to_one",
        )
        .merge(
            operations[["codigo_producto", *VOLUME_COLUMNS]],
            on="codigo_producto",
            how="left",
            validate="one_to_one",
        )
    )

    original = joined[
        ["caja_interior_largo", "caja_interior_ancho", "caja_interior_alto"]
    ].to_numpy(dtype=np.longdouble)
    external = joined[EXTERNAL_COLUMNS].to_numpy(dtype=np.longdouble)
    internal = external - np.longdouble(2.0 * THICKNESS)

    lower = np.longdouble("0.90") * original
    upper = np.minimum.reduce(
        [
            np.longdouble("1.10") * original,
            original / np.longdouble("0.94"),
            original + np.longdouble(40.0),
        ]
    )
    if not np.all(internal >= lower):
        raise ValueError("Incumplimiento del límite inferior de fit.")
    if not np.all(internal <= upper):
        raise ValueError("Incumplimiento del límite superior/headspace.")
    if not np.all(np.prod(internal, axis=1) >= np.prod(original, axis=1)):
        raise ValueError("Incumplimiento del volumen interno mínimo.")

    positive_headspace = internal > original
    headspace_margin = np.minimum(
        np.longdouble("0.06") * internal,
        np.longdouble(40.0),
    ) - (internal - original)
    if not np.all(headspace_margin[positive_headspace] >= 0):
        raise ValueError("Incumplimiento del headspace por eje.")

    counts = np.floor(PALLET / external).astype(np.int64)
    if np.any(counts < 1):
        raise ValueError("Hay una caja que no entra en el pallet.")
    capacity = np.prod(counts, axis=1).astype(np.int64)
    maximum_load = ECT * (2 * (external[:, 0] + external[:, 1]) / 1000) / G
    required_load = (
        (counts[:, 2] - 1)
        * joined["peso_neto_caja"].to_numpy(dtype=np.longdouble)
    )
    if not np.all(maximum_load >= required_load):
        raise ValueError("Incumplimiento de resistencia a compresión.")

    joined["tipo_fisico"] = joined[EXTERNAL_COLUMNS].apply(
        lambda row: "|".join(f"{float(value):.12f}" for value in row),
        axis=1,
    )
    if joined.groupby("candidate_id")["tipo_fisico"].nunique().max() != 1:
        raise ValueError("Un candidate_id quedó asociado a más de una caja física.")

    demand = joined[VOLUME_COLUMNS].to_numpy(dtype=np.int64)
    pallets = np.ceil(demand / capacity[:, None]).sum(axis=1).astype(np.int64)
    freight_by_sku = pallets * 150
    freight = Decimal(int(freight_by_sku.sum()))

    volumes = joined.groupby("tipo_fisico")[VOLUME_COLUMNS].sum()
    packaging = Decimal("0")
    for volume in volumes.to_numpy(dtype=np.int64).ravel():
        if volume > 0:
            packaging += Decimal(int(volume)) * unit_price(int(volume))

    total = freight + packaging
    score = (BASE_TOTAL - total) / BASE_TOTAL * Decimal(100)
    return packaging, freight, total, score, capacity, freight_by_sku


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_and_export(
    input_path: Path,
    data_dir: Path,
    output_dir: Path,
    expected_total: Decimal | None,
    expected_score: Decimal | None,
    reference_submission: Path | None,
) -> tuple[Path, Path]:
    getcontext().prec = 32
    solution = pd.read_csv(
        input_path,
        dtype={"codigo_producto": str, "candidate_id": str},
    ).sort_values("codigo_producto").reset_index(drop=True)
    products, operations = load_data(data_dir)
    solution = repair_dimensions(solution)
    packaging, freight, total, score, capacity, freight_by_sku = strict_validation(
        solution,
        products,
        operations,
    )

    if expected_total is not None and total != expected_total:
        raise ValueError(f"Costo inesperado: {total}; se esperaba {expected_total}.")
    rounded_score = score.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
    if expected_score is not None and rounded_score != expected_score:
        raise ValueError(
            f"Score inesperado: {rounded_score}; se esperaba {expected_score}."
        )

    solution["capacidad_pallet_validada"] = capacity
    solution["costo_flete_usd_validado"] = freight_by_sku
    submission = solution[
        ["codigo_producto", "caja_grosor_mm", *EXTERNAL_COLUMNS]
    ].copy()

    output_dir.mkdir(parents=True, exist_ok=True)
    submission_path = output_dir / "entrega_kaggle_optimo_10_11098.csv"
    full_path = output_dir / "solucion_completa_optimo_10_11098.csv"
    submission.to_csv(submission_path, index=False, float_format="%.12f")
    solution.to_csv(full_path, index=False, float_format="%.12f")

    # Se vuelve a abrir exactamente lo serializado y se revalida.
    serialized = pd.read_csv(submission_path, dtype={"codigo_producto": str})
    audit_solution = solution.drop(columns=EXTERNAL_COLUMNS).merge(
        serialized,
        on=["codigo_producto", "caja_grosor_mm"],
        how="left",
        validate="one_to_one",
    )
    packaging_2, freight_2, total_2, score_2, _, _ = strict_validation(
        audit_solution,
        products,
        operations,
    )
    if (packaging_2, freight_2, total_2) != (packaging, freight, total):
        raise ValueError("La serialización modificó los costos.")

    print(f"SKU: {len(submission)}")
    print(f"Tipos físicos: {submission[EXTERNAL_COLUMNS].drop_duplicates().shape[0]}")
    print(f"Packaging: USD {packaging:,.2f}")
    print(f"Flete: USD {freight:,.2f}")
    print(f"Total: USD {total:,.2f}")
    print(f"Ahorro: USD {BASE_TOTAL - total:,.2f}")
    print(f"Score: {score_2} -> {rounded_score}")
    print(f"SHA-256 entrega: {sha256(submission_path)}")
    print("Validación estricta: OK")

    if reference_submission is not None and reference_submission.exists():
        if submission_path.read_bytes() != reference_submission.read_bytes():
            raise ValueError("La entrega regenerada no coincide byte a byte con la referencia.")
        print("Coincidencia byte a byte con la entrega de referencia: OK")

    return submission_path, full_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=CERTIFICATES_DIR / "asignacion_optima_sin_margen.csv",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--expected-total",
        default="188079384.24",
        help="Use 0 para validar cualquier costo factible.",
    )
    parser.add_argument(
        "--expected-score",
        default="10.11098",
        help="Use 0 para validar cualquier score.",
    )
    parser.add_argument(
        "--reference-submission",
        type=Path,
        default=REFERENCE_RESULTS_DIR / "entrega_kaggle_optimo_10_11098.csv",
    )
    parser.add_argument(
        "--no-reference-check",
        action="store_true",
        help="Valida costos y restricciones sin exigir identidad byte a byte.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    validate_and_export(
        input_path=args.input,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        expected_total=(
            None if args.expected_total == "0" else Decimal(args.expected_total)
        ),
        expected_score=(
            None if args.expected_score == "0" else Decimal(args.expected_score)
        ),
        reference_submission=(
            None if args.no_reference_check else args.reference_submission
        ),
    )
