## Why

当前项目已经具备较强的 L0-L3 验证基础设施，但翻译能力仍主要依赖人工或 Agent 手写 slice、oracle 与 Rust replay。这个 change 的目标是把项目从“验证基础设施项目”推进到“受限自动翻译器 + 强验证项目”，让一个已通过 L1 的 C 函数 slice 能自动进入可编译、可修复、可审计、可复现的迁移闭环。

用户已明确取消“小而精”的规模限制，因此本 change 允许引入一个可扩展的翻译器 crate 和自动迁移工具；但第一版仍必须保持范围受限，先证明端到端闭环，而不是承诺通用 C99 全量翻译。

## What Changes

- 新增受限自动翻译管线：输入一个已通过 L1 的 C 函数 slice，自动抽取 context pack、pointer graph、type map、CFG，并生成 Rust draft。
- 新增自动 oracle/replay 生成能力：为 slice 自动生成 C oracle harness 初稿和 Rust replay test 初稿，接入现有 L2/L3 验证输出。
- 新增编译自愈闭环：Rust draft 编译失败时解析 `rustc` JSON error stack，生成有边界的 PatchPlan，并在安全约束内自动补丁和重跑。
- 新增翻译证据清单：最终输出继续进入现有 L3 evidence manifest，并明确记录翻译器版本、输入 slice、生成物、AI 使用、unsafe 比例、缓存键和验证结果。
- 采纳 Corrode 与现有 `c-to-rust-翻译器嵌入方案.md` 的可落地部分：独立 Rust crate、类型/表达式/语句/控制流/指针分层、默认 raw pointer、后续 CFG relooper 路线；第一版不追求通用 C99 全覆盖。
- 保留安全边界：first-party non-test unsafe 仍需小于 10%，新增 unsafe 必须进入 ledger；AI 只能作为候选生成或补丁建议来源，不能绕过本地编译、oracle、diff、negative diff 和 evidence gates。

## Capabilities

### New Capabilities
- `bounded-auto-translation-pipeline`: 受限 C 函数 slice 自动翻译闭环，包括上下文抽取、类型/指针/CFG 证据、Rust draft 生成、oracle/replay 初稿生成、编译自愈、L3 evidence manifest 集成和验证门禁。

### Modified Capabilities
- `flashdb-l3-agent-migration-loop`: 现有 L3 迁移循环需要接受“翻译器生成物”作为新的 evidence source，并要求自动翻译 slice 仍复用 L3 evidence manifest、unsafe ledger、version manifest 和缓存失效规则。

## Impact

- 代码：预计新增 `crates/c2r-translator/` 或等价 Rust crate、`validation/tools/auto_migrate.py` 或等价 CLI/脚本、自动生成的 Rust slice/replay 测试和 evidence 产物。
- 验证：复用现有 `validation/l2_slices`、`validation/l3-template`、pointer graph、test translation、unsafe ledger、version manifest、schema-aware diff 和 OpenSpec validation。
- 依赖：可引入 Rust 侧 C 解析依赖（优先本地、可锁版本），但必须在 version manifest 中记录；不得把在线 AI 服务作为必需运行依赖。
- 文档：新增中英文面向 Agent 的使用说明，说明受支持 C 子集、非目标、失败分级、自愈边界和证据路径。
- 风险：本 change 不声明“任意 C99 自动翻译成功”，不声明跨项目语义百分百由翻译器保证；正确性仍由 C oracle、Rust replay、diff/fuzz、negative diff、compile gate 和人工可审计 evidence 共同判定。
