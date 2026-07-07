---
name: opencode-preflight-safety
description: Use when preparing, reviewing, or launching OpenCode GLM competition workers, opencode-preflight, run-worker, run-plan, run-batch-profile, OpenCode evidence claims, or competition archive inputs in this repository.
---

# OpenCode Preflight Safety

Use this skill to keep OpenCode worker launch fast without losing the evidence,
credential, and archive boundaries. A launch command is ready only when it is
safe, current, and compatible with the repo harness.

## Hard Gates

- Do not copy, print, write, commit, export, or archive chat-provided provider
  credentials. Treat a key pasted in chat as exposed and use local credential
  configuration or a secret manager instead.
- `opencode --help` and `opencode --version` prove only that the binary starts.
  They do not prove `GLM-5.1` availability.
- Before `run-worker --mode opencode`, `retry-worker --mode opencode`, or
  `run-plan --mode opencode`, require a passed `opencode-preflight` report from
  the same run and launch policy: `opencode`, `GLM-5.1`, `c2rust-migrator`,
  `max`, `status=passed`, `exit_code=0`, `marker_exists=true`, and
  `contract_verification.status=executed`.
- `.codex/skills/*`, superpowers docs, `.opencode/node_modules/*`, and
  `.opencode/package*.json` are not competition archive inputs. Archive
  manifests must bind the OpenCode runbook, not developer skills.
- Do not share mutable worker out-roots. Every worker needs a unique assigned
  root such as `target/competition-out/workers/<worker-id>`.
- Local-simulation or hostless rehearsal can test wiring, but it does not close
  competition-exact OpenCode/GLM acceptance without the real host attestation
  and model probe.

## Command Discipline

1. Read the current repo entrypoints before writing commands:
   `.opencode/agents/c2rust-migrator.md` and
   `python3 -B -m validation.tools.opencode_agent_harness <subcommand> --help`.
2. Use the repo harness, not ad hoc OpenCode shell commands.
3. Prefer this preflight shape:

```bash
python3 -B -m validation.tools.opencode_agent_harness opencode-preflight \
  --run-id <run-id> \
  --out-root target/opencode-preflight \
  --opencode-model GLM-5.1 \
  --opencode-agent c2rust-migrator \
  --opencode-variant max
```

4. Pass the produced `harness/opencode-preflight-report.json` into
   `run-worker`, `retry-worker`, or `run-plan` with
   `--opencode-preflight-report`. Keep `--run-id`, `--db`, worker assignment,
   launch flags, and proof class consistent with the current run.
5. Aggregate only machine-readable worker reports, summaries, and hash-bound
   artifacts. Worker prose and chat output are audit context, not semantic
   evidence.

Use `python3 -B` in judge-facing commands and docs. On Windows, a local operator
may run `python -B` if that is the available interpreter, but do not publish the
Windows fallback as the canonical reproduction command.

## Red Flags

- "Preflight later" before OpenCode worker fanout.
- Exporting or logging a key from chat.
- Reusing `workers/latest` for multiple workers.
- Adding `.codex/skills` to `bundle-manifest.json.external_refs`.
- Treating `opencode models` prose, copied summaries, or old preflight reports
  as proof for a new run.
- Inventing harness flags from memory, such as `--out` when the current
  subcommand expects `--out-root`.

## Common Mistakes

| Mistake | Correct action |
| --- | --- |
| Fast worker command from chat request | Stop until a current passed preflight is bound. |
| Chat key in `export` command | Use local credentials; never echo or persist chat secrets. |
| Help/version treated as GLM proof | Require the harness model probe in preflight. |
| Shared out-root for fanout | Allocate one assigned out-root per worker. |
| Skills copied into archive | Keep skills as developer guidance only. |
| Plausible but stale flags | Re-read subcommand `--help` before publishing commands. |
