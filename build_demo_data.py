from __future__ import annotations

import json
from pathlib import Path

from hookforge_core import analyze_risk, export_document, simulate_hook, template_catalog, trigger_catalog, validate_hook

ROOT = Path(__file__).resolve().parent
EVENTS = {
    "post-file-save-tests": [
        {"trigger": "PostFileSave", "subject": "src/example.py"},
        {"trigger": "PostFileSave", "subject": "README.md"},
    ],
    "pre-tool-use-guard": [
        {"trigger": "PreToolUse", "subject": "fs_write"},
        {"trigger": "PreToolUse", "subject": "read_file"},
    ],
    "stop-test-gate": [
        {"trigger": "Stop", "subject": ""},
    ],
}


def build() -> dict[str, object]:
    templates = template_catalog()
    samples: dict[str, object] = {}
    for template in templates:
        hook = template["hook"]
        demo_hook = {
            "name": hook["name"],
            "description": hook.get("description", ""),
            "trigger": hook["trigger"],
            "matcher": hook.get("matcher", ""),
            "action": hook["action"],
            "enabled": hook.get("enabled", True),
        }
        if hook["action"]["type"] == "command" and "timeout" in hook:
            demo_hook["timeout"] = hook["timeout"]
        events = EVENTS[template["id"]]
        samples[template["id"]] = {
            "hook": demo_hook,
            "default_event": events[0],
            "validation": validate_hook(hook),
            "risk": analyze_risk(hook),
            "export": export_document(demo_hook),
            "simulations": [{"event": event, "result": simulate_hook(hook, event)} for event in events],
        }
    return {
        "meta": {"ok": True, "triggers": trigger_catalog(), "templates": templates},
        "samples": samples,
        "notice": "Static demo supports bundled templates and events only. Run the local app for arbitrary input.",
    }


if __name__ == "__main__":
    output = ROOT / "frontend" / "demo-data.json"
    output.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
