from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

from repo_paths import (
    CERTIFICATES_DIR,
    DATA_DIR,
    INTERMEDIATE_DIR,
    RESULTS_DIR,
)


PLANTS = [
    "buenos_aires",
    "curitiba",
    "santiago",
    "monterrey",
    "bakersfield",
]
VOLUME_COLUMNS = [f"volumen_producto_planta_{plant}" for plant in PLANTS]
TIERS = [
    (1, 19_999, 660),
    (20_000, 49_999, 600),
    (50_000, 99_999, 540),
    (100_000, 499_999, 480),
    (500_000, None, 420),
]


def load_operations(data_dir: Path) -> pd.DataFrame:
    operations = pd.read_csv(
        data_dir / "operaciones_planta.csv",
        dtype={"codigo_producto": str},
    )
    for column in VOLUME_COLUMNS:
        operations[column] = pd.to_numeric(
            operations[column], errors="raise"
        ).astype(np.int64)
    if operations["codigo_producto"].nunique() != 427:
        raise ValueError("Se esperaban exactamente 427 SKU en operaciones.")
    return operations


def nondominated_candidates(
    matrix: pd.DataFrame,
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """
    Reducción exacta.

    Una caja se elimina si otra admite un superconjunto de SKU y tiene una
    capacidad de pallet igual o mayor. La caja dominante puede replicar toda
    asignación de la dominada con packaging idéntico y flete no mayor.
    """
    sku_order = sorted(matrix["codigo_producto"].unique())
    sku_index = {sku: index for index, sku in enumerate(sku_order)}

    coverage_bits: dict[str, int] = {}
    for candidate_id, skus in matrix.groupby("candidate_id")["codigo_producto"]:
        bits = 0
        for sku in skus:
            bits |= 1 << sku_index[sku]
        coverage_bits[str(candidate_id)] = bits

    rows: list[tuple[int, int, str, int]] = []
    for row in candidates[["candidate_id", "capacidad_pallet"]].itertuples(index=False):
        candidate_id = str(row.candidate_id)
        if candidate_id in coverage_bits:
            bits = coverage_bits[candidate_id]
            rows.append(
                (int(row.capacidad_pallet), bits.bit_count(), candidate_id, bits)
            )
    rows.sort(key=lambda item: (-item[0], -item[1], item[2]))

    kept: list[tuple[int, int, str, int]] = []
    representative: dict[str, str] = {}
    for capacity, size, candidate_id, bits in rows:
        for _, _, kept_id, kept_bits in kept:
            if bits | kept_bits == kept_bits:
                representative[candidate_id] = kept_id
                break
        else:
            kept.append((capacity, size, candidate_id, bits))
            representative[candidate_id] = candidate_id

    kept_ids = {candidate_id for _, _, candidate_id, _ in kept}
    reduced_candidates = candidates[
        candidates["candidate_id"].isin(kept_ids)
    ].copy()
    reduced_matrix = matrix[matrix["candidate_id"].isin(kept_ids)].reset_index(drop=True)

    if len(reduced_candidates) != 953 or len(reduced_matrix) != 32_808:
        raise ValueError(
            "La reducción no reprodujo los 953 diseños y 32.808 aristas esperados: "
            f"obtuvo {len(reduced_candidates)} y {len(reduced_matrix)}."
        )
    return reduced_candidates, reduced_matrix, representative


def tier_price_mil(volume: int) -> int:
    for minimum, maximum, price_mil in TIERS:
        if volume >= minimum and (maximum is None or volume <= maximum):
            return price_mil
    raise ValueError(f"Volumen fuera de tiers: {volume}")


def assignment_objective_mil(
    assignment: pd.DataFrame,
    matrix: pd.DataFrame,
    operations: pd.DataFrame,
) -> tuple[int, int, int]:
    selected = assignment[["codigo_producto", "candidate_id"]].merge(
        matrix,
        on=["codigo_producto", "candidate_id"],
        how="left",
        validate="one_to_one",
    )
    if selected["costo_flete_usd"].isna().any():
        raise ValueError("La asignación contiene una arista no factible.")
    freight_mil = int(selected["costo_flete_usd"].sum()) * 1000

    assigned = assignment[["codigo_producto", "candidate_id"]].merge(
        operations[["codigo_producto", *VOLUME_COLUMNS]],
        on="codigo_producto",
        how="left",
        validate="one_to_one",
    )
    volumes = assigned.groupby("candidate_id")[VOLUME_COLUMNS].sum()
    packaging_mil = 0
    for volume in volumes.to_numpy(np.int64).ravel():
        if volume > 0:
            packaging_mil += int(volume) * tier_price_mil(int(volume))
    return packaging_mil, freight_mil, packaging_mil + freight_mil


def solution_from_edges(
    chosen_edges: list[int],
    matrix: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    solution = (
        matrix.loc[chosen_edges]
        .merge(candidates, on="candidate_id", how="left", validate="many_to_one")
        .sort_values("codigo_producto")
        .reset_index(drop=True)
    )
    if len(solution) != 427 or solution["codigo_producto"].nunique() != 427:
        raise ValueError("La solución no contiene una asignación por SKU.")
    return solution


class ImprovementCallback(cp_model.CpSolverSolutionCallback):
    def __init__(
        self,
        x: dict[int, cp_model.IntVar],
        matrix: pd.DataFrame,
        candidates: pd.DataFrame,
        output_path: Path,
        incumbent_mil: int,
        target_mil: int | None,
    ) -> None:
        super().__init__()
        self.x = x
        self.matrix = matrix
        self.candidates = candidates
        self.output_path = output_path
        self.best_mil = incumbent_mil
        self.target_mil = target_mil
        self.best_solution: pd.DataFrame | None = None

    def on_solution_callback(self) -> None:
        objective_mil = int(round(self.objective_value))
        if objective_mil >= self.best_mil:
            return
        chosen_edges = [
            int(edge) for edge in self.matrix.index if self.value(self.x[int(edge)])
        ]
        solution = solution_from_edges(chosen_edges, self.matrix, self.candidates)
        self.best_mil = objective_mil
        self.best_solution = solution
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        solution.to_csv(self.output_path, index=False)
        print(
            f"MEJORA: USD {objective_mil / 1000:,.2f} | "
            f"cota USD {self.best_objective_bound / 1000:,.2f} | "
            f"{self.wall_time:.1f} s",
            flush=True,
        )
        if self.target_mil is not None and objective_mil <= self.target_mil:
            print("Se alcanzó el objetivo conocido; se detiene la búsqueda.", flush=True)
            self.stop_search()


def solve(
    data_dir: Path,
    intermediate_dir: Path,
    incumbent_path: Path,
    output_path: Path,
    seconds: int,
    seed: int,
    workers: int,
    target_total: float | None,
) -> Path:
    candidates_all = pd.read_csv(
        intermediate_dir / "cajas_candidatas_t3_0.csv",
        dtype={"candidate_id": str},
    )
    matrix_all = pd.read_csv(
        intermediate_dir / "matriz_factibilidad_t3_0.csv",
        dtype={"codigo_producto": str, "candidate_id": str},
    )
    operations = load_operations(data_dir)
    incumbent_original = pd.read_csv(
        incumbent_path,
        dtype={"codigo_producto": str, "candidate_id": str},
    )

    candidates, matrix, representative = nondominated_candidates(
        matrix_all,
        candidates_all,
    )
    incumbent = incumbent_original[["codigo_producto", "candidate_id"]].copy()
    incumbent["candidate_id"] = incumbent["candidate_id"].map(representative)
    if incumbent["candidate_id"].isna().any():
        raise ValueError("No se pudo mapear el incumbente al universo reducido.")

    edge_lookup = {
        (row.codigo_producto, row.candidate_id): int(edge)
        for edge, row in matrix[["codigo_producto", "candidate_id"]].iterrows()
    }
    incumbent_edges = set()
    for row in incumbent.itertuples(index=False):
        key = (row.codigo_producto, row.candidate_id)
        if key not in edge_lookup:
            raise ValueError(f"Arista incumbente no factible: {key}")
        incumbent_edges.add(edge_lookup[key])

    incumbent_packaging, incumbent_freight, incumbent_total = assignment_objective_mil(
        incumbent,
        matrix,
        operations,
    )
    print(
        f"Reducción exacta: {len(candidates_all):,} -> {len(candidates):,} cajas; "
        f"{len(matrix_all):,} -> {len(matrix):,} aristas."
    )
    print(
        f"Incumbente: packaging USD {incumbent_packaging / 1000:,.2f}; "
        f"flete USD {incumbent_freight / 1000:,.2f}; "
        f"total USD {incumbent_total / 1000:,.2f}."
    )

    demand = operations.set_index("codigo_producto")[VOLUME_COLUMNS]
    model = cp_model.CpModel()
    x = {int(edge): model.new_bool_var(f"x_{edge}") for edge in matrix.index}

    for edges in matrix.groupby("codigo_producto").groups.values():
        model.add_exactly_one(x[int(edge)] for edge in edges)

    packaging_terms = []
    for candidate_id, edges in matrix.groupby("candidate_id").groups.items():
        for plant, volume_column in zip(PLANTS, VOLUME_COLUMNS):
            demand_terms = []
            maximum_volume = 0
            for edge in edges:
                sku = matrix.at[int(edge), "codigo_producto"]
                volume = int(demand.at[sku, volume_column])
                if volume > 0:
                    demand_terms.append(volume * x[int(edge)])
                    maximum_volume += volume
            if not demand_terms:
                continue

            q_by_tier = []
            z_by_tier = []
            for tier_index, (minimum, maximum, price_mil) in enumerate(TIERS):
                effective_maximum = (
                    maximum_volume
                    if maximum is None
                    else min(maximum, maximum_volume)
                )
                if minimum > effective_maximum:
                    continue
                z = model.new_bool_var(f"z_{candidate_id}_{plant}_{tier_index}")
                q = model.new_int_var(
                    0,
                    effective_maximum,
                    f"q_{candidate_id}_{plant}_{tier_index}",
                )
                model.add(q >= minimum * z)
                model.add(q <= effective_maximum * z)
                z_by_tier.append(z)
                q_by_tier.append(q)
                packaging_terms.append(price_mil * q)

            model.add_at_most_one(z_by_tier)
            model.add(sum(q_by_tier) == sum(demand_terms))

    freight_terms = [
        int(matrix.at[edge, "costo_flete_usd"]) * 1000 * x[int(edge)]
        for edge in matrix.index
    ]
    model.minimize(sum(freight_terms) + sum(packaging_terms))

    for edge in matrix.index:
        model.add_hint(x[int(edge)], int(edge in incumbent_edges))

    target_mil = None if target_total is None else int(round(target_total * 1000))
    callback = ImprovementCallback(
        x,
        matrix,
        candidates,
        output_path,
        incumbent_total,
        target_mil,
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.randomize_search = True
    solver.parameters.repair_hint = True
    solver.parameters.hint_conflict_limit = 1_000_000
    solver.parameters.polarity_exploit_ls_hints = True
    solver.parameters.log_search_progress = False

    status = solver.solve(model, callback)
    print(f"Estado: {solver.status_name(status)}")
    print(f"Objetivo final del solver: USD {solver.objective_value / 1000:,.2f}")
    print(f"Cota: USD {solver.best_objective_bound / 1000:,.2f}")
    print(f"Tiempo: {solver.wall_time:.1f} s")

    if callback.best_solution is not None:
        best_solution = callback.best_solution
    elif status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen_edges = [
            int(edge) for edge in matrix.index if solver.value(x[int(edge)])
        ]
        best_solution = solution_from_edges(chosen_edges, matrix, candidates)
    else:
        best_solution = (
            incumbent.merge(
                matrix,
                on=["codigo_producto", "candidate_id"],
                validate="one_to_one",
            )
            .merge(candidates, on="candidate_id", validate="many_to_one")
            .sort_values("codigo_producto")
            .reset_index(drop=True)
        )

    packaging, freight, total = assignment_objective_mil(
        best_solution,
        matrix,
        operations,
    )
    if total > incumbent_total:
        raise ValueError("El solver devolvió una solución peor que el incumbente.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    best_solution.to_csv(output_path, index=False)
    print(
        f"Solución guardada: {output_path}\n"
        f"Tipos: {best_solution['candidate_id'].nunique()}\n"
        f"Packaging: USD {packaging / 1000:,.2f}\n"
        f"Flete: USD {freight / 1000:,.2f}\n"
        f"Total: USD {total / 1000:,.2f}"
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--intermediate-dir", type=Path, default=INTERMEDIATE_DIR)
    parser.add_argument(
        "--incumbent",
        type=Path,
        default=CERTIFICATES_DIR / "incumbente_previo_188080231_80.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "solucion_busqueda.csv",
    )
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--seed", type=int, default=887)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--target-total",
        type=float,
        default=188_079_384.24,
        help="Se detiene al alcanzar este costo conocido. Use 0 para no detenerse.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    solve(
        data_dir=args.data_dir,
        intermediate_dir=args.intermediate_dir,
        incumbent_path=args.incumbent,
        output_path=args.output,
        seconds=args.seconds,
        seed=args.seed,
        workers=args.workers,
        target_total=None if args.target_total == 0 else args.target_total,
    )
