# 受限自动翻译管线 Agent 使用文档

本文面向 OpenCode、Codex 和其他可执行 Agent，说明 OpenSpec change `add-bounded-auto-translation-pipeline` 的受限自动 C-to-Rust 翻译流程。该流程生成的是 evidence-bound Rust draft candidate，不是默认接受的实现；最终是否通过仍由 L1-L3 evidence gates 判定。

## 入口原则

- 项目规模不再要求“只小而精”：可以增加 crate、工具、批处理和更多 target 验证；但每个迁移结论必须保持 slice 级、证据绑定、可回滚、可复现，不能放宽 L1-L3 gates。
- 从 OpenSpec 开始：先读取 `openspec status --change "add-bounded-auto-translation-pipeline" --json` 和 `openspec instructions apply --change "add-bounded-auto-translation-pipeline" --json`。
- 从 slice spec 开始：自动翻译不得直接吃一段裸 `c_source`。输入必须包含 target id、slice id、source commit、C 文件、函数签名、L1 evidence、build profile、fixture contract、Rust 输出边界、accepted metadata differences 和 non-goals。
- 从证据开始生成代码：`context-pack`、`type-map`、`cfg`、`pointer-graph` 必须先落盘，再允许 Rust draft。
- 把 AI 当候选生成器：AI 可以建议 draft 或 PatchPlan，但 AI 输出不是正确性证据，不能绕过本地编译、C oracle、Rust replay、schema-aware diff、negative diff、unsafe scan、version/cache 和 OpenSpec validation。
- 多 Agent 并行时只允许拆分只读分析或不相交写入。`slice spec`、public API、fixture、oracle 合约、unsafe ledger、schema 和自动修复中的文件不能被多个 Agent 同时改。

## 工作流

1. 选择已通过 L1 native validation 的目标和函数 slice。
2. 规范化 slice spec 与 build profile，记录 include paths、defines、target triple/ABI、compiler command 来源、preprocessing mode、tool versions 和 clang-backed type extraction 是否可用。
3. 生成或刷新 `l3-<slice>-context-pack.json`、`l3-<slice>-type-map.json`、`l3-<slice>-cfg.json`、`l3-<slice>-pointer-graph.json`。新生成的 pointer graph 使用 `schema_version=2`；只要 slice 同时存在指针读写并触发 alias-sensitive gate，`effect_graph` 必须记录 read/write effects 和每个 alias risk 对应的 `requires_noalias` 或 `may_alias` 边。
4. 翻译器只对支持 C 子集生成 Rust draft，并写入 `l3-<slice>-auto-translation-plan.json` 与 `l3-<slice>-auto-translation-events.jsonl`。
5. 从同一个 fixture contract 生成 C oracle harness draft 和 Rust replay test draft；无法映射输入/输出时标记 blocked。
6. 运行 `cargo check --message-format=json`。失败时写 `l3-<slice>-rust-check.json`，再生成 PatchPlan，默认最多 3 轮局部自愈。
7. 运行 Rust replay、schema-aware diff、negative diff、unsafe scan、version/cache gate 和 evidence manifest gate。
8. 只有同一 source commit、fixture hash、slice spec hash 和 build profile hash 下的 C oracle、Rust replay、diff、unsafe、version/cache 和 OpenSpec validation 都通过，才能把 candidate 升级为 accepted slice。

## 支持的 C 子集

MVP 只支持边界明确、可证据化的函数 slice：

- 函数签名、primitive integer/boolean-like expressions。
- primitive declarations、assignments、returns。
- simple calls，且 callee 事实在 context pack 或 direct caller/callee facts 中可追溯。
- 结构化 `if`、`while`、`for`、`return`。
- struct-by-name，不凭空推断未证明的 layout。
- 有 fixture contract 的 `const T*` input pointer、带明确长度 companion 的 buffer、out parameter struct/POD 写入等有限指针模式。
- 固定 fixture 驱动的 C oracle 和 Rust replay。

## 必须阻断或降级的构造

遇到下列情况，Agent 应写 unsupported/blocked evidence，而不是伪造通过：

- 缺失 L1 accepted native evidence。
- 缺失或不足的 build profile，尤其是 typedef、macro、integer width、ABI、struct layout、enum value、implicit cast 或 declaration disambiguation 无法证明。
- `goto`、computed goto、`switch` fallthrough、`setjmp/longjmp`、inline assembly、多入口非结构化 CFG。
- VLA、复杂 typedef 链、union bitfield、未建模宏副作用、跨线程语义。
- 未证明 alias 边、逃逸指针、返回 ownership 不明的 raw pointer。
- 无法从 fixture contract 映射 C 输入/输出到 Rust assertion。
- 任何要求修改 oracle 合约、fixture expected behavior、accepted differences、公共 API 边界、source slice boundary 或 unsafe budget 的自动修复。

## API 与指针边界

翻译器 crate 应暴露小而稳定的 slice-level API，例如 `translate_c_slice(request) -> TranslationResult`。request 必须包含 slice spec、build profile 和 evidence context；不要使用 `translate_c_to_rust(c_source: &str)` 这类裸源码 API 作为安全公共入口。

Rust-facing public API 默认不得暴露 raw pointer。指针相关 draft 的低层 IR 可以保留 raw pointer 或内部 FFI boundary，但对外必须优先使用 safe wrapper、validated buffer、newtype 或明确隔离的 internal layer。只有 slice contract 记录了 reviewed exception 时，公共边界才允许 raw pointer。

safe promotion 是可审计优化，不是默认猜测。每一次从 raw pointer 到 safe wrapper 的提升都必须写入 pointer graph 和 unsafe ledger，说明 read/write effect、alias 假设、len companion、nullability、ownership/lifetime 边界和覆盖测试。`auto_migrate.py` 生成的 v2 pointer graph 会把 `effect_graph` 纳入 cache invalidation；对应 cache metadata 也必须包含 `effect_graph_identity`，避免 effect/alias 证据变化后复用旧候选。

## Unsafe ledger 规则

- first-party non-test unsafe ratio 必须低于 10%。
- 每个新增 unsafe 都必须登记 ledger：文件、span、类别、原因、替代方案、覆盖测试和关联 evidence。
- unsafe scan 和 unsafe ledger 即使 unsafe 数为 0 也必须存在。
- 自动修复不得为了编译通过扩大 unsafe 预算、绕过 safe public API、删除 ledger 或放宽测试。

## 语义等价限制

本流程只支持有限语义等价声明：命名 slice、固定 source commit、固定 fixture 输入域、固定 build/config profile，以及 schema-aware diff 实际检查过的行为字段。它不证明：

- 全项目迁移完成。
- 任意 C99/C11 都能自动翻译。
- Rust draft 编译通过就等于语义等价。
- byte-for-byte flash image layout、GC/clean、sector rollover、power-loss、capacity pressure、async/multithreading、性能保持或未列入 fixture 的行为。
- pointer graph 是全程序 alias proof；它只是上下文与风险边界证据。v2 `effect_graph` 能证明“当前候选记录了哪些 effect 和 alias-risk 边”，不能替代 C oracle、Rust replay、unsafe ledger 或完整 alias solver。

## 外部方案的采纳、修正和推迟

参考文件：

- `F:\agent\codex\ctorustpaper\c-to-rust-翻译器嵌入方案.md`
- `F:\agent\codex\ctorustpaper\c-to-rust-slice-自动化翻译管线方案.md`

采纳：

- 新增独立 Rust translator crate 或等价模块。
- 类型、表达式、语句、控制流、指针、emitter 分层的工程方向。
- 新方案里的 `context extractor -> candidate translator -> build healer -> semantic verifier -> evidence emitter` 角色拆分。
- 从 L1 accepted catalog target 中按 complexity signals 自动选择 slice 的后续 batch migration 思路。
- 默认 raw pointer，再在有证据时做 safe promotion。
- 接入 C oracle、Rust replay、unsafe ledger 和 L3 evidence manifest。
- 编译失败后走 rustc JSON error stack、PatchPlan、自愈重跑的闭环。

修正：

- 不再把“项目小而精”作为当前项目约束。项目可以扩展为多 crate、多工具、多 target；受限的是每个 slice 的迁移声明和证据边界。
- 不采用“全自动 C -> Rust 翻译”的强表述。本 change 是 bounded automatic translation pipeline，只生成证据绑定候选。
- 不采用 `tree-sitter-only` 作为语义事实源。`tree-sitter-c` 可以做快速索引或切片定位；类型、宏展开、ABI、struct layout、implicit casts 必须来自 build profile、compile commands、clang/libclang、WSL/Linux/CI 或明确 unsupported evidence。
- 不把 DeepSeek 或任何单一模型作为硬依赖。AI 层必须 provider-agnostic、可关闭、可缓存、可审计；默认本地 pipeline 不能依赖在线 AI 才能运行。
- 不采用错误的 loop-label goto 初版方案。MVP 只支持结构化控制流；`goto` 和非结构化 CFG 默认 blocked。Corrode-style CFG relooper 留作后续能力，不在第一版强行翻译。
- 不把 raw pointer draft 暴露成默认 Rust public API。raw pointer 属于低层 draft/internal/FFI 边界，public API 仍需 safe wrapper 或 reviewed exception。
- 不把 Rust 编译通过、AI 建议、或 translator 输出当成正确性证明。

推迟：

- 通用 C99/C11 覆盖。
- 完整 Corrode-style CFG relooper。
- 宏求解、复杂 typedef 链、union bitfield、VLA、inline asm、setjmp/longjmp。
- differential fuzzing 扩展、code-test 同步翻译、跨项目大规模自动批处理的 pass-rate 目标。
- async/multithreaded runtime 优化。

## 运行命令

以下命令从仓库根目录 `C:\Users\Administrator\Documents\c-to-rust-flashdb` 运行。部分命令是本 change 预期新增的接口；在 schema、translator、auto_migrate 并行实现完成前，它们用于 Agent 对齐调用约定。

### OpenSpec 状态和任务

```powershell
openspec status --change "add-bounded-auto-translation-pipeline" --json
openspec instructions apply --change "add-bounded-auto-translation-pipeline" --json
openspec validate add-bounded-auto-translation-pipeline --strict
openspec validate --all
```

### L1 input selection

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1
Get-Content .\validation\evidence\l1-native-summary.json -Raw | ConvertFrom-Json
Get-Content .\validation\evidence\l1-low-cost-remediation-summary.json -Raw | ConvertFrom-Json
```

Agent 只能选择已有 accepted L1 native evidence 的 target。若 target 没有 accepted L1，自动翻译必须在生成 Rust 前写 blocked reason。

### Auto migration

预期接口：

```powershell
python .\validation\tools\auto_migrate.py `
  --slice-spec .\validation\evidence\libuv\l3-ip4-addr-slice-spec.json `
  --evidence-root .\validation\evidence\libuv `
  --max-repair-rounds 3
```

该命令应生成 context pack、type map、CFG、pointer graph、Rust draft provenance、translation events、oracle/replay drafts、rust check、PatchPlan/blocked repairs 和 evidence manifest 输入。

### C oracle

现有 libuv L2 oracle 生成命令需要 WSL/Linux，因为脚本内路径使用 `/mnt/c`：

```bash
python3 validation/l2_slices/tools/generate_oracles.py
```

预期 slice-spec-driven oracle 命令：

```powershell
python .\validation\tools\auto_migrate.py `
  --slice-spec .\validation\evidence\libuv\l3-ip4-addr-slice-spec.json `
  --only oracle
```

本地无 C toolchain 时只能记录 `SKIPPED_LOCAL_NO_C_TOOLCHAIN`，不能把语义门禁标记为 pass。语义通过必须有 `C_ORACLE_GENERATED` 或等价 CI/WSL/Linux evidence。

### Rust replay 和 L2/L3 报告

```powershell
Push-Location .\validation\l2_slices
cargo test
cargo run --bin emit_reports
Pop-Location
```

FlashDB CLI 相关 replay、unsafe scan 和 evidence search：

```powershell
Push-Location .\flashDB_rust
cargo test
cargo run -- unsafe-scan
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "C_ORACLE_GENERATED" --limit 20 --report ..\validation\evidence\flashdb\evidence-search-report.json
Pop-Location
```

### Compile self-healing

Rust draft 编译检查：

```powershell
Push-Location .\flashDB_rust
cargo check --message-format=json *> ..\validation\evidence\flashdb\l3-<slice>-rust-check.raw.jsonl
Pop-Location
```

现有 FlashDB 自愈工具：

```powershell
python .\validation\tools\flashdb_l3_self_healing.py `
  --evidence-dir .\validation\evidence\flashdb `
  --slice-id <slice>
```

预期 auto-translation 自愈由 `auto_migrate.py` 统一编排：

```powershell
python .\validation\tools\auto_migrate.py `
  --slice-spec .\validation\evidence\libuv\l3-ip4-addr-slice-spec.json `
  --only self-heal `
  --max-repair-rounds 3
```

### Evidence search

```powershell
Push-Location .\flashDB_rust
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "blocked" --limit 50
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "unsafe_ratio" --limit 50
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "l3-ip4-addr" --limit 50 --report ..\validation\evidence\flashdb\evidence-search-report.json
Pop-Location
```

### Final verification

对文档或管线 change，至少运行：

```powershell
openspec validate add-bounded-auto-translation-pipeline --strict
openspec validate --all
git diff --check
```

当 translator、auto_migrate 和 MVP slices 完成后，再补充：

```powershell
Push-Location .\crates\c2r-translator
cargo fmt -- --check
cargo test
Pop-Location

Push-Location .\validation\l2_slices
cargo fmt -- --check
cargo test
cargo run --bin emit_reports
Pop-Location

Push-Location .\flashDB_rust
cargo fmt -- --check
cargo test
cargo run -- unsafe-scan
Pop-Location
```

## Agent 完成条件

Agent 只有在以下证据都存在且新鲜时才能报告自动翻译 slice 完成：

- slice spec、build profile、cache metadata 和 version manifest 绑定同一输入。
- validation profile 绑定 `config/competition-env/environment.json` 的 `profile_id`、路径和 SHA256，cache metadata 的 `competition_environment_identity` 与其一致。
- context pack、type map、CFG、pointer graph 在 Rust draft 前生成。
- unsupported constructs 或 blocked repairs 已显式记录。
- C oracle、Rust replay、schema-aware diff、negative diff、rust check、unsafe scan、unsafe ledger、final verification 都在 L3 evidence manifest 中引用。
- OpenSpec change validation 和 `git diff --check` 通过。
