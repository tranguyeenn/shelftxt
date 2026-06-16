from __future__ import annotations

from pathlib import Path
from typing import Any
import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical internal fields used across preprocessing and ranking.
CANONICAL_COLUMNS = [
    "book_id",
    "title",
    "author",
    "genre",
    "read_status",
    "rating",
    "last_date_read",
]

DEFAULT_MAPPING_CONFIG: dict[str, Any] = {
    "column_mappings": {
        "ISBN/UID": "book_id",
        "Title": "title",
        "Authors": "author",
        "Genre": "genre",
        "Read Status": "read_status",
        "Star Rating": "rating",
        "Last Date Read": "last_date_read",
    },
    "required_fields": ["title", "read_status"],
    "defaults": {
        "book_id": None,
        "author": "unknown",
        "genre": "unknown",
        "rating": None,
        "last_date_read": None,
    },
    "type_hints": {
        "rating": "numeric",
        "last_date_read": "datetime",
    },
}


def _merge_mapping_config(user_config: dict[str, Any] | None) -> dict[str, Any]:
    config = {
        "column_mappings": dict(DEFAULT_MAPPING_CONFIG["column_mappings"]),
        "required_fields": list(DEFAULT_MAPPING_CONFIG["required_fields"]),
        "defaults": dict(DEFAULT_MAPPING_CONFIG["defaults"]),
        "type_hints": dict(DEFAULT_MAPPING_CONFIG["type_hints"]),
    }
    if not user_config:
        return config

    for key in ("column_mappings", "defaults", "type_hints"):
        if key in user_config and isinstance(user_config[key], dict):
            config[key].update(user_config[key])

    if "required_fields" in user_config and isinstance(user_config["required_fields"], list):
        config["required_fields"] = user_config["required_fields"]

    return config


def _coerce_types(df: pd.DataFrame, config: dict[str, Any], validation: dict[str, list[str]]) -> pd.DataFrame:
    for field, hint in config["type_hints"].items():
        if field not in df.columns:
            continue
        if hint == "numeric":
            df[field] = pd.to_numeric(df[field], errors="coerce")
        elif hint == "datetime":
            original = df[field].copy()
            parsed = pd.to_datetime(original, errors="coerce", format="%Y-%m-%d")
            missing = parsed.isna() & original.notna() & (original.astype(str).str.strip() != "")
            if missing.any():
                fallback = pd.to_datetime(original[missing], errors="coerce", format="%Y/%m/%d")
                parsed.loc[missing] = fallback
            missing = parsed.isna() & original.notna() & (original.astype(str).str.strip() != "")
            if missing.any():
                fallback = pd.to_datetime(original[missing], errors="coerce", format="%m/%d/%Y")
                parsed.loc[missing] = fallback
            failed = parsed.isna() & original.notna() & (original.astype(str).str.strip() != "")
            for value in original[failed].astype(str).tolist():
                message = f"Could not parse imported date value {value!r} for field '{field}'."
                logger.warning(message)
                validation["warnings"].append(message)
            df[field] = parsed
        else:
            validation["warnings"].append(f"Unknown type hint '{hint}' for field '{field}'.")
    return df


def _validate_dataframe(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, list[str]]:
    report = {"errors": [], "warnings": []}

    if df.empty:
        report["errors"].append("Uploaded CSV has no rows.")

    for required_field in config["required_fields"]:
        if required_field not in df.columns:
            report["errors"].append(f"Missing required field '{required_field}' after mapping.")
            continue

        series = df[required_field]
        if series.dtype == "O":
            usable_mask = series.notna() & (series.astype(str).str.strip() != "")
            if not usable_mask.any():
                report["errors"].append(f"Required field '{required_field}' has no usable values.")
        elif series.isna().all():
            report["errors"].append(f"Required field '{required_field}' has no usable values.")

    if "read_status" in df.columns:
        allowed = {"read", "to-read", "dnf"}
        unknown_values = (
            df["read_status"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.lower()
            .loc[lambda series: ~series.isin(allowed)]
            .unique()
            .tolist()
        )
        if unknown_values:
            report["warnings"].append(
                "Found unknown read_status values: " + ", ".join(map(str, unknown_values))
            )

    return report


def load_csv(csv: str | Path, mapping_config: dict[str, Any] | None = None) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """
    Load arbitrary CSV data and map it into ShelfTxt canonical fields.

    Returns (standardized_dataframe, validation_report).
    """
    config = _merge_mapping_config(mapping_config)
    raw_df = pd.read_csv(csv)

    mapped_df = pd.DataFrame()
    reverse_mappings = config["column_mappings"]

    # Map user-provided/raw columns into canonical columns.
    for raw_col, canonical_col in reverse_mappings.items():
        if raw_col in raw_df.columns:
            mapped_df[canonical_col] = raw_df[raw_col]

    # Ensure all canonical columns exist for downstream modules.
    for col in CANONICAL_COLUMNS:
        if col not in mapped_df.columns:
            mapped_df[col] = config["defaults"].get(col)

    validation_report = {"errors": [], "warnings": []}
    mapped_df = _coerce_types(mapped_df, config, validation_report)

    if "title" in mapped_df.columns:
        mapped_df["title"] = (
            mapped_df["title"]
            .where(mapped_df["title"].notna(), pd.NA)
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
        )
    if "author" in mapped_df.columns:
        mapped_df["author"] = (
            mapped_df["author"]
            .where(mapped_df["author"].notna(), pd.NA)
            .astype("string")
            .str.strip()
            .replace("", "unknown")
            .fillna("unknown")
        )
    if "genre" in mapped_df.columns:
        mapped_df["genre"] = (
            mapped_df["genre"]
            .where(mapped_df["genre"].notna(), pd.NA)
            .astype("string")
            .str.strip()
            .replace("", "unknown")
            .fillna("unknown")
        )
    if "read_status" in mapped_df.columns:
        mapped_df["read_status"] = (
            mapped_df["read_status"]
            .where(mapped_df["read_status"].notna(), pd.NA)
            .astype("string")
            .str.strip()
            .str.lower()
            .fillna("to-read")
        )

    next_report = _validate_dataframe(mapped_df, config)
    validation_report["errors"].extend(next_report["errors"])
    validation_report["warnings"].extend(next_report["warnings"])

    return mapped_df, validation_report
