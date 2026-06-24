## Why

FlashDB Rust 迁移目前已经有 L1/L2 验证基础和可编译的 `flashDB_rust` crate，但还缺一个面向真实 FlashDB 切片的 L3 迁移闭环：同一输入必须同时经过 C oracle 与 Rust replay，并用机器可读差分、编译自愈日志、unsafe 预算和性能烟测来约束迁移质量。

现在需要先跑通一个小而精的端到端切片，避免一次性重写全库破坏跨文件调用关系，也避免把 Rust seed layout 误宣称为 FlashDB 原生持久化 layout 等价。

English: this change introduces a bounded L3 loop for one FlashDB slice before attempting broader migration. It proves behavior through a C oracle, Rust replay, schema-aware diff, compile self-healing evidence, unsafe budget, and performance smoke, without claiming full byte-level FlashDB layout equivalence.

## What Changes

- 新增 FlashDB L3 agent migration loop 能力，首个目标切片限定为 KVDB 字符串生命周期：`fdb_kvdb_init`、`fdb_kv_set`、`fdb_kv_get`、`fdb_kv_del`、deinit/reopen。
- 为该切片建立 ContextPack，记录 C API、C 调用边、Rust API、fixture、oracle、accepted differences、unsafe ledger 和自愈边界。
- 生成并保存 C oracle report、Rust replay report、schema-aware diff、negative regression、performance smoke、compile self-healing 与 summary evidence。
- 规定编译/测试/差分失败的 error stack 分类、PatchPlan 日志、retry/rollback 和禁止自动修改范围。
- 保持 Rust 公共 API safe，默认 first-party non-test unsafe 为 0%；如未来必须引入 unsafe，必须进入白名单和 ledger。
- 明确本 change 不声明 FlashDB 全库迁移完成，也不声明 byte-for-byte flash image layout 完整等价。

English: the first slice is intentionally narrow and evidence-driven. It adds the loop, reports, and guardrails needed by other agents, while keeping implementation scope small and avoiding broad rewrites.

## Capabilities

### New Capabilities
- `flashdb-l3-agent-migration-loop`: 定义 FlashDB C 到 Rust 的 L3 单点渐进式迁移闭环，包括切片选择、跨文件上下文管理、C/Rust oracle 差分、编译自愈、安全预算、性能烟测和可追溯证据。

### Modified Capabilities

## Impact

- OpenSpec: 新增 `openspec/changes/run-flashdb-l3-agent-migration-loop` proposal/design/spec/tasks。
- Rust crate: 后续实现将集中在 `flashDB_rust/src/kvdb.rs`、`flashDB_rust/src/format.rs`、`flashDB_rust/src/replay.rs`、`flashDB_rust/src/cli.rs`、相关 tests 和 scripts。
- C oracle: 后续实现复用 `flashDB_rust/oracle/flashdb_c_oracle.c` 与 `flashDB_rust/oracle/generate_c_oracle.sh`，C oracle 证据优先在 Linux/WSL/CI 生成。
- Evidence: 后续实现新增或刷新 `validation/evidence/flashdb/` 下的 L3 报告和 summary。
- Dependencies: 不新增运行时第三方依赖；如测试框架扩展需要依赖，必须在任务中单独说明并保持项目小而精。

English: implementation impact is scoped to the local OpenSpec artifacts, the `flashDB_rust` crate, the existing C oracle harness, and machine-readable evidence under `validation/evidence/flashdb/`.
