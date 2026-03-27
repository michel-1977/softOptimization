# paretoinvest_nsgaii_example

Reproducible runner for the ParetoInvest illustrative NSGA-II experiment using:

- Official ParetoInvest Java algorithm binary (`portfolio-6.2.3-SNAPSHOT-jar-with-dependencies.jar`)
- Official ParetoInvest financial dataset bundle (`IB_Day.zip`) and assets list (`Assets.csv`)
- Same seed and NSGA-II configuration family described in the illustrative section (seed `12345`, `5000` evaluations, population `100`)

## What This Module Does

1. Reads official upstream artifacts from `_upstream/ParetoInvest`.
2. Generates JMetal input files using ParetoInvest's own preprocessing code.
3. Executes `org.uma.jmetal.portfolio.algorithm.NSGAIIExample`.
4. Stores a report with command, runtime, stdout/stderr, and result file path:
   `results/illustrative_example_report.json`

## Run

From repository root:

```powershell
.venv\Scripts\python.exe -m paretoinvest_nsgaii_example.scripts.run_illustrative_example
```

This now defaults to `--mode custom` (fully Python data-preprocessing + NSGA-II) with the same parameter values as the illustrative setup.
To run the upstream Java baseline instead:

```powershell
.venv\Scripts\python.exe -m paretoinvest_nsgaii_example.scripts.run_illustrative_example --mode baseline
```

If `_upstream/ParetoInvest` is missing, clone it first:

```powershell
git clone https://github.com/AntHidMar/ParetoInvest.git _upstream\ParetoInvest
```

## Default Configuration

- `population-size = 100`
- `num-assets-studied = 5`
- `num-assets-total = 100`
- `num-evals = 5000`
- `max-evals-without-changes = 100`
- `crossover-probability = 0.9`
- `crossover-distribution-index = 20.0`
- `mutation-distribution-index = 20.0`
- `mutation-probability = 0.01` (validated against upstream implicit rule `1/num-assets-total`)
- `seed = 12345`
- `market = ALL`
- `start-date = 2024-11-02`
- `end-date = 2025-11-02`

The report includes `paper_reference_ms = 5692` to compare observed wall-clock time against the value cited in the illustrative section.

You can pass mutation probability explicitly:

```powershell
.venv\Scripts\python.exe -m paretoinvest_nsgaii_example.scripts.run_illustrative_example --mutation-probability 0.01
```

Note: upstream `NSGAIIExample` computes mutation probability internally as `1/numberOfVariables`, so this argument is validated for consistency and logged in the JSON report.

## Attribution

This module vendors ParetoInvest preprocessing code from:

- `AntHidMar/ParetoInvest` (`ParetoInvest/models/GenerarArchivosEstadisticos_JMetal.py`)

Please keep upstream attribution and license terms when redistributing or publishing derived artifacts.
