"""Static demo payload stays synchronized with the pure backend."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from build_demo_data import build
from hookforge_core import analyze_risk, export_document, simulate_hook, validate_hook

ROOT = Path(__file__).resolve().parents[1]


class StaticDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "frontend" / "demo-data.json").read_text(encoding="utf-8"))

    def test_payload_is_current(self):
        self.assertEqual(self.data, build())

    def test_every_sample_matches_backend_results(self):
        self.assertEqual(len(self.data["samples"]), 3)
        for sample_id, sample in self.data["samples"].items():
            with self.subTest(sample=sample_id):
                hook = sample["hook"]
                self.assertTrue(validate_hook(hook)["valid"])
                self.assertEqual(sample["validation"], validate_hook(hook))
                self.assertEqual(sample["risk"], analyze_risk(hook))
                self.assertEqual(sample["export"], export_document(hook))
                for entry in sample["simulations"]:
                    self.assertEqual(entry["result"], simulate_hook(hook, entry["event"]))
                    self.assertFalse(entry["result"]["executed"])
                    if entry["result"]["action_requested"]:
                        self.assertFalse(entry["result"]["action_requested"]["executed"])

    def test_default_events_are_included(self):
        for sample_id, sample in self.data["samples"].items():
            with self.subTest(sample=sample_id):
                self.assertIn(sample["default_event"], [entry["event"] for entry in sample["simulations"]])

    def test_static_assets_use_subpath_safe_urls(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="./styles.css"', html)
        self.assertIn('src="./app.js"', html)
        self.assertIn('id="import-button"', html)
        self.assertIn('id="import-file"', html)
        self.assertNotRegex(html, r'(?:href|src)="/[^#]')
        self.assertTrue((ROOT / "frontend" / ".nojekyll").exists())


if __name__ == "__main__":
    unittest.main()
