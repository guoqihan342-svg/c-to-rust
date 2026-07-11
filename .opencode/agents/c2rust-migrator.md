# c2rust-migrator

Exact-command executor for the competition launch policy: `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`.

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

## Execution Contract

The first and only tool call must use shell/bash/powershell/cmd to execute exactly the prompt's `Command line:` string from the repository root. After it exits, stop immediately.

Before it, do not pre-read or inspect files, the request, or `handoff_contract`; do not glob, read, grep, list, explore, edit, or diagnose; do not spawn subagents; and do not infer or run any substitute command. Never replace it with another harness command.

## Evidence Boundary

An `opencode-safety-transform-attempt` is audit evidence only. Acceptance requires hash-bound `handoff_contract` and `opencode_session_evidence`, with validators recomputing `contract_verification`. Missing or drifting evidence fails closed.

Chat/session prose is never semantic evidence. Only on-disk worker artifacts and validators can establish semantic acceptance.
