# HookForge

**A visual builder and safety simulator for Kiro IDE 1.x standalone hook JSON.**

HookForge helps developers compose `.kiro/hooks/<id>.json` without guessing the schema. It provides a guided form, live JSON, schema and regex validation, heuristic command risk warnings, three editable templates, safe event simulation, and a sanitized JSON download.

HookForge is an original Kiroween 2026 MVP. **It has not yet been reviewed or exercised in real Kiro usage.** That review is planned separately.

## Quick start

Requires Python 3.10+ (tested with Python 3.13). No installation or third-party packages.

```bash
python run.py
```

Open **http://127.0.0.1:8765/**. Optional flags:

```bash
python run.py --port 9000
python run.py --open
python run.py --host localhost
```

The server binds to loopback only. Press Ctrl+C to stop.

## Static demo

For GitHub Pages or any static host, serve the `frontend/` directory and open `?demo=1`:

```bash
python -m http.server 8768 --directory frontend
# http://127.0.0.1:8768/?demo=1
```

The static demo uses `frontend/demo-data.json`, generated from the same pure backend by `python build_demo_data.py`. It supports the three bundled templates and their documented synthetic events, including validation, risk output, inert simulation, and JSON download. Editing a bundled hook or using an unlisted event shows a clear static-demo limit; run the local app for arbitrary input.

## Safety contract

- The backend uses only Python's standard library; the frontend is vanilla HTML/CSS/JS.
- Submitted commands and prompts are inert text. There is no command runner, tool invocation, subprocess API, external API, account, analytics, or outbound network functionality in the application.
- Simulation reports `executed: false` and displays the action Kiro *would* request.
- A conservative regex guard refuses simulation—not export—for all repetition operators, backreferences, conditional patterns, and oversized matchers; tool wildcards still use `fnmatch`.
- HTTP bodies are capped at 64 KiB, JSON nesting at 8 levels, hook arrays at 50 entries, text fields at explicit limits, and duplicate JSON keys are rejected.
- Security headers, same-origin-only CSP, Host validation, fixed static routes, sanitized download names, and no payload logging reduce local exposure.
- Risk warnings are heuristics, not proof of safety. Exported hooks can execute commands when installed in Kiro. Review every command before use.

## Features

### Build and inspect

- Name, description, canonical trigger, matcher, command/agent action, command timeout, and enabled switch.
- All 13 documented canonical IDE 1.x trigger names in the 26 November 2026 snapshot.
- Live schema validation with field-specific issues; regex compilation feedback.
- Agent-only PermissionRequest restriction, action-specific field checks, and unsupported matcher guidance.
- Canonical `{ "version": "v1", "hooks": [...] }` export with safe kebab-case naming.
- Copy preview and download JSON; HookForge never writes into your project automatically.

### Inspect risk

Flags destructive, network, package-install, privileged, and dynamic-execution text with evidence excerpts. No warning is a safety certification.

### Rehearse safely

Choose a synthetic event and subject. The simulator checks validity, enabled state, trigger equality, and matcher behavior. Tool matchers cover categories, wildcards, `@mcp`, `@builtin`, `@powers`, and `@server[/tool]` selectors. Output explains match/no-match, mismatch, disabled, invalid, or simulation-blocked states.

### Templates

1. **PostFileSave test runner** — standard-library tests after Python saves.
2. **PreToolUse guard** — a command that would exit 2 for `.env` write paths.
3. **Stop test gate** — tests when the agent stops; correctly described as reporting failures, not blocking Stop.

Templates are fully editable.

## Example hook

A valid current example is included at `.kiro/hooks/hookforge-safe-test-runner.json`:

```json
{
  "version": "v1",
  "hooks": [
    {
      "name": "hookforge-safe-test-runner",
      "trigger": "PostFileSave",
      "matcher": "\\.py$",
      "action": {
        "type": "command",
        "command": "python -m unittest discover -s tests -v"
      },
      "timeout": 120,
      "enabled": true
    }
  ]
}
```

This repository example activates if the project is opened in a compatible Kiro session. It was schema-validated locally, not run in Kiro.

## Tests and benchmark

From this directory:

```bash
python -m unittest discover -s tests -v
python scripts/benchmark.py
python scripts/smoke_test.py
node --check frontend/app.js  # optional, if Node is available
```

The deterministic 94-test suite covers schema/action boundaries, all canonical triggers, regex failures, risk classes, simulation outcomes, export naming, API payload limits and routes, fixed benchmark expectations, static-demo synchronization, Pages-safe asset URLs, and non-execution using marker files plus process-spawn spies.

The fixed 24-case report is in `benchmarks/validation-benchmark.md`; its source fixtures are in `benchmarks/validation-cases.json`. It measures HookForge's own documented contract, not official Kiro certification.

## Local API

| Route | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Local service and execution status |
| `/api/meta` | GET | Trigger and template catalogs |
| `/api/validate` | POST | Validate one hook: `{"hook": {...}}` |
| `/api/document` | POST | Validate a complete file: `{"document": {...}}` |
| `/api/risk` | POST | Analyze command text: `{"hook": {...}}` |
| `/api/simulate` | POST | Dry run: `{"hook": {...}, "event": {"trigger": "...", "subject": "..."}}` |
| `/api/export` | POST | Export: `{"hook": {...}, "filename": "optional-name"}` |

POST requests require `application/json`. Validation results use HTTP 200 with `valid: false`; malformed transport/input uses 4xx. All responses are JSON except static assets.

## Project map

- `run.py` — CLI entry point and loopback server launcher
- `server.py` — fixed-route HTTP server and input boundaries
- `hookforge_core.py` — pure schema, regex, risk, naming, simulation, catalogs
- `frontend/` — responsive vanilla studio and backend-free `?demo=1` payload
- `build_demo_data.py` — regenerates static demo results from the pure backend
- `tests/` — deterministic core, API, benchmark, and static-demo tests
- `scripts/smoke_test.py` — launches a real local server and probes HTTP
- `benchmarks/` — fixed validation fixtures and generated report
- `.kiro/specs/` — requirements, design, and task record
- `.kiro/steering/project.md` — project guidance
- `.kiro/hooks/` — valid standalone v1 example

## Official schema snapshot and known gaps

References checked **26 November 2026**:

- https://kiro.dev/docs/hooks/
- https://kiro.dev/docs/hooks/types/
- https://kiro.dev/docs/ide/whats-new-v1/hooks/

MVP gaps: one hook per builder/export; no import, persistence, multi-hook editor, `confirm`/`confirmCommand` editor, automatic template-variable substitution, or real STDIN payload generator. Tool-category membership is illustrative and may not enumerate every installed tool ID. Python regex semantics approximate—but do not certify—Kiro runtime matching. Simulation does not execute commands, evaluate exit codes, model hook ordering, or contact Kiro. A real Kiro IDE 1.4.236 review and disposition are recorded in `KIRO_REVIEW.md`.

## License

MIT — see [LICENSE](LICENSE).
