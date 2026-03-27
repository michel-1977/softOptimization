from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import json
import random
from typing import Iterable

try:
    from .io_utils import PortfolioInstance, load_instance
except ImportError:
    from io_utils import PortfolioInstance, load_instance


Objective = tuple[float, float]
Genome = tuple[int, ...]


@dataclass(frozen=True)
class Individual:
    genome: Genome
    objectives: Objective


def dominates(lhs: Objective, rhs: Objective) -> bool:
    return (lhs[0] <= rhs[0] and lhs[1] <= rhs[1]) and (lhs[0] < rhs[0] or lhs[1] < rhs[1])


def build_reference_point(objectives: Iterable[Objective]) -> Objective:
    points = list(objectives)
    max_f1 = max(point[0] for point in points)
    max_f2 = max(point[1] for point in points)
    margin_f1 = max(1e-6, abs(max_f1) * 0.10)
    margin_f2 = max(1e-6, abs(max_f2) * 0.10)
    return (max_f1 + margin_f1, max_f2 + margin_f2)


def hypervolume_2d(objectives: list[Objective], reference: Objective) -> float:
    if not objectives:
        return 0.0
    points = sorted(objectives, key=lambda point: (point[0], point[1]))
    hv = 0.0
    current_height = reference[1]
    for f1, f2 in points:
        width = max(0.0, reference[0] - f1)
        height = max(0.0, current_height - f2)
        hv += width * height
        if f2 < current_height:
            current_height = f2
    return hv


def hypervolume_contributions(front: list[Individual], reference: Objective) -> list[float]:
    points = [member.objectives for member in front]
    baseline = hypervolume_2d(points, reference)
    contributions: list[float] = []
    for idx in range(len(front)):
        reduced = points[:idx] + points[idx + 1 :]
        contributions.append(max(0.0, baseline - hypervolume_2d(reduced, reference)))
    return contributions


def evaluate_genome(instance: PortfolioInstance, genome: Genome) -> Objective:
    selected = [idx for idx, bit in enumerate(genome) if bit == 1]
    if not selected:
        return (1e6, 1e6)

    size = len(selected)
    weight = 1.0 / size
    expected_return = sum(instance.assets[idx].expected_return * weight for idx in selected)

    variance = 0.0
    for i in selected:
        for j in selected:
            variance += weight * weight * instance.covariance[i][j]

    cardinality_penalty = 0.0
    if size < instance.min_assets:
        cardinality_penalty = (instance.min_assets - size) * 1.5
    elif size > instance.max_assets:
        cardinality_penalty = (size - instance.max_assets) * 1.5

    return (-expected_return + cardinality_penalty, variance + cardinality_penalty)


def repair_genome(genome: Genome, instance: PortfolioInstance, rng: random.Random) -> Genome:
    genes = list(genome)
    selected = [idx for idx, bit in enumerate(genes) if bit == 1]
    unselected = [idx for idx, bit in enumerate(genes) if bit == 0]

    while len(selected) < instance.min_assets and unselected:
        pick = rng.choice(unselected)
        genes[pick] = 1
        unselected.remove(pick)
        selected.append(pick)

    while len(selected) > instance.max_assets:
        drop = rng.choice(selected)
        genes[drop] = 0
        selected.remove(drop)

    if not selected:
        genes[rng.randrange(len(genes))] = 1
    return tuple(genes)


def random_feasible_genome(instance: PortfolioInstance, rng: random.Random) -> Genome:
    size = rng.randint(instance.min_assets, instance.max_assets)
    picks = rng.sample(range(len(instance.assets)), size)
    genes = [0] * len(instance.assets)
    for idx in picks:
        genes[idx] = 1
    return tuple(genes)


def mutate_genome(
    genome: Genome,
    mutation_rate: float,
    instance: PortfolioInstance,
    rng: random.Random,
) -> Genome:
    genes = list(genome)
    for idx in range(len(genes)):
        if rng.random() < mutation_rate:
            genes[idx] = 1 - genes[idx]
    return repair_genome(tuple(genes), instance, rng)


def uniform_crossover(lhs: Genome, rhs: Genome, rng: random.Random) -> Genome:
    child = [lhs[idx] if rng.random() < 0.5 else rhs[idx] for idx in range(len(lhs))]
    return tuple(child)


def fast_non_dominated_sort(population: list[Individual]) -> tuple[list[list[int]], dict[int, int]]:
    domination_count = [0] * len(population)
    dominates_list: list[list[int]] = [[] for _ in population]
    fronts: list[list[int]] = [[]]

    for p_idx, p_item in enumerate(population):
        for q_idx, q_item in enumerate(population):
            if p_idx == q_idx:
                continue
            if dominates(p_item.objectives, q_item.objectives):
                dominates_list[p_idx].append(q_idx)
            elif dominates(q_item.objectives, p_item.objectives):
                domination_count[p_idx] += 1
        if domination_count[p_idx] == 0:
            fronts[0].append(p_idx)

    rank: dict[int, int] = {}
    current_front = 0
    while current_front < len(fronts) and fronts[current_front]:
        next_front: list[int] = []
        for p_idx in fronts[current_front]:
            rank[p_idx] = current_front
            for q_idx in dominates_list[p_idx]:
                domination_count[q_idx] -= 1
                if domination_count[q_idx] == 0:
                    next_front.append(q_idx)
        if next_front:
            fronts.append(next_front)
        current_front += 1

    return fronts, rank


def tournament_select(
    population: list[Individual], rank_map: dict[int, int], rng: random.Random
) -> int:
    cand_a, cand_b = rng.sample(range(len(population)), 2)
    rank_a = rank_map[cand_a]
    rank_b = rank_map[cand_b]
    if rank_a < rank_b:
        return cand_a
    if rank_b < rank_a:
        return cand_b

    score_a = population[cand_a].objectives[0] + population[cand_a].objectives[1]
    score_b = population[cand_b].objectives[0] + population[cand_b].objectives[1]
    if score_a < score_b:
        return cand_a
    if score_b < score_a:
        return cand_b
    return cand_a if rng.random() < 0.5 else cand_b


def trim_population(population: list[Individual], target_size: int) -> None:
    while len(population) > target_size:
        fronts, _ = fast_non_dominated_sort(population)
        worst_front_indices = fronts[-1]
        if len(worst_front_indices) == 1:
            population.pop(worst_front_indices[0])
            continue

        worst_front = [population[idx] for idx in worst_front_indices]
        reference = build_reference_point(item.objectives for item in worst_front)
        contributions = hypervolume_contributions(worst_front, reference)
        local_drop = min(
            range(len(worst_front)),
            key=lambda idx: (
                contributions[idx],
                worst_front[idx].objectives[0] + worst_front[idx].objectives[1],
            ),
        )
        population.pop(worst_front_indices[local_drop])


def extract_pareto_front(population: list[Individual]) -> list[Individual]:
    fronts, _ = fast_non_dominated_sort(population)
    return [population[idx] for idx in fronts[0]]


def run_sms_emoa(
    instance: PortfolioInstance,
    seed: int = 17,
    population_size: int = 64,
    generations: int = 700,
    crossover_rate: float = 0.9,
    mutation_rate: float | None = None,
) -> dict[str, object]:
    rng = random.Random(seed)
    if mutation_rate is None:
        mutation_rate = 1.0 / len(instance.assets)

    population: list[Individual] = []
    seen: set[Genome] = set()
    while len(population) < population_size:
        genome = random_feasible_genome(instance, rng)
        if genome in seen:
            continue
        seen.add(genome)
        population.append(Individual(genome=genome, objectives=evaluate_genome(instance, genome)))

    history: list[dict[str, float | int]] = []
    for generation in range(generations):
        _, rank_map = fast_non_dominated_sort(population)
        parent_a = population[tournament_select(population, rank_map, rng)]
        parent_b = population[tournament_select(population, rank_map, rng)]

        if rng.random() < crossover_rate:
            child_genome = uniform_crossover(parent_a.genome, parent_b.genome, rng)
        else:
            child_genome = parent_a.genome
        child_genome = mutate_genome(child_genome, mutation_rate, instance, rng)
        child = Individual(genome=child_genome, objectives=evaluate_genome(instance, child_genome))

        population.append(child)
        trim_population(population, population_size)

        if generation % 50 == 0 or generation == generations - 1:
            front = extract_pareto_front(population)
            history.append(
                {
                    "generation": generation + 1,
                    "front_size": len(front),
                    "best_return": max(-item.objectives[0] for item in front),
                    "best_variance": min(item.objectives[1] for item in front),
                }
            )

    front = sorted(
        extract_pareto_front(population),
        key=lambda item: (item.objectives[0], item.objectives[1]),
    )
    return {
        "front": front,
        "history": history,
        "population": population,
        "seed": seed,
        "generations": generations,
        "population_size": population_size,
    }


def write_front_csv(front: list[Individual], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "selected_assets", "expected_return", "variance", "genome"])
        for rank, item in enumerate(front, start=1):
            selected_assets = sum(item.genome)
            writer.writerow(
                [
                    rank,
                    selected_assets,
                    -item.objectives[0],
                    item.objectives[1],
                    "".join(str(bit) for bit in item.genome),
                ]
            )


def _cli() -> None:
    parser = argparse.ArgumentParser(description="ParetoInvest SMS-EMOA runner.")
    parser.add_argument("--instance", required=True, help="Path to a benchmark instance JSON file.")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--population", type=int, default=64)
    parser.add_argument("--generations", type=int, default=700)
    parser.add_argument("--out-front", type=str, default="")
    parser.add_argument("--out-history", type=str, default="")
    args = parser.parse_args()

    instance = load_instance(args.instance)
    result = run_sms_emoa(
        instance=instance,
        seed=args.seed,
        population_size=args.population,
        generations=args.generations,
    )
    front = result["front"]
    history = result["history"]

    if args.out_front:
        write_front_csv(front, args.out_front)
    if args.out_history:
        out_history = Path(args.out_history)
        out_history.parent.mkdir(parents=True, exist_ok=True)
        out_history.write_text(json.dumps(history, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "instance": instance.name,
                "front_size": len(front),
                "best_return": max(-item.objectives[0] for item in front),
                "min_variance": min(item.objectives[1] for item in front),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    _cli()
