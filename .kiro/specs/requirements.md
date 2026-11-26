# HookForge requirements

Status: implemented MVP; real Kiro review pending. Schema snapshot: 26 November 2026.

## Product intent

HookForge SHALL help a developer create, inspect, and safely rehearse a standalone Kiro IDE 1.x hook JSON file without schema guessing or executing submitted input.

## User stories and acceptance criteria

### 1. Guided builder

WHEN a developer opens the studio, HookForge SHALL expose name, description, trigger, matcher, action type, command or prompt, timeout, and enabled fields.

WHEN fields change, the JSON preview SHALL update locally and validation SHALL run through the local backend.

The preview SHALL use top-level `version: "v1"` and a `hooks` array.

### 2. Schema validation

The validator SHALL require a nonblank name, supported trigger, action object, and action-specific command/prompt.

The validator SHALL enforce string types, field lengths, whole-number timeout range `0..86400`, boolean enabled, known fields, and `PermissionRequest` command-only behavior.

The validator SHALL accept all 13 canonical PascalCase IDE 1.x triggers in the snapshot: `SessionStart`, `UserPromptSubmit`, `Stop`, `PreTaskExec`, `PostTaskExec`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostFileCreate`, `PostFileSave`, `PostFileDelete`, `PreCompaction`, and `PostCompaction`.

The validator SHALL reject legacy camelCase triggers, wrong schema versions, empty hook arrays, invalid action combinations, and matcher use on triggers with no matcher subject.

### 3. Regex validation and safe simulation

The backend SHALL compile nonblank matchers and report regex errors without crashing.

The simulator SHALL return invalid/no-match/would-fire decisions deterministically.

The simulator SHALL evaluate tool selectors, wildcards, categories, and regex matchers for tool triggers; file and prompt triggers SHALL use regex search against the subject.

The simulator SHALL refuse potentially catastrophic or unsupported simulation patterns with an explanation while leaving schema validity/export unaffected.

### 4. Risk warnings

The scanner SHALL identify destructive, network, privileged, package-install, and dynamic-execution patterns in command actions with severity and evidence.

The scanner SHALL state that heuristic silence is not proof of safety and SHALL NOT scan agent prompts as commands.

### 5. Safe event simulator

The simulator SHALL evaluate validation, enabled state, trigger equality, then matcher behavior.

WHEN a hook would fire, it SHALL show the requested command or agent prompt with `executed: false`.

HookForge SHALL NOT execute commands, call tools, contact external services, or inject prompts during simulation.

### 6. Templates

HookForge SHALL provide editable templates for PostFileSave test running, PreToolUse guarding, and Stop test gating.

The Stop template SHALL NOT claim Stop can block completion.

The PreToolUse template SHALL demonstrate an exit-code-2 guard for `.env` paths.

### 7. Export

Export SHALL be available only for schema-valid hooks.

Export SHALL produce valid v1 JSON with a newline and a safe kebab-case `<id>.json` filename, stripping traversal and duplicate `.json` suffixes.

HookForge SHALL offer a browser download and SHALL NOT automatically install or register hooks.

### 8. Runtime boundaries and privacy

The backend SHALL use only the Python standard library and bind only to loopback.

The frontend SHALL use vanilla HTML/CSS/JS and make no external runtime requests.

The API SHALL enforce body size, UTF-8, JSON syntax, duplicate-key rejection, nesting depth, content type, field allowlists, and text/array boundaries.

The server SHALL use fixed static routes, reject foreign Host headers, omit payload logging, and send restrictive security headers.

### 9. Quality and deliverables

The project SHALL include deterministic tests for schema validation, trigger support, regex errors, risks, simulation, export naming, API boundaries, and non-execution.

The project SHALL include a fixed benchmark report and reproducible fixture runner.

The project SHALL include `run.py`, README, MIT LICENSE, requirements/design/tasks specs, steering guidance, and a valid standalone v1 example.

The project SHALL pass its full test suite and a localhost server smoke test.

The project SHALL NOT claim real Kiro usage until a separate review occurs.

## Non-goals

No accounts, registration, publishing, remote API, package manager, Kiro CLI integration, command execution, rule acceptance, real hook runtime certification, import, persistence, multi-hook editing, or confirmation-prompt editor.

## Reference basis

- https://kiro.dev/docs/hooks/
- https://kiro.dev/docs/hooks/types/
- https://kiro.dev/docs/ide/whats-new-v1/hooks/
