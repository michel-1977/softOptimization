from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class Asset:
    asset_id: str
    expected_return: float
    volatility: float


@dataclass(frozen=True)
class PortfolioInstance:
    name: str
    min_assets: int
    max_assets: int
    assets: tuple[Asset, ...]
    covariance: tuple[tuple[float, ...], ...]


def _validate_square_matrix(matrix: list[list[float]], size: int) -> None:
    if len(matrix) != size:
        raise ValueError(f"Covariance row count {len(matrix)} does not match asset count {size}.")
    for row_id, row in enumerate(matrix):
        if len(row) != size:
            raise ValueError(
                f"Covariance row {row_id} has {len(row)} columns; expected {size}."
            )


def load_instance(path: str | Path) -> PortfolioInstance:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    assets_raw = raw["assets"]
    assets = tuple(
        Asset(
            asset_id=str(asset["id"]),
            expected_return=float(asset["expected_return"]),
            volatility=float(asset["volatility"]),
        )
        for asset in assets_raw
    )
    covariance_raw = [[float(value) for value in row] for row in raw["covariance"]]
    _validate_square_matrix(covariance_raw, len(assets))

    min_assets = int(raw["min_assets"])
    max_assets = int(raw["max_assets"])
    if min_assets < 1:
        raise ValueError("min_assets must be >= 1.")
    if max_assets > len(assets):
        raise ValueError("max_assets cannot exceed number of assets.")
    if min_assets > max_assets:
        raise ValueError("min_assets cannot be greater than max_assets.")

    covariance = tuple(tuple(row) for row in covariance_raw)
    return PortfolioInstance(
        name=str(raw["name"]),
        min_assets=min_assets,
        max_assets=max_assets,
        assets=assets,
        covariance=covariance,
    )
