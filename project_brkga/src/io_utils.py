from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class Project:
    project_id: str
    cost: int
    value: float
    risk: float
    prerequisites: tuple[str, ...]


@dataclass(frozen=True)
class PPSInstance:
    name: str
    budget: int
    risk_aversion: float
    projects: tuple[Project, ...]


def load_instance(path: str | Path) -> PPSInstance:
    # PowerShell-generated JSON may include UTF-8 BOM on Windows.
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))

    def normalize_prerequisites(value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list):
            return tuple(str(dep) for dep in value)
        if isinstance(value, dict):
            # Empty PowerShell hashtable from serialization of an empty array.
            return ()
        raise ValueError(f"Unsupported prerequisites value type: {type(value).__name__}")

    projects = tuple(
        Project(
            project_id=str(item["id"]),
            cost=int(item["cost"]),
            value=float(item["value"]),
            risk=float(item["risk"]),
            prerequisites=normalize_prerequisites(item.get("prerequisites", [])),
        )
        for item in raw["projects"]
    )

    if not projects:
        raise ValueError("Instance has no projects.")

    known_ids = {project.project_id for project in projects}
    for project in projects:
        if project.cost <= 0:
            raise ValueError(f"Project {project.project_id} has non-positive cost.")
        for dep in project.prerequisites:
            if dep not in known_ids:
                raise ValueError(
                    f"Project {project.project_id} references unknown prerequisite {dep}."
                )

    budget = int(raw["budget"])
    if budget <= 0:
        raise ValueError("Budget must be positive.")

    return PPSInstance(
        name=str(raw["name"]),
        budget=budget,
        risk_aversion=float(raw.get("risk_aversion", 0.25)),
        projects=projects,
    )
