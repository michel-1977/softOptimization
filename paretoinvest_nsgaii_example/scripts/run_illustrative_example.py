from __future__ import annotations

from pathlib import Path
from datetime import date, datetime, timedelta
import argparse
import csv
import importlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import time
import zipfile

import numpy as np
try:
    matplotlib = importlib.import_module("matplotlib")
    matplotlib.use("Agg")
    plt = importlib.import_module("matplotlib.pyplot")
except Exception:  # pragma: no cover
    matplotlib = None
    plt = None

try:
    pd = importlib.import_module("pandas")
except Exception:  # pragma: no cover
    pd = None


PAPER_REFERENCE_TIME_MS = 5692

# Rollback note:
# We intentionally keep baseline Java execution support below.
# Previous pandas/upstream-preprocessor flow was replaced by pure Python preprocessing
# for reliability under VS Code debug sessions.


def _check_numpy_runtime() -> None:
    required = ("array", "cov", "zeros", "argpartition")
    missing = [name for name in required if not hasattr(np, name)]
    if missing:
        module_file = getattr(np, "__file__", "<unknown>")
        module_version = getattr(np, "__version__", "<unknown>")
        raise RuntimeError(
            "Detected incomplete/broken NumPy runtime. "
            f"Missing attributes: {missing}. "
            f"Loaded module: {module_file}, version: {module_version}. "
            f"Type: {type(np)}. "
            "Reinstall NumPy in the selected interpreter and remove any local 'numpy' shadow modules."
        )


def resolve_java_bin(args: argparse.Namespace) -> str:
    if args.java_bin:
        return args.java_bin

    local_java_root = Path(".tools/java17").resolve()
    if local_java_root.exists():
        candidates = sorted(local_java_root.glob("jdk-*/bin/java.exe"))
        if candidates:
            return str(candidates[-1])
    return "java"


def require_java_11_or_newer(java_bin: str) -> None:
    probe = subprocess.run(
        [java_bin, "-version"],
        text=True,
        capture_output=True,
    )
    output = (probe.stderr or "") + "\n" + (probe.stdout or "")
    if probe.returncode != 0:
        raise RuntimeError("Java runtime not found. Install Java 11+ and ensure 'java' is in PATH.")

    # Handles lines like: java version "1.8.0_221" or openjdk version "17.0.11"
    match = re.search(r'version "([^"]+)"', output)
    if not match:
        raise RuntimeError(f"Unable to detect Java version from: {output.strip()}")
    version_text = match.group(1)

    if version_text.startswith("1."):
        major = int(version_text.split(".")[1])
    else:
        major = int(version_text.split(".")[0])

    if major < 11:
        raise RuntimeError(
            f"Java {version_text} detected. ParetoInvest JAR requires Java 11+ "
            "(class file version 55)."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run ParetoInvest NSGA-II illustrative example using the official upstream "
            "code path and official benchmark files."
        )
    )
    parser.add_argument(
        "--upstream-root",
        type=str,
        default="_upstream/ParetoInvest",
        help="Path to the cloned upstream ParetoInvest repository.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2024-11-02",
        help="Study start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2025-11-02",
        help="Study end date (YYYY-MM-DD).",
    )
    parser.add_argument("--population-size", type=int, default=100)
    parser.add_argument("--num-assets-studied", type=int, default=5)
    parser.add_argument("--num-assets-total", type=int, default=100)
    parser.add_argument("--num-evals", type=int, default=5000)
    parser.add_argument("--max-evals-without-changes", type=int, default=100)
    parser.add_argument("--crossover-probability", type=float, default=0.9)
    parser.add_argument("--crossover-distribution-index", type=float, default=20.0)
    parser.add_argument("--mutation-distribution-index", type=float, default=20.0)
    parser.add_argument(
        "--mutation-probability",
        type=float,
        default=None,
        help=(
            "Desired mutation probability. Upstream NSGAIIExample sets this internally as "
            "1/numberOfVariables, so this value is validated against that implicit behavior."
        ),
    )
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--market", type=str, default="ALL")
    parser.add_argument("--asset-class", type=str, default="us_equity")
    parser.add_argument("--asset-type", type=str, default="ALL")
    parser.add_argument("--refined-asset-type", type=str, default="ALL")
    parser.add_argument("--sector", type=str, default="ALL")
    parser.add_argument(
        "--allow-non-tradable",
        action="store_true",
        help="Include non-tradable assets (disabled by default for paper-style stock universe).",
    )
    parser.add_argument("--frequency", type=str, default="Day")
    parser.add_argument(
        "--keep-extracted",
        action="store_true",
        help="Keep extracted market CSV files after execution.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=("custom", "baseline"),
        default="baseline",
        help="Execution mode: custom Python NSGA-II or baseline upstream Java NSGA-II.",
    )
    parser.add_argument(
        "--java-bin",
        type=str,
        default="",
        help="Optional explicit path to java executable.",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Disable Pareto front plotting.",
    )
    return parser.parse_args()


def ensure_upstream_assets(upstream_root: Path) -> tuple[Path, Path, Path]:
    jar = upstream_root / "ParetoInvest" / "jar" / "portfolio-6.2.3-SNAPSHOT-jar-with-dependencies.jar"
    assets_csv = upstream_root / "data" / "Assets" / "Assets.csv"
    ib_day_zip = upstream_root / "data" / "financial_data" / "IB_Day.zip"

    missing = [str(path) for path in (jar, assets_csv, ib_day_zip) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing upstream ParetoInvest artifacts. Expected files not found:\n"
            + "\n".join(missing)
            + "\nClone https://github.com/AntHidMar/ParetoInvest into _upstream/ParetoInvest."
        )
    return jar, assets_csv, ib_day_zip


def extract_market_data(ib_day_zip: Path, target_dir: Path) -> Path:
    extract_root = target_dir / "financial_data"
    ib_day_dir = extract_root / "IB_Day"
    if ib_day_dir.exists() and any(ib_day_dir.glob("Day_*_.csv")):
        return ib_day_dir

    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ib_day_zip, "r") as archive:
        archive.extractall(extract_root)
    return ib_day_dir


def _parse_day(raw_value: str) -> date | None:
    text = str(raw_value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _count_records_in_window(file_path: Path, start_date: date, end_date: date) -> int:
    if pd is not None:
        try:
            df = pd.read_csv(
                file_path,
                header=0,
                encoding="utf-8",
                parse_dates=[0],
                index_col=[0],
                date_parser=lambda x: pd.to_datetime(x.rpartition("+")[0]),
            )
            df.index = pd.to_datetime(df.index)
            df = df.loc[~df.index.duplicated(keep="first")]
            start_ts = pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date)
            windowed = df[(df.index >= start_ts) & (df.index <= end_ts)]
            return int(len(windowed))
        except Exception:
            pass

    days: set[date] = set()
    with file_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            day = _parse_day(str(row.get("date", "")))
            if day is None:
                continue
            if start_date <= day <= end_date:
                days.add(day)
    return len(days)


def _load_candidate_assets(
    assets_csv: Path,
    market_csv_dir: Path,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    class_filter = args.asset_class.strip().lower()
    market_filter = args.market.strip().upper()
    asset_type_filter = args.asset_type.strip().upper()
    refined_asset_type_filter = args.refined_asset_type.strip().upper()
    sector_filter = args.sector.strip().upper()
    candidates: list[dict[str, object]] = []

    with assets_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            asset_class = str(row.get("class", "")).strip().lower()
            if class_filter != "all" and asset_class != class_filter:
                continue

            status = str(row.get("status", "")).strip().lower()
            if status != "active":
                continue

            tradable_text = str(row.get("tradable", "")).strip().lower()
            is_tradable = tradable_text in ("true", "1", "yes")
            if not args.allow_non_tradable and not is_tradable:
                continue

            exchange = str(row.get("exchange", "")).strip().upper()
            if market_filter != "ALL" and exchange != market_filter:
                continue

            asset_type = str(row.get("asset_type", "")).strip().upper()
            if asset_type_filter != "ALL" and asset_type != asset_type_filter:
                continue

            refined_asset_type = str(row.get("refined_asset_type", "")).strip().upper()
            if refined_asset_type_filter != "ALL" and refined_asset_type != refined_asset_type_filter:
                continue

            sector = str(row.get("FMP_sector", "")).strip().upper()
            if sector_filter != "ALL" and sector != sector_filter:
                continue

            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue

            file_path = market_csv_dir / f"{args.frequency}_{symbol}_.csv"
            if not file_path.exists():
                continue

            candidates.append(
                {
                    "symbol": symbol,
                    "class": asset_class,
                    "exchange": exchange,
                    "asset_type": asset_type,
                    "refined_asset_type": refined_asset_type,
                    "sector": sector,
                    "tradable": is_tradable,
                    "path": file_path,
                }
            )
    return candidates


def _select_top_assets_by_records(
    candidates: list[dict[str, object]],
    start_date: date,
    end_date: date,
    top_n: int,
) -> list[dict[str, object]]:
    top_assets: list[dict[str, object]] = []
    max_records = 0

    for item in candidates:
        file_path = item["path"]
        if not isinstance(file_path, Path):
            continue

        records = _count_records_in_window(file_path, start_date, end_date)
        item_with_records = dict(item)
        item_with_records["records_in_window"] = records
        if records > max_records:
            max_records = records

        if len(top_assets) < top_n:
            top_assets.append(item_with_records)
            top_assets.sort(key=lambda x: int(x["records_in_window"]), reverse=True)
        elif records > int(top_assets[-1]["records_in_window"]):
            top_assets[-1] = item_with_records
            top_assets.sort(key=lambda x: int(x["records_in_window"]), reverse=True)

        if len(top_assets) == top_n:
            threshold = max_records - (max_records * 0.1)
            if all(int(asset["records_in_window"]) >= threshold for asset in top_assets):
                break

    return top_assets


def _parse_asset_returns(
    file_path: Path,
    start_date: date,
    end_date: date,
) -> tuple[dict[date, float], float]:
    if pd is not None:
        try:
            df_temp = pd.read_csv(
                file_path,
                header=0,
                encoding="utf-8",
                parse_dates=[0],
                index_col=[0],
                date_parser=lambda x: pd.to_datetime(x.rpartition("+")[0]),
            )
            df_temp.index = pd.to_datetime(df_temp.index)
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            df_temp = df_temp.loc[start_str:end_str]
            df_temp = df_temp[~df_temp.index.duplicated(keep="first")]
            if len(df_temp) < 2:
                return {}, 0.0

            df_temp = df_temp.sort_index()
            df_temp = df_temp.resample("d").last()
            series_name = str(file_path).replace("_.csv", "")
            df_temp.rename(columns={"close": series_name}, inplace=True)
            df_temp = df_temp[[series_name]]
            df_temp[series_name] = df_temp[series_name].apply(pd.to_numeric, errors="coerce")
            df_temp[series_name] = df_temp[series_name].pct_change().apply(lambda x: np.log(1 + x))
            df_temp[series_name].replace([np.inf, -np.inf], np.nan, inplace=True)
            df_temp[series_name].dropna(inplace=True)

            if len(df_temp) == 0:
                return {}, 0.0
            series = df_temp[series_name]
            returns_by_day = {idx.date(): float(val) for idx, val in series.items()}
            total_return = float(series.sum())
            return returns_by_day, total_return
        except Exception:
            pass

    close_by_day: dict[date, float] = {}
    with file_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            day = _parse_day(str(row.get("date", "")))
            close_raw = str(row.get("close", "")).strip()
            if day is None or not close_raw:
                continue
            try:
                close = float(close_raw)
            except ValueError:
                continue
            if day < start_date or day > end_date or close <= 0.0:
                continue
            if day not in close_by_day:
                close_by_day[day] = close

    if len(close_by_day) < 2:
        return {}, 0.0

    ordered_days = sorted(close_by_day.keys())
    first_day = ordered_days[0]
    last_day = ordered_days[-1]
    returns_by_day: dict[date, float] = {}
    total_return = 0.0
    prev_close: float | None = None
    current_close: float | None = None
    day_cursor = first_day

    while day_cursor <= last_day:
        if day_cursor in close_by_day:
            current_close = close_by_day[day_cursor]
        if current_close is not None:
            if prev_close is not None and prev_close > 0.0 and current_close > 0.0:
                ret = math.log(current_close / prev_close)
                returns_by_day[day_cursor] = ret
                total_return += ret
            prev_close = current_close
        day_cursor += timedelta(days=1)

    return returns_by_day, total_return


def build_input_files(
    module_root: Path,
    assets_csv: Path,
    market_csv_dir: Path,
    args: argparse.Namespace,
) -> tuple[str, str, dict[str, object]]:
    start_dt = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")
    start_date = start_dt.date()
    end_date = end_dt.date()

    candidates = _load_candidate_assets(assets_csv, market_csv_dir, args)
    if len(candidates) < args.num_assets_total:
        raise FileNotFoundError(
            f"Only {len(candidates)} assets matched class/status/tradable/market/type/refined-type/sector filters with local files, "
            f"but num-assets-total={args.num_assets_total}."
        )

    selected_assets = _select_top_assets_by_records(candidates, start_date, end_date, args.num_assets_total)
    if len(selected_assets) < args.num_assets_total:
        raise RuntimeError(
            f"Could only select {len(selected_assets)} assets by record count in the date window, "
            f"but num-assets-total={args.num_assets_total}."
        )

    selected_assets = sorted(
        selected_assets,
        key=lambda item: Path(str(item["path"])).stat().st_size,
        reverse=True,
    )[: args.num_assets_total]

    per_asset_series: list[tuple[str, str, dict[date, float], float, int]] = []
    all_dates: set[date] = set()
    for item in selected_assets:
        file_path = Path(str(item["path"]))
        ret_series, total_ret = _parse_asset_returns(file_path, start_date, end_date)
        if not ret_series:
            continue
        asset_name = str(file_path).replace("_.csv", "")
        per_asset_series.append(
            (
                asset_name,
                str(item["symbol"]),
                ret_series,
                total_ret,
                int(item["records_in_window"]),
            )
        )
        all_dates.update(ret_series.keys())

    if len(per_asset_series) < 2:
        raise RuntimeError("Not enough assets with valid return series after preprocessing.")

    per_asset_series.sort(key=lambda item: item[3], reverse=True)
    dates_sorted = sorted(all_dates)
    n_rows = len(dates_sorted)
    n_cols = len(per_asset_series)
    matrix = np.full((n_rows, n_cols), np.nan, dtype=float)
    date_index = {day: idx for idx, day in enumerate(dates_sorted)}

    for col_idx, (_name, _symbol, ret_series, _total, _records) in enumerate(per_asset_series):
        for day, value in ret_series.items():
            matrix[date_index[day], col_idx] = value

        last_value = np.nan
        for row_idx in range(n_rows):
            if np.isnan(matrix[row_idx, col_idx]):
                if not np.isnan(last_value):
                    matrix[row_idx, col_idx] = last_value
            else:
                last_value = matrix[row_idx, col_idx]

        next_value = np.nan
        for row_idx in range(n_rows - 1, -1, -1):
            if np.isnan(matrix[row_idx, col_idx]):
                if not np.isnan(next_value):
                    matrix[row_idx, col_idx] = next_value
            else:
                next_value = matrix[row_idx, col_idx]

        if np.isnan(matrix[:, col_idx]).any():
            matrix[np.isnan(matrix[:, col_idx]), col_idx] = 0.0

    mean_returns = np.array([item[3] for item in per_asset_series], dtype=float)
    cov = np.cov(matrix, rowvar=False)

    start_tag = start_dt.strftime("%Y%m%d")
    end_tag = end_dt.strftime("%Y%m%d")
    base_dir = module_root / "resources" / "JMetal_Files" / f"{args.market}_{args.num_assets_studied}_{args.num_assets_total}"
    base_dir.mkdir(parents=True, exist_ok=True)

    mean_file = (
        f"_mean_hist_return_{args.market}_{args.num_assets_studied}_"
        f"{args.num_assets_total}_{start_tag}_{end_tag}_.csv"
    )
    cov_file = (
        f"_cov_hist_return_{args.market}_{args.num_assets_studied}_"
        f"{args.num_assets_total}_{start_tag}_{end_tag}_.csv"
    )

    mean_path = base_dir / mean_file
    cov_path = base_dir / cov_file

    with mean_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["", "0"])
        for idx, (name, _symbol, _series, _total, _records) in enumerate(per_asset_series):
            writer.writerow([name, f"{mean_returns[idx]:.16g}"])

    with cov_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = [""] + [name for (name, _symbol, _series, _total, _records) in per_asset_series]
        writer.writerow(header)
        for row_idx, (name, _symbol, _series, _total, _records) in enumerate(per_asset_series):
            writer.writerow([name] + [f"{float(cov[row_idx, col_idx]):.16g}" for col_idx in range(n_cols)])

    preprocess_info = {
        "filters": {
            "asset_class": args.asset_class,
            "status": "active",
            "allow_non_tradable": args.allow_non_tradable,
            "market": args.market,
            "asset_type": args.asset_type,
            "refined_asset_type": args.refined_asset_type,
            "sector": args.sector,
            "frequency": args.frequency,
            "start_date": args.start_date,
            "end_date": args.end_date,
        },
        "candidate_asset_count": len(candidates),
        "selected_asset_count": len(per_asset_series),
        "selected_asset_ids": [symbol for (_name, symbol, _series, _total, _records) in per_asset_series],
        "selected_asset_files": [name for (name, _symbol, _series, _total, _records) in per_asset_series],
        "selected_asset_records_in_window": {
            symbol: records for (_name, symbol, _series, _total, records) in per_asset_series
        },
    }

    return mean_file, cov_file, preprocess_info


def run_nsgaii(
    module_root: Path,
    jar_path: Path,
    mean_file: str,
    cov_file: str,
    args: argparse.Namespace,
    java_bin: str,
) -> dict[str, object]:
    command = [
        java_bin,
        "-cp",
        str(jar_path.resolve()),
        "org.uma.jmetal.portfolio.algorithm.NSGAIIExample",
        "resources/JMetal_Files/",
        str(args.population_size),
        args.market,
        str(args.num_assets_studied),
        str(args.num_assets_total),
        str(args.max_evals_without_changes),
        str(args.num_evals),
        "Results/Individuals/",
        mean_file,
        cov_file,
        str(args.crossover_probability),
        str(args.crossover_distribution_index),
        str(args.mutation_distribution_index),
        str(args.seed),
    ]

    started_at = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=module_root,
        text=True,
        capture_output=True,
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0

    result_dir = (
        module_root
        / "resources"
        / "JMetal_Files"
        / "Results"
        / "Individuals"
        / f"NSGAII_{args.market}_{args.num_assets_studied}_{args.num_assets_total}"
    )
    latest_result = None
    latest_fun = None
    latest_var = None
    if result_dir.exists():
        result_candidates = sorted(result_dir.glob("results_*"), key=lambda path: path.stat().st_mtime)
        if result_candidates:
            latest_result = str(result_candidates[-1])
        fun_candidates = sorted(result_dir.glob("FUN.NSGAII_*.csv"), key=lambda path: path.stat().st_mtime)
        if fun_candidates:
            latest_fun = str(fun_candidates[-1])
        var_candidates = sorted(result_dir.glob("VAR_NSGAII_*.csv"), key=lambda path: path.stat().st_mtime)
        if var_candidates:
            latest_var = str(var_candidates[-1])

    mutation_probability_effective = 1.0 / float(max(1, args.num_assets_studied * 2))

    payload = {
        "mode": "baseline",
        "command": command,
        "returncode": completed.returncode,
        "elapsed_ms": elapsed_ms,
        "paper_reference_ms": PAPER_REFERENCE_TIME_MS,
        "speed_ratio_vs_paper": elapsed_ms / PAPER_REFERENCE_TIME_MS if PAPER_REFERENCE_TIME_MS else None,
        "mutation_probability_effective": mutation_probability_effective,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "result_file": latest_result,
        "fun_file": latest_fun,
        "var_file": latest_var,
    }
    return payload


def _plot_front(points: list[tuple[float, float]], png_path: Path, csv_path: Path, title: str) -> dict[str, str]:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["risk", "return"])
        writer.writerows(points)

    info = {"plot_csv": str(csv_path), "plot_png": ""}
    if plt is None:
        return info

    try:
        risks = [p[0] for p in points]
        returns = [p[1] for p in points]
        plt.figure(figsize=(8, 5))
        plt.scatter(risks, returns, s=20, alpha=0.85)
        plt.xlabel("Risk")
        plt.ylabel("Return")
        plt.title(title)
        plt.grid(True, linestyle="--", alpha=0.35)
        plt.tight_layout()
        plt.savefig(png_path, dpi=150)
        plt.close()
        info["plot_png"] = str(png_path)
    except Exception:
        info["plot_png"] = ""
    return info


def _read_fun_csv(path: Path, negate_second_objective: bool = False) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if not path.exists():
        return points
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = [p.strip() for p in line.strip().split(",")]
            if len(parts) < 2:
                continue
            try:
                risk = float(parts[0])
                objective_2 = float(parts[1])
            except ValueError:
                continue
            ret = (-objective_2) if negate_second_objective else objective_2
            points.append((risk, ret))
    return points


def _non_dominated_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    front: list[tuple[float, float]] = []
    for i, point in enumerate(points):
        dominated = False
        for j, candidate in enumerate(points):
            if i == j:
                continue
            if _dominates(candidate, point):
                dominated = True
                break
        if not dominated:
            front.append(point)
    front.sort(key=lambda p: p[0])
    return front


def _objective_ranges(points: list[tuple[float, float]]) -> dict[str, float | None]:
    if not points:
        return {
            "risk_min": None,
            "risk_max": None,
            "return_min": None,
            "return_max": None,
        }
    risks = [p[0] for p in points]
    returns = [p[1] for p in points]
    return {
        "risk_min": float(min(risks)),
        "risk_max": float(max(risks)),
        "return_min": float(min(returns)),
        "return_max": float(max(returns)),
    }


def _load_problem_matrices(module_root: Path, args: argparse.Namespace, mean_file: str, cov_file: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    base_dir = module_root / "resources" / "JMetal_Files" / f"{args.market}_{args.num_assets_studied}_{args.num_assets_total}"
    mean_path = base_dir / mean_file
    cov_path = base_dir / cov_file
    if not mean_path.exists() or not cov_path.exists():
        raise FileNotFoundError(f"Missing generated input files:\n{mean_path}\n{cov_path}")

    asset_names: list[str] = []
    mean_values: list[float] = []
    with mean_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        _header = next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            asset_names.append(row[0])
            mean_values.append(float(row[1]))

    cov_map: dict[str, list[float]] = {}
    with cov_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            raise RuntimeError("Covariance file is empty.")
        cov_cols = header[1:]
        for row in reader:
            if len(row) < 2:
                continue
            cov_map[row[0]] = [float(v) for v in row[1:]]

    ordered_assets = [name for name in asset_names if name in cov_map]
    if len(ordered_assets) < 2:
        raise RuntimeError("Not enough aligned assets in mean/cov files.")
    mean_array = np.array([mean_values[asset_names.index(name)] for name in ordered_assets], dtype=float)
    cov_array = np.array([cov_map[name] for name in ordered_assets], dtype=float)
    return mean_array, cov_array, ordered_assets


def _decode_companies_baseline(index_vars: np.ndarray, total_assets: int, k_assets: int) -> np.ndarray:
    selected: list[int] = []
    used: set[int] = set()
    i = 0
    while len(selected) < k_assets and i < index_vars.size:
        company = int(index_vars[i] * float(total_assets))
        company = max(0, min(company, total_assets - 1))
        retries = 0
        while company in used and retries < total_assets:
            company = (company + 1) % total_assets
            retries += 1
        if company not in used:
            used.add(company)
            selected.append(company)
        i += 1

    filler = 0
    while len(selected) < k_assets and filler < total_assets:
        if filler not in used:
            used.add(filler)
            selected.append(filler)
        filler += 1
    return np.array(selected, dtype=int)


def _redistribute_between_bounds(weights: np.ndarray, min_weight: float, max_weight: float, max_iters: int = 100) -> np.ndarray:
    out = weights.astype(float).copy()
    n = out.size
    if n <= 1:
        return out

    changed = True
    iteration = 0
    while changed and iteration < max_iters:
        changed = False
        iteration += 1
        for i in range(n):
            value = float(out[i])
            if value > max_weight:
                excess = value - max_weight
                out[i] = max_weight
                share = excess / float(n - 1)
                for j in range(n):
                    if j != i:
                        out[j] += share
                changed = True
            elif value < min_weight:
                deficit = min_weight - value
                out[i] = min_weight
                share = deficit / float(n - 1)
                for j in range(n):
                    if j != i:
                        out[j] -= share
                changed = True
    return out


def _evaluate_baseline_encoded(
    variables: np.ndarray,
    mean_ret: np.ndarray,
    cov: np.ndarray,
    k_assets: int,
) -> tuple[float, float, np.ndarray, np.ndarray, np.ndarray]:
    n_total = mean_ret.size
    k = min(max(1, k_assets), n_total)
    if variables.size < (2 * k):
        raise ValueError(f"Expected at least {2 * k} decision variables, got {variables.size}.")

    index_vars = np.clip(variables[:k], 0.0, 1.0)
    weight_vars = np.clip(variables[k : 2 * k], 0.0, 1.0)
    companies = _decode_companies_baseline(index_vars, n_total, k)

    aligned_index_vars = index_vars.copy()
    for i in range(k):
        scaled = float(index_vars[i]) * float(n_total)
        frac = (scaled - math.floor(scaled)) / float(n_total)
        aligned_index_vars[i] = (float(companies[i]) / float(n_total)) + frac

    sum_weights = float(np.sum(weight_vars))
    if not np.isfinite(sum_weights) or sum_weights <= 0.0:
        weights = np.full(k, 1.0 / float(k), dtype=float)
    else:
        weights = weight_vars / sum_weights

    min_investment = 1.0 / (float(k) * 2.0)
    max_investment = (1.0 / float(k)) * 2.0
    weights = _redistribute_between_bounds(weights, min_investment, max_investment, max_iters=100)

    selected_mean = mean_ret[companies]
    selected_cov = cov[np.ix_(companies, companies)]
    portfolio_return = float(np.sum(selected_mean * weights))
    variance = float(weights @ selected_cov @ weights)
    variance = max(variance, 0.0)
    portfolio_risk = float(math.sqrt(variance) * math.sqrt(250.0))

    updated_variables = np.concatenate([aligned_index_vars, weights]).astype(float)
    return portfolio_risk, portfolio_return, updated_variables, companies, weights


def _dominates(a: tuple[float, float], b: tuple[float, float]) -> bool:
    # Minimize risk and maximize return => minimize (risk, -return).
    a_obj = (a[0], -a[1])
    b_obj = (b[0], -b[1])
    return (a_obj[0] <= b_obj[0] and a_obj[1] <= b_obj[1]) and (a_obj[0] < b_obj[0] or a_obj[1] < b_obj[1])


def _fast_non_dominated_sort(population: list[dict[str, object]]) -> list[list[int]]:
    n = len(population)
    domination_count = [0] * n
    dominates_set = [[] for _ in range(n)]
    fronts: list[list[int]] = [[]]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            fi = (population[i]["risk"], population[i]["ret"])
            fj = (population[j]["risk"], population[j]["ret"])
            if _dominates(fi, fj):
                dominates_set[i].append(j)
            elif _dominates(fj, fi):
                domination_count[i] += 1
        if domination_count[i] == 0:
            population[i]["rank"] = 0
            fronts[0].append(i)

    current = 0
    while current < len(fronts) and fronts[current]:
        next_front: list[int] = []
        for p in fronts[current]:
            for q in dominates_set[p]:
                domination_count[q] -= 1
                if domination_count[q] == 0:
                    population[q]["rank"] = current + 1
                    next_front.append(q)
        if next_front:
            fronts.append(next_front)
        current += 1
    return fronts


def _crowding_distance(population: list[dict[str, object]], front: list[int]) -> None:
    if not front:
        return
    for idx in front:
        population[idx]["crowding"] = 0.0
    if len(front) <= 2:
        for idx in front:
            population[idx]["crowding"] = float("inf")
        return

    for key in ("risk", "ret"):
        sorted_idx = sorted(front, key=lambda i: float(population[i][key]))
        population[sorted_idx[0]]["crowding"] = float("inf")
        population[sorted_idx[-1]]["crowding"] = float("inf")
        min_v = float(population[sorted_idx[0]][key])
        max_v = float(population[sorted_idx[-1]][key])
        if abs(max_v - min_v) < 1e-15:
            continue
        for pos in range(1, len(sorted_idx) - 1):
            prev_v = float(population[sorted_idx[pos - 1]][key])
            next_v = float(population[sorted_idx[pos + 1]][key])
            population[sorted_idx[pos]]["crowding"] = float(population[sorted_idx[pos]]["crowding"]) + (next_v - prev_v) / (max_v - min_v)


def _binary_tournament(population: list[dict[str, object]], rng: random.Random) -> dict[str, object]:
    a, b = rng.sample(population, 2)
    if int(a["rank"]) < int(b["rank"]):
        return a
    if int(b["rank"]) < int(a["rank"]):
        return b
    if float(a["crowding"]) > float(b["crowding"]):
        return a
    if float(b["crowding"]) > float(a["crowding"]):
        return b
    return a if rng.random() < 0.5 else b


def _sbx_crossover(p1: np.ndarray, p2: np.ndarray, rng: random.Random, eta: float) -> tuple[np.ndarray, np.ndarray]:
    c1 = p1.copy()
    c2 = p2.copy()
    for i in range(p1.size):
        if rng.random() <= 0.5 and abs(p1[i] - p2[i]) > 1e-14:
            x1 = min(p1[i], p2[i])
            x2 = max(p1[i], p2[i])
            lower, upper = 0.0, 1.0
            rand = rng.random()
            beta = 1.0 + (2.0 * (x1 - lower) / (x2 - x1))
            alpha = 2.0 - beta ** (-(eta + 1.0))
            if rand <= 1.0 / alpha:
                betaq = (rand * alpha) ** (1.0 / (eta + 1.0))
            else:
                betaq = (1.0 / (2.0 - rand * alpha)) ** (1.0 / (eta + 1.0))
            child1 = 0.5 * ((x1 + x2) - betaq * (x2 - x1))

            beta = 1.0 + (2.0 * (upper - x2) / (x2 - x1))
            alpha = 2.0 - beta ** (-(eta + 1.0))
            if rand <= 1.0 / alpha:
                betaq = (rand * alpha) ** (1.0 / (eta + 1.0))
            else:
                betaq = (1.0 / (2.0 - rand * alpha)) ** (1.0 / (eta + 1.0))
            child2 = 0.5 * ((x1 + x2) + betaq * (x2 - x1))

            c1[i] = min(max(child1, lower), upper)
            c2[i] = min(max(child2, lower), upper)
    return c1, c2


def _polynomial_mutation(x: np.ndarray, mutation_probability: float, eta: float, rng: random.Random) -> np.ndarray:
    y = x.copy()
    for i in range(y.size):
        if rng.random() > mutation_probability:
            continue
        lower, upper = 0.0, 1.0
        if upper - lower <= 0.0:
            continue
        delta1 = (y[i] - lower) / (upper - lower)
        delta2 = (upper - y[i]) / (upper - lower)
        rand = rng.random()
        mut_pow = 1.0 / (eta + 1.0)
        if rand <= 0.5:
            xy = 1.0 - delta1
            val = 2.0 * rand + (1.0 - 2.0 * rand) * (xy ** (eta + 1.0))
            deltaq = (val ** mut_pow) - 1.0
        else:
            xy = 1.0 - delta2
            val = 2.0 * (1.0 - rand) + 2.0 * (rand - 0.5) * (xy ** (eta + 1.0))
            deltaq = 1.0 - (val ** mut_pow)
        y[i] = min(max(y[i] + deltaq * (upper - lower), lower), upper)
    return y


def run_nsgaii_custom(module_root: Path, mean_file: str, cov_file: str, args: argparse.Namespace) -> dict[str, object]:
    mean_ret, cov, asset_names = _load_problem_matrices(module_root, args, mean_file, cov_file)
    n_assets_total = len(asset_names)
    k_assets = min(max(1, int(args.num_assets_studied)), n_assets_total)
    n_vars = 2 * k_assets
    mutation_probability = args.mutation_probability if args.mutation_probability is not None else (1.0 / float(n_vars))
    rng = random.Random(args.seed)
    np_rng = np.random.default_rng(args.seed)

    population: list[dict[str, object]] = []
    for _ in range(args.population_size):
        x0 = np_rng.random(n_vars)
        risk, ret, x, companies, weights = _evaluate_baseline_encoded(x0, mean_ret, cov, k_assets)
        population.append(
            {
                "x": x,
                "risk": risk,
                "ret": ret,
                "companies": companies,
                "weights": weights,
                "rank": 0,
                "crowding": 0.0,
            }
        )

    evaluations = args.population_size
    offspring_size = max(1, args.population_size // 2)
    started_at = time.perf_counter()

    while evaluations < args.num_evals:
        fronts = _fast_non_dominated_sort(population)
        for front in fronts:
            _crowding_distance(population, front)

        offspring: list[dict[str, object]] = []
        while len(offspring) < offspring_size and evaluations < args.num_evals:
            p1 = _binary_tournament(population, rng)
            p2 = _binary_tournament(population, rng)
            c1 = p1["x"].copy()
            c2 = p2["x"].copy()

            if rng.random() <= args.crossover_probability:
                c1, c2 = _sbx_crossover(c1, c2, rng, args.crossover_distribution_index)

            c1 = _polynomial_mutation(c1, mutation_probability, args.mutation_distribution_index, rng)
            c2 = _polynomial_mutation(c2, mutation_probability, args.mutation_distribution_index, rng)

            for child in (c1, c2):
                if len(offspring) >= offspring_size or evaluations >= args.num_evals:
                    break
                risk, ret, child_vars, companies, weights = _evaluate_baseline_encoded(child, mean_ret, cov, k_assets)
                offspring.append(
                    {
                        "x": child_vars,
                        "risk": risk,
                        "ret": ret,
                        "companies": companies,
                        "weights": weights,
                        "rank": 0,
                        "crowding": 0.0,
                    }
                )
                evaluations += 1

        combined = population + offspring
        fronts = _fast_non_dominated_sort(combined)
        next_population: list[dict[str, object]] = []
        for front in fronts:
            _crowding_distance(combined, front)
            if len(next_population) + len(front) <= args.population_size:
                next_population.extend(combined[idx] for idx in front)
            else:
                sorted_front = sorted(front, key=lambda idx: float(combined[idx]["crowding"]), reverse=True)
                slots = args.population_size - len(next_population)
                next_population.extend(combined[idx] for idx in sorted_front[:slots])
                break
        population = next_population

    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = (
        module_root
        / "resources"
        / "JMetal_Files"
        / "Results"
        / "Individuals"
        / f"NSGAII_{args.market}_{args.num_assets_studied}_{args.num_assets_total}"
    )
    result_dir.mkdir(parents=True, exist_ok=True)

    fun_path = result_dir / f"FUN.NSGAII_{args.market}_{args.num_assets_studied}_{args.num_assets_total}_{timestamp}_{args.num_evals}_.csv"
    var_path = result_dir / f"VAR_NSGAII_{args.market}_{args.num_assets_studied}_{args.num_assets_total}_{timestamp}_{args.num_evals}_.csv"
    result_path = result_dir / f"results_custom_{timestamp}_{args.num_evals}.txt"

    with fun_path.open("w", encoding="utf-8") as fun_handle:
        for ind in population:
            fun_handle.write(f"{ind['risk']},{-float(ind['ret'])}\n")

    with var_path.open("w", encoding="utf-8") as var_handle:
        for ind in population:
            var_handle.write(",".join(str(float(v)) for v in ind["x"]) + "\n")

    ranked = []
    for ind in population:
        risk = float(ind["risk"])
        ret = float(ind["ret"])
        fitness = (ret - 0.0697) / math.sqrt(risk) if risk > 1e-15 else float("-inf")
        ranked.append((fitness, ret, risk, ind["companies"], ind["weights"], ind["x"]))
    ranked.sort(key=lambda row: row[0], reverse=True)

    with result_path.open("w", encoding="utf-8") as out:
        out.write("Custom NSGA-II execution trace (Python)\n")
        out.write(f"population_size={args.population_size}\n")
        out.write(f"offspring_size={offspring_size}\n")
        out.write(f"num_evals={args.num_evals}\n")
        out.write(f"seed={args.seed}\n")
        out.write(f"crossover_probability={args.crossover_probability}\n")
        out.write(f"crossover_distribution_index={args.crossover_distribution_index}\n")
        out.write(f"mutation_probability={mutation_probability}\n")
        out.write(f"mutation_distribution_index={args.mutation_distribution_index}\n")
        out.write(f"n_variables_effective={n_vars}\n\n")
        out.write("rank,fitness_baseline,return,risk,selected_assets\n")
        for rank, row in enumerate(ranked, start=1):
            selected = [asset_names[int(i)] for i in row[3]]
            out.write(f"{rank},{row[0]},{row[1]},{row[2]},{'|'.join(selected)}\n")

    points_all = [(float(ind["risk"]), float(ind["ret"])) for ind in population]
    payload = {
        "mode": "custom",
        "returncode": 0,
        "elapsed_ms": elapsed_ms,
        "paper_reference_ms": PAPER_REFERENCE_TIME_MS,
        "speed_ratio_vs_paper": elapsed_ms / PAPER_REFERENCE_TIME_MS if PAPER_REFERENCE_TIME_MS else None,
        "mutation_probability_effective": mutation_probability,
        "n_variables_effective": n_vars,
        "stdout": "",
        "stderr": "",
        "result_file": str(result_path),
        "fun_file": str(fun_path),
        "var_file": str(var_path),
        "points_total": len(points_all),
        "points_non_dominated": len(_non_dominated_points(points_all)),
        **_objective_ranges(points_all),
        "objective_semantics": {
            "objective_0_in_fun": "risk (minimize)",
            "objective_1_in_fun": "-return (minimize)",
            "plotted_return": "return",
        },
    }
    if not args.no_plot:
        plot = _plot_front(
            points=points_all,
            png_path=result_dir / f"pareto_front_custom_{timestamp}_{args.num_evals}.png",
            csv_path=result_dir / f"pareto_front_custom_{timestamp}_{args.num_evals}.csv",
            title=f"Pareto Front (Custom) - {args.market} {args.num_assets_studied}/{args.num_assets_total}",
        )
        payload.update(plot)
    return payload


def main() -> None:
    args = parse_args()
    _check_numpy_runtime()
    module_root = Path(__file__).resolve().parents[1]
    upstream_root = Path(args.upstream_root).resolve()

    jar_path, assets_csv, ib_day_zip = ensure_upstream_assets(upstream_root)
    market_csv_dir = extract_market_data(ib_day_zip, module_root / "data")
    mean_file, cov_file, preprocess_info = build_input_files(module_root, assets_csv, market_csv_dir, args)

    if args.mode == "custom":
        report = run_nsgaii_custom(module_root, mean_file, cov_file, args)
    else:
        java_bin = resolve_java_bin(args)
        require_java_11_or_newer(java_bin)
        # Baseline path retained for rollback and direct upstream comparison.
        report = run_nsgaii(module_root, jar_path, mean_file, cov_file, args, java_bin)
        # Legacy rollback handle (kept intentionally):
        # report = run_nsgaii(module_root, jar_path, mean_file, cov_file, args, java_bin)
        fun_file = report.get("fun_file")
        raw_points: list[tuple[float, float]] = []
        if isinstance(fun_file, str) and fun_file:
            raw_points = _read_fun_csv(Path(fun_file), negate_second_objective=True)
        if raw_points:
            pareto_points = _non_dominated_points(raw_points)
            plot_points = pareto_points if pareto_points else raw_points
            report["points_total"] = len(raw_points)
            report["points_non_dominated"] = len(pareto_points)
            report.update(_objective_ranges(plot_points))
            if not args.no_plot:
                result_dir = (
                    module_root
                    / "resources"
                    / "JMetal_Files"
                    / "Results"
                    / "Individuals"
                    / f"NSGAII_{args.market}_{args.num_assets_studied}_{args.num_assets_total}"
                )
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                plot = _plot_front(
                    points=plot_points,
                    png_path=result_dir / f"pareto_front_baseline_{ts}_{args.num_evals}.png",
                    csv_path=result_dir / f"pareto_front_baseline_{ts}_{args.num_evals}.csv",
                    title=f"Pareto Front (Baseline) - {args.market} {args.num_assets_studied}/{args.num_assets_total}",
                )
                report.update(plot)
        else:
            report["points_total"] = 0
            report["points_non_dominated"] = 0
            report.update(_objective_ranges([]))
        report["objective_semantics"] = {
            "objective_0_in_fun": "risk (minimize)",
            "objective_1_in_fun": "-return (minimize)",
            "plotted_return": "-objective_1",
        }

    report["preprocessing"] = preprocess_info

    report_path = module_root / "results" / "illustrative_example_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not args.keep_extracted:
        extract_root = module_root / "data" / "financial_data"
        if extract_root.exists():
            shutil.rmtree(extract_root)

    print(json.dumps({k: report[k] for k in ("returncode", "elapsed_ms", "paper_reference_ms", "result_file")}, indent=2))
    if report["returncode"] != 0:
        raise RuntimeError("NSGA-II run failed. Check results/illustrative_example_report.json for stderr.")


if __name__ == "__main__":
    main()
