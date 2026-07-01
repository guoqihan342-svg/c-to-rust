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
- A top-level JSON error envelope and protected `summary_path.unlink()` are useful P1 hardening items, but they must not displace the first four P0 items.
- The showcase-boundary warnings in `c-to-rust-flashdb-rust-skeleton-评估报告.md` are valid: handwritten `flashDB_rust` is not automatic translation output, and every before/after exhibit must bind the real source pin, baseline/final/oracle source, and proof class.

## Parallel Work Split

- Agent A: timeout envelope red tests and implementation.
- Agent B: atomic write helper red tests and critical artifact replacement.
- Agent C: Python command portability, OpenCode prompt command line, and contract parser consistency.
- Agent D: retry cap, OpenCode lock classification, fencing/lease/transaction contract.
- Agent E: minimal fixes for the three translator smoke failures.

All agents should hand back small patches or worktree diffs. One main integrator merges serially and runs full verification.

## 2026-07-02 Implementation Progress

- Done: Task 1 timeout envelope; Task 2 Python command portability split with the shared `python3 -B` portable strategy; Task 3 atomic critical evidence writes; Task 4 retry/lock/lease/fencing guardrails; Task 5 Steps 1-2 POSIX shell contract; Task 6 translator smoke fixes.
- Verified: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`, `python -B -m unittest validation.tools.test_doc_mirror_contract -q`, and `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report`.
- Remaining: Task 5 Step 3 cleanup/error-envelope hardening; Task 7 judge smoke and final roadmap checkbox. If time is tight, Step 5.3 can remain P1 after H7 because it does not block the completed P0 stability contracts.

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

- [x] **Step 4: Verify**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK, with new tests proving timeout kwargs and timeout evidence.

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

- [ ] **Step 3: Harden cleanup and top-level failures**

Wrap stale summary cleanup in best-effort error handling. If adding a top-level JSON error envelope, make it deterministic and avoid masking the original nonzero exit code.

- [ ] **Step 4: Verify**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK.

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

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -B -m unittest validation.tools.test_opencode_agent_harness -q
python -B -m unittest validation.tools.test_doc_mirror_contract -q
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
```

- [ ] **Step 2: Run or record judge smoke**

Refresh one judge entrypoint smoke if local prerequisites are available. If not available, record the exact blocker and keep proof class honest as local-only or not-run.

- [ ] **Step 3: Update roadmap status**

When H7 is complete, mark H7 checked in the canonical roadmap and English mirror, listing the verification commands and remaining non-goals.
