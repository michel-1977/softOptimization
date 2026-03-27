# softOptimization

Local repository with two reproducible optimization projects:

1. `financial_sms_emoa/`: ParetoInvest implementation using SMS-EMOA for bi-objective portfolio optimization (maximize expected return, minimize portfolio variance).
2. `project_brkga/`: PPSSolver implementation using BRKGA for constrained project portfolio selection.
3. `paretoinvest_nsgaii_example/`: illustrative NSGA-II run wired to the official ParetoInvest upstream code/data artifacts for baseline comparison.

Each project includes:

- Solver source code (`src/`)
- Benchmark/test instances (`instances/`)
- Reproducibility scripts (`scripts/`)
- SHA-256 manifest for benchmark files (`MANIFEST.sha256`)
- Output folder for deterministic runs (`results/`)

## Quick Start

Create environment and install dependencies in one shot:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
```

Run each project benchmark suite:

```powershell
.venv\Scripts\python.exe financial_sms_emoa\scripts\run_benchmarks.py
.venv\Scripts\python.exe project_brkga\scripts\run_benchmarks.py
```

Run the illustrative ParetoInvest NSGA-II example:

```powershell
.venv\Scripts\python.exe -m paretoinvest_nsgaii_example.scripts.run_illustrative_example
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
