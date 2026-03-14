from __future__ import annotations

import enum
from pathlib import Path
from typing import Any, Mapping

import yaml


# ---- Safer loader (optional: disables YAML timestamp -> datetime coercion) ----
class SafeNoDatesLoader(yaml.SafeLoader):
    pass


# Remove implicit resolver for timestamps so "2026-01-13" stays a string
for ch, resolvers in list(SafeNoDatesLoader.yaml_implicit_resolvers.items()):
    SafeNoDatesLoader.yaml_implicit_resolvers[ch] = [
        (tag, regexp) for (tag, regexp) in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]


# ---- Dumper that writes Enums as plain scalars ----
class SafeEnumDumper(yaml.SafeDumper):
    pass


def _enum_representer(dumper: yaml.Dumper, data: enum.Enum) -> yaml.Node:
    """
    Represent Enums as plain YAML scalars.
    - StrEnum -> its string value
    - IntEnum -> its integer value
    - Other Enum -> its name (human-readable)
    """
    # Python 3.11+: StrEnum exists
    StrEnum = getattr(enum, "StrEnum", None)

    if StrEnum is not None and isinstance(data, StrEnum):
        return dumper.represent_str(str(data.value))

    if isinstance(data, enum.IntEnum):
        # Ensure it's a real int, not an enum object
        return dumper.represent_int(int(data.value))

    # Fallback: store the name for regular Enums
    return dumper.represent_str(data.name)


# Apply to any Enum subclass (covers IntEnum, StrEnum, Enum, etc.)
SafeEnumDumper.add_multi_representer(enum.Enum, _enum_representer)


def load_yaml(path: str | Path) -> Any:
    path = Path(path).expanduser()
    with path.open("r", encoding="utf-8") as f:
        return yaml.load(f, Loader=SafeNoDatesLoader)


def write_yaml(path: str | Path, data: Any) -> None:
    path = Path(path).expanduser()
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            Dumper=SafeEnumDumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )