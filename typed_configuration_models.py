"""Immutable typed models for read-only configuration parity analysis.

These models are deliberately detached from the trading runtime. They describe
source configuration and unit semantics but do not resolve environment values,
mutate module globals, or become authoritative policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ConfigUnit(str, Enum):
    FRACTION = "fraction"
    PERCENT_POINTS = "percent_points"
    SECONDS = "seconds"
    MINUTES = "minutes"
    BOOLEAN = "boolean"
    COUNT = "count"
    PATH = "path"
    TEXT = "text"


class SourceKind(str, Enum):
    AUDIT_ENVIRONMENT = "audit_environment"
    AUDIT_PARAMETER = "audit_parameter"
    SOURCE_ENV_SETDEFAULT = "source_env_setdefault"
    SOURCE_CONSTANT = "source_constant"


@dataclass(frozen=True, slots=True)
class SourceSelector:
    kind: SourceKind
    path: str
    name: str


@dataclass(frozen=True, slots=True)
class TypedConfigContract:
    config_id: str
    selector: SourceSelector
    unit: ConfigUnit
    expected_raw: Any
    expected_normalized: Any
    scope: str
    authoritative: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class ObservedConfigValue:
    config_id: str
    selector: SourceSelector
    unit: ConfigUnit
    raw: Any
    normalized: Any
    source_line: int | None
    parity: bool
    detail: str


def normalize_value(value: Any, unit: ConfigUnit) -> Any:
    """Normalize a raw source value without consulting runtime state."""
    if unit is ConfigUnit.BOOLEAN:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"not a boolean: {value!r}")

    if unit in {ConfigUnit.PATH, ConfigUnit.TEXT}:
        return None if value is None else str(value)

    if unit is ConfigUnit.COUNT:
        return int(float(value))

    numeric = float(value)
    if unit is ConfigUnit.PERCENT_POINTS:
        return numeric / 100.0
    if unit in {ConfigUnit.FRACTION, ConfigUnit.SECONDS, ConfigUnit.MINUTES}:
        return numeric
    raise ValueError(f"unsupported unit: {unit}")
