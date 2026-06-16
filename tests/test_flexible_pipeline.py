import csv
import tempfile
import unittest
from pathlib import Path

from backend.ingest.load_csv import load_csv
from backend.ingest.pipeline import run_flexible_pipeline, validate_uploaded_csv


class FlexiblePipelineTests(unittest.TestCase):
    def _write_csv(self, rows):
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "upload.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return temp_dir, path

    def test_load_csv_maps_user_schema_to_canonical_columns(self):
        rows = [
            {
                "Book Name": "Dune",
                "Writer": "Frank Herbert",
                "Status": "read",
                "My Rating": "5",
                "Finished On": "2024-01-01",
            },
            {
                "Book Name": "Neuromancer",
                "Writer": "William Gibson",
                "Status": "to-read",
                "My Rating": "",
                "Finished On": "",
            },
        ]
        temp_dir, csv_path = self._write_csv(rows)
        self.addCleanup(temp_dir.cleanup)

        df, report = load_csv(
            csv_path,
            mapping_config={
                "column_mappings": {
                    "Book Name": "title",
                    "Writer": "author",
                    "Status": "read_status",
                    "My Rating": "rating",
                    "Finished On": "last_date_read",
                }
            },
        )

        self.assertIn("title", df.columns)
        self.assertIn("author", df.columns)
        self.assertIn("read_status", df.columns)
        self.assertIn("rating", df.columns)
        self.assertIn("last_date_read", df.columns)
        self.assertEqual(df.loc[0, "title"], "Dune")
        self.assertEqual(df.loc[0, "author"], "Frank Herbert")
        self.assertEqual(report["errors"], [])

    def test_load_csv_accepts_slash_separated_finish_date(self):
        rows = [
            {
                "Title": "Dune",
                "Authors": "Frank Herbert",
                "Read Status": "read",
                "Last Date Read": "2025/02/02",
            }
        ]
        temp_dir, csv_path = self._write_csv(rows)
        self.addCleanup(temp_dir.cleanup)

        df, report = load_csv(csv_path)

        self.assertEqual(report["errors"], [])
        self.assertEqual(df.loc[0, "last_date_read"].date().isoformat(), "2025-02-02")

    def test_load_csv_reports_invalid_finish_date(self):
        rows = [
            {
                "Title": "Dune",
                "Authors": "Frank Herbert",
                "Read Status": "read",
                "Last Date Read": "not-a-date",
            }
        ]
        temp_dir, csv_path = self._write_csv(rows)
        self.addCleanup(temp_dir.cleanup)

        with self.assertLogs("backend.ingest.load_csv", level="WARNING") as logs:
            df, report = load_csv(csv_path)

        self.assertTrue(df.loc[0, "last_date_read"] is None or str(df.loc[0, "last_date_read"]) == "NaT")
        self.assertTrue(any("Could not parse imported date value" in line for line in logs.output))
        self.assertTrue(any("Could not parse imported date value" in warning for warning in report["warnings"]))

    def test_validate_uploaded_csv_rejects_missing_required_fields(self):
        rows = [
            {
                "Writer": "Frank Herbert",
                "Status": "read",
                "My Rating": "5",
            }
        ]
        temp_dir, csv_path = self._write_csv(rows)
        self.addCleanup(temp_dir.cleanup)

        report = validate_uploaded_csv(
            csv_path,
            mapping_config={
                "column_mappings": {
                    "Writer": "author",
                    "Status": "read_status",
                    "My Rating": "rating",
                }
            },
        )

        self.assertEqual(report["status"], "reject")
        self.assertTrue(any("title" in err for err in report["errors"]))

    def test_run_flexible_pipeline_returns_ranked_outputs(self):
        rows = [
            {
                "Book Name": "Dune",
                "Writer": "Frank Herbert",
                "Status": "read",
                "My Rating": "5",
                "Finished On": "2024-01-01",
            },
            {
                "Book Name": "Hyperion",
                "Writer": "Dan Simmons",
                "Status": "read",
                "My Rating": "4",
                "Finished On": "2024-05-01",
            },
            {
                "Book Name": "Snow Crash",
                "Writer": "Neal Stephenson",
                "Status": "to-read",
                "My Rating": "",
                "Finished On": "",
            },
        ]
        temp_dir, csv_path = self._write_csv(rows)
        self.addCleanup(temp_dir.cleanup)

        result = run_flexible_pipeline(
            csv_path,
            mapping_config={
                "column_mappings": {
                    "Book Name": "title",
                    "Writer": "author",
                    "Status": "read_status",
                    "My Rating": "rating",
                    "Finished On": "last_date_read",
                }
            },
        )

        self.assertIn(result["validation"]["status"], {"accept", "accept_with_warnings"})
        self.assertIn("score", result["read_ranked"].columns)
        self.assertIn("score", result["tbr_ranked"].columns)
        self.assertGreaterEqual(len(result["read_ranked"]), 1)


if __name__ == "__main__":
    unittest.main()
