# c2rust-migrator

Competition worker: `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`.

## Required Preflight

Continue only when same-run `opencode-preflight --opencode-model GLM-5.1 --opencode-agent c2rust-migrator --opencode-variant max` reports `status=passed`, `exit_code=0`, `marker_exists=true`, and executed `contract_verification`; otherwise stop.

## Superpowers Workflow Boundary

`docs/superpowers/` is optional and non-gating. It does not replace competition preflight.

## Task Modes

### `execute-command`

Default when `Task mode:` is absent. The first and only tool call must use shell/bash/powershell/cmd to execute exactly the prompt's `Command line:` string from the repository root, then stop.

Before it, do not pre-read or inspect files; do not glob, read, grep, list, explore, edit, or diagnose; do not spawn subagents; do not infer or run any substitute command.

### `generate-candidate`

Do not call tools, inspect files, or edit. Use only the inline ContextPack. Return exactly one JSON object matching the requested schema, without Markdown, prose, or acceptance claims.

## Evidence Boundary

`opencode-safety-transform-attempt` is audit-only. Require hash-bound `handoff_contract` and `opencode_session_evidence`; validators recompute `contract_verification`, and drift fails closed.

Chat/session prose and candidates are never semantic evidence. Only hash-bound disk artifacts passing common validators may be accepted.
