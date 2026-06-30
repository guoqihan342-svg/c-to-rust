---
name: c2rust-migration
description: Repo-owned workflow for C-to-Rust migration harness work in this repository. Use when Codex works on FlashDB or other C-to-Rust slices, C2Rust baselines, oracle/replay/diff evidence, unsafe-reduction repair loops, workflow metrics artifacts, competition scoring checklists, typed-IR candidate diagnostics, migration evidence refreshes, or multi-agent worker handoffs.
---

# C2Rust Migration

Use this skill when working on C-to-Rust migration slices in this repository. The competition-facing priority is the harness / agent / workflow loop, not broad handwritten transpiler coverage.

## Mainline

1. Start from a real C unit or slice spec.
2. Produce or inspect the C2Rust/raw candidate baseline.
3. Compile the Rust candidate or record the compile failure as evidence.
4. Run C oracle / Rust replay / schema-aware diff when the slice supports it.
5. Record unsafe ledger, route decision, validation profile, and workflow metrics.
6. Only accept semantic progress when current evidence proves equivalence for the declared slice boundary.

Typed IR and generic emitter work is supporting infrastructure: use it for trivial fast paths, candidate diagnostics, and fail-closed feature gaps. Do not let typed-IR coverage expansion displace the verified harness loop.

## Competition Score Path

Use this order for judge-facing work:

1. Select a real C unit with a pinned source commit, slice spec, source span, compile flags, and input hashes.
2. Produce C2Rust baseline context or record a fail-closed skipped/blocked baseline with version, flags, environment, reason, and `output_ref=null`.
3. Compile the Rust candidate or record the rustc error stack as evidence.
4. Run C oracle, Rust replay, schema-aware diff, negative diff, and unsafe ledger before claiming semantic progress.
5. Run the agent safety loop only against a verified unsafe baseline; each patch must target one unsafe site or one compile blocker.
6. Emit repair patch events, workflow trace, final verification, and `workflow-metrics.json` bound by `competition-run-summary.json`.

Do not spend a development round on docs, schemas, refactors, or route metadata unless the change removes a harness blocker, improves repair/retry convergence, improves unsafe monotonicity evidence, advances a real slice state, adds a fail-closed classification, or removes a competition reproduction blocker.

## Repair Loop

- Default repair cap is 5 rounds.
- Each worker round proposes one minimal patch with one intended safety or compile effect.
- After each patch, rerun the narrow compile/test/oracle checks that cover the changed behavior.
- Accept a patch only when the candidate still passes the relevant oracle/diff gate and the unsafe delta or compile status improves.
- On failure, roll back to the last-good candidate, write a repair hint from the concrete error stack or diff, and continue until the cap is reached.
- Each failed or retried worker attempt must leave machine-readable audit evidence: attempt id, worker id, hint id, previous summary/final gate, selected last-good summary or candidate reference when available, rollback action/status, new summary/final gate, and artifact hashes.
- Attempt history and rollback evidence prove repair auditability only; they do not prove S2 convergence, accepted unsafe reduction, semantic acceptance, or OpenCode runtime compliance by themselves.
- Never repair by weakening fixtures, accepted-difference policy, public API boundaries, slice boundaries, unsafe budgets, or oracle expectations.

## Worker Handoff

- Give each worker one unit, one out-root, and one expected artifact set.
- Keep generated artifacts under repository-scoped or explicitly named output roots.
- Do not share mutable output directories between workers.
- Require each worker to report commands, artifact paths, status, and blocked reason.
- Merge worker output only after checking current files and evidence directly.
- For batch work, split independent units first, then run workers concurrently; do not parallelize edits to the same source, schema, or evidence file.
- Aggregate only machine-readable worker summaries and bound workflow metrics; treat worker prose as diagnostic context, not evidence.

## OpenCode Worker Out-Root Contract

- `assign-slice` must allocate a unique repo-relative `isolated_out_root` per worker in the run; prefer `target/competition-out/workers/<worker-id>`.
- Assignment requests must include `out_root`, and `run-worker` must reject the request before executing anything if `request.out_root` differs from the SQLite ledger's `agents.isolated_out_root`.
- `run-worker` must delete any stale expected summary before execution and then accept only the assigned `<isolated_out_root>/summary/competition-run-summary.json`.
- `record-worker-summary` must reject summaries outside that assigned expected summary path, even when the path stays inside the repository.
- If an OpenCode process exits 0 but does not write the expected summary, record `missing-summary` repair evidence; do not treat process success or chat text as acceptance.
- In `--mode opencode`, require `run-worker` to write a machine-readable handoff contract and OpenCode session evidence, and bind both from the worker report, event stream, repair hint, and artifact index.
- `retry-worker` must reuse the same worker, ledger assignment, out-root, and repair hint; the revalidation result comes only from the newly written final gate.
- `retry-worker` may count a retry as revalidated only from the newly written final gate; repair history, rollback ids, or an OpenCode process exit code are audit signals, not semantic acceptance.
- The SQLite ledger is scheduling, lease, recovery, and artifact index state. Semantic evidence still comes only from on-disk summaries, evidence, workflow metrics, and validators.

## Handoff Checklist

Before handing work back or starting another slice, leave these facts current:

- The exact branch, local commit, and remote commit when a push is expected.
- The focused validation commands that were run and their status.
- The artifact paths for route/profile/final verification, patch events, workflow trace, workflow metrics, and competition summary.
- The accepted boundary: generated candidate, verified unsafe baseline, accepted evidence authoritative, semantic pass, blocked, or refused.
- The next smallest harness step when the slice is not accepted.

## Commit Gate

- Run focused unit or contract tests that cover the changed module before committing.
- Run `git diff --check` before committing.
- Commit after validation when the change is ready; do not leave validated goal progress uncommitted.
- Push the active branch when the user goal includes remote delivery, then verify local `HEAD` and the remote branch point to the same commit.

## Evidence Rules

- Prefer existing repo scripts before adding new runtime code.
- Treat C2Rust output as candidate context and baseline material, not final semantic proof.
- Keep tool operations repository-confined: accept only POSIX relative paths, reject absolute paths, drive prefixes, backslashes, `~`, and `..` for repo MCP inputs.
- For docs, keep the Chinese source and English mirror synchronized in the same change.
- For coverage claims, update the relevant coverage matrix or workflow metrics artifact instead of relying on checklist percentages.
- For harness runs, require `competition-run-summary.json` to bind `workflow_metrics.path` and `sha256`; the referenced `workflow-metrics.json` must include units, convergence, fail-closed count, unsafe-reduction status, repair/auto-recovery placeholders or measurements, wall clock, LLM calls, and per-unit status.
- Mark `unsafe_reduction.status=measured` only when every bound worker workflow metrics artifact provides measured baseline/current unsafe counts and their `units_total` covers the parent attempted units. Aggregate baseline/current counts, compute `reduced_by`, and use `ratio=current_total_unsafe / baseline_total_unsafe`; otherwise keep `unsafe_reduction.status=not_measured`.
- For competition environment work, make tool assumptions explicit; do not silently depend on locally installed Windows tools.
- Do not claim full verifier/runtime completion unless the current validation profile, oracle/replay/diff evidence, unsafe ledger, and final gates prove it.

## Common Commands

Run focused doc mirror validation after roadmap edits:

```bash
python -B -m unittest validation.tools.test_doc_mirror_contract
```

Run the MCP scaffold contract tests after editing the thin verifier MCP:

```bash
python -B -m unittest validation.tools.test_c2rust_verifier_mcp
```

Run the translator coverage matrix after changing typed-IR or route evidence:

```bash
python -B validation/tools/translator_coverage_matrix.py --matrix validation/translator-coverage-matrix.json
```

Run focused competition runner contract tests after editing `run_competition.py`, its summary schema, validator, or workflow metrics:

```bash
python -B -m unittest validation.tools.test_run_competition validation.tools.test_validate_competition_run_summary
```

Run focused OpenCode harness contract tests after editing `opencode_agent_harness.py` or its worker assignment/run/summary ledger behavior:

```bash
python -B -m unittest validation.tools.test_opencode_agent_harness
```

## Thin MCP / Stdio Server

The repo-local scaffold is `validation/tools/c2rust_verifier_mcp.py`.
It registers:

- `translate_slice`: plans the existing migration command for a slice.
- `run_oracle`: plans the existing verifier/oracle command path.
- `read_evidence`: reads existing JSON evidence inside the repository.
- `coverage_matrix`: delegates to the existing translator coverage matrix report.

It also exposes a minimal MCP-style stdio JSON-RPC server:

```bash
python -B validation/tools/c2rust_verifier_mcp.py --stdio
```

The server supports `initialize`, `tools/list`, `tools/call`, and `notifications/initialized`. Tool calls still only plan existing commands or read evidence; they do not execute semantic verification or turn any candidate into accepted evidence.

Run the focused contract tests with:

```bash
python -B -m unittest validation.tools.test_c2rust_verifier_mcp
```
