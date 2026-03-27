from __future__ import annotations

from pathlib import Path
import argparse
import csv
import json
import statistics
import time

ROOT = Path(__file__).resolve().parents[1]

from project_brkga.src.io_utils import load_instance
from project_brkga.src.pps_brkga import run_brkga, solution_to_dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all BRKGA project benchmark instances.")
    parser.add_argument("--instances-dir", type=str, default=str(ROOT / "instances"))
    parser.add_argument("--results-dir", type=str, default=str(ROOT / "results"))
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--population", type=int, default=120)
    parser.add_argument("--generations", type=int, default=500)
    parser.add_argument("--repetitions", type=int, default=7)
    return parser.parse_args()


def run_suite(args: argparse.Namespace) -> dict[str, object]:
    instances_dir = Path(args.instances_dir)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    instance_files = sorted(instances_dir.glob("pps_*.json"))
    if not instance_files:
        raise FileNotFoundError(
            f"No instance files matching 'pps_*.json' were found in: {instances_dir}"
        )

    for instance_file in instance_files:
        instance = load_instance(instance_file)
        runs: list[dict[str, object]] = []
        runtime_start = time.perf_counter()

        for rep in range(args.repetitions):
            seed = args.seed + rep
            result = run_brkga(
                instance=instance,
                seed=seed,
                population_size=args.population,
                generations=args.generations,
            )
            best = result["best"]
            runs.append(
                {
                    "seed": seed,
                    "fitness": best.fitness,
                    "total_value": best.total_value,
                    "total_risk": best.total_risk,
                    "total_cost": best.total_cost,
                    "selected_projects": len(best.selected_projects),
                    "solution": solution_to_dict(best),
                    "history": result["history"],
                }
            )

        elapsed = time.perf_counter() - runtime_start
        best_run = max(runs, key=lambda item: item["fitness"])
        fitness_values = [item["fitness"] for item in runs]
        row = {
            "instance": instance.name,
            "projects": len(instance.projects),
            "budget": instance.budget,
            "best_fitness": best_run["fitness"],
            "mean_fitness": statistics.mean(fitness_values),
            "std_fitness": statistics.pstdev(fitness_values),
            "best_total_value": best_run["total_value"],
            "best_total_risk": best_run["total_risk"],
            "best_total_cost": best_run["total_cost"],
            "selected_projects": best_run["selected_projects"],
            "runtime_sec": elapsed,
            "repetitions": args.repetitions,
        }
        summary_rows.append(row)

        (results_dir / f"{instance_file.stem}_best_solution.json").write_text(
            json.dumps(best_run["solution"], indent=2),
            encoding="utf-8",
        )
        (results_dir / f"{instance_file.stem}_runs.json").write_text(
            json.dumps(runs, indent=2),
            encoding="utf-8",
        )

        print(
            f"{instance.name}: best={row['best_fitness']:.4f} mean={row['mean_fitness']:.4f} "
            f"std={row['std_fitness']:.4f} projects={row['selected_projects']} time={elapsed:.3f}s"
        )

    summary_csv = results_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    payload = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "parameters": {
            "seed": args.seed,
            "population": args.population,
            "generations": args.generations,
            "repetitions": args.repetitions,
        },
        "instances": summary_rows,
    }
    (results_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    args = parse_args()
    try:
        payload = run_suite(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        raise
    print(json.dumps({"completed_instances": len(payload["instances"])}, indent=2))


if __name__ == "__main__":
    main()
