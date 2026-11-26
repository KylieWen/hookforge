# HookForge fixed validation benchmark

Snapshot: 26 November 2026. Engine: `hookforge_core.validate_document`.

This is a small, original, deterministic conformance benchmark for HookForge's documented MVP contract—not an official Kiro certification or a measurement of real IDE behavior.

| Metric | Result |
|---|---:|
| Fixed cases | 24 |
| Canonical trigger acceptance | 13/13 |
| Invalid-schema rejection | 11/11 |
| Total expectations met | 24/24 (100.0%) |

## Case results

| Case | Category | Expected | Actual errors | Result |
|---|---|---|---|---|
| `trigger-session-start` | trigger | valid | none | PASS |
| `trigger-user-prompt-submit` | trigger | valid | none | PASS |
| `trigger-stop` | trigger | valid | none | PASS |
| `trigger-pre-task-exec` | trigger | valid | none | PASS |
| `trigger-post-task-exec` | trigger | valid | none | PASS |
| `trigger-pre-tool-use` | trigger | valid | none | PASS |
| `trigger-post-tool-use` | trigger | valid | none | PASS |
| `trigger-permission-request` | trigger | valid | none | PASS |
| `trigger-post-file-create` | trigger | valid | none | PASS |
| `trigger-post-file-save` | trigger | valid | none | PASS |
| `trigger-post-file-delete` | trigger | valid | none | PASS |
| `trigger-pre-compaction` | trigger | valid | none | PASS |
| `trigger-post-compaction` | trigger | valid | none | PASS |
| `legacy-camelcase-trigger` | negative | reject: `trigger` | `trigger` | PASS |
| `wrong-version` | negative | reject: `version` | `version` | PASS |
| `missing-command` | negative | reject: `required` | `required` | PASS |
| `missing-agent-prompt` | negative | reject: `required` | `required` | PASS |
| `boolean-timeout` | negative | reject: `timeout_type` | `timeout_type` | PASS |
| `string-enabled` | negative | reject: `enabled_type` | `enabled_type` | PASS |
| `broken-regex` | negative | reject: `regex` | `regex` | PASS |
| `permission-agent-action` | negative | reject: `action_unsupported` | `action_unsupported` | PASS |
| `unknown-action-field` | negative | reject: `unknown_field` | `unknown_field` | PASS |
| `stop-with-matcher` | negative | reject: `matcher_unsupported` | `matcher_unsupported` | PASS |
| `empty-hooks` | negative | reject: `required` | `required` | PASS |

Reproduce with `python scripts/benchmark.py`. Cases are fixed in `benchmarks/validation-cases.json`.
