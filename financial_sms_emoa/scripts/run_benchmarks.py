from __future__ import annotations

from pathlib import Path
import argparse
import csv
import json
import time

ROOT = Path(__file__).resolve().parents[1]

from financial_sms_emoa.src.io_utils import load_instance
from financial_sms_emoa.src.paretoinvest_sms_emoa import (
    build_reference_point,
    hypervolume_2d,
    run_sms_emoa,
    write_front_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all financial SMS-EMOA benchmark instances.")
    parser.add_argument("--instances-dir", type=str, default=str(ROOT / "instances"))
    parser.add_argument("--results-dir", type=str, default=str(ROOT / "results"))
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--population", type=int, default=64)
    parser.add_argument("--generations", type=int, default=700)
    return parser.parse_args()


def run_suite(args: argparse.Namespace) -> dict[str, object]:
    instances_dir = Path(args.instances_dir)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    instance_files = sorted(instances_dir.glob("instance_*.json"))
    if not instance_files:
        raise FileNotFoundError(
            f"No instance files matching 'instance_*.json' were found in: {instances_dir}"
        )

    for instance_file in instance_files:
        instance = load_instance(instance_file)
        start = time.perf_counter()
        result = run_sms_emoa(
            instance=instance,
            seed=args.seed,
            population_size=args.population,
            generations=args.generations,
        )
        elapsed = time.perf_counter() - start
        front = result["front"]
        objectives = [item.objectives for item in front]
        reference = build_reference_point(objectives)
        hv = hypervolume_2d(objectives, reference)
        best_return = max(-item.objectives[0] for item in front)
        best_variance = min(item.objectives[1] for item in front)

        front_path = results_dir / f"{instance_file.stem}_front.csv"
        write_front_csv(front, front_path)
        history_path = results_dir / f"{instance_file.stem}_history.json"
        history_path.write_text(json.dumps(result["history"], indent=2), encoding="utf-8")

        row = {
            "instance": instance.name,
            "assets": len(instance.assets),
            "front_size": len(front),
            "best_return": best_return,
            "best_variance": best_variance,
            "hypervolume": hv,
            "runtime_sec": elapsed,
            "seed": args.seed,
            "population": args.population,
            "generations": args.generations,
        }
        rows.append(row)
        print(
            f"{instance.name}: front={row['front_size']} best_return={best_return:.6f} "
            f"best_variance={best_variance:.6f} hv={hv:.6f} time={elapsed:.3f}s"
        )

    summary_csv = results_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary_json = results_dir / "summary.json"
    payload = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "parameters": {
            "seed": args.seed,
            "population": args.population,
            "generations": args.generations,
        },
        "instances": rows,
    }
    summary_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
