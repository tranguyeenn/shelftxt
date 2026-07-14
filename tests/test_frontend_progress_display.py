import json
import subprocess
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def _run_progress_display_cases():
    script = r"""
const fs = require("fs");
const path = require("path");
const ts = require("typescript");
const vm = require("vm");

const source = fs.readFileSync(path.join(process.cwd(), "src/lib/progressDisplay.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
}).outputText;
const context = { exports: {}, module: { exports: {} }, require };
context.exports = context.module.exports;
vm.runInNewContext(compiled, context);
const {
  displayProgressPercent,
  progressPercentValue,
  readingProgressSummary
} = context.module.exports;

const cases = [
  ["zero", { tracking_mode: "percentage", progress_pct: 0, pages_read: 0, total_pages: null }],
  ["partial", { tracking_mode: "percentage", progress_pct: 84, pages_read: 0, total_pages: null }],
  ["complete", { tracking_mode: "percentage", progress_pct: 100, pages_read: 0, total_pages: null }],
  ["decimal", { tracking_mode: "percentage", progress_pct: 83.6, pages_read: 0, total_pages: null }],
  ["pages", { tracking_mode: "pages", progress_pct: 0, pages_read: 213, total_pages: 352 }],
  ["missing-total", { tracking_mode: "pages", progress_pct: 0, pages_read: 213, total_pages: null }],
  ["negative", { tracking_mode: "percentage", progress_pct: -5, pages_read: 0, total_pages: null }],
  ["too-high", { tracking_mode: "percentage", progress_pct: 130, pages_read: 0, total_pages: null }],
  ["nan", { tracking_mode: "percentage", progress_pct: Number.NaN, pages_read: 0, total_pages: null }]
];

console.log(JSON.stringify(Object.fromEntries(cases.map(([name, book]) => [
  name,
  {
    value: progressPercentValue(book),
    label: displayProgressPercent(book),
    summary: readingProgressSummary(book)
  }
]))));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=FRONTEND,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_progress_display_percent_cases():
    results = _run_progress_display_cases()

    assert results["zero"]["label"] == "0%"
    assert results["partial"]["label"] == "84%"
    assert results["complete"]["label"] == "100%"
    assert results["decimal"]["label"] == "84%"


def test_progress_display_page_based_and_missing_total_cases():
    results = _run_progress_display_cases()

    assert round(results["pages"]["value"]) == 61
    assert results["pages"]["label"] == "61%"
    assert results["pages"]["summary"] == "213 / 352 pages"
    assert results["missing-total"]["label"] == "0%"
    assert results["missing-total"]["summary"] == "213 pages read"


def test_progress_display_clamps_invalid_values():
    results = _run_progress_display_cases()

    assert results["negative"]["label"] == "0%"
    assert results["too-high"]["label"] == "100%"
    assert results["nan"]["label"] == "0%"
