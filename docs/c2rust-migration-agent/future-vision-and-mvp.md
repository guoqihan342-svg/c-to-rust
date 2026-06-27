# 未来愿景与 MVP 路线

本文是中文主文档。英文镜像见 `future-vision-and-mvp.en.md`。

## 1. 目标

构建一个从 `input.c` → `c2rust-migrator` → `output.rs` 的端到端 MVP pipeline。当前已完成第一阶段证明（FlashDB crc32 能经真实 clang AST lowering + typed IR + generic emitter 生成可编译 Rust candidate），但离工业级 C→Rust 翻译器还有大量缺口。

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

- [x] 真实 clang AST dump 解析（`clang_frontend.rs`）
- [x] typed IR 数据结构（`IrFunction` / `IrStmt` / `IrExpr` / `IrType`）
- [x] generic typed IR emitter（标量 + 控制流 + pointer slice 子集）
- [x] readonly global const array 支持
- [x] route decision 和 validation profile 证据绑定
- [x] C oracle harness 草稿生成
- [x] Rust replay 执行和 diff gate
- [x] 旧 crc32 特例代码已删除
- [x] FlashDB crc32 通过 accepted evidence semantic pass

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
- [ ] 从 `validation/projects.json` 中选择 5+ 项目跑完整 L1→L3
- [ ] usual arithmetic conversions 的显式模型
- [ ] struct field write（有 alias/noalias 证明）
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

## 4. 当前核心原则

1. **C oracle 是唯一 ground truth**。typed IR、clang lowering、Rust candidate 都只是描述和候选。
2. **Fail-closed**。不确定时拒绝翻译，记录原因，不假装成功。
3. **证据链可审计**。每一步决策都有 machine-readable evidence，受 validator 交叉校验。
4. **Route 只管候选路径**。语义接受由 validation profile + gates 决定。
5. **IR 描述 C，不预测 Rust**。Rust 的类型推断、ownership 推断是 lowering 层的责任。
6. **禁止恢复专用 fallback**。旧 crc32 模板、canned recognizer 已删除，不能重新引入项目专用代码。
7. **坦诚的边界比夸大的 demo 可信**。所有文档必须诚实列出"现在支持"和"显式不支持"。
