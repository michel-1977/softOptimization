# softOptimization

Local repository with two reproducible optimization projects:

1. `financial_sms_emoa/`: ParetoInvest implementation using SMS-EMOA for bi-objective portfolio optimization (maximize expected return, minimize portfolio variance).
2. `project_brkga/`: PPSSolver implementation using BRKGA for constrained project portfolio selection.

Each project includes:

- Solver source code (`src/`)
- Benchmark/test instances (`instances/`)
- Reproducibility scripts (`scripts/`)
- SHA-256 manifest for benchmark files (`MANIFEST.sha256`)
- Output folder for deterministic runs (`results/`)

## Quick Start

Run each project benchmark suite:

```powershell
python financial_sms_emoa\scripts\run_benchmarks.py
python project_brkga\scripts\run_benchmarks.py
```

Verify checksums:

```powershell
powershell -ExecutionPolicy Bypass -File financial_sms_emoa\scripts\verify_manifest.ps1
powershell -ExecutionPolicy Bypass -File project_brkga\scripts\verify_manifest.ps1
```

If the benchmark instances are regenerated, refresh checksums with:

```powershell
powershell -ExecutionPolicy Bypass -File financial_sms_emoa\scripts\generate_manifest.ps1
powershell -ExecutionPolicy Bypass -File project_brkga\scripts\generate_manifest.ps1
```
