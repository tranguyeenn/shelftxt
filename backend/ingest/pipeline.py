from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backend.ingest.load_csv import load_csv
from backend.preprocess.clean_books import clean_books
from backend.preprocess.normalize import compute_recency, normalize_rating
from backend.ranking.score import score_read_books, score_tbr_books


def validate_uploaded_csv(csv_path: str | Path, mapping_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Lightweight validation gate before expensive processing.
    """
    path = Path(csv_path)
    report: dict[str, Any] = {
        "status": "accept",
        "errors": [],
        "warnings": [],
        "row_count": 0,
        "columns": [],
    }

    if not path.exists():
        report["status"] = "reject"
        report["errors"].append(f"File not found: {path}")
        return report
    if path.suffix.lower() != ".csv":
        report["warnings"].append("File extension is not .csv; attempting CSV parse anyway.")

    try:
        preview_df = pd.read_csv(path, nrows=100)
    except pd.errors.ParserError:
        report["status"] = "reject"
        report["errors"].append("Failed to parse CSV")
        return report

    report["row_count"] = len(preview_df)
    report["columns"] = preview_df.columns.tolist()
    if preview_df.empty:
        report["status"] = "reject"
        report["errors"].append("CSV contains no data rows.")
        return report

    _, schema_report = load_csv(path, mapping_config=mapping_config)
    report["errors"].extend(schema_report["errors"])
    report["warnings"].extend(schema_report["warnings"])

    if report["errors"]:
        report["status"] = "reject"
    elif report["warnings"]:
        report["status"] = "accept_with_warnings"

    return report


def run_flexible_pipeline(
    csv_path: str | Path,
    mapping_config: dict[str, Any] | None = None,
    rating_weight: float = 0.7,
    recency_weight: float = 0.3,
) -> dict[str, Any]:
    """
    End-to-end dataset processing for arbitrary user CSV schemas.
    """
    validation_report = validate_uploaded_csv(csv_path, mapping_config=mapping_config)
    if validation_report["status"] == "reject":
        return {"validation": validation_report, "read_ranked": pd.DataFrame(), "tbr_ranked": pd.DataFrame()}

    standardized_df, mapping_report = load_csv(csv_path, mapping_config=mapping_config)
    standardized_df = clean_books(standardized_df)
    standardized_df = normalize_rating(standardized_df)
    standardized_df = compute_recency(standardized_df)

    read_ranked = score_read_books(
        standardized_df,
        rating_weight=rating_weight,
        recency_weight=recency_weight,
    )
    tbr_ranked = score_tbr_books(standardized_df)

    merged_warnings = [*validation_report["warnings"], *mapping_report["warnings"]]
    merged_errors = [*validation_report["errors"], *mapping_report["errors"]]

    final_validation = dict(validation_report)
    final_validation["warnings"] = sorted(set(merged_warnings))
    final_validation["errors"] = sorted(set(merged_errors))

    return {
        "validation": final_validation,
        "read_ranked": read_ranked,
        "tbr_ranked": tbr_ranked,
    }
