# C2Rust Migration Agent

这里是 `design-c2rust-migration-agent` 的可执行设计文档集合，供 OpenCode、Codex 或其他智能体按 OpenSpec 分阶段执行 C 到 Rust 迁移。英文镜像见 `README.en.md`。

## 当前状态

- OpenSpec change：`design-c2rust-migration-agent`
- 第一目标：FlashDB
- 源码克隆：`sources/FlashDB`
- 源码 commit：`93d175549da579b8abac07bd175ce4c3f9dde829`
- Rust 输出项目名：`flashDB_rust`
- C2Rust 角色：只作为 baseline/oracle，不作为最终交付代码
- 安全目标：first-party non-test unsafe 低于 10%
- 核心翻译架构和证据状态：见 `core-translation-architecture.md` / `core-translation-architecture.en.md`；typed IR candidate generation 当前是 `GenericTypedIr` / `Unsupported` 两路线模型，generic emitter 已覆盖局部固定长度整数数组读取/写入、窄化标量整数二元 `+`、`-`、`*`、`/`、`%`、`&`、`|`、`^`、`<<`、`>>`、signed unary `-value`，comparison expression 的条件位置和窄 value-position C `int` 0/1 结果 candidate generation，以及 logical not `!expr` 的条件位置和窄 value-position C `int` 0/1 结果 candidate generation，新 evidence 可绑定 `candidate_generation.typed_ir`，clang-lowered direct call 也会进入 `call_expressions` / `direct_call_edges` 证据；scalar-only 且 `GenericTypedIr` candidate 的 `candidate_route.token_cost=0` 时，确定性候选现在作为 L0 route signal，非 scalar pointer surface 仍至少 L1，alias risk floor 仍优先；external direct callee 的 call-site/signature/source binding 已有默认 validator 一致性校验，但这只证明证据链一致，不表示 external callee 语义已通过；semantic acceptance 仍由 validation gates 决定。
- 核心翻译边界：上述 bitwise OR `|` / left shift `<<`、signed unary minus、comparison expression 和 logical not 都只是 candidate generation only；bitwise OR `|` / left shift `<<` 目前仅覆盖窄化标量整数候选生成，不代表完整 C 位运算或位移语义；comparison 目前仅覆盖条件位置和窄 value-position C `int` 0/1 materialization，例如 `return x > 0`、assignment RHS 和 declaration initializer；logical not 目前覆盖整数条件零比较，以及窄 value-position C `int` 0/1 结果语义。pointer comparison、float comparison、mixed-width/unsigned conversions、comparison cast operand、call/inc/dec/deref/side-effect operand、pointer null test、float truthiness、unsupported type、短路逻辑、完整 usual scalar conversions、无效 shift count、signed shift/overflow UB parity、unsigned/wrapping 取负、浮点取负、特殊 literal/min-value 边界和 semantic acceptance 仍 fail closed。

## 双语文档约定

- 面向用户或 Agent 的新增文档，默认使用中文主文档 `.md` 和英文镜像 `.en.md`。
- 修改已有文档时，如果改动超过小修小补，应同步维护对应英文镜像。
- OpenSpec parser anchors 必须保留英文，例如 `## ADDED Requirements`、`### Requirement:`、`#### Scenario:`、`WHEN`、`THEN`。
- 本目录仍有早期文档采用“中文说明 + English summary”混合格式；后续触及时按上述约定拆成完整双语版本。

## 文档地图

- `README.md` / `README.en.md`：本目录索引、状态和双语文档约定。
- `baseline-record.json`：机器可读的版本、hash、源码和工具可用性记录。
- `baseline-and-versioning.md`：Agent、schema、PatchPlan 和 `flashDB_rust` 的版本策略。
- `build-and-c2rust-baseline.md`：FlashDB build capture、C2Rust baseline 和 C oracle fallback。
- `agent-contract.md`：OpenCode/Codex runtime contract、phase、IO、subagent、AI policy、async/thread policy。
- `context-store-and-self-healing.md`：SQLite/JSONL schema、ContextPack、impact set、rustc repair loop、PatchPlan。
- `core-translation-architecture.md` / `core-translation-architecture.en.md`：当前 `clang_frontend -> typed IR + globals -> translation_route -> validation` 架构、核心代码地图、两路线 typed IR candidate model、candidate_generation evidence schema、clang-lowered direct-call evidence、external direct-callee binding validator 和 typed IR legacy cleanup 边界。
- `flashdb-rust-skeleton-and-milestone.md`：`flashDB_rust` crate layout 和首个 host-verifiable milestone。
- `testing-unsafe-cache-and-milestone.md`：测试、differential oracle、unsafe budget、cache policy、performance gates。
- `bounded-auto-translation-pipeline.md` / `bounded-auto-translation-pipeline.en.md`：受限自动翻译管线 Agent 使用文档。

## 快速使用

```bash
openspec status --change "design-c2rust-migration-agent" --json
openspec instructions apply --change "design-c2rust-migration-agent" --json
```

然后运行 Agent phase，例如：

```bash
c2rust-migrator --phase index --change design-c2rust-migration-agent --input request.json
```

## 运行原则

- 实现前先走 OpenSpec。
- context local-first，并限制 token。
- 只在只读任务或不相交写入任务上并行多个 subagent。
- 先用确定性规则，再使用 AI。
- AI 输出只能作为候选，不能作为证据。
- C2Rust 输出只作 baseline/oracle。
- 优先迁移小的、可编译通过的 slice。
- 用 Rust 测试和 C/Rust differential evidence 证明行为。
- 跟踪 unsafe，并把比例控制在 10% 以下。
- 只有显式 invalidation 和 equivalence gates 时才加 cache。

## Native Windows 工具说明

当前主机已有 native LLVM `clang`（默认路径 `C:/Program Files/LLVM/bin/clang.exe`），本轮真实 clang AST smoke 已使用它验证。PATH 仍可能缺少 native `c2rust`、`cmake`、`bear`、`intercept-build`、`cargo-nextest`、`cargo-llvm-cov`、`cargo-fuzz` 和 `cargo-geiger`。设计仍然有效，但这些 gate 需要 WSL/Linux 或后续工具安装后才能声称完整迁移验证完成。
