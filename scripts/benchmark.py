#!/usr/bin/env python3
"""Run the fixed HookForge schema validation benchmark and write its report."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hookforge_core import validate_document

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cases = json.loads((ROOT / "benchmarks/validation-cases.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        document = case["document"] if "document" in case else {"version": case.get("version", "v1"), "hooks": case.get("hooks", [case["hook"]])}
        result = validate_document(document)
        actual_codes = {issue["code"] for issue in result["issues"] if issue["severity"] == "error"}
        passed = result["valid"] == case["expected_valid"]
        if case.get("expected_code"):
            passed = passed and case["expected_code"] in actual_codes
        rows.append({**case, "passed": passed, "actual_codes": sorted(actual_codes)})
    passed_count = sum(row["passed"] for row in rows)
    valid_count = sum(row["expected_valid"] for row in rows)
    negative_count = sum(not row["expected_valid"] for row in rows)
    trigger_rows = [row for row in rows if row["category"] == "trigger" and row["expected_valid"]]
    trigger_passed = sum(row["passed"] for row in trigger_rows)
    lines = [
        "# HookForge fixed validation benchmark", "",
        "Snapshot: 26 November 2026. Engine: `hookforge_core.validate_document`.", "",
        "This is a small, original, deterministic conformance benchmark for HookForge's documented MVP contract—not an official Kiro certification or a measurement of real IDE behavior.", "",
        "| Metric | Result |", "|---|---:|",
        f"| Fixed cases | {len(rows)} |",
        f"| Valid-document acceptance | {sum(row['passed'] for row in rows if row['expected_valid'])}/{valid_count} |",
        f"| Canonical trigger acceptance | {trigger_passed}/{len(trigger_rows)} |",
        f"| Invalid-schema rejection | {sum(row['passed'] for row in rows if not row['expected_valid'])}/{negative_count} |",
        f"| Total expectations met | {passed_count}/{len(rows)} ({passed_count / len(rows):.1%}) |", "",
        "## Case results", "",
        "| Case | Category | Expected | Actual errors | Result |", "|---|---|---|---|---|",
    ]
    for row in rows:
        expected = "valid" if row["expected_valid"] else f"reject: `{row.get('expected_code', 'invalid')}`"
        actual = ", ".join(f"`{code}`" for code in row["actual_codes"]) or "none"
        lines.append(f"| `{row['id']}` | {row['category']} | {expected} | {actual} | {'PASS' if row['passed'] else 'FAIL'} |")
    lines += ["", "Reproduce with `python scripts/benchmark.py`. Cases are fixed in `benchmarks/validation-cases.json`.", ""]
    report = "\n".join(lines)
    (ROOT / "benchmarks/validation-benchmark.md").write_text(report, encoding="utf-8")
    print(f"Benchmark: {passed_count}/{len(rows)} expectations met")
    return 0 if passed_count == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
