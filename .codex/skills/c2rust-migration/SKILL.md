---
name: c2rust-migration
description: Repo-owned workflow for C-to-Rust migration harness work in this repository. Use when Codex works on FlashDB or other C-to-Rust slices, C2Rust baselines, oracle/replay/diff evidence, unsafe-reduction repair loops, workflow metrics artifacts, competition scoring checklists, typed-IR candidate diagnostics, migration evidence refreshes, or multi-agent worker handoffs.
---

# C2Rust Migration

Use this skill when working on C-to-Rust migration slices in this repository. The competition-facing priorities are core translation capability and harness architecture. Core translation capability is demonstrated by a real before/after: C2Rust or another candidate baseline, verified unsafe baseline, accepted safety-refactoring patch, oracle-equivalence evidence, and measured unsafe reduction. Harness architecture is demonstrated by the automated planner/worker/verifier/repairer/reporter loop that proves, repairs, rolls back, measures, and reproduces that before/after.

## Mainline

1. Start from a real C unit or slice spec.
2. Produce or inspect the C2Rust/raw candidate baseline.
3. Compile the Rust candidate or record the compile failure as evidence.
4. Promote the candidate to a verified unsafe baseline only through C oracle / Rust replay / schema-aware diff evidence.
5. Run the safety-refactoring loop against that baseline: one minimal patch per round, oracle/diff/unsafe gates after each patch, rollback on failure, and repair hints from the concrete stack or diff.
6. Record unsafe ledger, route decision, validation profile, workflow trace, before/after artifacts, and workflow metrics.
7. Only accept semantic progress when current evidence proves equivalence for the declared slice boundary and the accepted patch strictly improves unsafe count or compile status.

Typed IR and generic emitter work is supporting infrastructure: use it for trivial fast paths, candidate diagnostics, and fail-closed feature gaps. Do not let typed-IR coverage expansion displace the verified harness loop.

## Competition Score Path

Use this order for judge-facing work:

1. Select one real C unit that can converge quickly and is judge-readable. Default to the FlashDB competition-pinned `fdb_calc_crc32`; switch to zlib-ng `adler32` if C2Rust/toolchain setup blocks the D1-D2 safety-loop risk check.
2. Produce C2Rust baseline context or record a fail-closed skipped/blocked baseline with version, flags, environment, reason, and `output_ref=null`.
3. Compile the Rust candidate or record the rustc error stack as evidence.
4. Run C oracle, Rust replay, schema-aware diff, negative diff, and unsafe ledger before claiming semantic progress.
5. Run the agent safety loop only against a verified unsafe baseline; each patch must target one unsafe site or one compile blocker.
6. Accept at least one patch only when oracle/diff remains green and unsafe strictly decreases, then emit the original unsafe Rust, final Rust, accepted patch, step log, repair history, rollback evidence, final verification, and `workflow-metrics.json` bound by `competition-run-summary.json`.
7. Package the same artifact as a harness architecture exhibit: planner, worker, verifier, repairer, reporter contracts plus a one-command reproduction path.

Do not spend a development round on docs, schemas, refactors, or route metadata unless the change removes a before/after harness blocker, improves repair/retry convergence, improves unsafe monotonicity evidence, advances a real slice state, adds a fail-closed classification, or removes a competition reproduction blocker.

## Competition Reproduction Gates

- Use `python3 -B` for judge-facing Linux/CI commands. Do not publish legacy bare Python commands in quickstarts, replay commands, profiles, or CI gates.
- Before treating a competition config or judge-chain change as release-ready, run both LF-stable hash gates:

```bash
python3 -B -m validation.tools.resync_sha_bindings --scan-root config/competition-env --dry-run --check
python3 -B -m validation.tools.resync_sha_bindings --scope judge-chain --dry-run --check
```

- For P0-H8 hash portability work, validate a fresh LF checkout before claiming the judge entrypoint is portable:

```bash
git clone -c core.autocrlf=false --no-local . target/repro-clone-lf-<stamp>
cd target/repro-clone-lf-<stamp>
python3 -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json
python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --dry-run --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
```

- Run `--require-local-artifacts` only after the entrypoints have generated their expected artifacts in that checkout. A fresh clone does not contain `target/` artifacts by default.
- Keep OpenCode profile claims exact: command `opencode`, model `GLM-5.1`, bounded `auto_retry=true`, 5 repair rounds, repo-local runtime dirs, and a passed `opencode-preflight` before worker launch. Treat any non-OpenCode command, non-GLM 5.1 model, missing/failed preflight, or missing marker as a launch blocker.
- `opencode-preflight` must prove model availability before launch with the same repo-local runtime env. If `opencode models` does not expose `GLM-5.1`, the report must fail closed with `root_cause_key=opencode_model_unavailable`, `opencode_model_availability.status=unavailable` or `probe_failed`, `opencode_run_launched=false`, and no marker. A local-simulation OpenCode pass does not close P0-H9 unless it is rerun on the competition GLM/OpenCode host or an equivalent provider configuration.
- Treat `git ls-files --eol` and `.gitattributes` drift as competition-entry blockers when text artifacts carry hash bindings.

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
- Before using `run-worker --mode opencode`, `retry-worker --mode opencode`, or `run-plan --mode opencode`, run `opencode-preflight` and pass the resulting `harness/opencode-preflight-report.json` through `--opencode-preflight-report`. The report must be `status=passed`, `exit_code=0`, `marker_exists=true`, and `contract_verification.status=executed`.
- Treat a missing or failed OpenCode preflight report as a launch blocker, not as a worker failure or semantic result. Do not start OpenCode workers without a passed preflight report bound into the worker report/event/artifact index.
- `retry-worker` must reuse the same worker, ledger assignment, out-root, and repair hint; the revalidation result comes only from the newly written final gate.
- `retry-worker` may count a retry as revalidated only from the newly written final gate; repair history, rollback ids, or an OpenCode process exit code are audit signals, not semantic acceptance.
- When a revalidated retry has a bound worker `workflow-metrics.json`, annotate repair history, retry rounds, and auto recovery only after verifying the existing metrics hash, then refresh the summary hash; never turn unmeasured unsafe data into measured unsafe reduction.
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
- For planned batch profiles, set `emit_route_governance_metrics_report=true` when the run is intended to support public claims or milestone evidence; `run-batch-profile` must bind the resulting `summary/route-governance-metrics-report.json` by path and sha256. Treat this report as claim-boundary/capability-refusal metrics, not as semantic acceptance.
- When reporting S2 repair/unsafe progress, pass hash-bound `competition-run-summary.json` files via `--competition-summary`; report tools must verify the bound `workflow-metrics.json` path and sha256 before summarizing repair rounds, auto recovery, unsafe reduction, root causes, wall clock, or LLM calls.
- For harness runs, require `competition-run-summary.json` to bind `workflow_metrics.path` and `sha256`; the referenced `workflow-metrics.json` must include units, convergence, fail-closed count, unsafe-reduction status, repair/auto-recovery placeholders or measurements, wall clock, LLM calls, and per-unit status.
- Mark `unsafe_reduction.status=measured` only when every bound worker workflow metrics artifact provides measured baseline/current unsafe counts and their `units_total` covers the parent attempted units. Aggregate baseline/current counts, compute `reduced_by`, and use `ratio=current_total_unsafe / baseline_total_unsafe`; otherwise keep `unsafe_reduction.status=not_measured`.
- Mark `translation_before_after.status=bound` only when per-unit metrics bind real original/final Rust artifacts, accepted patch or patch log, oracle evidence, and measured unsafe before/after with matching repo-relative paths and sha256 hashes. If the run only reuses accepted evidence, route-refused artifacts, or current unsafe scans, keep `translation_before_after.status=not_provided`.
- For competition environment work, make tool assumptions explicit; do not silently depend on locally installed Windows tools.
- Do not claim full verifier/runtime completion unless the current validation profile, oracle/replay/diff evidence, unsafe ledger, and final gates prove it.

## Common Commands

Run focused doc mirror validation after roadmap edits:

```bash
python3 -B -m unittest validation.tools.test_doc_mirror_contract
```

Run the MCP scaffold contract tests after editing the thin verifier MCP:

```bash
python3 -B -m unittest validation.tools.test_c2rust_verifier_mcp
```

Run the translator coverage matrix after changing typed-IR or route evidence:

```bash
python3 -B validation/tools/translator_coverage_matrix.py --matrix validation/translator-coverage-matrix.json
```

Run focused competition runner contract tests after editing `run_competition.py`, its summary schema, validator, or workflow metrics:

```bash
python3 -B -m unittest validation.tools.test_run_competition validation.tools.test_validate_competition_run_summary
```

Run focused OpenCode harness contract tests after editing `opencode_agent_harness.py` or its worker assignment/run/summary ledger behavior:

```bash
python3 -B -m unittest validation.tools.test_opencode_agent_harness
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
python3 -B validation/tools/c2rust_verifier_mcp.py --stdio
```

The server supports `initialize`, `tools/list`, `tools/call`, and `notifications/initialized`. Tool calls still only plan existing commands or read evidence; they do not execute semantic verification or turn any candidate into accepted evidence.

Run the focused contract tests with:

```bash
python3 -B -m unittest validation.tools.test_c2rust_verifier_mcp
```
