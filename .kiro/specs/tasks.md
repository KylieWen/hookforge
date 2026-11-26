# HookForge tasks

Status key: `[x]` completed locally, `[ ]` pending. Real Kiro review is intentionally not marked complete.

## 1. Specification and safety contract

- [x] Record original product intent and non-goals.
- [x] Check official Kiro hook schema, trigger, actions, and IDE migration references (26 November 2026 snapshot).
- [x] Define non-execution, loopback-only, no-external-API constraints.
- [x] Document Python regex and tool-ID approximation boundaries.

## 2. Backend

- [x] Implement pure schema/domain validation for one hook and complete documents.
- [x] Support 13 canonical IDE 1.x triggers and reject legacy aliases.
- [x] Implement action-specific conditional validation and PermissionRequest restriction.
- [x] Implement regex compilation and conservative simulation safety guard.
- [x] Implement destructive/network/privileged/package/dynamic risk heuristics.
- [x] Implement inert event simulation with clear decision states.
- [x] Implement sanitized export naming and canonical v1 JSON.
- [x] Implement three original templates and trigger metadata.
- [x] Implement loopback-only HTTP server with fixed static routes and structured JSON.
- [x] Enforce content type, UTF-8, body, depth, duplicate-key, and field boundaries.
- [x] Add CSP and local-exposure headers; suppress payload logging.

## 3. Frontend

- [x] Build responsive original HookForge visual design with inline SVG only.
- [x] Implement all requested form controls and action switching.
- [x] Add live JSON, validation diagnostics, and export path preview.
- [x] Add copy and downloadable JSON export.
- [x] Add command risk panel.
- [x] Add safe simulator controls, verdict chain, and inert action request.
- [x] Add template loading and schema/boundary reference disclosure.
- [x] Prevent stale asynchronous validation responses.
- [x] Render submitted values as text, not HTML.

## 4. Deliverables

- [x] Add `run.py`, README, and MIT LICENSE.
- [x] Add `.kiro/specs/requirements.md`, `design.md`, and `tasks.md`.
- [x] Add `.kiro/steering/project.md`.
- [x] Add valid `.kiro/hooks/hookforge-safe-test-runner.json` using version v1 and hooks array.
- [x] Add fixed 24-case benchmark fixtures and reproducible report generator.

## 5. Verification

- [x] Add deterministic schema/action/trigger/regex tests.
- [x] Add destructive/network/privileged risk tests.
- [x] Add simulation match, mismatch, disabled, invalid, selector, and regex-safety tests.
- [x] Add export naming and invalid-export tests.
- [x] Add API routes, malformed input, limits, Host, header, and error tests.
- [x] Add marker-file and process-spy non-execution tests at core and HTTP levels.
- [x] Add benchmark expectation synchronization test.
- [x] Add real localhost subprocess smoke test.
- [x] Run full test suite and fixed benchmark.
- [x] Run Python and JavaScript syntax checks.
- [x] Run localhost server smoke test.

## 6. Separate future review

- [ ] Review exported hook in real Kiro IDE 1.x.
- [ ] Confirm installed tool IDs and runtime regex behavior.
- [ ] Decide whether to add import, multi-hook editing, confirmation fields, or persistence.
- [ ] Do not claim production readiness or official Kiro certification before review.

No registration, login, publication, push, rule acceptance, or real hook execution was performed.
