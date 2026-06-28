# 未来愿景与 MVP 路线

本文是中文主文档。英文镜像见 `future-vision-and-mvp.en.md`。

## 1. 目标

构建一个从 `input.c` → `c2rust-migrator` → `output.rs` 的端到端 MVP pipeline。当前已完成第一阶段证明（FlashDB `real-fdb-calc-crc32` named slice 能经真实 clang AST dump lowering + typed IR + generic emitter 生成可编译 Rust candidate，并通过 accepted evidence 绑定语义门禁），但离工业级 C→Rust 翻译器还有大量缺口。

边界必须说清楚：`validation/evidence/*/l1-native-build.json` 只证明原始 C 项目在固定环境中可构建或可烟测，不证明 Rust 翻译成功。当前真实自动翻译能力仍主要集中在经过挑选的函数切片；大项目 evidence catalogue 是迁移输入池和基线，不是"已能翻译真实大项目"的证据。

## 1.1. 待办执行规则

从本文开始，后续核心翻译开发默认按本文件的 P0/P1/P2 待办推进；除非出现阻塞 bug，优先顺序不再被临时 demo 或单个项目牵着走。

- **先扩翻译能力，再扩仪式**：新增 schema、manifest、gate 前，必须能说明它解决了具体翻译风险、验证误判或复现问题。
- **FlashDB 只是用例**：可以继续用 FlashDB 做回归样本，但不能写 FlashDB 专用 recognizer、模板或特判路径。
- **候选生成不等于语义接受**：typed IR、C2Rust、LLM 和手写规则都只是 candidate source；语义通过只由 C oracle、Rust replay、diff、negative diff、unsafe ledger 和 final verification 决定。
- **C oracle 也有边界**：oracle 只能证明固定 source commit、fixture、编译器/flags、target ABI、平台模型和 observable output contract 下的行为；未定义行为、实现定义行为、硬件/RTOS/volatile 副作用和测试覆盖不足必须显式记录，不能被"通过测试"掩盖。
- **C2Rust baseline 必须可追溯**：route/profile 中的 C2Rust candidate 只能作为 `candidate_context_only`，必须绑定 baseline manifest；当 baseline 真正生成输出时，还必须绑定 output path/status/sha256，并由 validator 拒绝漂移。
- **比赛环境配置是适配参考和证据 profile**：`config/competition-env/environment.json` 是当前默认比赛环境配置入口；开发时参考其中的 Ubuntu、Rust、Python、Node、gcc、镜像源和缺失工具约束。本机不需要强行复刻该环境，但新增默认构建、测试和验证路径不能违反这些约束；`validation/environment-profiles/...` 只作为兼容入口。
- **默认路径必须暴露真实能力**：无 clang 的默认 CI/比赛路径不能把 legacy string translator 的成功包装成 typed-IR 成功；typed IR 因 `CLANG_PATH` 或工具缺失未运行时，evidence、metrics 和公开叙述必须明确标记 unavailable/compatibility fallback。
- **交接文档要短而可审计**：`CONTEXT.md` 只能作为当前状态、最近验证和下一步的 handoff；长会话日志要拆分或归档，不能作为 release 文档、外部评估入口或能力证明。
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

- [ ] 拆分 `crates/c2r-translator/src/lib.rs`：当前仍约 69 行，先做行为保持拆分，把 CLI/manifest、旧字符串 translator、typed IR route、artifact 写入、unsafe/metadata 统计等责任拆到子模块；已完成公开 model schema 拆分、artifact/IO leaf helper（`write_json_file`、`write_text_file`、`translation_events_jsonl`）拆分、core translation artifact writer helper（`write_core_translation_artifacts`）拆分、feature-gated clang dry-run artifact writer（`write_clang_dry_run_artifact`）拆分、clang lowering report artifact writer cluster（`write_clang_lowering_report_artifact`、`typed_ir_candidate_evidence`、`readonly_global_summary`）拆分、clang-lowered translation/evidence 私有模块（`clang_lowered_translation.rs`）拆分、legacy string translator 私有模块（`legacy_translation.rs`）拆分，以及 `write_translation_artifacts` public orchestration 拆分，crate root API 保持兼容；仍待 CLI/manifest orchestration、generic typed IR route、unsafe/metadata 统计、parser/evidence builder/emitter 的后续拆分；拆分提交必须保持现有测试通过。
- [x] 统一 clang 前端事实：当前主路径是 `CLANG_PATH` 调用 `clang -Xclang -ast-dump=json -fsyntax-only`；`--emit-clang-dry-run` artifact 现在标记 `artifact_kind=clang-dry-run`、`status=diagnostic_only`、`claim_boundary.role=diagnostic_only` 和 `active_frontend.kind=clang_ast_dump_json`，`LIBCLANG_PATH` 仅作为 `ignored_env_for_ast_dump`/`observed_libclang_path` 诊断元数据，不参与 lowering，也不表示真实 libclang 解析路径已启用。
- [x] 明确比赛环境 clang 路线：`config/competition-env/environment.json` 现在把 clang 声明为 optional capability/optional lane；默认构建、测试和验证不要求 clang。需要真实 clang AST dump typed-IR 路线时使用 `auto_migrate.py --competition-clang-lane`，该 lane 自动启用 `clang-lowering-report`，要求 `CLANG_PATH`，缺失时清晰失败；只传 `--emit-clang-lowering-report` 仍是 diagnostic opt-in，缺 clang 时写 unavailable 报告。
- [ ] 建立 no-clang typed-IR fixture replay CI：提交小型 clang AST JSON 或 skeleton fixture，使默认 CI 在没有 `CLANG_PATH` 时仍能跑 `AST JSON/skeleton -> typed IR -> generic emitter -> rustc/check` 回归；真实 clang lane 继续由 `--competition-clang-lane` 验证前端集成。手写 IR 单测不能替代这条回归。
- [x] 建立 translator + validation 的核心 CI：`.github/workflows/core-translator-validation-ci.yml` 现在覆盖 `crates/c2r-translator` 默认与 all-features 单测、核心 validation unittest、repo-level unsafe budget gate 和 `git diff --check`；触发路径包含 translator、validation tools/templates、`validation/l2_slices`、competition env 和 unsafe ledger，避免只依赖 `flashDB Rust CI`。
- [x] 在声明 checksum/hash 翻译覆盖前修复无符号整数模运算语义：typed IR 已对 C unsigned `+`、`-`、`*` 发射显式 `wrapping_add` / `wrapping_sub` / `wrapping_mul`，并用 debug/overflow-checks runtime 红测覆盖 `u32::MAX + 1`、`0u32 - 1` 和 unsigned multiply。signed overflow、division/modulo zero 和非法 shift count 仍是单独的 fail-closed/contract 问题。
- [ ] 明确 signed overflow/division/modulo/shift 的 UB contract：signed `+`/`-`/`*` 只有在 slice contract 或 compiler flags 明确声明 `-fwrapv`/二补码回绕 profile 时才允许发射 wrapping；否则必须 fail-closed 或记录 precondition。division/modulo zero、非法 shift count 和实现定义 signed shift 必须有 negative test、evidence 字段和 refusal reason，不能依赖 Rust debug/release 差异。
- [x] 把 unsafe budget 的最小持续监控接入 CI：`validation/tools/unsafe_budget.py` 默认覆盖 `crates/c2r-translator/src`、`flashDB_rust/src`、`validation/l2_slices/src`，输出扫描范围、分母行数、unsafe findings、比例、登记状态和 ledger 引用；`validation/unsafe-budget-ledger.json` 作为 repo-level 登记入口；核心 CI 以 `--max-ratio 0.10` 执行该 gate。
- [ ] 强化 C oracle/UB/平台边界：每个 accepted slice 必须记录 observable output、fixture 代表性、编译器和 flags、target ABI、endianness/word-size 假设、sanitizer/diagnostic 状态、已知 UB/implementation-defined 边界、硬件/RTOS/volatile 依赖是否被建模；证据不足时只能保留 candidate 或 blocked，不能升级为 semantic pass。
- [ ] 加强 unsafe ledger 治理粒度：登记项后续应扩展到 span、替代方案、覆盖测试、source evidence 和审核状态，而不是只依赖 path+category 的最小登记键。
- [ ] 收窄公开叙述：README、路线图和 evidence summary 必须区分 L1 native-build baseline、candidate generation、accepted semantic pass；不能把 native-build catalogue 写成真实项目自动翻译完成。
- [ ] 标明 showcase 边界：`flashDB_rust` 当前属于手写安全实现/验证基线，不能被当作自动翻译产物；任何对外展示都必须区分 handwritten implementation、translator-generated candidate、accepted evidence 和 semantic pass。
- [ ] 落地 L0-L4 路由治理：区分 catalogue/native baseline、translation route signal 和 semantic acceptance；L0 只代表 deterministic 0-token candidate signal，L1 包含 native C baseline，也可在当前 route policy 中表示非 scalar typed IR candidate signal，L2 代表候选编译 + unsafe/diff 证据，L3 才能声明 named slice 语义通过，L4 是拒绝或 accepted-evidence-authoritative 边界。
- [x] 禁止 clang-lowered typed IR 失败后无遥测地静默 fallback 到 legacy string translator：translator 原始 artifact 现在写入 `translation_source`，fallback 时记录 `selected`、`fallback_from`、`fallback_reason`，JSONL 追加 `translation_fallback`；`auto_migrate.py` 归一化后继续保留该字段，并在 `route_decision.candidate_generation.primary_candidate` 中绑定主候选来源。
- [ ] 降级并退役 legacy string translator：把它标成 compatibility-only candidate source，默认 route/metrics 中单独计数，禁止把它称为 parser 或 typed-IR success；当 no-clang fixture replay 与真实 clang lane 覆盖最小切片后，从 primary candidate path 中移除，只保留诊断或历史 evidence 兼容入口。
- [x] 把 route metadata 的最小候选清单做实为 provenance：`auto_migrate.py` 现在在 route/profile evidence 中写入 `selection_policy.stage=post_generation_provenance`、`selected_candidate_id` 和 `candidate_set`，覆盖 primary Rust draft、typed-IR signal 和 `c2rust-baseline` context；validator 会拒绝 id 漂移、C2Rust baseline 冒充语义来源和 candidate `semantic_pass=true`。
- [ ] 把 route metadata 升级成真实 candidate-selection layer。当前 `candidate_set` 是后生成阶段清单，`selection_policy.full_router=false`；后续 route governance 仍需 score/hard gate、fallback chain 优先级、refusal reason、validation gate 汇总，并接入 C2Rust/LLM 候选调度。
- [ ] 明确 out pointer 语义边界：safe API 可以把单值 `out[0] = value` 映射成返回值/report 字段；typed IR generic candidate 优先保留为 `&mut [T]` 写入；null、alias/noalias、multi-pointer、inout pointer 必须分别有 negative test 或 fail-closed 证据。
- [ ] 标记第一个外部可评估 Milestone：在上述 CI 和文档边界稳定后打 tag/release，release notes 写清 commit、验证命令、evidence manifest hash、competition profile hash、支持子集、non-goals 和已知拒绝项，不能把 named slice 结论扩大到项目级。

### P1: 扩大语法和内存模型覆盖

- [ ] 继续扩 generic typed IR emitter，而不是恢复 crc32/FlashDB 特例：已初始化 record local copy、按值 record dot-field compound assignment、statement 位置按值 record dot-field inc/dec、唯一具名完整直接标量字段清单下的 whole-record return、readonly `const struct T *p` 的简单 `p->scalar_field` 读、readonly record pointer `p == NULL`/`p != NULL` presence check、flow-sensitive null-guarded `p->scalar_field` read，以及单 pointer 参数下 mutable `struct T *p` 的直接 `p->scalar_field = scalar`、简单 standalone `p->scalar_field += scalar`、同字段 definite write 后 `p->scalar_field` 读、会继续执行路径都写同字段的 direct if-return 分支读和 statement 位置 `p->scalar_field++` / `--p->scalar_field` 已进入候选子集；后续优先做多 pointer alias/noalias proof、value-position/复杂 target/field inc-dec、direct if-return 之外更深的 path-sensitive facts，以及更强的 layout/ABI evidence 证明。
- [ ] 设计组合式 side-effect expression lowering：把 sequence point、求值顺序、value-position/statement-position、`++`/`--`、deref/index/member/call side effect 作为可组合 IR/emitter 规则建模；当前按整段语句形状匹配的 helper 只能作为过渡实现，每个迁移步骤都要有 red/green 测试和 fail-closed reason。
- [ ] 设计 alias/noalias 与 pointer escape 模型：把 readonly slice、mutable out slice、nullable pointer、unknown alias、volatile/hardware register 分成可证明路径和 L4 拒绝路径。
- [ ] 完成 integer conversion 纪律：所有 clang `ImplicitCastExpr`、integer promotion、usual arithmetic conversions、narrowing/truncation 都要在 IR 中显式可见。
- [ ] 扩控制流：`switch`/`goto` 先进入 CFG 证据和 fail-closed classifier，再考虑 relooper 和 Rust candidate。
- [ ] 扩真实切片池：从 FlashDB、libuv、zlib-ng 等项目挑选更多非玩具函数，要求每个切片都有 C oracle、Rust replay、diff 和 negative diff。
- [ ] 建立生成式能力/拒绝率 metrics artifact 和 report command：从 route/profile/final-verification evidence 聚合 C construct、route level、candidate source、target、slice、generated/blocked/refused/accepted、失败原因、人工介入点、unsafe ratio、fixture case count、negative diff 覆盖和性能 smoke 状态；每个外部可评估 milestone 必须发布该报告，用这些数据约束公开叙述，不能只列 native-build catalogue。
- [ ] 把性能 smoke 前移到真实切片扩展：每个新增 L3 named slice 至少记录一个轻量 benchmark/performance-smoke 或明确 `performance_not_claimed`；完整 performance regression gate 仍属于 Phase 4。
- [ ] 建模嵌入式/平台依赖边界：FlashDB、RTOS、文件系统、flash 断电恢复、volatile/硬件寄存器和多线程/中断交互必须通过 mockable platform contract、host simulation、target evidence 或 L4 refusal 处理，不能靠普通 host fixture 默认代表。

### P2: Agent/LLM 与长期研究路线

- [ ] LLM 只作为候选源，不作为事实源：AI candidate manifest 必须记录 provider/model/version 或等价标签、prompt scope、输入 artifact hash、输出 hash、是否应用、接受/拒绝 gate。
- [ ] 增加模型变更影响评估：维护小型 golden slice 回归集，同一输入在不同模型/版本下的候选差异必须被记录，并由验证门禁裁决；provider/model/prompt/input hash 变化只能使 AI candidate/cache 失效，不能改变 C oracle ground truth。
- [ ] 保留 C2Rust baseline/repair 路线：作为 L2 候选生成和对照来源，但输出必须经过相同验证，不允许绕过 fail-closed。
- [ ] 在 P0 语义稳定后再做多候选 router：把 L0 deterministic recipes、L1 generic typed IR、L2 C2Rust baseline/repair、L3 LLM candidate、L4 refuse 汇入同一个可审计 decision object，带 score 或 hard gate。这不能替代 C oracle，也不能让任何候选绕过共同 validation pipeline。
- [ ] 发布量化评估和案例报告：每个 milestone 都应给出真实项目/函数数、accepted/refused/blocked 比例、主要失败类别、平均人工介入点、性能 smoke 结果、unsafe 统计、可复现命令、evidence hash、社区复核状态和已知 non-goals；没有这些数据时只能称为研究原型/受限 MVP。
- [ ] 把 CFG/SSA/MIR/LLVM/self-hosting 等研究路线放在长期 backlog；在 P0 CI、模块拆分、真实切片语义通过率稳定前，不把它们作为主线开发。

## 5. 当前核心原则

1. **C oracle 是唯一 ground truth**。typed IR、clang lowering、Rust candidate 都只是描述和候选。
2. **Fail-closed**。不确定时拒绝翻译，记录原因，不假装成功。
3. **证据链可审计**。每一步决策都有 machine-readable evidence，受 validator 交叉校验。
4. **Route 只管候选路径**。语义接受由 validation profile + gates 决定。
5. **IR 描述 C，不预测 Rust**。Rust 的类型推断、ownership 推断是 lowering 层的责任。
6. **禁止恢复专用 fallback**。旧 crc32 模板、canned recognizer 已删除，不能重新引入项目专用代码。
7. **坦诚的边界比夸大的 demo 可信**。所有文档必须诚实列出"现在支持"和"显式不支持"。
