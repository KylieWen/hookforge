# HookForge Kiro Review

## Review record

- Date: 2026-11-26
- Reviewer: Kiro IDE 1.4.236, live authenticated Google session
- Workspace: `hookforge`
- Scope: `hookforge_core.py`, `server.py`, `frontend/app.js`
- Mode: read-only review; Kiro did not modify project files
- Prompt: "Review hookforge_core.py, server.py, and frontend/app.js for security and correctness. Do not modify files. Run the test suite and summarize concrete issues with file and line references."

Kiro attempted `pytest`, which is not installed, and then attempted the standard-library runner. Its shell output did not return reliably inside the IDE. Qoder independently ran `python -m unittest discover -s tests -v`: 86 tests passed in 2.151 seconds before the review fixes. Kiro was given that verified result and asked to stop retrying test commands and finish the static review.

## Findings and disposition

Kiro's original line references were approximate. The locations below are verified against the reviewed source.

| # | Kiro finding | Disposition |
|---|---|---|
| 1 | `_unsafe_regex_reason` could miss catastrophic regex constructs and permit simulation DoS. | **Accepted and fixed.** The simulator now allows only a non-repeating regex subset. All unescaped repetition operators, numeric/named backreferences, and conditional patterns are blocked from simulation but remain valid for export. Tool wildcards continue through `fnmatch`. |
| 2 | `_host_allowed` could be bypassed through DNS resolution. | **Rejected as a false positive.** The code performs no DNS resolution. It compares the parsed hostname exactly against `127.0.0.1`, `localhost`, or `::1`, rejects userinfo, and requires the actual server port. |
| 3 | Recursive JSON depth checking could overflow the stack. | **Rejected as a false positive.** `json.loads` recursion is caught, and `_check_depth` stops at depth 8 before recursion can grow with attacker-controlled nesting. The deep-nesting regression test passes. |
| 4 | Hardcoded tool categories may not enumerate every installed Kiro tool ID. | **Accepted as a documented boundary.** Categories are illustrative conveniences, not a security boundary. Exact IDs, wildcards, source selectors, and safe regex matching remain available. README already disclosed this limitation. |
| 5 | Windows device-name handling could miss lowercase variants. | **Rejected as a false positive.** `slug.upper()` is a case-insensitive comparison, the `.json` suffix is removed before checking, and reserved names are prefixed with `hookforge-`. Tests cover `CON`, `nul`, `COM1`, and `lpt9.json`. |
| 6 | `Content-Length` parsing could admit negative or huge values. | **Partly accepted and hardened.** Negative and oversized values were already rejected. The handler now also requires exactly one ASCII-digit-only `Content-Length` header, rejecting duplicates, signs, whitespace-only values, and ambiguous framing. |
| 7 | MCP tool matching assumes `mcp_{server}_{tool}` naming. | **Accepted as a documented approximation.** This mirrors the supported Kiro MCP tool-ID convention but is not a runtime compatibility certificate. Source selectors and exact IDs remain available. |
| 8 | `showToast` could create XSS through user-controlled content. | **Rejected as a false positive.** The value is assigned with `textContent`, never `innerHTML`; the server also sends a restrictive CSP and `X-Content-Type-Options: nosniff`. |
| 9 | `fieldPath` returning `null` could bypass validation. | **Rejected as a false positive.** Unmapped diagnostic paths are still rendered as validation errors. Returning `null` only avoids marking an unrelated form field invalid; it does not bypass server validation or enable export. |
| 10 | Generic exception responses without logging hinder debugging. | **Accepted as an intentional privacy tradeoff.** The local tool deliberately avoids logging submitted commands, prompts, paths, or payloads. Responses expose only a generic error code and message. |

## Changes made after review

- Replaced heuristic regex risk detection with a conservative non-repeating simulation subset in `hookforge_core.py:89`.
- Preserved safe tool wildcard matching before regex safety checks in `hookforge_core.py:346`.
- Required one canonical `Content-Length` header in `server.py:189`.
- Added bounded chunked-body draining for rejected requests in `server.py:141`, preventing malformed rejected bodies from holding a handler thread indefinitely.
- Added regression tests for repetition variants, safe regex features, tool wildcards, duplicate `Content-Length`, signed `Content-Length`, and malformed chunked requests.
- Updated README security and review-status notes.

## Verification after fixes

- `python -m unittest discover -s tests -v`: **94/94 passed** after review fixes, static-demo synchronization tests, and Pages-safe asset URL tests.
- `python scripts/benchmark.py`: **47/47 expectations met** (13/13 canonical triggers, 18/18 valid documents, 29/29 invalid-schema rejections).
- `python scripts/smoke_test.py`: **10/10 checks passed** against the real local server.
- `node --check frontend/app.js`: passed.
- Browser verification against `http://127.0.0.1:8767/`:
  - Dangerous matcher `(a+)+$` remained exportable but simulation stopped safely with "Regex repetition is not applied in the safe simulator."
  - Tool wildcard `mcp_*_query` matched synthetic tool `mcp_db_query`.
  - Simulation displayed the requested command with `EXECUTED: FALSE` and did not execute it.
- Browser verification against the backend-free `http://127.0.0.1:8768/?demo=1`:
  - All three bundled templates loaded with current validation and risk data.
  - PostFileSave, PreToolUse, and Stop simulations matched backend-generated results.
  - Unsupported edits are labeled as a static-demo limit rather than a server failure.
  - Re-importing a bundled export succeeded in both local and static demo modes; invalid hooks were rejected without replacing the current form.

## Post-review Windows hardening

Independent clean-ZIP testing later exposed intermittent `ConnectionAbortedError` responses when rejecting signed, conflicting, or oversized `Content-Length` headers on Windows. The handler now drains a bounded amount of already-sent request data before replying, and a conflicting-header regression was added. This work was performed and verified independently after Kiro's review; it is not attributed to Kiro.

- `python -m unittest discover -s tests -v`: **95/95 passed**.
- Oversized-body rejection: **50/50 consecutive runs passed**.
- Signed and conflicting header rejection: **30/30 consecutive runs passed each**.
- Final clean ZIP: **10/10 consecutive full-suite runs passed**.
- `python scripts/benchmark.py`: **47/47 expectations met**.

## Kiro conclusion excerpt

Kiro's final response stated that the codebase showed "strong security awareness with proper input validation, security headers, and a clear separation between analysis and execution" and that the core "never executes hooks" principle was maintained. Its main actionable finding was the regex-simulation concern, which was addressed and regression-tested as described above.
