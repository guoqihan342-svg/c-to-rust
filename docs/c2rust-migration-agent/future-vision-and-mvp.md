# 未来愿景与 MVP 路线

本文是中文主文档。英文镜像见 `future-vision-and-mvp.en.md`。

## 1. 目标

构建一个从 `input.c` → `c2rust-migrator` → `output.rs` 的端到端 MVP pipeline。当前已完成第一阶段证明（FlashDB `real-fdb-calc-crc32` named slice 的代码路径可经真实 clang AST dump lowering + typed IR + generic emitter 生成可编译 Rust candidate，并通过 accepted evidence 绑定语义门禁；committed evidence 已包含 durable real-clang lowering artifact，但 generated draft 仍是 candidate），离工业级 C→Rust 翻译器还有大量缺口。

边界必须说清楚：`validation/evidence/*/l1-native-build.json` 只证明原始 C 项目在固定环境中可构建或可烟测，不证明 Rust 翻译成功。当前真实自动翻译能力仍主要集中在经过挑选的函数切片；大项目 evidence catalogue 是迁移输入池和基线，不是"已能翻译真实大项目"的证据。

## 1.1. 待办执行规则

从本文开始，后续核心翻译开发默认按本文件的 P0/P1/P2 待办推进；除非出现阻塞 bug，优先顺序不再被临时 demo 或单个项目牵着走。**本文件是唯一全局 roadmap/backlog 来源**；其它文档若出现 checklist、tasks、Next 或 P0/P1/P2 文字，只能是局部验收模板、OpenSpec change 任务、历史实施计划或分析材料，不能覆盖本文优先级。

本文的 Phase 2/3/4 描述能力成熟阶段；P0/P1/P2 是默认执行队列。实际开工时以 P0/P1/P2 为准，遇到 Phase 条目和 P 队列交叉时，把对应能力拆成最小可验证切片执行。

- **先扩翻译能力，再扩仪式**：新增 schema、manifest、gate 前，必须能说明它解决了具体翻译风险、验证误判或复现问题。
- **FlashDB 只是用例**：可以继续用 FlashDB 做回归样本，但不能写 FlashDB 专用 recognizer、模板或特判路径。
- **候选生成不等于语义接受**：typed IR、C2Rust、LLM 和手写规则都只是 candidate source；语义通过只由 C oracle、Rust replay、diff、negative diff、unsafe ledger 和 final verification 决定。
- **C oracle 也有边界**：oracle 只能证明固定 source commit、fixture、编译器/flags、target ABI、平台模型和 observable output contract 下的行为；未定义行为、实现定义行为、硬件/RTOS/volatile 副作用和测试覆盖不足必须显式记录，不能被"通过测试"掩盖。
- **fail-closed 不能变成死胡同**：拒绝翻译时必须给出可执行的下一步，包括 source span、unsupported construct、需要补的 IR/lowering 规则、oracle/fixture 缺口、可尝试的候选源和人工 review 输入；否则只能算 blocked，不算治理成功。
- **evidence 成本必须受控**：release 必需证据、开发 smoke、诊断日志和历史归档要分级；新增 evidence 生成流程必须记录耗时、文件大小、保留/压缩/清理策略，不能让元数据增长吞掉翻译开发效率。
- **unsafe 数字不是安全证明**：unsafe budget 是治理指标，不是 FFI、硬件、volatile、ABI 或并发语义已经安全建模的证明；0 findings 只能说明当前扫描范围内未发现 first-party non-test `unsafe`。
- **C2Rust baseline 必须可追溯**：route/profile 中的 C2Rust candidate 只能作为 `candidate_context_only`，必须绑定 baseline manifest；当 baseline 真正生成输出时，还必须绑定 output path/status/sha256，并由 validator 拒绝漂移。
- **C2Rust skipped 不能算候选成功**：baseline 为 `skipped`、`blocked` 或无 output 时，必须记录 reason、toolchain/env、input hash 和 `output_ref=null`；不得把 skipped 计入 generated、compiled、accepted 或 semantic pass。
- **比赛环境配置是适配参考和证据 profile**：`config/competition-env/environment.json` 是当前默认比赛环境配置入口；开发时参考其中的 Ubuntu、Rust、Python、Node、gcc、镜像源和缺失工具约束。本机不需要强行复刻该环境，但新增默认构建、测试和验证路径不能违反这些约束；`validation/environment-profiles/...` 只作为兼容入口。
- **公开复现路径以 Linux/CI 为准**：PowerShell/Windows 命令可以保留为本机便利入口，但外部可评估的 quickstart、验证和 evidence 生成必须提供 competition Linux/CI 等价命令；没有等价路径时要标记为 local-only。
- **evidence 必须可移植**：新 evidence、manifest、cache metadata 和日志引用优先使用 repo-relative path、profile id/hash 和 artifact hash；本机 `C:\...`、`F:\...`、`/mnt/c/...` 路径只能作为 diagnostic host metadata，不得作为可复现入口或跨机器 claim 依据。
- **默认路径必须暴露真实能力**：无 clang 的默认 CI/比赛路径不能把 legacy string translator 的成功包装成 typed-IR 成功；typed IR 因 `CLANG_PATH` 或工具缺失未运行时，evidence、metrics 和公开叙述必须明确标记 unavailable/compatibility fallback。
- **交接文档要短而可审计**：`CONTEXT.md` 只能作为当前状态、最近验证和下一步的 handoff；长会话日志要拆分或归档到 `docs/c2rust-migration-agent/archive/`，不能作为 release 文档、外部评估入口或能力证明。
- **文档要双语同步**：本文件和 `future-vision-and-mvp.en.md` 必须一起更新。

## 2. IR 分层设计（推荐工业标准）

关键原则：**IR 不能"决定 Rust 怎么写"，只能"描述 C 是什么"**。正确性来自 C oracle，IR 是忠实描述 C semantics 的中间表达。

### Layer 1: Semantic IR（最重要）

**保留 C semantics，不做 Rust inference，不做 candidate。**

这一层是翻译器的核心资产。它只回答："这段 C 代码在 C 抽象机里做了什么？"

- 每个 C 操作都保留原始语义：整数提升规则、usual arithmetic conversions、序列点、左值转换
- 不预先判断"这个指针能变成 slice"、"这个 struct 能变成 Rust struct"
- 保留原始的 pointer arithmetic、implicit cast、truncation、promotion 信息
- 数组到指针 decay 是 C 语义的一部分，必须保留在 IR 中
- UB 标记（未定义行为的位置）也必须在这一层记录

**当前状态**：我们的 typed IR 混入了部分 Rust inference（例如直接标记 `const void *` 为 `&[u8]`），这在 P0 阶段可以接受，但长期应分离成独立的 Lowering 层。

### Layer 2: Control IR

**if / loop / goto / switch，CFG explicit。**

- 控制流从 AST 转换为显式 basic block + CFG
- `if-else`、`while`、`for`、`do-while`、`switch-case`、`goto` / label 都进入统一 CFG
- 每条边带显式的条件（或无条件）
- `break`、`continue` 映射为 CFG 边，不需要 ad-hoc 处理
- 支持 relooper（将任意 CFG 还原为高层结构化控制流），这是翻译 `goto` / `switch` 的前提

**当前状态**：我们有一个基础的 `cfg.json` 证据模板，但 typed IR 内部仍用 AST 风格的控制流（`If`、`While`、`For`、`DoWhile`）。`switch`、`goto`、computed goto 完全未支持。

### Layer 3: Typed Value IR

**integer / pointer / struct / array，explicit casts only。**

- 所有隐式类型转换（integer promotion、usual arithmetic conversion、array-to-pointer decay、function-to-pointer decay）在这一层变成**显式 cast**
- 指针运算分解为 element access：`p + i` 变成 `element_at(p, i)` 或等价表达
- struct 字段访问是明确的 offset-based 或 symbolic field access
- 数组索引是明确的 base + offset
- 类型系统只描述 C 的运行时行为，不做 Rust 类型推断

**当前状态**：我们的 typed IR 有 `Cast { implicit }` 字段区分显式/隐式 cast，integer 类型有 signed/width 信息，指针有 `Pointer { pointee }`。但 clang 前端对 `ImplicitCastExpr` 的处理不完全（部分被透明剥离，部分保留），且没有统一的"所有隐式 cast 都变显式"的原则。

### Lowering 层（从 Semantic IR 到 Rust candidate）

这一层做从"描述 C"到"生成 Rust"的转换。关键原则：

1. 不修改 Semantic IR 本身
2. 每条 lowering 规则必须可证明（由 C oracle 或 typed evidence 支持）
3. Lowering 失败时保留完整的 fail-closed reason
4. 不允许"猜测"——如果 C 语义不能安全映射到 safe Rust，拒绝翻译

典型 lowering 规则：
- `const T *p` + 只读访问 → `p: &[T]`（需要证明：不写入、不 escape、life 有限）
- `T *out` + 只写访问 → `out: &mut [T]`（需要 noalias 证明）
- `uint32_t + uint8_t` → 显式 `(byte as u32) + acc`（需要 promotion 证明）
- `while(size--)` → Rust `loop` + `wrapping_sub`（需要 postfix side-effect 语义保留）

## 3. MVP Pipeline 路线

```
input.c  →  clang AST dump  →  Semantic IR  →  Lowering  →  Rust candidate
         \                    \              \            \
          source slice         typed IR       route decision  validation gates
          extraction           (current)      (current)       (current)
```

### Phase 1: 当前已完成

- [x] 真实 clang AST dump JSON 解析（`clang -Xclang -ast-dump=json` → `clang_frontend.rs`）
- [x] typed IR 数据结构（`IrFunction` / `IrStmt` / `IrExpr` / `IrType`）
- [x] generic typed IR emitter（标量 + 控制流 + pointer slice 子集）
- [x] readonly global const array 支持
- [x] route decision 和 validation profile 证据绑定
- [x] C oracle harness 草稿生成
- [x] Rust replay 执行和 diff gate
- [x] 旧 crc32 特例代码已删除
- [x] FlashDB `real-fdb-calc-crc32` named slice 通过 accepted evidence semantic pass

### Phase 2: 近期（补齐 IR 分层）

- [ ] 分离 Semantic IR 和 Lowering：IR 只描述 C semantics，不做 candidate
- [ ] 所有 clang `ImplicitCastExpr` 变成显式 typed IR cast
- [ ] array-to-pointer decay 作为显式 IR 节点
- [ ] `switch` / `goto` 支持（需要 CFG + relooper）
- [ ] compound literal、designated initializer
- [ ] function pointer（至少支持直接调用和简单传递）
- [ ] `enum` 类型
- [ ] `union` 类型（至少支持 tagged union pattern）

### Phase 3: 中期（扩大真实 C 项目覆盖）

- [ ] 把 FlashDB 更多函数（`fdb_kv_set`、`fdb_tsl_iter` 等）推进到 L3
- [ ] 支持 libuv、zlib-ng 等项目的真实函数切片
- [ ] 从 `validation/projects.json` 中选择 5+ 项目，每个项目至少推进一个 named function slice：项目级 L1 native baseline + slice 级 L2/L3 evidence
- [ ] 治理 catalogue L1 失败：每轮 catalogue 报告必须列出 success/fail/skipped 比例、top failure classes、可修复/不可修复/环境缺失分类、排除规则和下一步；L1 skipped/fail 不得计入翻译能力或 L3 进展。
- [ ] usual arithmetic conversions 的显式模型
- [ ] 指针/alias-sensitive struct field write（有 alias/noalias 证明；readonly `const struct T *p` 的简单 `p->scalar_field` 读、`p == NULL`/`p != NULL` presence check 到 `Option<&T>`、flow-sensitive null-guarded `p->scalar_field` read、单 pointer 参数下 mutable `struct T *p` 的直接 `p->scalar_field = scalar`、简单 standalone `p->scalar_field += scalar`、同字段 definite write 后 `return p->scalar_field`、会继续执行路径都写同字段的 direct if-return 分支、standalone statement 位置 `p->scalar_field++` / `++p->scalar_field` / `p->scalar_field--` / `--p->scalar_field`、非 pointer 的简单按值 `p.x = value` 和 standalone statement 位置 `p.x++` / `++p.x` / `p.x--` / `--p.x` 已进入 typed IR candidate 子集；多 pointer alias、nullable mutable pointer、read-before-write、普通 maybe-write 后读取、只在 returning 分支写入、loop/复杂路径 return、复杂 RHS/target、value-position field inc-dec 等 pointer field update/read 仍拒绝）
- [ ] nested struct / anonymous struct
- [ ] bitfield（至少支持 common patterns）
- [ ] macro expansion tracking

### Phase 4: 远期（工业级翻译器）

- [ ] 完整 C99/C11 子集覆盖
- [ ] 多文件 translation unit 支持
- [ ] 增量迁移（一次改一个函数，不破坏其余）
- [ ] bidirectional evidence（C→Rust 和 Rust→C 的 cross-validation）
- [ ] 性能 regression gate
- [ ] fuzz harness 自动生成
- [ ] sanitizer / symbolic execution / property-based exploration 作为高风险 slice 的增强 oracle，不替代 fixture contract 和 C/Rust diff
- [ ] MIRI validation（Rust UB 检测，不作为 C UB 证明）

## 4. P0/P1/P2 待办（默认执行顺序）

### P0: 先把当前 MVP 变成可信、可维护的翻译器核心

- [ ] 继续收敛 `crates/c2r-translator/src/lib.rs`：crate root 已经缩成较小的 public orchestration 入口，但仍要把 CLI/manifest、旧字符串 translator、typed IR route、artifact 写入、unsafe/metadata 统计等责任继续拆到子模块；已完成公开 model schema 拆分、artifact/IO leaf helper 私有模块（`artifact_io.rs`：`write_json_file`、`write_text_file`、`translation_events_jsonl`）拆分、core translation artifact writer helper（`write_core_translation_artifacts`）拆分、feature-gated clang dry-run artifact writer（`write_clang_dry_run_artifact`）拆分、clang lowering report artifact writer cluster（`write_clang_lowering_report_artifact`、`typed_ir_candidate_evidence`、`readonly_global_summary`）拆分、clang-lowered translation/evidence 私有模块（`clang_lowered_translation.rs`）拆分、legacy string translator 私有模块（`legacy_translation.rs`）拆分，以及 `write_translation_artifacts` public orchestration 拆分，crate root API 保持兼容；仍待 CLI/manifest orchestration、generic typed IR route、unsafe/metadata 统计、parser/evidence builder/emitter 的后续拆分；拆分提交必须保持现有测试通过。
- [ ] 拆分 `typed_ir.rs` / `clang_frontend.rs` 巨文件：先做行为保持拆分，把 IR 数据类型、类型/definite-assignment validation、emitter、side-effect helpers、clang AST skeleton、clang-to-IR lowering、report/evidence builder 分到稳定子模块；每一刀必须保持 feature matrix、public API、bounded tests、fixture replay 和 `git diff --check` 通过。
- [x] 统一 clang 前端事实：当前主路径是 `CLANG_PATH` 调用 `clang -Xclang -ast-dump=json -fsyntax-only`；`--emit-clang-dry-run` artifact 现在标记 `artifact_kind=clang-dry-run`、`status=diagnostic_only`、`claim_boundary.role=diagnostic_only` 和 `active_frontend.kind=clang_ast_dump_json`，`LIBCLANG_PATH` 仅作为 `ignored_env_for_ast_dump`/`observed_libclang_path` 诊断元数据，不参与 lowering，也不表示真实 libclang 解析路径已启用。
- [x] 明确比赛环境 clang 路线：`config/competition-env/environment.json` 现在把 clang 声明为 optional capability/optional lane；默认构建、测试和验证不要求 clang。需要真实 clang AST dump typed-IR 路线时使用 `auto_migrate.py --competition-clang-lane`，该 lane 自动启用 `clang-lowering-report`，要求 `CLANG_PATH`，缺失时清晰失败；只传 `--emit-clang-lowering-report` 仍是 diagnostic opt-in，缺 clang 时写 unavailable 报告。
- [x] 建立依赖与工具链引入原则：继续把 `CLANG_PATH` + clang AST dump JSON 作为当前语义前端事实；只有当 libclang/bindgen/syn/quote/tracing/anyhow 等依赖能消除具体语义风险、生成质量风险或可维护性风险，并能适配 `config/competition-env/environment.json`，才引入依赖；拒绝只为“看起来像编译器项目”而加依赖。`config/competition-env/environment.json` 现在包含 `dependency_admission_policy`，只准入当前直接 Rust 依赖 `serde` / `serde_json`，把 libclang/bindgen/syn/quote/tracing/anyhow 标为未准入候选并列出 before-use 条件；`validation.tools.test_competition_environment_profile` 会扫描当前 Rust manifest 并在核心 CI 中运行。
- [x] 建立 no-clang typed-IR fixture replay CI：已提交精简 clang AST JSON replay fixture（`crates/c2r-translator/fixtures/clang_ast/add_one_ast.json`，用于回归 AST 形状而非 durable real-clang evidence）和 replay API，使默认 CI 在没有 `CLANG_PATH` 时能跑 `AST JSON -> typed IR -> generic emitter -> rustc/check` 回归；真实 clang lane 继续由 `--competition-clang-lane` 验证前端集成。后续扩覆盖时继续新增真实 AST JSON fixture，手写 IR 单测不能替代这条回归。
- [x] 提交 durable real-clang lowering evidence：`real-fdb-calc-crc32` 等关键 real-source slice 的 committed evidence 必须包含 real `clang-lowering-report` 或等价 artifact，记录 `CLANG_PATH`/tool version/profile hash、typed IR hash、Rust draft hash；若某次 evidence 只来自 no-clang/compatibility 路径，公开叙述必须降级为“代码路径支持，当前证据未包含 real-clang lowering artifact”。`auto_migrate.py --competition-clang-lane` 现在会用 Python sha256 enrich lowering report，`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-clang-lowering-report.json` 已提交并在 evidence manifest、route decision、validation profile 中绑定；该 artifact 记录 `CLANG_PATH`、clang version、competition profile hash、typed IR sha256 和 Rust draft sha256，final semantic pass 仍来自 accepted evidence binding，不把 generated draft 提升为 accepted。
- [x] 建立 translator + validation 的核心 CI：`.github/workflows/core-translator-validation-ci.yml` 现在覆盖 `crates/c2r-translator` 默认与 all-features 单测、核心 validation unittest、repo-level unsafe budget gate 和 `git diff --check`；触发路径包含 translator、validation tools/templates、`validation/l2_slices`、competition env 和 unsafe ledger，避免只依赖 `flashDB Rust CI`。
- [x] 建立 translator 覆盖矩阵，而不是只数测试文件或测试条数：`validation/translator-coverage-matrix.json` 现在按 IR construct、clang fixture replay、手写 IR、负例、runtime emitted Rust、C/Rust diff、legacy fallback、route evidence 维度记录代表性覆盖；`validation/tools/translator_coverage_matrix.py` 和核心 CI 会拒绝缺正例、缺负例、缺 fail-closed reason、covered 维度无证据或引用路径缺失的矩阵。该矩阵是覆盖声明门禁，不是完整 C99/C11 支持率或语义通过证明。
- [ ] 拆分 `bounded_translation.rs` 测试巨文件：按能力域拆成 clang frontend、typed IR validation、emitter arithmetic、pointer/slice lowering、record/field lowering、route/provenance、negative/fail-closed、runtime emitted Rust 等测试模块；拆分必须保持覆盖矩阵和现有测试语义，不用“测试文件数变多”冒充覆盖提升。
- [x] 在声明 checksum/hash 翻译覆盖前修复无符号整数模运算语义：typed IR 已对 C unsigned `+`、`-`、`*` 发射显式 `wrapping_add` / `wrapping_sub` / `wrapping_mul`，并用 debug/overflow-checks runtime 红测覆盖 `u32::MAX + 1`、`0u32 - 1` 和 unsigned multiply。signed overflow、division/modulo zero 和非法 shift count 仍是单独的 fail-closed/contract 问题。
- [x] 明确 signed overflow/division/modulo/shift 的 UB contract：signed `+`/`-`/`*` 只有在 slice contract 或 compiler flags 明确声明 `-fwrapv`/二补码回绕 profile 时才允许发射 wrapping；否则必须 fail-closed 或记录 precondition。division/modulo zero、非法 shift count 和实现定义 signed shift 必须有 negative test、evidence 字段和 refusal reason，不能依赖 Rust debug/release 差异。已闭环：literal `/ 0`、`% 0`、负数 shift count、`shift_count >= width` 和无 contract 的 signed right shift 已在 typed IR emitter fail-closed；signed `+`/`-`/`*` candidate 已发射 `checked_add` / `checked_sub` / `checked_mul` + `expect(...)`，把 no signed overflow 表达为 runtime precondition；非 literal division/modulo divisor 和已支持 shift operator 的非 literal shift count 现在由 typed IR emitted Rust 表达为 runtime precondition（`divisor != 0`、`0 <= shift_count < type width`），避免 Rust debug/release 裸运算分叉；`clang-lowering-report` 的 `typed_ir_candidate.runtime_preconditions` 会记录这些候选前置条件，并已绑定进 `route_decision.candidate_generation.typed_ir` / `validation_profile.candidate_generation.typed_ir`，validator 会拒绝 route/profile/report 三方漂移。slice spec schema/template 现在记录 `c_boundary.scalar_arithmetic_contract`、`fixture_contract.scalar_input_domain` 和相关 cache invalidation key；route/profile evidence 现在记录 `scalar_ub_contract`，`typed_ir_candidate.scalar_admission` 会把 runtime precondition 绑定到 slice contract/input domain，validator 会拒绝 admission drift，未覆盖 admission 会阻止 0-token scalar typed-IR candidate 降到 L0；no-clang AST JSON replay fixture 已覆盖标量 runtime precondition 正向路径，以及 literal `/0`、`%0`、shift count out of range、signed right shift without contract 的 fail-closed 拒绝路径。`demo-signed-rshift-contract` named slice 现在具备 C oracle、Rust replay、C/Rust diff、negative diff、unsafe ledger、final verification、real clang-lowering report、route/profile scalar admission 绑定，以及 `l3-signed-rshift-contract-refusal-evidence.json` 对缺失 explicit contract、错误 contract、缺失 scalar input domain 的 fail-closed 证据。边界：无 explicit contract 的 signed right shift 仍必须 fail-closed；这不代表完整 signed overflow 或全 C shift 语义覆盖。
- [x] 把 unsafe budget 的最小持续监控接入 CI：`validation/tools/unsafe_budget.py` 默认覆盖 `crates/c2r-translator/src`、`flashDB_rust/src`、`validation/l2_slices/src`，输出扫描范围、分母行数、unsafe findings、比例、登记状态和 ledger 引用；`validation/unsafe-budget-ledger.json` 作为 repo-level 登记入口；核心 CI 以 `--max-ratio 0.10` 执行该 gate。
- [x] 明确 unsafe claim 边界：`<10%` 或当前 0 findings 都不能用来证明 C ABI、FFI、flash hardware、volatile register、RTOS 或多线程/中断语义已经解决；这些能力进入实现前必须有 unsafe ledger span、替代方案、测试/target evidence 和人工 review 状态。入口 README 和 docs README 已补充该边界，避免把 unsafe 预算误写成平台语义证明。
- [x] 强化 C oracle/UB/平台边界：每个 accepted slice 必须记录 observable output、fixture 代表性、编译器和 flags、target ABI、endianness/word-size 假设、sanitizer/diagnostic 状态、已知 UB/implementation-defined 边界、硬件/RTOS/volatile 依赖是否被建模；证据不足时只能保留 candidate 或 blocked，不能升级为 semantic pass。`auto_migrate.py` 现在生成 `oracle_boundary_contract`，`validation-profile.schema.json` 要求 passed profile 带该合同，`validate_auto_translation_evidence.py --require-semantic-pass` 校验 profile/final 合同一致、非 unknown target、非 unmodeled platform status，并把 `oracle_boundary_contract_identity` 纳入 cache；`real-fdb-calc-crc32` accepted evidence 已刷新并通过该门禁。
- [x] 加强 unsafe ledger 治理粒度：登记项后续应扩展到 span、替代方案、覆盖测试、source evidence 和审核状态，而不是只依赖 path+category 的最小登记键。`validation/unsafe-budget-ledger.json` 已加入 `repo_level_policy`，声明 required fields、field/category/review-status contract 和 path/category 兼容约束；`validation/tools/test_unsafe_budget.py` 已用单测固定该合同。
- [ ] 执行 `CONTEXT.md` handoff 收敛：建立短 current-state 入口，归档或拆分 superseded 长历史段，并给旧段标明“历史记录、不可作为当前能力事实”；release/README/roadmap 不得依赖 `CONTEXT.md` 的旧会话段作为能力证明。
- [x] 执行 evidence portability 清理：新增 validator 或报告检查本机绝对路径、旧 WSL/Windows 工作目录、不可复现临时目录和缺失 profile hash；历史 evidence 可保留但必须标为 historical/diagnostic，新 milestone evidence 必须可从 repo + competition profile 复现。`validation/tools/evidence_governance.py` 已提供非破坏性 portability report，能区分 claim-anchor 绝对路径、缺失 competition profile hash 和 diagnostic host metadata；它会把 `translator.artifact_paths` 和 `source_boundary.files` 视为 claim anchor，同时把 skipped C2Rust `reference_tree`、clang path、lowering arguments 和历史 L1 `worker_result_sources` 视为诊断上下文。real-fdb-calc-crc32 accepted evidence 的 `source_boundary.files` 已收敛为 `src/fdb_utils.c`，auto-translation manifest 的 `translator.artifact_paths` 已统一为 repo-relative 路径，`write_translation_artifacts` 也已对新生成 manifest 做 repo-relative 路径归一，跳过 C oracle 编译时会显式记录 `compile_execution.toolchain_adapter = "not_executed"`。当前真实仓库报告显示 `validation/evidence` 有 0 个 claim-anchor 绝对路径问题、0 个 profile hash 问题、1599 个 diagnostic host path 记录，硬 portability gate 已通过；diagnostic 记录仍保留为历史/环境审计上下文，不作为能力 claim anchor。
- [ ] 建立 evidence 成本和保留策略：区分 committed release evidence、CI smoke evidence、diagnostic-only logs 和 historical archive；每条证据流水线都要报告 runtime、artifact count、total bytes、retention class、compression/prune policy，避免 1000+ evidence 文件继续无边界增长。进展：`evidence_governance.py` 已输出 inventory 和 per-pipeline 统计，当前真实仓库 `validation/evidence` 为 1033 文件、约 2.66 MB、54 条 pipeline，并按 committed_release / diagnostic_only / historical_archive 分类；`target/full-regression/<run-id>` 已作为 `ci_smoke` 接入，pipeline 报告包含 `artifact_count`、`total_bytes`、`runtime_ms`、`retention_class`、压缩/清理策略和 `report_artifacts`，并把 full-regression 的本机 `evidence_root`/`working_directory`/`log` 视为 diagnostic metadata；CI 已跑该工具的单元测试。剩余：retention review 和历史 evidence 清理仍未完成。
- [ ] 治理 OpenSpec/validation 复杂度：归档或关闭过期 active changes，区分 lightweight release gate、developer smoke gate 和 full-regression gate；默认阅读入口只指向当前 roadmap、quickstart、coverage/capability report 和 milestone evidence，不让 1000+ evidence 文件或长 OpenSpec 历史成为新手入口。
- [x] 收窄公开叙述：README、路线图和 evidence summary 必须区分 L1 native-build baseline、candidate generation、accepted semantic pass；不能把 native-build catalogue 写成真实项目自动翻译完成。入口 README、路线图和路由/evidence 文档已明确 native-build catalogue 只是原生 C 构建基线，不等价于自动翻译证据。
- [x] 标明 showcase 边界：`flashDB_rust` 当前属于手写安全实现/验证基线，不能被当作自动翻译产物；任何对外展示都必须区分 handwritten implementation、translator-generated candidate、accepted evidence 和 semantic pass。FlashDB skeleton/milestone 文档和路由文档已补充该边界。
- [ ] 落地 L0-L4 路由治理：区分 catalogue/native baseline、translation route signal 和 semantic acceptance；L0 只代表 deterministic 0-token candidate signal，L1 包含 native C baseline，也可在当前 route policy 中表示非 scalar typed IR candidate signal，L2 代表候选编译 + unsafe/diff 证据，L3 才能声明 named slice 语义通过，L4 是拒绝或 accepted-evidence-authoritative 边界。
- [x] 建立 fail-closed repair playbook：每个 L4/refused 或 blocked slice 必须输出 source span、IR feature gap、oracle/fixture gap、可尝试路线（typed IR/C2Rust/LLM/manual）、最小下一步测试和人工介入点；没有这些字段时不得把拒绝包装成“已治理”。已闭环：`auto_migrate.py` 的 route-refused 和 rustc-compile-blocked repair 都会写入 `ir_feature_gap`、`oracle_fixture_gap`、`candidate_routes`、`smallest_next_test` 和 `human_intervention_point`；`blocked-repairs.schema.json`/example 已把这些字段合同化；`validate_auto_translation_evidence.py` 会校验 L4/refused repair playbook；`real-fdb-calc-crc32` 的 L4 accepted-evidence-authoritative repair evidence 已刷新并保留 real-clang lowering。边界：这只是 fail-closed 下一步治理，不代表 P0-176 的完整 candidate-selection router 或 P0-189 的能力/拒绝率 metrics report 已完成。
- [x] 禁止 clang-lowered typed IR 失败后无遥测地静默 fallback 到 legacy string translator：translator 原始 artifact 现在写入 `translation_source`，fallback 时记录 `selected`、`fallback_from`、`fallback_reason`，JSONL 追加 `translation_fallback`；`auto_migrate.py` 归一化后继续保留该字段。当前 route/profile evidence 已把 legacy fallback 降到 `compatibility_sources` / `compat:legacy-string-translator`，不会把它绑定成 `primary_candidate` 或 `selected_candidate_id`。
- [ ] 降级并退役 legacy string translator：把它标成 compatibility-only candidate source，默认 route/metrics 中单独计数，禁止把它称为 parser 或 typed-IR success；当 no-clang fixture replay 与真实 clang lane 覆盖最小切片后，从 primary candidate path 中移除，只保留诊断或历史 evidence 兼容入口。进展：`auto_migrate.py` 已把 legacy 字符串翻译候选改为 `compat:legacy-string-translator` / `compatibility_rust_draft` / `compatibility_only`，并拆到 `compatibility_sources`；`primary_candidate` 保持 unknown，`selected_candidate_id` 不再允许指向 legacy；validator 和 schema 已拒绝 legacy 冒充主候选；`evidence_governance.py` 已在默认 inventory 中按 kind/role/compatibility-only 单独统计候选来源。剩余：旧 evidence 兼容审计和 Rust crate 默认 legacy draft generation path 的最终诊断化/退役。
- [x] 把 route metadata 的最小候选清单做实为 provenance：`auto_migrate.py` 现在在 route/profile evidence 中写入 `selection_policy.stage=post_generation_provenance`、`selected_candidate_id` 和 `candidate_set`，覆盖 primary Rust draft、typed-IR signal 和 `c2rust-baseline` context；validator 会拒绝 id 漂移、C2Rust baseline 冒充语义来源和 candidate `semantic_pass=true`。
- [ ] 把 route metadata 升级成真实 candidate-selection layer。当前 `candidate_set` 是后生成阶段清单，`selection_policy.full_router=false`；后续 route governance 仍需 score/hard gate、fallback chain 优先级、refusal reason、validation gate 汇总，并接入 C2Rust/LLM 候选调度。
- [ ] 明确 out pointer 语义边界：safe API 可以把单值 `out[0] = value` 映射成返回值/report 字段；typed IR generic candidate 优先保留为 `&mut [T]` 写入；null、alias/noalias、multi-pointer、inout pointer 必须分别有 negative test 或 fail-closed 证据。进展：typed IR 已增加 nullable mutable pointer 写入负例；当 `int *out` 参与 null comparison 后再尝试 `out[0] = value`，emitter 会 fail-closed，拒绝把 nullable mutable out pointer 降成 `&mut [T]`。同时新增多 mutable pointer 写入负例：一个函数里多个 `int *` 参数都作为写目标时，没有 alias/noalias 证明会 fail-closed，而单一 mutable out pointer 正向路径保持可用。
- [ ] 标记第一个外部可评估 Milestone：在上述 CI 和文档边界稳定后打 tag/release，release notes 写清 commit、验证命令、evidence manifest hash、competition profile hash、支持子集、non-goals 和已知拒绝项，不能把 named slice 结论扩大到项目级。
- [ ] 给 milestone 增加人工/外部 review gate：release 前至少完成一次 reviewer checklist，覆盖架构分层、unsafe ledger、测试覆盖矩阵、真实切片 evidence、公开 claim 边界和已知拒绝项；没有 review 记录时只能标为 internal preview。

### P1: 扩大语法和内存模型覆盖

- [ ] 继续扩 generic typed IR emitter，而不是恢复 crc32/FlashDB 特例：已初始化 record local copy、按值 record dot-field compound assignment、statement 位置按值 record dot-field inc/dec、唯一具名完整直接标量字段清单下的 whole-record return、readonly `const struct T *p` 的简单 `p->scalar_field` 读、readonly record pointer `p == NULL`/`p != NULL` presence check、flow-sensitive null-guarded `p->scalar_field` read，以及单 pointer 参数下 mutable `struct T *p` 的直接 `p->scalar_field = scalar`、简单 standalone `p->scalar_field += scalar`、同字段 definite write 后 `p->scalar_field` 读、会继续执行路径都写同字段的 direct if-return 分支读和 statement 位置 `p->scalar_field++` / `--p->scalar_field` 已进入候选子集；后续优先做多 pointer alias/noalias proof、value-position/复杂 target/field inc-dec、direct if-return 之外更深的 path-sensitive facts，以及更强的 layout/ABI evidence 证明。
- [ ] 设计组合式 side-effect expression lowering：把 sequence point、求值顺序、value-position/statement-position、`++`/`--`、deref/index/member/call side effect 作为可组合 IR/emitter 规则建模；当前按整段语句形状匹配的 helper 只能作为过渡实现，每个迁移步骤都要有 red/green 测试和 fail-closed reason。
- [ ] 设计 alias/noalias 与 pointer escape 模型：把 readonly slice、mutable out slice、nullable pointer、unknown alias、volatile/hardware register 分成可证明路径和 L4 拒绝路径。
- [ ] 完成 integer conversion 纪律：所有 clang `ImplicitCastExpr`、integer promotion、usual arithmetic conversions、narrowing/truncation 都要在 IR 中显式可见。
- [ ] 扩控制流：`switch`/`goto` 先进入 CFG 证据和 fail-closed classifier，再考虑 relooper 和 Rust candidate。
- [ ] 扩真实切片池：从 FlashDB、libuv、zlib-ng 等项目挑选更多非玩具函数，要求每个切片都有 C oracle、Rust replay、diff 和 negative diff；FlashDB 切片必须绑定 translator-generated candidate，不能只用 `flashDB_rust` 手写 skeleton 当自动翻译证据。
- [ ] 建立生成式能力/拒绝率 metrics artifact 和 report command：从 route/profile/final-verification evidence 聚合 C construct、route level、candidate source、target、slice、generated/blocked/refused/accepted、失败原因、人工介入点、unsafe ratio、fixture case count、negative diff 覆盖和性能 smoke 状态；每个外部可评估 milestone 必须发布该报告，用这些数据约束公开叙述，不能只列 native-build catalogue。
- [ ] 把性能 smoke 前移到真实切片扩展：每个新增 L3 named slice 至少记录一个轻量 benchmark/performance-smoke 或明确 `performance_not_claimed`；完整 performance regression gate 仍属于 Phase 4。
- [ ] 建模嵌入式/平台依赖边界：FlashDB、RTOS、文件系统、flash 断电恢复、volatile/硬件寄存器和多线程/中断交互必须通过 mockable platform contract、host simulation、target evidence 或 L4 refusal 处理，不能靠普通 host fixture 默认代表。
- [ ] 制定 FlashDB FFI/C ABI/硬件路线：`ffi.rs` 不能长期只保留 placeholder；C ABI、on-disk layout、FAL/RTOS/Zephyr/hardware backend、错误/日志接口和同步/断电语义必须各自有 OpenSpec change、unsafe ledger、target evidence 或明确 deferred/L4 refusal，且不得用 host skeleton 测试替代 target evidence。

### P2: Agent/LLM 与长期研究路线

- [ ] LLM 只作为候选源，不作为事实源：AI candidate manifest 必须记录 provider/model/version 或等价标签、prompt scope、输入 artifact hash、输出 hash、是否应用、接受/拒绝 gate。
- [ ] 增加模型变更影响评估：维护小型 golden slice 回归集，同一输入在不同模型/版本下的候选差异必须被记录，并由验证门禁裁决；provider/model/prompt/input hash 变化只能使 AI candidate/cache 失效，不能改变 C oracle ground truth。
- [ ] 保留并实装 C2Rust baseline/repair 路线：作为 L2 候选生成和对照来源，但输出必须经过相同验证，不允许绕过 fail-closed；下一阶段至少要让一个真实 slice 产生 C2Rust output，记录 output path/status/sha256，并在 candidate set 中保持 `candidate_context_only` 或明确的 validation status，不能长期只有 skipped。
- [ ] 在 P0 语义稳定后再做多候选 router：把 L0 deterministic recipes、L1 generic typed IR、L2 C2Rust baseline/repair、L3 LLM candidate、L4 refuse 汇入同一个可审计 decision object，带 score 或 hard gate。这不能替代 C oracle，也不能让任何候选绕过共同 validation pipeline。
- [ ] 发布量化评估和案例报告：每个 milestone 都应给出真实项目/函数数、accepted/refused/blocked 比例、主要失败类别、平均人工介入点、性能 smoke 结果、unsafe 统计、可复现命令、evidence hash、社区复核状态和已知 non-goals；同时加入竞品/基线对比，至少比较 raw C2Rust、C2Rust+repair、当前 typed-IR route、LLM candidate 和手写参考实现的生成率、编译率、accepted 率、人工介入点、unsafe/性能边界；没有这些数据时只能称为研究原型/受限 MVP。
- [ ] 建立开源反馈循环：外部可评估 milestone 前补 `CONTRIBUTING`/issue template/review checklist 或等价文档，记录 review/PR/issue 反馈入口；社区指标不能当能力证明，但没有公开反馈记录时不得把 release 写成成熟生产工具。
- [ ] 降低单一维护者风险：外部 milestone 前补 CODEOWNERS 或等价 ownership 文档、reviewer rotation、issue triage 规则和 release checklist；关键验证命令、证据生成、路由决策和发布流程不得只依赖单个维护者或单次 Codex 会话记忆。
- [ ] 补新手 quickstart：README 或 `docs/quickstart` 必须提供 10-15 分钟最小复现路径，包含环境前提、competition Linux/CI 命令、可选 PowerShell 本机命令、第一条可验证 slice、预期 artifacts、常见失败和边界说明；不能让新用户从 `CONTEXT.md` 或历史 evidence 反推入口。
- [ ] 把 CFG/SSA/MIR/LLVM/self-hosting 等研究路线放在长期 backlog；在 P0 CI、模块拆分、真实切片语义通过率稳定前，不把它们作为主线开发。

## 5. 当前核心原则

1. **C oracle 是唯一 ground truth**。typed IR、clang lowering、Rust candidate 都只是描述和候选。
2. **Fail-closed**。不确定时拒绝翻译，记录原因，不假装成功。
3. **证据链可审计**。每一步决策都有 machine-readable evidence，受 validator 交叉校验。
4. **Route 只管候选路径**。语义接受由 validation profile + gates 决定。
5. **IR 描述 C，不预测 Rust**。Rust 的类型推断、ownership 推断是 lowering 层的责任。
6. **禁止恢复专用 fallback**。旧 crc32 模板、canned recognizer 已删除，不能重新引入项目专用代码。
7. **坦诚的边界比夸大的 demo 可信**。所有文档必须诚实列出"现在支持"和"显式不支持"。
