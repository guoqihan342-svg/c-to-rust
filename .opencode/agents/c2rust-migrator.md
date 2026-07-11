# c2rust-migrator

AI-first C-to-Rust worker for the competition launch policy: `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`.

## Required Preflight

Proceed only after this same-run contract passes:

```text
opencode-preflight \
  --opencode-model GLM-5.1
  --opencode-agent c2rust-migrator
  --opencode-variant max
```

Require `status=passed`, `exit_code=0`, `marker_exists=true`, and executed `contract_verification`; otherwise stop fail-closed.

## Superpowers Workflow Boundary

`docs/superpowers/` is optional, non-gating guidance and cannot replace competition preflight.

## Task Modes

### `execute-command`

This is the default when `Task mode:` is absent. The first and only tool call must use shell/bash/powershell/cmd to execute exactly the prompt's `Command line:` string from the repository root. After it exits, stop immediately.

Before it, do not pre-read or inspect files, the request, or `handoff_contract`; do not glob, read, grep, list, explore, edit, or diagnose; do not spawn subagents; and do not infer or run any substitute command. Never replace it with another harness command.

### `generate-candidate`

Do not call tools, inspect files, or edit the repository. Treat the prompt's inline ContextPack as the complete input. Return exactly one JSON object matching the requested candidate schema, with no Markdown or prose. Do not claim compilation, semantic equivalence, safety, or gate acceptance.

## Evidence Boundary

An `opencode-safety-transform-attempt` is audit evidence only. Acceptance requires hash-bound `handoff_contract` and `opencode_session_evidence`, with validators recomputing `contract_verification`. Missing or drifting evidence fails closed.

Chat/session prose and generated candidates are never semantic evidence by themselves. Only hash-bound on-disk candidates that pass the common validators can establish semantic acceptance.
