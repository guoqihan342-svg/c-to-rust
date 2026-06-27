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
- **比赛环境配置是适配参考和证据 profile**：`config/competition-env/environment.json` 是当前默认比赛环境配置入口；开发时参考其中的 Ubuntu、Rust、Python、Node、gcc、镜像源和缺失工具约束。本机不需要强行复刻该环境，但新增默认构建、测试和验证路径不能违反这些约束；`validation/environment-profiles/...` 只作为兼容入口。
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
- [ ] 指针/alias-sensitive struct field write（有 alias/noalias 证明；非 pointer 的简单按值 `p.x = value` 和 standalone statement 位置 `p.x++` / `++p.x` / `p.x--` / `--p.x` 已进入 typed IR candidate 子集）
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
- [ ] MIRI validation（Rust UB 检测，不作为 C UB 证明）

## 4. P0/P1/P2 待办（默认执行顺序）

### P0: 先把当前 MVP 变成可信、可维护的翻译器核心

- [ ] 拆分 `crates/c2r-translator/src/lib.rs`：当前仍约 3.7k 行，先做行为保持拆分，把 CLI/manifest、旧字符串 translator、typed IR route、artifact 写入、unsafe/metadata 统计等责任拆到子模块；已完成公开 model schema 拆分、artifact/IO leaf helper（`write_json_file`、`write_text_file`、`translation_events_jsonl`）拆分、core translation artifact writer helper（`write_core_translation_artifacts`）拆分、feature-gated clang dry-run artifact writer（`write_clang_dry_run_artifact`）拆分，以及 clang lowering report artifact writer cluster（`write_clang_lowering_report_artifact`、`typed_ir_candidate_evidence`、`readonly_global_summary`）拆分，crate root API 保持兼容；仍待 CLI/manifest orchestration、legacy string translator、typed IR route、`write_translation_artifacts` public orchestration、unsafe/metadata 统计、parser/evidence builder/emitter 的后续拆分；拆分提交必须保持现有测试通过。
- [ ] 统一 clang 前端事实：当前主路径是 `clang -Xclang -ast-dump=json -fsyntax-only`，`LIBCLANG_PATH`/libclang dry-run skeleton 只能保留为诊断占位或删除，不能让读者误解为真实 libclang 解析路径。
- [ ] 建立 translator + validation 的核心 CI：至少覆盖 `crates/c2r-translator` 单测、typed-ir/clang-frontend feature 组合、核心 validation 工具测试、`git diff --check`；不能只依赖 `flashDB Rust CI`。
- [ ] 把 unsafe budget 做成持续监控：默认覆盖 first-party non-test Rust crate（至少 `crates/c2r-translator`、`flashDB_rust`、`validation/l2_slices`），报告写明扫描范围、分母、unsafe hit、比例和登记状态；CI 检查比例低于 10%，新增 unsafe 必须登记来源、理由和验证门禁。
- [ ] 收窄公开叙述：README、路线图和 evidence summary 必须区分 L1 native-build baseline、candidate generation、accepted semantic pass；不能把 native-build catalogue 写成真实项目自动翻译完成。
- [ ] 落地 L0-L4 路由治理：区分 catalogue/native baseline、translation route signal 和 semantic acceptance；L0 只代表 deterministic 0-token candidate signal，L1 包含 native C baseline，也可在当前 route policy 中表示非 scalar typed IR candidate signal，L2 代表候选编译 + unsafe/diff 证据，L3 才能声明 named slice 语义通过，L4 是拒绝或 accepted-evidence-authoritative 边界。
- [ ] 明确 out pointer 语义边界：safe API 可以把单值 `out[0] = value` 映射成返回值/report 字段；typed IR generic candidate 优先保留为 `&mut [T]` 写入；null、alias/noalias、multi-pointer、inout pointer 必须分别有 negative test 或 fail-closed 证据。
- [ ] 标记第一个外部可评估 Milestone：在上述 CI 和文档边界稳定后打 tag/release，release notes 写清 commit、验证命令、evidence manifest hash、competition profile hash、支持子集、non-goals 和已知拒绝项，不能把 named slice 结论扩大到项目级。

### P1: 扩大语法和内存模型覆盖

- [ ] 继续扩 generic typed IR emitter，而不是恢复 crc32/FlashDB 特例：已初始化 record local copy、按值 record dot-field compound assignment、statement 位置按值 record dot-field inc/dec 和唯一具名完整直接标量字段清单下的 whole-record return 已进入候选子集；后续优先做 pointer-aware record access、value-position/复杂 target/pointer-alias-sensitive update field write，以及更强的 layout/ABI evidence 证明。
- [ ] 设计 alias/noalias 与 pointer escape 模型：把 readonly slice、mutable out slice、nullable pointer、unknown alias、volatile/hardware register 分成可证明路径和 L4 拒绝路径。
- [ ] 完成 integer conversion 纪律：所有 clang `ImplicitCastExpr`、integer promotion、usual arithmetic conversions、narrowing/truncation 都要在 IR 中显式可见。
- [ ] 扩控制流：`switch`/`goto` 先进入 CFG 证据和 fail-closed classifier，再考虑 relooper 和 Rust candidate。
- [ ] 扩真实切片池：从 FlashDB、libuv、zlib-ng 等项目挑选更多非玩具函数，要求每个切片都有 C oracle、Rust replay、diff 和 negative diff。

### P2: Agent/LLM 与长期研究路线

- [ ] LLM 只作为候选源，不作为事实源：AI candidate manifest 必须记录 provider/model/version 或等价标签、prompt scope、输入 artifact hash、输出 hash、是否应用、接受/拒绝 gate。
- [ ] 增加模型变更影响评估：维护小型 golden slice 回归集，同一输入在不同模型/版本下的候选差异必须被记录，并由验证门禁裁决；provider/model/prompt/input hash 变化只能使 AI candidate/cache 失效，不能改变 C oracle ground truth。
- [ ] 保留 C2Rust baseline/repair 路线：作为 L2 候选生成和对照来源，但输出必须经过相同验证，不允许绕过 fail-closed。
- [ ] 把 CFG/SSA/MIR/LLVM/self-hosting 等研究路线放在长期 backlog；在 P0 CI、模块拆分、真实切片语义通过率稳定前，不把它们作为主线开发。

## 5. 当前核心原则

1. **C oracle 是唯一 ground truth**。typed IR、clang lowering、Rust candidate 都只是描述和候选。
2. **Fail-closed**。不确定时拒绝翻译，记录原因，不假装成功。
3. **证据链可审计**。每一步决策都有 machine-readable evidence，受 validator 交叉校验。
4. **Route 只管候选路径**。语义接受由 validation profile + gates 决定。
5. **IR 描述 C，不预测 Rust**。Rust 的类型推断、ownership 推断是 lowering 层的责任。
6. **禁止恢复专用 fallback**。旧 crc32 模板、canned recognizer 已删除，不能重新引入项目专用代码。
7. **坦诚的边界比夸大的 demo 可信**。所有文档必须诚实列出"现在支持"和"显式不支持"。
