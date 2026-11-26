---
inclusion: always
---

# HookForge project guidance

## Purpose and status

HookForge is an original Kiroween 2026 MVP: a visual builder and safety simulator for standalone Kiro IDE 1.x hook JSON. Local implementation is complete. Real Kiro usage/review is pending and must not be claimed.

## Technical constraints

- Backend: Python standard library only. Target Python 3.10+.
- Frontend: vanilla HTML, CSS, and JavaScript. No frameworks, CDNs, external fonts, analytics, or runtime network calls beyond same-origin localhost.
- Server: loopback only; default `127.0.0.1:8765`.
- Submitted commands/prompts are data, never executable input. Never add subprocess, shell, eval, exec, tool invocation, or external API paths for them.
- Keep domain logic pure in `hookforge_core.py`; transport logic belongs in `server.py`.
- Use fixed static routes and explicit input limits. Do not add arbitrary file read/write endpoints.
- Preserve explicit `executed: false` and dry-run language in simulation output.

## Schema conventions

- Export top-level `version: "v1"` and `hooks` array.
- Use canonical PascalCase IDE 1.x triggers; do not accept 0.x camelCase aliases.
- Matcher applies only to UserPromptSubmit, tool triggers, and file triggers.
- PermissionRequest is command-only.
- Stop is nonblocking. Never describe the Stop template as preventing completion.
- Schema snapshot basis: https://kiro.dev/docs/hooks/ and https://kiro.dev/docs/hooks/types/ (checked 26 November 2026).

## UI and code conventions

- Keep the dark forge/lime visual language, responsive layout, keyboard focus, reduced-motion support, and accessible labels/status regions.
- Insert user-controlled values with `textContent`/safe DOM APIs, never HTML interpolation.
- Use stable diagnostic codes and JSON paths.
- Risk warnings are advisory and never establish safety.
- Sanitize export filenames into one kebab-case `.json` component; never write automatically into a user's project.

## Verification before considering changes complete

```bash
python -m unittest discover -s tests -v
python scripts/benchmark.py
python scripts/smoke_test.py
node --check frontend/app.js
```

Add deterministic tests for changed validation, trigger, risk, simulation, naming, API, or safety behavior. Non-execution tests should use marker files and process-spawn spies.

## Product boundaries

No accounts, registration, publishing, push, package installs, external APIs, command execution from submitted input, rule acceptance, or claims of real Kiro usage. Current gaps include one-hook editing, no import/persistence, no confirmation editor, illustrative tool IDs, approximate regex semantics, and no actual Kiro runtime certification.
