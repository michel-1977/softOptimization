# financial_sms_emoa

ParetoInvest multi-objective portfolio optimizer using SMS-EMOA.

## Problem

Given a set of candidate assets and a covariance matrix, build portfolios under cardinality constraints:

- Objective 1: maximize expected return
- Objective 2: minimize portfolio variance

Internally, SMS-EMOA is solved in minimization form using objectives:

- `f1 = -expected_return`
- `f2 = variance`

## Structure

- `src/io_utils.py`: instance loading and validation
- `src/paretoinvest_sms_emoa.py`: SMS-EMOA implementation + CLI
- `instances/instance_*.json`: deterministic benchmark set (12 instances)
- `scripts/run_benchmarks.py`: full benchmark runner
- `scripts/generate_instances.ps1`: deterministic instance generation
- `scripts/generate_manifest.ps1`: SHA-256 manifest builder
- `scripts/verify_manifest.ps1`: SHA-256 verification
- `MANIFEST.sha256`: checksum manifest

## Reproduce

```powershell
python financial_sms_emoa\scripts\run_benchmarks.py --seed 17 --population 64 --generations 700
```

Generate or refresh instances:

```powershell
powershell -ExecutionPolicy Bypass -File financial_sms_emoa\scripts\generate_instances.ps1
```

Refresh checksums:

```powershell
powershell -ExecutionPolicy Bypass -File financial_sms_emoa\scripts\generate_manifest.ps1
```
