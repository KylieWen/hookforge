# HookForge design

Status: implemented MVP. This design describes local behavior, not verified Kiro runtime behavior.

## Architecture

HookForge is a loopback-only, single-process web application:

```text
Browser (vanilla HTML/CSS/JS)
    │ same-origin fetch, JSON
    ▼
server.py (ThreadingHTTPServer, fixed routes, transport boundaries)
    │
    ▼
hookforge_core.py (pure functions; no shell, subprocess, socket, or write APIs)
```

`run.py` is the only CLI entry point. It validates host/port, starts the server, prints the loopback URL, and optionally opens a browser. Static assets are allowlisted, never resolved from arbitrary request paths.

## Domain model

A builder produces one hook:

```text
Hook {
  name: string
  description?: string
  trigger: canonical IDE 1.x name
  matcher?: string
  action: {type: "command", command: string}
        | {type: "agent", prompt: string}
  timeout?: integer seconds
  enabled?: boolean
}
```

Export wraps it as `{version: "v1", hooks: [Hook]}`. Blank description/matcher are omitted. Defaults are timeout 60 seconds and enabled true.

## Validation pipeline

1. Transport validates content type, length, UTF-8, JSON, duplicate keys, nesting, and route payload fields.
2. Domain validation checks object shape, known keys, required fields, types, lengths, action conditionals, canonical trigger, matcher support, and regex compilation.
3. Risk analysis scans command text independently; warnings do not invalidate configuration.
4. Export is refused when domain errors exist.
5. Simulation repeats domain validation before any decision.

Diagnostics use stable `code`, `path`, `severity`, and `message` fields. Document validation prefixes hook issue paths with `$.hooks[index]`.

## Trigger and matcher model

| Trigger group | Subject | Matcher behavior |
|---|---|---|
| File create/save/delete | File path | Python regex search approximation |
| UserPromptSubmit | Prompt text | Python regex search approximation |
| Pre/PostToolUse, PermissionRequest | Tool name/ID | Category, source selector, wildcard, then regex search |
| SessionStart, Stop, task, compaction | None | Matcher must be blank/absent |

Tool selectors include built-in categories, `@mcp`, `@builtin`, `@powers`, and `@server`/`@server/tool`. Category membership is a documented illustrative set, not a live Kiro tool registry.

PermissionRequest accepts command actions only. Blocking metadata covers UserPromptSubmit, PreTaskExec, and PreToolUse; Stop is never labeled blocking.

## Safety design

### Non-execution

Submitted action text is never passed to an interpreter, shell, process launcher, tool runtime, or network client. Core imports no execution APIs. Simulation returns a separate action-request object containing the inert text and explicit false execution flags.

Tests use temporary marker files and monkeypatch `subprocess.run`, `subprocess.Popen`, and `os.system` to fail if execution is attempted. They exercise both core and HTTP paths.

### Regex safety

Compilation is separated from application. Validation accepts syntactically valid patterns for export. Before applying a matcher to event text, simulation rejects:

- patterns over 256 characters,
- numeric backreferences,
- repeated groups with nested repetition or alternation,
- large counted repetitions over 1000.

This conservative guard avoids unbounded regex work; it is intentionally not a full regex equivalence or performance proof.

### Input and local exposure

- Loopback bind only; foreign Host values rejected.
- 64 KiB body limit; 8-level JSON limit; 50-hook document limit.
- Duplicate JSON keys rejected; unknown route/event/action/hook fields rejected.
- Explicit field limits: name 200, description 1000, matcher 512, action text 16384, event subject 4096, filename request 200, timeout 86400.
- Fixed static map; no directory traversal or user-controlled file reads/writes.
- No request payload logging. Internal errors return generic JSON.
- CSP `default-src 'self'`, `connect-src 'self'`, no objects/base/form actions; no CORS headers.
- Frontend inserts user values with `textContent`, never HTML interpolation.

### Export naming

Filename source is explicit filename or hook name. NFKD ASCII normalization, lowercasing, non-alphanumeric collapsing, one optional trailing `.json` removal, Windows device-name avoidance, 80-character slug cap, and a fallback produce one safe `.json` component. The server never writes the file; the browser downloads a Blob.

## Frontend behavior

A responsive two-column workspace presents composition and live inspection. Debounced sequence numbers prevent stale validation responses from overwriting newer edits. The form hides/disables inapplicable action fields and matcher input. Trigger changes update helper text and the simulator's default event.

The simulator presents a verdict, decision chain, and inert action request. Template cards create fresh editable state. Clipboard uses the browser API; downloads use a temporary object URL. No localStorage, analytics, external font, CDN, or third-party script is used.

## API contract

All successful responses use HTTP 200. Domain-invalid hooks return `valid: false` rather than a transport error. Malformed transport/input returns structured 4xx JSON. Unexpected exceptions return a generic 500 without traces.

Routes: `GET /api/health`, `GET /api/meta`, `POST /api/validate`, `POST /api/document`, `POST /api/risk`, `POST /api/simulate`, `POST /api/export`.

## Templates

- PostFileSave `\.py$` → `python -m unittest discover -s tests -v`.
- PreToolUse category `write` → inline Python reads synthetic STDIN shape and would exit 2 for `.env` paths. HookForge only displays this command.
- Stop → unittest command with a clear nonblocking description.

## Verification strategy

- Pure core tests: schema, triggers, regex, risk, simulation, naming, examples/templates, process spies.
- Ephemeral loopback HTTP tests: static assets, security headers, routes, malformed bodies, limits, duplicate keys, Host rejection, API behavior, non-execution.
- Benchmark: 24 fixed cases, 13 trigger acceptance plus 11 negatives.
- Smoke: start `run.py` as a real subprocess on an ephemeral port; probe health, metadata, assets, validation, risk, simulation, export, marker non-creation, and 404 handling; terminate reliably.
- Frontend syntax: `node --check` when Node is available; Python compile checks.

## Deliberate boundaries

No real Kiro runtime calls, command execution, STDIN payload generation beyond subject, confirmation editor, multi-hook UI, import, persistence, installation, or registry. Python regex and illustrative tool IDs may differ from Kiro. Real Kiro review remains a separate task.
