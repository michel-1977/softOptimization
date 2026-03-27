# Add Reproducible SMS-EMOA and BRKGA Optimization Projects

## Summary

This PR bootstraps the local `softOptimization` repository with two independent, reproducible optimization implementations:

1. `financial_sms_emoa/`: ParetoInvest-style SMS-EMOA for bi-objective portfolio optimization.
2. `project_brkga/`: PPSSolver-style BRKGA for constrained project portfolio selection.

Both projects include deterministic benchmark/test instance generation, benchmark runners, result output folders, and SHA-256 manifest tooling.

## What Changed

- Added repository documentation and reproducibility quick-start.
- Added `financial_sms_emoa`:
  - SMS-EMOA core algorithm (`src/paretoinvest_sms_emoa.py`)
  - Instance loader/validator (`src/io_utils.py`)
  - 12 benchmark instances under `instances/`
  - Benchmark runner (`scripts/run_benchmarks.py`)
  - Instance generation + checksum scripts
  - `MANIFEST.sha256`
- Added `project_brkga`:
  - BRKGA core solver (`src/pps_brkga.py`)
  - Instance loader/validator (`src/io_utils.py`)
  - 10 deterministic test instances under `instances/`
  - Benchmark runner (`scripts/run_benchmarks.py`)
  - Instance generation + checksum scripts
  - `MANIFEST.sha256`
- Added `.gitignore` with result artifact handling while keeping `.gitkeep`.

## Repro Commands

```powershell
python financial_sms_emoa\scripts\run_benchmarks.py
python project_brkga\scripts\run_benchmarks.py
```

```powershell
powershell -ExecutionPolicy Bypass -File financial_sms_emoa\scripts\verify_manifest.ps1
powershell -ExecutionPolicy Bypass -File project_brkga\scripts\verify_manifest.ps1
```

## Validation Performed

- Generated all financial and project benchmark instances from deterministic scripts.
- Generated both SHA-256 manifests.
- Verified manifest integrity for all instance files with `verify_manifest.ps1`.
