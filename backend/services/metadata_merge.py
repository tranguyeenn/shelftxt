"""Reusable rules for combining sparse metadata without losing useful values."""

from collections.abc import Mapping
from typing import Any


def has_metadata_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def merge_metadata_records(
    base: Mapping[str, Any],
    incoming: Mapping[str, Any] | None,
    *,
    list_fields: set[str] | frozenset[str] = frozenset(),
    prefer_incoming: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Merge sparse records, unioning lists and never replacing data with empties."""
    merged = dict(base)
    if not incoming:
        return merged

    for field, value in incoming.items():
        if not has_metadata_value(value):
            continue
        if field in list_fields:
            current = merged.get(field) or []
            merged[field] = list(dict.fromkeys([*current, *value]))
        elif field in prefer_incoming or not has_metadata_value(merged.get(field)):
            merged[field] = value
    return merged
