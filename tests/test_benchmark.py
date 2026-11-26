"""Benchmark fixture expectations remain synchronized with the validator."""
import json
import unittest
from pathlib import Path

from hookforge_core import validate_document

ROOT = Path(__file__).resolve().parents[1]


class BenchmarkTests(unittest.TestCase):
    def test_fixed_cases(self):
        cases = json.loads((ROOT / "benchmarks/validation-cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 47)
        for case in cases:
            with self.subTest(case=case["id"]):
                document = case["document"] if "document" in case else {"version": case.get("version", "v1"), "hooks": case.get("hooks", [case["hook"]])}
                result = validate_document(document)
                self.assertEqual(result["valid"], case["expected_valid"])
                if case.get("expected_code"):
                    self.assertIn(case["expected_code"], {issue["code"] for issue in result["issues"]})


if __name__ == "__main__":
    unittest.main()
