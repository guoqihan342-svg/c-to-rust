## Context

当前仓库已经具备三类基础：第一，`flashDB_rust` 是一个可编译、可测试的小型 Rust crate，包含 safe Rust KVDB/TSDB API、memory/file flash 后端、fixture replay/diff、CLI smoke/stress/unsafe-scan；第二，`flashDB_rust/oracle` 已固定 FlashDB 上游 commit `93d175549da579b8abac07bd175ce4c3f9dde829`，可在 Linux/WSL/CI 生成 C oracle；第三，`validation/gates.md` 已定义 L0-L3 分层门禁，只有 L3 可支持命名切片上的有限语义等价声明。

English: the repository already has a compilable Rust foundation, a pinned C oracle producer, and layered validation gates. This design adds the missing L3 loop for one named FlashDB slice.

关键约束：

- 本机 Windows 当前没有可用 C 原生 toolchain；真实 C oracle 必须在 Linux/WSL/CI 生成，Windows 本地只能记录 skip marker。
- 当前 Rust `format.rs` 是 seed record log，不是 FlashDB 原生 sector/image layout；本 change 不把 layout hash 差异当作行为等价。
- 用户要求跨文件上下文管理、编译自愈、安全、速度、低 token、小而精、必要时接入 AI，并默认使用多智能体并行。
- Rust first-party non-test unsafe 目标为 0%，验收红线为小于 10% 且必须有 ledger。

## Goals / Non-Goals

**Goals:**

- 选择一个可验证的 L3 切片：KVDB 字符串生命周期 `init -> set -> get -> delete -> reopen`。
- 为该切片生成 ContextPack，覆盖 C 文件/API/调用边、Rust 模块/API、fixture、oracle、tests、unsafe ledger、accepted differences。
- 建立 C oracle report、Rust replay report、schema-aware diff、negative regression、performance smoke 和 L3 summary 的证据路径。
- 建立编译/测试/差分自愈闭环：rustc JSON error stack -> 分类 -> PatchPlan -> 最小补丁 -> 分级重跑 -> 证据落盘。
- 将多智能体并行限定在互不写同一文件的读分析、报告生成、验证执行和缺陷定位上，避免并发编辑冲突。
- 使用缓存降低 token 和运行成本，缓存键包含 source commit、file hashes、Cargo.lock、命令参数、toolchain version、feature/env 与 context schema。

English goals: prove one bounded KVDB lifecycle slice with reproducible evidence, safe Rust APIs, controlled repair, and cached context. Use parallel agents for independent analysis, not uncontrolled concurrent mutation.

**Non-Goals:**

- 不迁移完整 FlashDB 全库。
- 不声明 FlashDB 原生 flash image byte-for-byte layout 等价。
- 不在本轮实现 TSDB、GC/recovery、power-loss recovery、C ABI 完整绑定。
- 不为通过测试而放宽 C oracle contract、golden fixture、accepted differences 或 unsafe policy。
- 不默认引入异步 runtime 或业务多线程；性能优化必须先有 smoke/measurement 证据。

## Decisions

### Decision: 首个 L3 切片选择 KVDB 字符串生命周期

理由：该路径覆盖 `fdb_kvdb_init`、`fdb_kv_set`、`fdb_kv_get`、`fdb_kv_del`、reopen，并跨 `fdb_kvdb.c`、`fdb.c`、`fdb_file.c`、`fdb_utils.c`，能够验证跨文件上下文管理；同时行为边界比 TSDB callback/status 和 GC/recovery 更小。

Alternative considered: TSDB append/query/status。暂缓原因是 callback、timestamp/status 语义和 synthetic id 差异更复杂，适合作为第二个 L3 slice。

### Decision: 复用现有 `flashDB_rust` safe API 和 replay/diff 入口

理由：`KvDb::set/get/delete/entries/compact`、`FlashDevice`、`replay.rs`、CLI `replay/diff` 已存在，扩展这些边界比新造 runner 更小、更可验证。若未来需要 FlashDB-compatible layout，必须通过显式 adapter 或 versioned layout API 进入，不能隐式替换 seed layout。

Alternative considered: 直接用 c2rust 输出大段 unsafe Rust。暂缓原因是会放大 unsafe、借用错误和跨文件 API 破坏风险。

### Decision: 自愈采用 rule-first、AI-optional

规则修复先处理 import/module path、局部类型包装/解包、borrow scope 收窄、格式化和 evidence path 创建。AI 只用于生成候选 PatchPlan 或解释复杂 root cause，不作为事实来源；所有 AI 建议必须通过编译、测试、diff 和 evidence 验证。

Alternative considered: 每个错误都直接交给 AI。拒绝原因是 token 成本高、可追溯性弱、容易在语义 diff 上改测试而不是修逻辑。

### Decision: 并行只用于独立工作流

多智能体可并行执行 C slice 研读、Rust API 研读、oracle/diff 研读、自愈策略研读、独立验证命令和 evidence 审计。实际代码补丁按单 writer 串行合并，每个 PatchPlan 必须有 impact set 和 rollback id。

Alternative considered: 多智能体同时写多个模块。拒绝原因是容易破坏 public API、fixture schema 和报告 contract。

### Decision: 性能优化先做 smoke 和缓存，不默认异步化

L3 先记录 operation counters、elapsed time、target/backend/toolchain，不将性能数据替代正确性门禁。异步、多线程或批量并发 replay 只允许用于 agent 调度、验证编排或后续有测量支撑的 Rust 内部优化；FlashDB slice 的业务语义保持同步确定性。

Alternative considered: 直接引入 async runtime 或 rayon。暂缓原因是当前 crate 无第三方运行时依赖，且嵌入式 KV/TS 行为更需要确定性和可复现 oracle。

## Risks / Trade-offs

- [Risk] Windows 本地无法生成 C oracle -> Mitigation: 本地记录 `SKIPPED_LOCAL_NO_C_TOOLCHAIN`，L3 pass 必须依赖 Linux/WSL/CI 的 `C_ORACLE_GENERATED` 证据。
- [Risk] seed layout 与 FlashDB native layout 不一致 -> Mitigation: accepted differences 只允许 layout/hash/meta 类字段，不允许 value/status/count 等行为字段。
- [Risk] 自动修复掩盖语义差异 -> Mitigation: test/diff failure 禁止通过改 golden、改 accepted differences 或弱化断言自动修复。
- [Risk] borrow checker 修复诱导 unsafe -> Mitigation: 默认 0% unsafe，新增 unsafe 必须人工批准、ledger、测试覆盖和替代方案说明。
- [Risk] 多智能体并发编辑冲突 -> Mitigation: 并行任务以只读和验证为主，补丁由主 agent 串行应用。
- [Risk] 缓存污染导致 stale context -> Mitigation: 缓存键绑定 source commit、file hash、toolchain、feature/env 与 context schema。

## Migration Plan

1. 冻结 L3 slice、fixture、FlashDB source pin、feature matrix 和 evidence schema。
2. 生成 ContextPack，记录 C/Rust 边界和 impact set。
3. 先写失败用例和 fixture diff 期望，证明当前行为缺口。
4. 串行实施最小 Rust 补丁，按 error stack 生成 PatchPlan 并分级重跑。
5. 在本地完成 `cargo fmt -- --check`、`cargo check`、`cargo test`、replay/diff、unsafe scan、performance smoke。
6. 在 Linux/WSL/CI 生成真实 C oracle 并执行 C/Rust diff。
7. 汇总 L3 evidence，明确 pass/fail、accepted differences、unsafe ratio 和下一 slice。

Rollback strategy: 每个 PatchPlan 记录 rollback id；同一 root cause 超过 retry limit、引入新错误类别、扩大 unsafe、修改 oracle/golden contract 或出现行为 diff mismatch 时回滚到最后 known-good patch。

## Open Questions

- L3 第一次实现是否只覆盖 memory backend，还是同时纳入 file backend reopen？建议先包含 file backend reopen，因为 KV lifecycle 的持久化语义需要它。
- 是否在第一轮引入 property/fuzz 测试？建议暂不引入第三方依赖，先用 deterministic fixture 和 negative regression；后续 slice 再评估 `proptest`。
- Linux/WSL/CI oracle 证据由本仓 CI 直接生成，还是由外部 agent 上传 artifact？建议优先使用现有 GitHub Actions。
