# project_brkga

PPSSolver implementation using a Biased Random-Key Genetic Algorithm (BRKGA).

## Problem

Constrained project portfolio selection with:

- Global budget limit
- Optional project prerequisites
- Benefit-value maximization with risk-aware scoring

Fitness decoded by BRKGA:

`fitness = total_value - risk_aversion * total_risk`

## Structure

- `src/io_utils.py`: instance loading and validation
- `src/pps_brkga.py`: BRKGA implementation + CLI
- `instances/pps_*.json`: deterministic test instances
- `scripts/run_benchmarks.py`: reproducibility benchmark runner
- `scripts/generate_instances.ps1`: deterministic instance generation
- `scripts/generate_manifest.ps1`: SHA-256 manifest builder
- `scripts/verify_manifest.ps1`: SHA-256 verification
- `MANIFEST.sha256`: checksum manifest

## Reproduce

```powershell
python project_brkga\scripts\run_benchmarks.py --seed 31 --population 120 --generations 500 --repetitions 7
```

Generate or refresh instances:

```powershell
powershell -ExecutionPolicy Bypass -File project_brkga\scripts\generate_instances.ps1
```

Refresh checksums:

```powershell
powershell -ExecutionPolicy Bypass -File project_brkga\scripts\generate_manifest.ps1
```
