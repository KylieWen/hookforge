"""Pure HookForge validation, risk analysis, and dry-run simulation.

This module deliberately has no subprocess, shell, socket, or filesystem-writing
APIs. Hook commands are treated as inert text throughout.
"""
from __future__ import annotations

import fnmatch
import json
import re
import unicodedata
from typing import Any

SCHEMA_VERSION = "v1"
MAX_TEXT = 16_384
MAX_MATCHER = 512
MAX_TIMEOUT = 86_400
MAX_HOOKS = 50
MAX_EVENT_DEPTH = 8

# Canonical IDE 1.x PascalCase names. IDE 0.x aliases are intentionally absent.
TRIGGERS = (
    "SessionStart",
    "UserPromptSubmit",
    "Stop",
    "PreTaskExec",
    "PostTaskExec",
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "PostFileCreate",
    "PostFileSave",
    "PostFileDelete",
    "PreCompaction",
    "PostCompaction",
)
SUBJECT_TRIGGERS = {
    "UserPromptSubmit": "prompt text",
    "PreToolUse": "tool name",
    "PostToolUse": "tool name",
    "PermissionRequest": "tool name",
    "PostFileCreate": "file path",
    "PostFileSave": "file path",
    "PostFileDelete": "file path",
}
TOOL_TRIGGERS = {"PreToolUse", "PostToolUse", "PermissionRequest"}
NO_MATCHER_TRIGGERS = set(TRIGGERS) - set(SUBJECT_TRIGGERS)
TOOL_CATEGORIES = {
    "read": {"read_file", "read_files", "grep", "glob", "list_directory"},
    "write": {"write_file", "edit_file", "create_file", "delete_file", "fs_write"},
    "shell": {"execute_bash", "execute_command", "run_command", "shell"},
    "web": {"web_search", "web_fetch", "fetch_url"},
    "spec": {"create_spec", "update_spec", "get_spec", "list_specs"},
}
ALLOWED_HOOK_KEYS = {"name", "description", "trigger", "matcher", "action", "timeout", "enabled"}
ALLOWED_ACTION_KEYS = {"type", "command", "prompt"}
ALLOWED_EVENT_KEYS = {"trigger", "subject", "tool_input", "metadata"}


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "path": path, "message": message}


def _warning(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "warning", "code": code, "path": path, "message": message}


def _text(value: Any) -> bool:
    return isinstance(value, str)


def regex_check(pattern: Any) -> dict[str, Any]:
    """Compile a matcher without applying it to user-controlled event text."""
    if pattern is None or pattern == "":
        return {"ok": True, "kind": "always", "message": "Matches every event."}
    if not _text(pattern):
        return {"ok": False, "kind": "invalid", "message": "Matcher must be a string."}
    if len(pattern) > MAX_MATCHER:
        return {"ok": False, "kind": "invalid", "message": f"Matcher must be at most {MAX_MATCHER} characters."}
    if "\x00" in pattern:
        return {"ok": False, "kind": "invalid", "message": "Matcher cannot contain a null character."}
    try:
        re.compile(pattern)
    except (re.error, OverflowError, RecursionError) as exc:
        return {"ok": False, "kind": "invalid", "message": f"Invalid regular expression: {exc}"}
    return {"ok": True, "kind": "regex", "message": "Valid regular expression."}


def _unsafe_regex_reason(pattern: str) -> str | None:
    """Allow only regex constructs whose matching cost cannot amplify exponentially."""
    if len(pattern) > 256:
        return "Matcher is too long for safe simulation (maximum 256 characters)."
    escaped = False
    in_class = False
    for index, char in enumerate(pattern):
        if escaped:
            if char in "123456789":
                return "Backreferences are not applied in the safe simulator."
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if in_class:
            if char == "]":
                in_class = False
            continue
        if char == "[":
            in_class = True
            continue
        if char in "*+{":
            return "Regex repetition is not applied in the safe simulator."
        if char == "?" and not (index > 0 and pattern[index - 1] == "("):
            return "Regex repetition is not applied in the safe simulator."
        if pattern.startswith(("(?P=", "(?("), index):
            return "Conditional and named backreferences are not applied in the safe simulator."
    return None


def validate_hook(hook: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(hook, dict):
        return {"valid": False, "issues": [_error("type", "$", "Hook must be a JSON object.")], "regex": None}

    for key in sorted(set(hook) - ALLOWED_HOOK_KEYS):
        issues.append(_error("unknown_field", f"$.{key}", f"Unknown hook field '{key}'."))

    name = hook.get("name")
    if not _text(name) or not name.strip():
        issues.append(_error("required", "$.name", "Name is required and cannot be blank."))
    elif len(name) > 200:
        issues.append(_error("length", "$.name", "Name must be at most 200 characters."))

    if "description" in hook:
        description = hook["description"]
        if not _text(description):
            issues.append(_error("type", "$.description", "Description must be a string."))
        elif len(description) > 1000:
            issues.append(_error("length", "$.description", "Description must be at most 1000 characters."))

    matcher = hook.get("matcher")
    matcher_result = regex_check(matcher)
    if not matcher_result["ok"]:
        issues.append(_error("regex", "$.matcher", matcher_result["message"]))

    trigger = hook.get("trigger")
    if not _text(trigger) or trigger not in TRIGGERS:
        issues.append(_error("trigger", "$.trigger", "Choose a supported IDE 1.x PascalCase trigger."))
    elif trigger in NO_MATCHER_TRIGGERS and matcher not in (None, ""):
        issues.append(_error("matcher_unsupported", "$.matcher", f"{trigger} does not expose a matcher subject."))

    action = hook.get("action")
    action_type = None
    if not isinstance(action, dict):
        issues.append(_error("required", "$.action", "Action must be an object."))
    else:
        for key in sorted(set(action) - ALLOWED_ACTION_KEYS):
            issues.append(_error("unknown_field", f"$.action.{key}", f"Unknown action field '{key}'."))
        action_type = action.get("type")
        if action_type not in ("command", "agent"):
            issues.append(_error("action_type", "$.action.type", "Action type must be 'command' or 'agent'."))
        elif action_type == "command":
            command = action.get("command")
            if not _text(command) or not command.strip():
                issues.append(_error("required", "$.action.command", "Command is required and cannot be blank."))
            elif len(command) > MAX_TEXT:
                issues.append(_error("length", "$.action.command", f"Command must be at most {MAX_TEXT} characters."))
            if "prompt" in action:
                issues.append(_error("action_field", "$.action.prompt", "Remove prompt when action type is command."))
        else:
            prompt = action.get("prompt")
            if not _text(prompt) or not prompt.strip():
                issues.append(_error("required", "$.action.prompt", "Prompt is required and cannot be blank."))
            elif len(prompt) > MAX_TEXT:
                issues.append(_error("length", "$.action.prompt", f"Prompt must be at most {MAX_TEXT} characters."))
            if "command" in action:
                issues.append(_error("action_field", "$.action.command", "Remove command when action type is agent."))
        if trigger == "PermissionRequest" and action_type == "agent":
            issues.append(_error("action_unsupported", "$.action.type", "PermissionRequest supports command actions only."))

    if "timeout" in hook:
        timeout = hook["timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            issues.append(_error("timeout_type", "$.timeout", "Timeout must be a whole number of seconds."))
        elif timeout < 0 or timeout > MAX_TIMEOUT:
            issues.append(_error("timeout_range", "$.timeout", f"Timeout must be between 0 and {MAX_TIMEOUT} seconds."))
        elif action_type == "agent":
            issues.append(_warning("timeout_ignored", "$.timeout", "Kiro ignores timeout for agent actions."))

    if "enabled" in hook and not isinstance(hook["enabled"], bool):
        issues.append(_error("enabled_type", "$.enabled", "Enabled must be true or false."))

    return {"valid": not any(i["severity"] == "error" for i in issues), "issues": issues, "regex": matcher_result}


def validate_document(document: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    normalized = {"version": SCHEMA_VERSION, "hooks": []}
    if not isinstance(document, dict):
        return {"valid": False, "document": normalized, "issues": [_error("type", "$", "Hook file must be a JSON object.")]}
    for key in sorted(set(document) - {"version", "hooks"}):
        issues.append(_error("unknown_field", f"$.{key}", f"Unknown top-level field '{key}'."))
    if document.get("version") != SCHEMA_VERSION:
        issues.append(_error("version", "$.version", "version must be the string 'v1'."))
    hooks = document.get("hooks")
    if not isinstance(hooks, list):
        issues.append(_error("required", "$.hooks", "hooks must be an array."))
    elif not hooks:
        issues.append(_error("required", "$.hooks", "hooks must contain at least one hook."))
    elif len(hooks) > MAX_HOOKS:
        issues.append(_error("length", "$.hooks", f"A maximum of {MAX_HOOKS} hooks is supported."))
    else:
        normalized["hooks"] = hooks
        for index, hook in enumerate(hooks):
            result = validate_hook(hook)
            for issue in result["issues"]:
                copied = dict(issue)
                copied["path"] = copied["path"].replace("$.", f"$.hooks[{index}].", 1)
                issues.append(copied)
    return {"valid": not any(i["severity"] == "error" for i in issues), "document": normalized, "issues": issues}


RISK_RULES = (
    ("destructive.recursive_delete", "destructive", "high", "Recursive or forced deletion", r"\brm\s+(?=[^;\n]*(?:-[a-z]*[rf][a-z]*|--recursive|--force))|\bdel\s+/[fsq]|\brmdir\s+/s\b|\bRemove-Item\b[^;\n]*-Recurse|\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-[a-z]*f"),
    ("destructive.disk_or_system", "destructive", "high", "Disk, filesystem, or system destruction", r"\bmkfs(?:\.\w+)?\b|\bdd\s+if=|\bformat\s+[a-z]:|\bdiskpart\b|\bshutdown\b|\breboot\b|\bInitialize-Disk\b"),
    ("network.transfer", "network", "medium", "Network transfer or remote connection", r"\bcurl\b|\bwget\b|\bInvoke-WebRequest\b|\biwr\b|\bscp\b|\bssh\b|\bftp\b|\bnc\s|\bncat\s|\bhttps?://"),
    ("network.package_install", "network", "medium", "Package installation may fetch from a registry", r"\b(?:npm|pnpm|yarn|bun)\s+(?:i|install|add)\b|\bpip3?\s+install\b|\buv\s+(?:add|sync|pip\s+install)\b|\bapt(?:-get)?\s+install\b"),
    ("privileged.escalation", "privileged", "high", "Privilege elevation or administration", r"\bsudo\b|\bdoas\b|\bsu\s+-|\brunas\b|\bSet-ExecutionPolicy\b|\bicacls\b|\btakeown\b|\bchown\b|\bchmod\s+(?:777|-[rR])"),
    ("execution.dynamic", "destructive", "high", "Dynamic code execution can hide the final operation", r"\beval\s|\b(?:bash|sh|cmd|powershell|pwsh)\s+-[a-z]*c\b|\bInvoke-Expression\b|\bStart-Process\b"),
)


def analyze_risk(hook: Any) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    if isinstance(hook, dict) and isinstance(hook.get("action"), dict):
        action = hook["action"]
        if action.get("type") == "command" and _text(action.get("command")):
            command = action["command"]
            for rule_id, category, severity, title, pattern in RISK_RULES:
                match = re.search(pattern, command, re.IGNORECASE)
                if match:
                    start = max(0, match.start() - 18)
                    end = min(len(command), match.end() + 30)
                    warnings.append({
                        "id": rule_id, "category": category, "severity": severity,
                        "title": title, "evidence": command[start:end],
                        "message": "Review this operation before installing the hook. HookForge never executes it.",
                    })
    return {
        "warnings": warnings,
        "summary": {"high": sum(w["severity"] == "high" for w in warnings), "medium": sum(w["severity"] == "medium" for w in warnings)},
        "advisory": "Heuristic text analysis only; absence of warnings does not establish safety.",
    }


def filename_for(hook: Any, requested: Any = None) -> str:
    """Return a safe single-component kebab-case JSON filename."""
    source = requested if _text(requested) and requested.strip() else (hook.get("name") if isinstance(hook, dict) else "")
    source = unicodedata.normalize("NFKD", source or "").encode("ascii", "ignore").decode("ascii")
    source = re.sub(r"\.json$", "", source, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:80].rstrip("-") or "hookforge-hook"
    # Windows device names remain reserved even with a .json extension.
    if slug.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        slug = "hookforge-" + slug.lower()
    return slug + ".json"


def export_document(hook: Any, requested: Any = None) -> dict[str, Any]:
    validation = validate_hook(hook)
    if not validation["valid"]:
        return {"ok": False, "errors": [i for i in validation["issues"] if i["severity"] == "error"]}
    filename = filename_for(hook, requested)
    # Keep builder output canonical and omit blank optional fields.
    clean = {key: value for key, value in hook.items() if value is not None}
    if clean.get("matcher") == "":
        clean.pop("matcher")
    if clean.get("description") == "":
        clean.pop("description")
    document = {"version": SCHEMA_VERSION, "hooks": [clean]}
    content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    return {"ok": True, "filename": filename, "path": f".kiro/hooks/{filename}", "content": content, "document": document}


def _tool_matcher_matches(pattern: str, tool_name: str) -> tuple[bool, str]:
    if pattern in ("", "*"):
        return True, "wildcard matched every tool"
    if pattern in TOOL_CATEGORIES:
        matched = tool_name in TOOL_CATEGORIES[pattern]
        return matched, f"category '{pattern}' {'matched' if matched else 'did not match'} '{tool_name}'"
    if pattern == "@mcp":
        return tool_name.startswith("mcp_"), f"MCP source selector {'matched' if tool_name.startswith('mcp_') else 'did not match'}"
    if pattern == "@builtin":
        return not tool_name.startswith("mcp_"), "built-in source selector evaluated"
    if pattern == "@powers":
        return tool_name.startswith("powers_"), "Powers source selector evaluated"
    if pattern.startswith("@"):
        body = pattern[1:]
        if "/" in body:
            server, tool = body.split("/", 1)
            target = f"mcp_{server}_{tool}"
            return fnmatch.fnmatchcase(tool_name, target), f"source selector '{pattern}' evaluated"
        return fnmatch.fnmatchcase(tool_name, f"mcp_{body}_*"), f"source selector '{pattern}' evaluated"
    if ("*" in pattern or "?" in pattern) and not re.search(r"[\[\]()+|^$\\]", pattern):
        return fnmatch.fnmatchcase(tool_name, pattern), f"wildcard '{pattern}' evaluated against '{tool_name}'"
    try:
        return re.search(pattern, tool_name) is not None, f"regex searched '{tool_name}'"
    except re.error:
        return False, "invalid regex"


def _subject_for_event(trigger: str, event: dict[str, Any]) -> str:
    if trigger in TOOL_TRIGGERS:
        return event.get("subject", "")
    return event.get("subject", "")


def simulate_hook(hook: Any, event: Any) -> dict[str, Any]:
    """Decide whether a hook would fire; never execute its action."""
    base = {"dry_run": True, "executed": False, "fired": False, "action_requested": None}
    validation = validate_hook(hook)
    if not validation["valid"]:
        return {**base, "status": "invalid", "reason": "Fix hook validation errors before simulating.", "issues": validation["issues"]}
    if not isinstance(event, dict):
        return {**base, "status": "invalid_event", "reason": "Event must be a JSON object."}
    for key in sorted(set(event) - ALLOWED_EVENT_KEYS):
        return {**base, "status": "invalid_event", "reason": f"Unknown event field '{key}'."}
    event_trigger = event.get("trigger")
    if event_trigger not in TRIGGERS:
        return {**base, "status": "invalid_event", "reason": "Choose a supported event trigger."}
    subject = event.get("subject", "")
    if not _text(subject):
        return {**base, "status": "invalid_event", "reason": "Event subject must be a string."}
    if len(subject) > 4096:
        return {**base, "status": "invalid_event", "reason": "Event subject must be at most 4096 characters."}
    if event_trigger in SUBJECT_TRIGGERS and not subject:
        return {**base, "status": "invalid_event", "reason": f"This event needs a {SUBJECT_TRIGGERS[event_trigger]} subject."}
    if hook.get("enabled", True) is False:
        return {**base, "status": "disabled", "reason": "Hook is disabled; Kiro would skip it."}
    if hook["trigger"] != event_trigger:
        return {**base, "status": "trigger_mismatch", "reason": f"Hook listens for {hook['trigger']}, not {event_trigger}."}

    pattern = hook.get("matcher") or ""
    if hook["trigger"] in TOOL_TRIGGERS:
        wildcard = ("*" in pattern or "?" in pattern) and not re.search(r"[\[\]()+|^$\\]", pattern)
        uses_regex = pattern not in ("", "*") and pattern not in TOOL_CATEGORIES and not pattern.startswith("@") and not wildcard
        if uses_regex:
            unsafe = _unsafe_regex_reason(pattern)
            if unsafe:
                return {**base, "status": "simulation_blocked", "reason": unsafe}
        matched, detail = _tool_matcher_matches(pattern, subject)
    else:
        unsafe = _unsafe_regex_reason(pattern)
        if unsafe:
            return {**base, "status": "simulation_blocked", "reason": unsafe}
        try:
            matched = re.search(pattern, subject) is not None if pattern else True
        except re.error as exc:
            return {**base, "status": "invalid", "reason": f"Regex error: {exc}"}
        detail = "matcher found a match" if matched else "matcher did not find a match"
    if not matched:
        return {**base, "status": "no_match", "reason": detail}

    action = hook["action"]
    requested = {"type": action["type"], "executed": False}
    if action["type"] == "command":
        requested.update({"command": action["command"], "timeout_seconds": hook.get("timeout", 60), "timeout_disabled": hook.get("timeout", 60) == 0})
    else:
        requested["prompt"] = action["prompt"]
    return {
        **base, "fired": True, "status": "would_fire", "reason": detail,
        "action_requested": requested,
        "note": "The action is displayed only. No command, tool, network request, or agent prompt was run.",
    }


def trigger_catalog() -> list[dict[str, Any]]:
    return [
        {"name": trigger, "subject": SUBJECT_TRIGGERS.get(trigger), "matcher": trigger in SUBJECT_TRIGGERS,
         "command_only": trigger == "PermissionRequest", "blocking": trigger in {"UserPromptSubmit", "PreTaskExec", "PreToolUse"}}
        for trigger in TRIGGERS
    ]


def template_catalog() -> list[dict[str, Any]]:
    guard = (
        'python -c "import json,sys; e=json.load(sys.stdin); '
        "p=str(e.get('tool_input',{}).get('path','')).replace(chr(92),'/'); "
        "sys.exit(2 if p.endswith('.env') or '/.env' in p else 0)\""
    )
    return [
        {
            "id": "post-file-save-tests", "title": "PostFileSave test runner", "eyebrow": "VERIFY ON SAVE",
            "description": "Run the project's standard-library tests after an agent saves a Python file.",
            "hook": {"name": "Test Python on save", "description": "Run tests after agent-edited Python files are saved.", "trigger": "PostFileSave", "matcher": r"\.py$", "action": {"type": "command", "command": "python -m unittest discover -s tests -v"}, "timeout": 120, "enabled": True},
        },
        {
            "id": "pre-tool-use-guard", "title": "PreToolUse guard", "eyebrow": "PROTECT SECRETS",
            "description": "Block agent write tools when the requested path targets a .env file.",
            "hook": {"name": "Guard .env writes", "description": "Exit 2 to block writes to .env files before the tool executes.", "trigger": "PreToolUse", "matcher": "write", "action": {"type": "command", "command": guard}, "timeout": 10, "enabled": True},
        },
        {
            "id": "stop-test-gate", "title": "Stop test gate", "eyebrow": "CHECK BEFORE DONE",
            "description": "Run tests when the agent stops. Failures are reported; Stop itself cannot block completion.",
            "hook": {"name": "Test gate at stop", "description": "Run the test suite when the agent completes its turn.", "trigger": "Stop", "action": {"type": "command", "command": "python -m unittest discover -s tests -v"}, "timeout": 120, "enabled": True},
        },
    ]
