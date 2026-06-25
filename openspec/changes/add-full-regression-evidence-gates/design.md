## Context

当前全量回归入口是 `scripts/run-full-regression.ps1`。它已经顺序运行 catalog、translator、L2 slices、auto-translation evidence、FlashDB Cargo gates、fixture replay/diff、unsafe scan、version manifest、stress、evidence search、OpenSpec 和 git diff check。

主要缺口不在“命令数量”，而在 evidence 消费强度：L2 report 生成没有进入 full regression；FlashDB L3 manifest template 已存在但没有被每轮校验；fixture diff 缺少负向控制；unsafe scan 主要是控制台输出；version manifest 写出后没有被绑定检查消费；test translation/coverage 证据没有作为门禁。

## Goals / Non-Goals

**Goals:**

- 让 full regression 每轮校验关键 evidence，而不是只运行编译和测试命令。
- 让 L2/L3 的 positive diff、negative diff、unsafe、version/config、test translation、coverage matrix 都能机器检查。
- 增强 unsafe scan 的 JSON 产物和类别覆盖，使 0 unsafe 也有审计证据。
- 保持本地优先、无新增在线 AI 依赖、失败即早停，并保留 `-ContinueOnFailure` 的审计能力。
- 让新门禁能在 30 轮或更短 smoke 回归中运行，不要求恢复 10000 轮长跑。

**Non-Goals:**

- 不把当前 translator 扩展成通用 C99 翻译器。
- 不新增 cargo-fuzz、llvm-cov、符号执行器或在线 AI provider 作为必需依赖。
- 不声明 full regression 能证明生产数据百分百等价；真实生产数据仍必须以脱敏 fixture 进入 replay/diff。
- 不把性能 smoke 当作正确性证明，也不引入异步或多线程重写 FlashDB 业务逻辑。

## Decisions

1. Full regression consumes committed and generated evidence through small validators.

   Rationale: 当前项目的强项是 evidence discipline。把校验集中到 Python/Rust 小工具，比在 PowerShell 中写复杂 JSON 逻辑更可测、更可复用。

   Alternative considered: 只在文档里要求人工检查。Rejected because it cannot fail CI or repeated local regression deterministically.

2. L2 reports are refreshed before L2 evidence validation.

   Rationale: L2 evidence drift is otherwise easy: Rust tests can pass while report JSON remains stale. The regression must generate or refresh evidence before validating summaries.

   Alternative considered: Only validate committed JSON. Rejected because it misses generator regressions.

3. Negative diff gates are expected-failure commands with explicit evidence.

   Rationale: A negative control must prove that the diff gate catches a deliberate semantic mutation. The wrapper should treat a failing diff command as pass only when the failure matches the expected mismatch class.

   Alternative considered: Produce a synthetic JSON file without running the diff tool. Rejected because it tests the artifact shape, not the executable diff path.

4. Unsafe scan reports use category-level findings.

   Rationale: `unsafe` count alone is too weak for Rust migration. `extern "C"`, `repr(C)`, `transmute`, raw pointers, unsafe impls and unsafe blocks have different review meanings and should be ledgerable.

   Alternative considered: Keep regex-only line scan. Rejected because it misses inline and boundary unsafety classes.

5. Version/config binding is checked after version manifest generation.

   Rationale: Evidence and cache reuse must fail when tool/schema/package version inputs drift. The manifest is useful only if a gate consumes it.

   Alternative considered: Store version manifest for audit only. Rejected because audit-only evidence cannot prevent stale acceptance.

6. Test translation coverage remains bounded and manifest-driven.

   Rationale: The project does not yet have full automatic code-test translation for every target. The gate should require explicit coverage evidence for accepted slices without pretending unimplemented targets are covered.

   Alternative considered: Require coverage for all 40 catalog targets immediately. Rejected because it would block progress on accepted L2/L3 slices with unrelated catalog work.

## Risks / Trade-offs

- [Risk] More gates increase per-round runtime. → Mitigation: validators are lightweight; heavy stress remains controllable with `-SkipLongStress` and `-StressLoops`.
- [Risk] Existing historical evidence may be incomplete. → Mitigation: gate only accepted/current L2 and L3 evidence sets, and produce explicit blocked/missing reports instead of silently passing.
- [Risk] Regex-based unsafe classification can still miss Rust syntax edge cases. → Mitigation: expand categories now and keep findings conservative; future work can replace it with a Rust parser without changing report contract.
- [Risk] Negative controls can become brittle if output messages change. → Mitigation: match machine-readable status/mismatch fields when available and keep logs as evidence.

## Migration Plan

1. Add OpenSpec requirements for full-regression evidence gates and consumption by existing L2/L3/auto-translation capabilities.
2. Add focused validator tests first for missing/mutated evidence cases.
3. Implement small validators and report emitters.
4. Wire validators into `scripts/run-full-regression.ps1` after the corresponding producer step.
5. Run targeted unit tests, OpenSpec validation, and a short full regression smoke round.

Rollback is straightforward: revert the new validators, CLI report option, regression steps, and generated evidence files. Existing FlashDB Rust functionality and translator APIs are not changed by the gates themselves.

## Open Questions

- Whether future CI should run the full evidence gate on every PR or only on migration branches.
- Whether full branch coverage should later use `llvm-cov`; this change records coverage claims through evidence manifests only.
