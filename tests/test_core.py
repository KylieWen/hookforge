"""Deterministic tests for pure HookForge behavior."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hookforge_core import (
    SCHEMA_VERSION,
    TRIGGERS,
    _unsafe_regex_reason,
    analyze_risk,
    export_document,
    filename_for,
    regex_check,
    simulate_hook,
    template_catalog,
    trigger_catalog,
    validate_document,
    validate_hook,
)


def command_hook(**overrides):
    hook = {"name": "Run tests", "trigger": "PostFileSave", "matcher": r"\.py$", "action": {"type": "command", "command": "python -m unittest discover -s tests -v"}, "timeout": 60, "enabled": True}
    hook.update(overrides)
    return hook


def codes(result):
    return {issue["code"] for issue in result["issues"] if issue["severity"] == "error"}


class SchemaTests(unittest.TestCase):
    def test_valid_command_document(self):
        hook = command_hook(description="Tests on save")
        result = validate_document({"version": "v1", "hooks": [hook]})
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["document"]["version"], SCHEMA_VERSION)

    def test_valid_agent_document(self):
        hook = {"name": "Review", "trigger": "PostToolUse", "action": {"type": "agent", "prompt": "Review the tool result."}}
        self.assertTrue(validate_hook(hook)["valid"])

    def test_invalid_version_and_empty_hooks(self):
        self.assertIn("version", codes(validate_document({"version": "1", "hooks": [command_hook()]})))
        self.assertIn("required", codes(validate_document({"version": "v1", "hooks": []})))

    def test_document_boundaries(self):
        self.assertIn("type", codes(validate_document([])))
        self.assertIn("required", codes(validate_document({"version": "v1"})))
        self.assertIn("unknown_field", codes(validate_document({"version": "v1", "hooks": [command_hook()], "extra": 1})))
        self.assertIn("length", codes(validate_document({"version": "v1", "hooks": [command_hook()] * 51})))

    def test_required_name_trigger_action(self):
        for field in ("name", "trigger", "action"):
            hook = command_hook()
            del hook[field]
            with self.subTest(field=field):
                self.assertFalse(validate_hook(hook)["valid"])

    def test_blank_name_rejected(self):
        self.assertIn("required", codes(validate_hook(command_hook(name="  "))))

    def test_description_type_and_length(self):
        self.assertIn("type", codes(validate_hook(command_hook(description=4))))
        self.assertIn("length", codes(validate_hook(command_hook(description="x" * 1001))))

    def test_action_conditional_fields(self):
        self.assertIn("required", codes(validate_hook(command_hook(action={"type": "command"}))))
        self.assertIn("required", codes(validate_hook(command_hook(action={"type": "agent"}))))
        self.assertIn("action_type", codes(validate_hook(command_hook(action={"type": "shell"}))))
        self.assertIn("action_field", codes(validate_hook(command_hook(action={"type": "command", "command": "true", "prompt": "x"}))))
        self.assertIn("action_field", codes(validate_hook(command_hook(action={"type": "agent", "prompt": "x", "command": "true"}))))

    def test_unknown_nested_fields_rejected(self):
        self.assertIn("unknown_field", codes(validate_hook(command_hook(extra=True))))
        self.assertIn("unknown_field", codes(validate_hook(command_hook(action={"type": "command", "command": "true", "cwd": "/tmp"}))))

    def test_timeout_boundaries(self):
        for timeout in (True, 1.5, "60", -1, 86401):
            with self.subTest(timeout=timeout):
                self.assertIn("timeout_type" if isinstance(timeout, bool) or not isinstance(timeout, int) else "timeout_range", codes(validate_hook(command_hook(timeout=timeout))))
        for timeout in (0, 1, 86400):
            self.assertTrue(validate_hook(command_hook(timeout=timeout))["valid"])

    def test_agent_timeout_warns_without_invalidating(self):
        hook = {"name": "Prompt", "trigger": "Stop", "timeout": 10, "action": {"type": "agent", "prompt": "Summarize."}}
        result = validate_hook(hook)
        self.assertTrue(result["valid"])
        self.assertEqual({i["code"] for i in result["issues"]}, {"timeout_ignored"})

    def test_enabled_must_be_boolean(self):
        self.assertIn("enabled_type", codes(validate_hook(command_hook(enabled="false"))))

    def test_permission_request_is_command_only(self):
        hook = command_hook(trigger="PermissionRequest", matcher="write", action={"type": "agent", "prompt": "Check it."})
        self.assertIn("action_unsupported", codes(validate_hook(hook)))

    def test_max_action_length(self):
        hook = command_hook(action={"type": "command", "command": "x" * 16385})
        self.assertIn("length", codes(validate_hook(hook)))


class TriggerAndRegexTests(unittest.TestCase):
    def test_canonical_trigger_list(self):
        self.assertEqual(len(TRIGGERS), 13)
        self.assertIn("PostFileSave", TRIGGERS)
        self.assertIn("PreToolUse", TRIGGERS)
        self.assertIn("Stop", TRIGGERS)
        self.assertNotIn("fileEdited", TRIGGERS)
        self.assertNotIn("agentStop", TRIGGERS)

    def test_all_triggers_validate_without_matcher(self):
        for trigger in TRIGGERS:
            with self.subTest(trigger=trigger):
                hook = command_hook(trigger=trigger, matcher="")
                self.assertTrue(validate_hook(hook)["valid"])

    def test_non_subject_triggers_reject_matcher(self):
        for trigger in ("Stop", "SessionStart", "PreTaskExec", "PostTaskExec", "PreCompaction", "PostCompaction"):
            with self.subTest(trigger=trigger):
                self.assertIn("matcher_unsupported", codes(validate_hook(command_hook(trigger=trigger, matcher=".*"))))

    def test_subject_triggers_accept_regex(self):
        for trigger in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "PostFileCreate", "PostFileSave", "PostFileDelete"):
            with self.subTest(trigger=trigger):
                self.assertTrue(validate_hook(command_hook(trigger=trigger, matcher=r"\.py$"))["valid"])

    def test_invalid_regex(self):
        result = validate_hook(command_hook(matcher="["))
        self.assertIn("regex", codes(result))
        self.assertFalse(result["regex"]["ok"])
        self.assertFalse(regex_check("(")["ok"])
        self.assertTrue(regex_check(r"\.(py|js)$")["ok"])

    def test_matcher_type_and_length(self):
        self.assertIn("regex", codes(validate_hook(command_hook(matcher=4))))
        self.assertIn("regex", codes(validate_hook(command_hook(matcher="x" * 513))))

    def test_empty_matcher_is_always(self):
        self.assertEqual(regex_check("")["kind"], "always")
        self.assertTrue(validate_hook(command_hook(matcher=""))["valid"])

    def test_trigger_catalog_metadata(self):
        catalog = {item["name"]: item for item in trigger_catalog()}
        self.assertTrue(catalog["PreToolUse"]["blocking"])
        self.assertFalse(catalog["Stop"]["blocking"])
        self.assertTrue(catalog["PermissionRequest"]["command_only"])
        self.assertFalse(catalog["Stop"]["matcher"])


class RiskTests(unittest.TestCase):
    def ids(self, command):
        return {warning["id"] for warning in analyze_risk(command_hook(action={"type": "command", "command": command}))["warnings"]}

    def test_destructive_patterns(self):
        self.assertIn("destructive.recursive_delete", self.ids("rm -rf build"))
        self.assertIn("destructive.recursive_delete", self.ids("git reset --hard HEAD"))
        self.assertIn("destructive.recursive_delete", self.ids("Remove-Item build -Recurse"))
        self.assertIn("destructive.disk_or_system", self.ids("mkfs.ext4 /dev/sda"))

    def test_network_patterns(self):
        self.assertIn("network.transfer", self.ids("curl https://example.com"))
        self.assertIn("network.transfer", self.ids("wget file.tar.gz"))
        self.assertIn("network.package_install", self.ids("npm install left-pad"))

    def test_privileged_patterns(self):
        self.assertIn("privileged.escalation", self.ids("sudo apt update"))
        self.assertIn("privileged.escalation", self.ids("runas /user:admin cmd"))

    def test_multiple_warnings_and_summary(self):
        result = analyze_risk(command_hook(action={"type": "command", "command": "sudo rm -rf / && curl example.com"}))
        ids = {warning["id"] for warning in result["warnings"]}
        self.assertTrue({"privileged.escalation", "destructive.recursive_delete", "network.transfer"}.issubset(ids))
        self.assertEqual(result["summary"]["high"], 2)
        self.assertEqual(result["summary"]["medium"], 1)

    def test_clean_command_has_no_warnings(self):
        self.assertEqual(self.ids("python -m unittest discover -s tests -v"), set())

    def test_agent_prompt_not_scanned_as_command(self):
        hook = command_hook(action={"type": "agent", "prompt": "Explain sudo curl rm -rf without running it."})
        self.assertEqual(analyze_risk(hook)["warnings"], [])

    def test_advisory_is_not_safety_guarantee(self):
        self.assertIn("does not establish safety", analyze_risk(command_hook())["advisory"])


class SimulationTests(unittest.TestCase):
    def test_fires_and_returns_inert_action(self):
        result = simulate_hook(command_hook(), {"trigger": "PostFileSave", "subject": "src/app.py"})
        self.assertTrue(result["fired"])
        self.assertEqual(result["status"], "would_fire")
        self.assertFalse(result["executed"])
        self.assertFalse(result["action_requested"]["executed"])
        self.assertEqual(result["action_requested"]["timeout_seconds"], 60)

    def test_regex_no_match(self):
        result = simulate_hook(command_hook(), {"trigger": "PostFileSave", "subject": "README.md"})
        self.assertFalse(result["fired"])
        self.assertEqual(result["status"], "no_match")

    def test_trigger_mismatch(self):
        result = simulate_hook(command_hook(), {"trigger": "PostFileDelete", "subject": "src/app.py"})
        self.assertEqual(result["status"], "trigger_mismatch")

    def test_disabled(self):
        result = simulate_hook(command_hook(enabled=False), {"trigger": "PostFileSave", "subject": "app.py"})
        self.assertEqual(result["status"], "disabled")

    def test_invalid_config_cannot_fire(self):
        result = simulate_hook(command_hook(matcher="["), {"trigger": "PostFileSave", "subject": "app.py"})
        self.assertEqual(result["status"], "invalid")

    def test_event_validation(self):
        for event in (None, [], {}, {"trigger": "Unknown"}, {"trigger": "PostFileSave"}, {"trigger": "PostFileSave", "subject": 2}, {"trigger": "PostFileSave", "subject": "x" * 4097}):
            with self.subTest(event=event):
                self.assertFalse(simulate_hook(command_hook(), event)["fired"])
        self.assertEqual(simulate_hook(command_hook(), {"trigger": "PostFileSave", "subject": "a.py", "unknown": 1})["status"], "invalid_event")

    def test_agent_action_request_has_prompt_not_command(self):
        hook = command_hook(action={"type": "agent", "prompt": "Add tests."})
        result = simulate_hook(hook, {"trigger": "PostFileSave", "subject": "a.py"})
        self.assertEqual(result["action_requested"]["prompt"], "Add tests.")
        self.assertNotIn("command", result["action_requested"])

    def test_timeout_zero_reported_disabled(self):
        result = simulate_hook(command_hook(timeout=0), {"trigger": "PostFileSave", "subject": "a.py"})
        self.assertTrue(result["action_requested"]["timeout_disabled"])

    def test_tool_category_and_wildcard(self):
        self.assertTrue(simulate_hook(command_hook(trigger="PreToolUse", matcher="write"), {"trigger": "PreToolUse", "subject": "fs_write"})["fired"])
        self.assertTrue(simulate_hook(command_hook(trigger="PreToolUse", matcher="mcp_*_query"), {"trigger": "PreToolUse", "subject": "mcp_db_query"})["fired"])
        self.assertFalse(simulate_hook(command_hook(trigger="PreToolUse", matcher="read"), {"trigger": "PreToolUse", "subject": "fs_write"})["fired"])

    def test_tool_source_selector(self):
        hook = command_hook(trigger="PreToolUse", matcher="@postgres/query")
        self.assertTrue(simulate_hook(hook, {"trigger": "PreToolUse", "subject": "mcp_postgres_query"})["fired"])
        self.assertFalse(simulate_hook(hook, {"trigger": "PreToolUse", "subject": "mcp_postgres_exec"})["fired"])

    def test_prompt_subject(self):
        hook = command_hook(trigger="UserPromptSubmit", matcher="deploy|release")
        self.assertTrue(simulate_hook(hook, {"trigger": "UserPromptSubmit", "subject": "Please deploy this"})["fired"])

    def test_stop_has_no_subject(self):
        hook = command_hook(trigger="Stop", matcher="")
        self.assertTrue(simulate_hook(hook, {"trigger": "Stop", "subject": ""})["fired"])

    def test_catastrophic_regex_blocked_only_from_simulation(self):
        hook = command_hook(matcher=r"(a+)+$")
        self.assertTrue(validate_hook(hook)["valid"])
        self.assertTrue(_unsafe_regex_reason(r"(a+)+$"))
        result = simulate_hook(hook, {"trigger": "PostFileSave", "subject": "a" * 100 + "!"})
        self.assertEqual(result["status"], "simulation_blocked")
        self.assertFalse(result["fired"])

    def test_all_repetition_is_blocked_from_simulation(self):
        patterns = (r"\d+", r".*", r"a{1,1000}", r"(a?){1000}", r"(?:a?){1000}", r"((a?)?)?$")
        for pattern in patterns:
            with self.subTest(pattern=pattern):
                hook = command_hook(matcher=pattern)
                self.assertTrue(validate_hook(hook)["valid"])
                self.assertTrue(_unsafe_regex_reason(pattern))
                result = simulate_hook(hook, {"trigger": "PostFileSave", "subject": "a" * 100 + "!"})
                self.assertEqual(result["status"], "simulation_blocked")
                self.assertFalse(result["fired"])

    def test_non_repeating_regex_features_remain_simulatable(self):
        patterns = (r"\.py$", r"\.(py|js)$", r"[a-z]", r"(?i)\.py$", r"(?:py|js)$")
        for pattern in patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNone(_unsafe_regex_reason(pattern))
                hook = command_hook(matcher=pattern)
                result = simulate_hook(hook, {"trigger": "PostFileSave", "subject": "app.py"})
                self.assertEqual(result["status"], "would_fire")

    def test_backreference_blocked_from_simulation(self):
        hook = command_hook(matcher=r"(a)\1$")
        self.assertTrue(validate_hook(hook)["valid"])
        self.assertEqual(simulate_hook(hook, {"trigger": "PostFileSave", "subject": "aa"})["status"], "simulation_blocked")

    def test_nonexecution_with_marker_and_process_spies(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executed.txt"
            command = f'python -c "from pathlib import Path; Path(r\'{marker}\').write_text(\'bad\')"'
            hook = command_hook(action={"type": "command", "command": command})
            with mock.patch("subprocess.run", side_effect=AssertionError("executed")), mock.patch("subprocess.Popen", side_effect=AssertionError("executed")), mock.patch("os.system", side_effect=AssertionError("executed")):
                result = simulate_hook(hook, {"trigger": "PostFileSave", "subject": "a.py"})
                exported = export_document(hook)
            self.assertTrue(result["fired"])
            self.assertTrue(exported["ok"])
            self.assertFalse(marker.exists())

    def test_command_text_never_evaled(self):
        marker_command = "__import__('pathlib').Path('should-not-exist').write_text('x')"
        result = simulate_hook(command_hook(action={"type": "command", "command": marker_command}), {"trigger": "PostFileSave", "subject": "a.py"})
        self.assertEqual(result["action_requested"]["command"], marker_command)
        self.assertFalse(Path("should-not-exist").exists())


class ExportAndTemplateTests(unittest.TestCase):
    def test_export_shape_and_content(self):
        hook = command_hook(description="", matcher="")
        result = export_document(hook, "My Hook")
        self.assertTrue(result["ok"])
        self.assertEqual(result["filename"], "my-hook.json")
        self.assertEqual(result["path"], ".kiro/hooks/my-hook.json")
        self.assertEqual(json.loads(result["content"]), {"version": "v1", "hooks": [{k: v for k, v in hook.items() if k not in {"description", "matcher"}}]})
        self.assertTrue(result["content"].endswith("\n"))

    def test_filename_sanitizes_traversal_and_separators(self):
        hook = command_hook(name="../../evil name")
        self.assertEqual(filename_for(hook), "evil-name.json")
        self.assertEqual(filename_for(hook, r"..\..\CON.json"), "hookforge-con.json")
        self.assertEqual(filename_for(hook, "a/b\\c:d"), "a-b-c-d.json")
        self.assertEqual(filename_for(hook, "💥"), "hookforge-hook.json")

    def test_windows_device_names_are_avoided(self):
        for name in ("CON", "nul", "COM1", "lpt9.json"):
            with self.subTest(name=name):
                self.assertTrue(filename_for(command_hook(), name).startswith("hookforge-"))

    def test_filename_limits_and_duplicate_json_suffix(self):
        name = filename_for(command_hook(), "x" * 200)
        self.assertLessEqual(len(name), 85)
        self.assertEqual(name.count(".json"), 1)
        self.assertTrue(name.endswith(".json"))

    def test_invalid_export_is_refused(self):
        result = export_document(command_hook(name=""))
        self.assertFalse(result["ok"])
        self.assertIn("errors", result)

    def test_example_validates(self):
        example = json.loads((Path(__file__).resolve().parents[1] / ".kiro/hooks/hookforge-safe-test-runner.json").read_text(encoding="utf-8"))
        self.assertTrue(validate_document(example)["valid"])

    def test_three_templates_valid_and_original(self):
        templates = template_catalog()
        self.assertEqual([t["id"] for t in templates], ["post-file-save-tests", "pre-tool-use-guard", "stop-test-gate"])
        for template in templates:
            with self.subTest(template=template["id"]):
                self.assertTrue(validate_hook(template["hook"])["valid"])
        self.assertEqual(templates[0]["hook"]["trigger"], "PostFileSave")
        self.assertEqual(templates[1]["hook"]["trigger"], "PreToolUse")
        self.assertEqual(templates[2]["hook"]["trigger"], "Stop")

    def test_template_guard_simulates_block_request(self):
        hook = template_catalog()[1]["hook"]
        self.assertTrue(simulate_hook(hook, {"trigger": "PreToolUse", "subject": "fs_write"})["fired"])
        self.assertIn("sys.exit(2", hook["action"]["command"])

    def test_templates_do_not_mutate_builder_defaults(self):
        first = copy.deepcopy(template_catalog()[0])
        first["hook"]["name"] = "Changed"
        self.assertNotEqual(template_catalog()[0]["hook"]["name"], "Changed")


if __name__ == "__main__":
    unittest.main()
