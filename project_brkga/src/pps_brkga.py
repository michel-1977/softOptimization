from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import random

try:
    from .io_utils import PPSInstance, load_instance
except ImportError:
    from io_utils import PPSInstance, load_instance


@dataclass(frozen=True)
class DecodedSolution:
    fitness: float
    total_value: float
    total_risk: float
    total_cost: int
    selected_projects: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    keys: tuple[float, ...]
    decoded: DecodedSolution


def decode_keys(instance: PPSInstance, keys: tuple[float, ...]) -> DecodedSolution:
    projects = instance.projects
    order = sorted(range(len(projects)), key=lambda idx: keys[idx], reverse=True)

    selected: set[str] = set()
    selected_order: list[str] = []
    remaining_budget = instance.budget
    total_value = 0.0
    total_risk = 0.0
    total_cost = 0

    pending = order
    for _ in range(len(projects)):
        progressed = False
        next_pending: list[int] = []
        for idx in pending:
            project = projects[idx]
            if any(dep not in selected for dep in project.prerequisites):
                next_pending.append(idx)
                continue
            if project.cost <= remaining_budget:
                selected.add(project.project_id)
                selected_order.append(project.project_id)
                remaining_budget -= project.cost
                total_cost += project.cost
                total_value += project.value
                total_risk += project.risk
                progressed = True
        if not progressed:
            break
        pending = next_pending

    fitness = total_value - instance.risk_aversion * total_risk
    return DecodedSolution(
        fitness=fitness,
        total_value=total_value,
        total_risk=total_risk,
        total_cost=total_cost,
        selected_projects=tuple(selected_order),
    )


def evaluate_population(instance: PPSInstance, population: list[tuple[float, ...]]) -> list[Candidate]:
    return [Candidate(keys=keys, decoded=decode_keys(instance, keys)) for keys in population]


def run_brkga(
    instance: PPSInstance,
    seed: int = 31,
    population_size: int = 120,
    generations: int = 500,
    elite_fraction: float = 0.20,
    mutant_fraction: float = 0.10,
    inheritance_prob: float = 0.70,
) -> dict[str, object]:
    rng = random.Random(seed)
    gene_count = len(instance.projects)
    if gene_count == 0:
        raise ValueError("Instance has no projects.")

    n_elite = max(1, int(population_size * elite_fraction))
    n_mutants = max(1, int(population_size * mutant_fraction))
    n_crossovers = population_size - n_elite - n_mutants
    if n_crossovers < 1:
        n_crossovers = 1
        n_mutants = max(1, population_size - n_elite - n_crossovers)
    if n_elite + n_mutants + n_crossovers != population_size:
        n_crossovers = population_size - n_elite - n_mutants

    def random_keys() -> tuple[float, ...]:
        return tuple(rng.random() for _ in range(gene_count))

    population = [random_keys() for _ in range(population_size)]
    best_candidate: Candidate | None = None
    history: list[dict[str, float | int]] = []

    for generation in range(generations):
        evaluated = evaluate_population(instance, population)
        evaluated.sort(key=lambda cand: cand.decoded.fitness, reverse=True)
        current_best = evaluated[0]
        if best_candidate is None or current_best.decoded.fitness > best_candidate.decoded.fitness:
            best_candidate = current_best

        if generation % 25 == 0 or generation == generations - 1:
            history.append(
                {
                    "generation": generation + 1,
                    "best_fitness": current_best.decoded.fitness,
                    "best_value": current_best.decoded.total_value,
                    "best_cost": current_best.decoded.total_cost,
                    "selected_projects": len(current_best.decoded.selected_projects),
                }
            )

        elites = evaluated[:n_elite]
        non_elites = evaluated[n_elite:]
        if not non_elites:
            non_elites = elites

        next_population: list[tuple[float, ...]] = [item.keys for item in elites]
        for _ in range(n_crossovers):
            elite_parent = rng.choice(elites).keys
            other_parent = rng.choice(non_elites).keys
            child = tuple(
                elite_parent[idx] if rng.random() < inheritance_prob else other_parent[idx]
                for idx in range(gene_count)
            )
            next_population.append(child)

        for _ in range(n_mutants):
            next_population.append(random_keys())

        population = next_population[:population_size]

    assert best_candidate is not None
    return {
        "best": best_candidate.decoded,
        "history": history,
        "seed": seed,
        "population_size": population_size,
        "generations": generations,
        "parameters": {
            "elite_fraction": elite_fraction,
            "mutant_fraction": mutant_fraction,
            "inheritance_prob": inheritance_prob,
        },
    }


def solution_to_dict(solution: DecodedSolution) -> dict[str, object]:
    return {
        "fitness": solution.fitness,
        "total_value": solution.total_value,
        "total_risk": solution.total_risk,
        "total_cost": solution.total_cost,
        "selected_projects": list(solution.selected_projects),
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="PPSSolver BRKGA runner.")
    parser.add_argument("--instance", required=True, help="Path to a project benchmark instance.")
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--population", type=int, default=120)
    parser.add_argument("--generations", type=int, default=500)
    parser.add_argument("--out", type=str, default="")
    parser.add_argument("--out-history", type=str, default="")
    args = parser.parse_args()

    instance = load_instance(args.instance)
    result = run_brkga(
        instance=instance,
        seed=args.seed,
        population_size=args.population,
        generations=args.generations,
    )
    best = result["best"]

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(solution_to_dict(best), indent=2), encoding="utf-8")

    if args.out_history:
        history_path = Path(args.out_history)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(result["history"], indent=2), encoding="utf-8")

    print(json.dumps(solution_to_dict(best), indent=2))


if __name__ == "__main__":
    _cli()
