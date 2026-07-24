"""Translate long Hive warehouse S3 keys to short storage keys and back."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

WAREHOUSE_PREFIX = "data/"


@dataclass(frozen=True)
class PathMaps:
    schema_paths: dict[str, str]
    schema_path_pattern: re.Pattern[str] | None
    schema_path_replace: str | None
    tables: dict[str, str]
    reverse_schema: dict[str, str]
    reverse_tables: dict[str, str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PathMaps:
        schema_paths = {str(k): str(v) for k, v in raw.get("schema_paths", {}).items()}
        pattern_cfg = raw.get("schema_path_pattern") or {}
        pattern = pattern_cfg.get("match")
        replace = pattern_cfg.get("replace")
        schema_path_pattern = re.compile(pattern) if pattern else None
        tables = {str(k): str(v) for k, v in raw.get("tables", {}).items()}
        reverse_schema = {short: long for long, short in schema_paths.items()}
        reverse_tables = {short: long for long, short in tables.items()}
        return cls(
            schema_paths=schema_paths,
            schema_path_pattern=schema_path_pattern,
            schema_path_replace=replace,
            tables=tables,
            reverse_schema=reverse_schema,
            reverse_tables=reverse_tables,
        )

    @classmethod
    def load(cls, path: Path) -> PathMaps:
        with path.open(encoding="utf-8") as handle:
            return cls.from_dict(yaml.safe_load(handle) or {})


def load_path_maps(config_path: str | Path | None = None) -> PathMaps:
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "path_maps.yaml"
    return PathMaps.load(Path(config_path))


def _schema_long_to_short(maps: PathMaps, schema_long: str) -> str | None:
    if schema_long in maps.schema_paths:
        return maps.schema_paths[schema_long]
    if maps.schema_path_pattern and maps.schema_path_replace:
        match = maps.schema_path_pattern.match(schema_long)
        if match:
            return maps.schema_path_pattern.sub(maps.schema_path_replace, schema_long)
    return None


def _schema_short_to_long(maps: PathMaps, short_segment: str) -> str | None:
    if short_segment in maps.reverse_schema:
        return maps.reverse_schema[short_segment]
    if short_segment.startswith("o") and short_segment[1:].isdigit():
        return f"data/org{short_segment[1:]}.db"
    return None


def is_warehouse_key(key: str) -> bool:
    """Return True when the key looks like a Hive warehouse path (data/<schema>.db/...)."""
    if not key.startswith(WAREHOUSE_PREFIX):
        return False
    parts = key.split("/")
    return len(parts) >= 2 and parts[1].endswith(".db")


def encode_key(key: str, maps: PathMaps) -> str:
    """Rewrite a client-visible S3 object key to the short storage form."""
    if not key or not is_warehouse_key(key):
        return key

    parts = key.split("/")
    schema_long = f"{parts[0]}/{parts[1]}"
    short_schema = _schema_long_to_short(maps, schema_long)
    if short_schema is None:
        return key

    encoded: list[str] = [short_schema]
    index = 2
    if index < len(parts):
        table_long = parts[index]
        short_table = maps.tables.get(table_long)
        if short_table is None:
            encoded.extend(parts[index:])
            return "/".join(encoded)
        encoded.append(short_table)
        index += 1

    if index < len(parts):
        encoded.extend(parts[index:])
    return "/".join(encoded)


def decode_key(key: str, maps: PathMaps) -> str:
    """Rewrite a storage S3 object key back to the client-visible form."""
    if not key:
        return key

    parts = key.split("/")
    schema_long = _schema_short_to_long(maps, parts[0])
    if schema_long is None:
        return key

    decoded = schema_long.split("/")
    index = 1
    if index < len(parts):
        short_table = parts[index]
        table_long = maps.reverse_tables.get(short_table)
        if table_long is None:
            decoded.extend(parts[index:])
            return "/".join(decoded)
        decoded.append(table_long)
        index += 1

    if index < len(parts):
        decoded.extend(parts[index:])
    return "/".join(decoded)


def encoded_key_max_length(key: str, maps: PathMaps) -> int:
    """Return encoded key length (for diagnostics / smoke tests)."""
    return len(encode_key(key, maps))
