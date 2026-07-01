# Harness Stability Hardening Implementation Plan

Chinese original: `2026-07-02-harness-stability-hardening.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Independent analysis and red-test drafting may run in parallel, but edits to `validation/tools/opencode_agent_harness.py` and `validation/tools/test_opencode_agent_harness.py` must be merged through one owner or isolated worktrees.

**Goal:** Move the OpenCode multi-agent harness from "functionally runnable" to "judge-run controllable": external processes cannot hang indefinitely, evidence cannot be half-written and accepted, commands cannot fail because of Python or shell drift, and failures are indexed precisely in the repair/block ledger.

**Architecture:** Keep the existing planner -> worker -> verifier -> repairer -> reporter loop. Do not introduce a new framework layer. H7 only adds stability contracts: timeout envelope, portable command contract, atomic artifact writer, retry/lock/fencing guardrails, and a translator smoke gate. The SWE-bench/LangGraph-style value is recoverable DAG discipline plus worker contracts, not a harness rewrite at this stage.

**Tech Stack:** Python stdlib `subprocess`/`tempfile`/`os.replace`/`sqlite3`/`shlex`, existing unittest suite, Cargo translator tests, repo-local validator commands.

---

## External Review Assessment

- `opencode-agent-harness-逐行稳定性审查.md` is directionally correct. Missing timeouts, non-atomic writes, inconsistent command environments, and the missing defensive outer retry cap are P0.
- `fencing_token` and `assign_slice` transactions are future parallel-planner risks. Pick one path now: document the token as audit-only, or enforce it in assignment/worker consumers.
- Stale summary cleanup is H7/P0: if an old summary cannot be removed, the harness must fail closed instead of launching a worker or accepting old evidence. A top-level JSON error envelope is P1 hardening and must not displace the first four P0 items.
- The showcase-boundary warnings in `c-to-rust-flashdb-rust-skeleton-评估报告.md` are valid: handwritten `flashDB_rust` is not automatic translation output, and every before/after exhibit must bind the real source pin, baseline/final/oracle source, and proof class.

## Review Finding to H7 Backlog Mapping

| External review item | Assessment | Current treatment | Priority |
|---|---|---|---|
| Subprocesses have no timeout | Valid; a judge-visible hang is the highest-risk failure mode | Covered by Task 1, normalizing timeouts to `124` / `timed_out=true` | H7/P0 |
| Bare `"python"` conflicts with the competition profile's `python3` | Valid; avoid interpreter drift and local absolute interpreter leakage | Covered by Task 2, using the `python3 -B` portable contract for public commands and worker argv | H7/P0 |
| Critical evidence writes are non-atomic | Valid; partial JSON can break resume and validator flows | Covered by Task 3, using same-directory temp files plus `os.replace` for critical artifacts | H7/P0 |
| `auto_retry` lacks an independent outer cap | Valid; the inner five-round cap needs a second guardrail | Covered by Task 4, using `REPAIR_ROUND_CAP + 2` and recording the decision in graph/report artifacts | H7/P0 |
| OpenCode SQLite lock detection is too narrow | Valid; third-party CLI stderr is unstable | Covered by Task 4 with broader equivalent lock-signal classification | H7/P0 |
| `fencing_token` semantics are unclear | Valid; the field must not be mistaken for enforced concurrency fencing | Covered by Task 4; current contract defines it as an audit-only monotonic counter | H7/P0 |
| `assign_slice` check-then-write window | Valid but mostly a future parallel-planner risk | Covered by Task 4 with `BEGIN IMMEDIATE` assignment transactions | H7/P0 |
| `subprocess.list2cmdline` mixed with a POSIX shell contract | Valid; Linux/OpenCode prompts should use POSIX semantics | Covered by Task 5 through `shlex.join` plus POSIX parser alignment | H7/P0 |
| Stale summary deletion failure is unhandled | Valid; Windows, antivirus, or concurrent handles can trigger it | Covered by Task 5.3a: fail closed, do not launch the worker, and do not accept the stale summary | H7/P0 |
| Deterministic worker has no transient retry | Reasonable finding, but it should not displace the H7 mainline; deterministic workers remain fail-fast until idempotency and side-effect contracts are explicit | Deferred; a future short retry window must first define idempotent input, out-root cleanup, and summary overwrite contracts | P1/Deferred |
| Top-level JSON error envelope | Valuable, but not a blocker for the completed stability contract | Deferred to Task 5.3b; needs a separate design to avoid swallowing traceback or breaking exit codes | P1 |
| Real subprocess timeout integration tests | Valuable because they cover OS behavior that mocks miss | Completed with a real `subprocess.run` sleep timeout test proving a 1-second timeout is normalized to `124` at the OS boundary | Done/Post-H7 |

## Parallel Work Split

- Agent A: timeout envelope red tests and implementation.
- Agent B: atomic write helper red tests and critical artifact replacement.
- Agent C: Python command portability, OpenCode prompt command line, and contract parser consistency.
- Agent D: retry cap, OpenCode lock classification, fencing/lease/transaction contract.
- Agent E: minimal fixes for the three translator smoke failures.

All agents should hand back small patches or worktree diffs. One main integrator merges serially and runs full verification.

## 2026-07-02 Implementation Progress

- Done: Task 1 timeout envelope; Task 2 Python command portability split with the shared `python3 -B` portable strategy; Task 3 atomic critical evidence writes; Task 4 retry/lock/lease/fencing guardrails; Task 5 Steps 1-2 POSIX shell contract; Task 6 translator smoke fixes.
- Verified: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`, `python -B -m unittest validation.tools.test_doc_mirror_contract -q`, `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report`, `python -B -m validation.tools.validate_auto_translation_evidence --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --evidence-root validation/evidence --require-semantic-pass`, `python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json`, and `python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id competition_environment_smoke --out target/h7-judge-smoke/summary/judge-entrypoints-run-report.json`.
- Current patch: Task 5 Step 3a stale summary cleanup fail-closed has focused test coverage; focused `--entrypoint-id` runner post-run local-artifact validation now writes `selected-entrypoints-validation-config.json` and deep-validates only the entrypoints executed in that run, so smoke/triage runs are not failed by stale artifacts from unexecuted `target/` outputs.
- Latest patch: Task 1 now includes a real subprocess timeout integration test. It calls `subprocess.run` with a `time.sleep(5)` child process and proves that `timeout_seconds=1` returns around the one-second boundary with exit code `124` and stable timeout stderr; this closes the verification gap where only mocked `TimeoutExpired` behavior was covered. `validate_judge_entrypoints --require-local-artifacts` also binds the smoke-summary step set to `commands.jsonl`, so a command log missing any summary step fails closed instead of masquerading as a complete smoke evidence chain.
- H7/P0 status: closed. The `competition_environment_smoke` entrypoint runs through the runner and post-run deep validation under local `local-simulation`; environment checks still record local proof-class degradation and do not claim `competition-exact`.
- Deferred: the top-level JSON error envelope and deterministic-worker short retry policy remain P1 and do not block H7.

## Current Checklist

- Second-review recheck: `C:\Users\Administrator\Downloads\opencode-agent-harness-逐行稳定性审查.md` is directionally correct, but the current code has absorbed its H7/P0 stability items. Treat that report as a closed risk checklist and regression-test source, not as a reason to reopen the same P0 work.
- H7/P0 implemented: timeout, portable command, atomic write, retry cap, OpenCode lock classification, fencing audit contract, assignment transaction, POSIX shell contract, and translator smoke fix are implemented in code and tests.
- Stale summary cleanup included in H7/P0: old-summary removal failures now fail closed, do not launch the worker, do not record the old summary, and open a `stale_summary_cleanup_failed` repair hint.
- Judge smoke refreshed: the focused `competition_environment_smoke` runner passed, and post-run validation uses the generated selected-entrypoint config; local proof class remains `local-simulation`.
- Post-H7 verification strengthened: the real `subprocess.run` sleep timeout integration test passed, covering OS timeout behavior that mocks do not cover.
- Command-log drift guard strengthened: local-artifact deep validation now requires `commands.jsonl` to cover every smoke-summary step.
- P1 deferred: top-level JSON error envelope, deterministic-worker short retry policy, and consistency cleanup for bare `python` commands in docs/examples.

## Post-H7 Execution Plan

1. Full public packet first: run non-focused `run_judge_entrypoints`, generate and validate `judge-milestone-bundle.json`, `milestone-release-notes.md`, `public-release-packet.json`, and the competition config archive. If deep validation fails, refresh the affected entrypoint's `target/` artifact first; do not weaken the current config/profile hashes to match stale output.
2. S1 C2Rust baseline next: make one real slice produce C2Rust Rust output, output sha256, and compile-only status while staying `candidate_context_only`; blocked or skipped states are failure evidence and repair input only.
3. S1 verifier: connect the compile-only baseline to the C oracle, Rust replay, diff, negative diff, and unsafe ledger. Only a passing run may be called a `verified-unsafe-baseline`.
4. S2 safety loop: wire OpenCode/LLM patches on the same unit, accepting only one minimal unsafe-reduction diff per round. Failed rounds roll back, repair hints are capped at five rounds, and acceptance requires green compile/diff/oracle gates plus strictly lower unsafe count.
5. Proof-class closeout: until evidence is refreshed on the real competition or equivalent Linux environment, local artifacts remain `local-simulation`; if an external release still lacks `competition-exact` or `ci-approximation` evidence, the public packet must list that gap as a release blocker.
6. P1 hardening timebox: the top-level JSON error envelope, deterministic-worker short retry policy, doc-command consistency cleanup, and historical marking for old plan checklists run only when P0-A through P0-D are not displaced.

---

### Task 1: External Process Timeout Envelope

**Files:**
- Modify: `validation/tools/opencode_agent_harness.py`
- Modify: `validation/tools/test_opencode_agent_harness.py`

- [x] **Step 1: Write failing tests**

Add tests where a fake `command_runner` raises `subprocess.TimeoutExpired`. Cover at least `run_worker_process_once`, OpenCode worker execution, preflight marker execution, and merge/evaluate subprocess execution. Assert every call receives a finite `timeout` kwarg, the normalized result uses `returncode == 124`, stdout/stderr preserve timeout tails, and summaries/reports carry `timed_out=true` plus `timeout_seconds`.

- [x] **Step 2: Implement minimal timeout plumbing**

Add a configurable timeout field, for example `--worker-timeout-seconds`, propagated through `run-plan`, `run-worker`, `retry-worker`, `evaluate --profile`, and batch profile loading. Default must be finite and competition-safe. Follow `validation/tools/run_competition_smoke.py`: timeout is a final-gate failure, not a silent retry success.

- [x] **Step 3: Normalize timeout evidence**

Catch `subprocess.TimeoutExpired` beside `OSError`, return a `CompletedProcess` with exit code `124`, and write blocked/repair summaries with `root_cause_key=process_timeout` or an equivalent stable key. Ensure auto-retry can retry a timeout while still respecting the five-round cap and final blocked status.

- [x] **Step 3a: Add real subprocess timeout integration test**

Add one focused test that uses the real `subprocess.run` command runner with the current Python interpreter and a `time.sleep(5)` child process. With `timeout_seconds=1`, the harness must return within a bounded wall-clock window, report `returncode == 124`, and include `timed out after 1 seconds` in stderr.

- [x] **Step 4: Verify**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK, with tests proving timeout kwargs, timeout evidence, and real subprocess timeout behavior.

### Task 2: Python Command Portability Split

**Files:**
- Modify: `validation/tools/opencode_agent_harness.py`
- Modify: `validation/tools/test_opencode_agent_harness.py`
- Review: `config/competition-env/toolchain-check.sh`

- [x] **Step 1: Write failing tests**

Add tests that reject hard-coded runtime `["python", ...]` for harness-owned subprocesses, while keeping public reproduction/prompt commands portable and free of local absolute `sys.executable` paths. Tests should cover worker command construction, retry command construction, preflight marker command construction, and merge plan argv.

- [x] **Step 2: Implement command helpers**

Use the competition-profile portable command string `python3 -B ...` for harness subprocess argv, public evidence, OpenCode prompts, and reproduction commands, because `toolchain-check.sh` verifies `python3` in the competition profile. Do not leak `C:\...python.exe` or `/home/.../python` into judge-facing artifact command fields.

- [x] **Step 3: Update assertions**

Update existing tests currently expecting literal `"python"` to assert the portable command contract: harness subprocess argv, prompt command lines, retry commands, and merge plans use `python3 -B`, and evidence validators still reject local absolute interpreter paths.

- [x] **Step 4: Verify**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK.

### Task 3: Atomic Critical Evidence Writes

**Files:**
- Modify: `validation/tools/opencode_agent_harness.py`
- Modify: `validation/tools/test_opencode_agent_harness.py`

- [x] **Step 1: Write failing tests**

Add a testable writer hook or monkeypatch so a write fails after creating a temporary file. Assert the final artifact path is either the old complete file or absent, never a partial JSON/log that validators can read as current evidence.

- [x] **Step 2: Add writer helpers**

Add `atomic_write_text(path, text, encoding="utf-8")` and `atomic_write_json(path, payload)`. Use same-directory temp files, flush/close them, then `os.replace(temp_path, path)`. Clean temp files best-effort on failure.

- [x] **Step 3: Replace critical writes first**

Prioritize `context-pack.json`, `agent-index.json`, `resume-manifest.json`, `competition-run-summary.json`, repair hint payloads, worker stdout/stderr logs, merge/evaluate reports, OpenCode session evidence, and contract files. Non-critical diagnostic writes can remain direct until later, but new critical paths must use helpers.

- [x] **Step 4: Verify**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK, and `rg -n "\.write_text\(" validation/tools/opencode_agent_harness.py` shows only documented non-critical direct writes or none.

### Task 4: Retry, Lock, Lease, and Fencing Guardrails

**Files:**
- Modify: `validation/tools/opencode_agent_harness.py`
- Modify: `validation/tools/test_opencode_agent_harness.py`

- [x] **Step 1: Write retry cap tests**

Add a test proving `run_plan(auto_retry=True)` cannot loop forever even if `retry_worker` never returns a success or internally regresses. Expected behavior: it exits after a defensive outer cap derived from `REPAIR_ROUND_CAP`, writes blocked state, and records attempt count.

- [x] **Step 2: Expand OpenCode lock classification**

Extend `opencode_database_locked` to match lowercased equivalents such as `database table is locked`, `sqlite_busy`, `sqlite busy`, and `SQLITE_BUSY`. Add tests for each signal and for unrelated stderr not matching.

- [x] **Step 3: Clarify fencing token**

Choose one path:

Audit-only: document `fencing_token` in context/agent contract and schema as an audit monotonic counter, and add a test that reports this boundary.

Enforced: pass the token to worker consumers and fail closed when assignment token does not match the current lease row.

- [x] **Step 4: Close or document assignment race**

If future parallel planning is supported, wrap assignment read/write in `BEGIN IMMEDIATE`. If planning remains single-owner, record that as an explicit contract and test that `plan-source-file`/`assign-slice` claim single-planner ownership.

- [x] **Step 5: Verify**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK.

### Task 5: OpenCode Shell Contract Consistency

**Files:**
- Modify: `validation/tools/opencode_agent_harness.py`
- Modify: `validation/tools/test_opencode_agent_harness.py`

- [x] **Step 1: Write command parsing tests**

Add paths with spaces and quoted arguments. Assert the command line placed in OpenCode prompts parses to the same argv used by `verify_opencode_contract_execution`.

- [x] **Step 2: Use one shell convention**

For Linux/competition OpenCode prompts, prefer POSIX shell semantics through `shlex.join`. Keep Windows-only convenience paths out of judge-facing prompt/evidence. Update `command_matches_for_contract` so generated command strings and observed shell commands are normalized under the same convention.

- [x] **Step 3a: Harden stale summary cleanup**

If `summary/competition-run-summary.json` already exists and cannot be removed before a retry or new attempt, fail closed with `runner_kind=stale-summary-cleanup`, `summary_status=stale-summary-cleanup-failed`, `root_cause_key=stale_summary_cleanup_failed`, and do not launch the worker or record the stale summary.

- [ ] **Step 3b: Decide top-level JSON error envelope**

If adding a top-level JSON error envelope, make it deterministic and avoid masking the original nonzero exit code. This is P1 unless a judge entrypoint currently assumes every harness CLI failure writes parseable JSON to stdout.

- [x] **Step 4: Verify H7/P0 path**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK. The top-level JSON error envelope remains Task 5.3b/P1 and is intentionally not required for this verification step.

### Task 6: Translator Smoke and Showcase Boundary Fixes

**Files:**
- Modify as needed: `crates/c2r-translator/src/typed_ir.rs`
- Modify as needed: `crates/c2r-translator/tests/bounded_translation.rs`
- Modify as needed: docs/README/showcase references

- [x] **Step 1: Lock current failures**

Reproduce: `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report`

Expected before fix: three known failures around nullable pointer fail-closed behavior and assertion drift.

- [x] **Step 2: Fix the real safety bug**

The nullable readonly pointer use after a null check must fail closed unless the code has a proven non-null borrowed slice in the supported subset. It must not generate `values[0]` from an `Option<&[i32]>` without unwrapping or proving non-null.

- [x] **Step 3: Fix assertion drift without hiding bugs**

For the two reason-string failures, either restore the intended validation order so the original fail-closed reason appears, or update the tests to assert the stable root-cause key if the new diagnostic is more precise. Do not weaken tests to accept any error.

- [x] **Step 4: Keep showcase claims honest**

Ensure docs and public artifacts still distinguish handwritten `flashDB_rust`, translator-generated candidates, accepted evidence, before/after safety exhibit, C oracle source, and proof class.

- [x] **Step 5: Verify**

Run: `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report`

Expected: OK.

### Task 7: Final H7 Verification Gate

**Files:**
- Modify: `docs/c2rust-migration-agent/future-vision-and-mvp.md`
- Modify: `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
- Modify as needed: judge entrypoint artifacts/configs

- [x] **Step 1: Run focused tests**

Run:

```powershell
python -B -m unittest validation.tools.test_opencode_agent_harness -q
python -B -m unittest validation.tools.test_doc_mirror_contract -q
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
```

- [x] **Step 2: Run or record judge smoke**

Refreshed focused judge smoke:

```powershell
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id competition_environment_smoke --out target/h7-judge-smoke/summary/judge-entrypoints-run-report.json
```

Expected/observed: runner exits 0; report status is passed; proof class remains `local-simulation`; selected-entrypoint post-run validation uses `target/h7-judge-smoke/summary/selected-entrypoints-validation-config.json`.

- [x] **Step 3: Update roadmap status**

Mark H7 checked in the canonical roadmap and English mirror, listing the verification commands and remaining non-goals.
