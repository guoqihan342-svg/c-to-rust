英文镜像见 `2026-07-02-harness-stability-hardening.en.md`。

# Harness Stability Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Independent analysis and red-test drafting may run in parallel, but edits to `validation/tools/opencode_agent_harness.py` and `validation/tools/test_opencode_agent_harness.py` must be merged through one owner or isolated worktrees.

**Goal:** 把 OpenCode 多 agent harness 从“功能能跑”推进到“评委现场可控”：外部进程不会无限挂起，证据不会半写被接受，命令不会因 Python/OS shell 漂移失效，失败能被 repair/block ledger 精确索引。

**Architecture:** 保持现有 planner -> worker -> verifier -> repairer -> reporter 闭环，不引入新的框架层。H7 只加稳定性合同：timeout envelope、portable command contract、atomic artifact writer、retry/lock/fencing guard、translator smoke gate。LangGraph/SWE-bench-style 的价值体现在可恢复 DAG 和 worker 契约，不在此阶段重写 harness。

**Tech Stack:** Python stdlib `subprocess`/`tempfile`/`os.replace`/`sqlite3`/`shlex`, existing unittest suite, Cargo translator tests, repo-local validator commands.

---

## 外部审查判断

- `opencode-agent-harness-逐行稳定性审查.md` 大体有道理，尤其无 timeout、非原子写、命令环境不一致、retry 外层无防御 cap 这四项是 P0。
- `fencing_token` 和 `assign_slice` 事务属于“未来并行 planner 风险”，可以先二选一：要么明确 audit-only 并写入 contract，要么补消费侧校验和事务。
- stale summary cleanup 属于 H7/P0：旧 summary 删除失败时必须 fail-closed，不能启动 worker 或接受旧 evidence。顶层 JSON error envelope 属于 P1 小硬化，可以跟随 H7 后续做，但不能挤掉前四项。
- `c-to-rust-flashdb-rust-skeleton-评估报告.md` 对 showcase 边界的提醒成立：手写 `flashDB_rust` 不能当自动翻译产物；before/after 必须绑定真实 source pin、baseline/final/oracle 来源和 proof class。

## 审查条目到 H7 待办映射

| 外部审查条目 | 判断 | 当前处理 | 优先级 |
|---|---|---|---|
| 子进程无 timeout | 成立；评委现场 hang 是最高风险 | 已进入 Task 1，timeout 规范化为 `124` / `timed_out=true` | H7/P0 |
| 裸 `"python"` 与比赛 profile 的 `python3` 不一致 | 成立；必须避免解释器漂移和本机绝对路径泄漏 | 已进入 Task 2，公开命令和 worker argv 统一 `python3 -B` portable contract | H7/P0 |
| 关键 evidence 非原子写 | 成立；半截 JSON 会破坏 resume/validator | 已进入 Task 3，关键 artifact 使用同目录临时文件 + `os.replace` | H7/P0 |
| `auto_retry` 外层无独立 cap | 成立；虽有内层 5 轮 cap，但缺第二道保险 | 已进入 Task 4，外层上限为 `REPAIR_ROUND_CAP + 2` 并进 graph/report | H7/P0 |
| OpenCode SQLite lock 匹配过窄 | 成立；第三方 CLI stderr 不稳定 | 已进入 Task 4，扩展等价 lock 信号分类 | H7/P0 |
| `fencing_token` 语义不清 | 成立；字段存在但不应被误读成强并发防护 | 已进入 Task 4，当前定义为 audit-only monotonic counter 并写入 contract | H7/P0 |
| `assign_slice` check-then-write 窗口 | 成立但偏未来风险 | 已进入 Task 4，用 `BEGIN IMMEDIATE` 明确分配事务 | H7/P0 |
| `subprocess.list2cmdline` 与 POSIX shell contract 混用 | 成立；Linux/OpenCode prompt 应按 POSIX | 已进入 Task 5，使用 `shlex.join` 与 POSIX parser 对齐 | H7/P0 |
| stale summary 删除失败未处理 | 成立；Windows/杀毒/并发句柄会触发 | 已进入 Task 5.3a，删除失败 fail-closed，不启动 worker，不接受旧 summary | H7/P0 |
| deterministic worker 零瞬时重试 | 有道理但不应抢 H7 主线；deterministic worker 当前按 fail-fast 处理，避免在缺少幂等/副作用合同前重复执行 | 后置；未来若要加短重试窗口，必须先定义幂等输入、输出目录清理和 summary 覆盖合同 | P1/Deferred |
| 顶层 JSON error envelope | 有价值，但不应阻塞已完成稳定性合同 | 后置为 Task 5.3b；需要独立设计，避免吞 traceback 或改坏 exit code | P1 |
| 真实子进程集成 timeout 测试 | 有价值，能覆盖 mock 不到的 OS 行为 | 已补真实 `subprocess.run` sleep timeout 集成测试，验证 1 秒超时会在 OS 层被规范化为 `124` | Done/Post-H7 |

## 并行分工

- Agent A: timeout envelope 红测和实现。
- Agent B: atomic write helper 红测和关键 artifact 替换。
- Agent C: Python command portability、OpenCode prompt command line、contract parser 一致性。
- Agent D: retry cap、OpenCode lock 分类、fencing/lease/transaction contract。
- Agent E: translator smoke 三个失败测试的最小修复。

所有 agent 只提交小 patch 或 worktree diff，最终由主集成者串行合并并跑完整验证。

## 2026-07-02 实施进度

- 已完成：Task 1 timeout envelope；Task 2 Python command portability split（统一 `python3 -B` portable strategy）；Task 3 atomic critical evidence writes；Task 4 retry/lock/lease/fencing guardrails；Task 5 Step 1-2 POSIX shell contract；Task 6 translator smoke 修复。
- 已验证：`python -B -m unittest validation.tools.test_opencode_agent_harness -q`、`python -B -m unittest validation.tools.test_doc_mirror_contract -q`、`cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report`、`python -B -m validation.tools.validate_auto_translation_evidence --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --evidence-root validation/evidence --require-semantic-pass`、`python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json`、`python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id competition_environment_smoke --out target/h7-judge-smoke/summary/judge-entrypoints-run-report.json`。
- 当前补丁：Task 5 Step 3a stale summary cleanup fail-closed 已有单测覆盖；focused `--entrypoint-id` runner 的 post-run local-artifact validation 现在会生成 `selected-entrypoints-validation-config.json`，只深校验本次执行的入口，避免未执行入口的旧 `target/` artifact 让 smoke/triage 误失败。
- 最新补丁：Task 1 追加真实子进程 timeout 集成测试，直接调用 `subprocess.run` 执行 `time.sleep(5)`，验证 `timeout_seconds=1` 时 harness 会在约 1 秒内返回 `124` 并写出稳定 timeout stderr；这关闭了“只 mock `TimeoutExpired`、没覆盖 OS 行为”的验证缺口。`validate_judge_entrypoints --require-local-artifacts` 还把 smoke summary 的 step 集合绑定到 `commands.jsonl`，缺任一 summary step 的 command log 会 fail-closed，避免单步日志冒充完整 smoke 证据链。
- H7/P0 状态：已封顶。`competition_environment_smoke` 在本机 `local-simulation` proof class 下可跑通 runner 和 post-run 深校验；环境检查仍按 proof class 记录本机降级，不冒充 `competition-exact`。
- 后置：顶层 JSON error envelope、deterministic worker 短重试策略，均为 P1，不阻塞 H7。

## 当前核对表

- 二次审查复核：`C:\Users\Administrator\Downloads\opencode-agent-harness-逐行稳定性审查.md` 的技术判断总体成立，但当前代码已吸收其中 H7/P0 稳定性项。后续执行时把该报告作为已关闭风险清单和回归测试来源，而不是重新打开同一批 P0 工作。
- H7/P0 implemented：timeout、portable command、atomic write、retry cap、OpenCode lock、fencing audit contract、assignment transaction、POSIX shell contract、translator smoke fix 均已落到代码和测试。
- stale summary cleanup included in H7/P0：旧 summary 删除失败现在 fail-closed，不启动 worker，不记录旧 summary，并打开 `stale_summary_cleanup_failed` repair hint。
- judge smoke refreshed：focused `competition_environment_smoke` runner 已通过，post-run 深校验使用选中入口过滤配置；本地 proof class 明确保持 `local-simulation`。
- post-H7 verification strengthened：真实 `subprocess.run` sleep timeout 集成测试已通过，覆盖 mock 不到的 OS timeout 行为。
- command-log drift guard strengthened：本地 artifact 深校验现在要求 `commands.jsonl` 覆盖 smoke summary 的全部 steps。
- P1 deferred：top-level JSON error envelope、deterministic worker short retry policy、文档/示例中裸 `python` 命令的一致性清理。

## H7 后执行方案

1. 全量 public packet 优先：运行非 focused `run_judge_entrypoints`，生成并验证 `judge-milestone-bundle.json`、`milestone-release-notes.md`、`public-release-packet.json` 和 competition config archive。若深校验失败，优先刷新对应 entrypoint 的 `target/` artifact，不修改当前 config/profile hash 去迎合旧输出。
2. S1 C2Rust baseline 次优先：让一个真实 slice 产出 C2Rust Rust output、output sha256 和 compile-only status，保持 `candidate_context_only`；blocked/skipped 只能作为失败证据和 repair 输入。
3. S1 verifier：把 compile-only baseline 接进 C oracle、Rust replay、diff、negative diff 和 unsafe ledger，成功后才称为 `verified-unsafe-baseline`。
4. S2 safety loop：在同一单元上接 OpenCode/LLM patch，每轮只收一个最小 unsafe-reduction diff；失败回滚，repair hint 最多 5 轮，验收以 compile/diff/oracle 绿和 unsafe 严格下降为准。
5. proof class 收尾：真实比赛/等价 Linux 环境刷新前，本机 artifact 只能保持 `local-simulation`；若外部发布仍没有 `competition-exact` 或 `ci-approximation` 证据，必须在 public packet 中列为 release blocker。
6. P1 hardening timebox：顶层 JSON error envelope、deterministic worker 短重试、文档命令一致性清理和旧计划 checklist 历史标记只在 P0-A 到 P0-D 不被挤占时执行。

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

Catch `subprocess.TimeoutExpired` beside `OSError`, return a `CompletedProcess` with exit code `124`, and write blocked/repair summaries with `root_cause_key=process_timeout` or an equivalent stable key. Ensure auto-retry can retry a timeout but still respects the five-round cap and final blocked status.

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

If `summary/competition-run-summary.json` already exists and cannot be removed before a retry/new attempt, fail closed with `runner_kind=stale-summary-cleanup`, `summary_status=stale-summary-cleanup-failed`, `root_cause_key=stale_summary_cleanup_failed`, and do not launch the worker or record the stale summary.

- [ ] **Step 3b: Decide top-level JSON error envelope**

If adding a top-level JSON error envelope, make it deterministic and avoid masking the original nonzero exit code. This is P1 unless a judge entrypoint currently assumes every harness CLI failure writes parseable JSON to stdout.

- [x] **Step 4: Verify H7/P0 path**

Run: `python -B -m unittest validation.tools.test_opencode_agent_harness -q`

Expected: OK. Top-level JSON error envelope remains Task 5.3b/P1 and is intentionally not required for this verification step.

### Task 6: Translator Smoke and Showcase Boundary Fixes

**Files:**
- Modify as needed: `crates/c2r-translator/src/typed_ir.rs`
- Modify as needed: `crates/c2r-translator/tests/bounded_translation.rs`
- Modify as needed: docs/README/showcase references

- [x] **Step 1: Lock current failures**

Reproduce: `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report`

Expected before fix: three known failures around nullable pointer fail-closed behavior and assertion drift.

- [x] **Step 2: Fix the real safety bug**

The nullable readonly pointer use after a null check must fail closed unless the code has a proven non-null borrowed slice in the supported subset. It must not generate `values[0]` from an `Option<&[i32]>` without unwrapping/proving non-null.

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
