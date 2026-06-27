# c-to-rust 翻译器加强分析

> 日期：2026-06-27
> 基于当前 `codex/flashdb-rust-skeleton` 分支代码审查
> 英文镜像：`translator-strengthening-analysis.en.md`

## 一、当前判断

这份分析的核心判断仍成立：**验证体系已经比翻译器能力更强，当前主要瓶颈是 typed IR 翻译器继续追上门禁，而不是继续增加门禁。**

但早期版本里“先装 clang”“typed IR 指针参数完全卡住”“`fdb_calc_crc32` 还只能 L4/refused”这些判断已经过期。当前分支已经具备：

- native LLVM `clang` 真实 AST smoke，可从 `clang -ast-dump=json` 进入 `clang_frontend.rs`。
- `real-fdb-calc-crc32` 可经 clang-lowered typed IR + readonly globals 走到 `GenericTypedIr` candidate，并通过 rustc smoke。
- readonly integer pointer 参数可发射为 Rust slice，例如 `const uint32_t *p -> p: &[u32]`。
- readonly pointer `NULL` presence check 可发射为 `Option<&[T]>` 加 `.is_none()` / `.is_some()`。
- 普通 readonly pointer direct deref read 已可发射为 slice 0 下标，例如 `return *p; -> return p[0usize];`。
- 窄化 readonly pointer offset-deref read 已可发射为 slice 下标，例如 `return *(p+i); -> return p[i as usize];`，也覆盖 `*(i+p)` 和 literal offset。
- clang 前端已支持固定宽度整数标量 typedef aliases：`int8_t`、`int16_t`、`int32_t`、`int64_t`、`uint8_t`、`uint16_t`、`uint32_t`、`uint64_t`。

这些都是 **candidate generation**。它们不等于真实 FlashDB slice 已经 `semantic_pass=true`。

## 二、双路径现状

| 路径 | 代码 | 当前定位 |
|------|------|----------|
| 字符串 translator | `crates/c2r-translator/src/lib.rs` | legacy/demo/bounded fixtures；不应继续堆复杂 C 语义；crc32 byte-cursor canned route 已删除，遇到未建模副作用应 fail closed |
| typed IR translator | `crates/c2r-translator/src/typed_ir.rs` + `clang_frontend.rs` | 当前主线；从真实 clang AST lowering 到 compact skeleton，再到 typed IR，再由 generic emitter 生成 Rust candidate |

当前 typed IR route 只有两类：

- `GenericTypedIr`：generic emitter 生成了 Rust candidate。
- `Unsupported`：fail closed，无 Rust candidate，保留 reason 和 route metadata。

`GenericTypedIr` 只回答“能否生成候选 Rust 草案”，不决定 `semantic_pass`。

## 三、P0 瓶颈更新

### P0.1 typed IR emitter 子集仍太窄

已经支持的关键增量：

- 标量声明、赋值、return、`if`、`while`。
- 普通 compound body 和 scoped `ForStmt` init 中多 `VarDecl` declaration statement 展开，例如 `int a = 1, b = 2;` 和 `for (int i = 0, j = 0; i < limit; i++)`。
- 每次读取前都能证明已有赋值的无初始化标量局部声明，例如 `int tmp; tmp = 7; return tmp;`。
- 标量整数 `+ - * / % & | ^ << >>`、signed unary `-`。
- clang-lowered simple scalar compound assignment family，包含 simple variable target 上 clang-proven integer promotion/truncation 的窄化路径。
- declaration initializer、assignment RHS 和 return value 中的 clang-preserved value-position integer implicit casts。
- comparison 条件位置和窄 value-position C `int` 0/1 materialization。
- logical not 条件位置和窄 value-position C `int` 0/1 materialization。
- condition-position 和窄 value-position short-circuit `&&` / `||`，value-position 会 materialize 成 C `int` 0/1。
- 纯整数 value-position `ConditionalOperator` / `?:`，通过 lazy `IrExpr::Conditional` 发射。
- 带显式 typed IR scope 的窄化 `ForStmt`，覆盖 simple scalar declaration/assignment init（含多个简单 `VarDecl` declarator）、condition、step 和 body，并发射为 Rust block + `while` candidate。
- readonly pointer slice 参数、直接 `NULL` presence check、直接 readonly `*p` read、窄化 readonly `*(p+i)` / `*(i+p)` read。
- 固定宽度整数标量 typedef aliases lowering 到 typed IR，并发射 Rust `i8` / `i16` / `i32` / `i64` / `u8` / `u16` / `u32` / `u64`。
- readonly global const integer array、局部固定长度整数数组读写。
- bounded direct identifier calls。
- byte cursor `*p++` 的窄化 prelude 路径。

仍缺失的 P0 能力：

- 当前显式整数 cast 和 compound-assignment promotion guard 之外的完整 usual scalar conversions 分类。
- pointer write / alias / ownership 模型。

### P0.2 clang 前端不再是“未打通”，但覆盖仍窄

真实 clang smoke 已跑通，所以现在问题不是“装 clang”，而是 clang skeleton / typed IR 支持的 AST 子集仍窄：

- `CompoundAssignOperator` 已支持 standalone simple scalar variable target；当 target/result 一致、compute lhs/result 一致且所有相关类型都是受支持整数时，也支持 clang-proven integer promotion/truncation。
- `&&` / `||` 已支持 condition-position 和窄 value-position；value-position 的 return value、assignment RHS 和 declaration initializer 已覆盖。
- 普通 compound body 和 `ForStmt` init 中的 `DeclStmt` 已能把多个简单 `VarDecl` 按源码顺序展开。
- 无 initializer 的标量局部声明现在可在 generic typed IR route 中发射，但前提是保守 assignment-before-read guard 能证明每次读取前都已初始化。
- 普通 `ConditionalOperator` 已支持纯整数 value-position；GNU `BinaryConditionalOperator` 仍 fail closed。
- `ForStmt` 已支持窄化 scoped lowering：init 只接受简单 scalar `DeclStmt`（含多个简单 `VarDecl` declarator）或 assignment，condition 复用当前 condition emitter，step 只接受简单 assignment/compound assignment/postfix inc-dec，body 复用现有 statement 子集；`continue` / `break` / `goto` / `switch`、condition variable slot、空 condition/step 和复杂 init/step 仍 fail closed。
- `Deref(Binary(Add, p, i))` 已在 readonly integer pointer + 无副作用整数 index 条件下规范化为 bounded slice index；其他 pointer arithmetic 仍未建模。
- `type_from_qual_type()` 已能识别 fixed-width integer typedef aliases；raw `signed char` / `short` / `long long` 这类目标相关 spelling、plain `char`、plain `long` 和完整 usual scalar conversions 仍不放开。
- struct/record、field access、switch/goto/do-while 仍未进入安全 emitter。

## 四、路线建议

当前最合适的顺序不是回到 FlashDB 专用模板，而是继续按 typed IR 小切片推进：

1. **usual conversions 分类**：继续把可证明的 integral cast 和 compute-type 规则固化成显式 guard，不要一次性声明完整 C conversion。
2. **struct / memory model 设计**：flat struct、field access、pointer write、alias/ownership 需要独立设计和验证 gate。
3. **更宽控制流**：在 `ForStmt` 已有 scoped MVP 后，再设计 `break` / `continue` / `do-while` / `switch` / `goto` 的明确语义和验证边界。

## 五、边界

仍应 fail closed：

- 任意 pointer comparison、pointer truthiness、nullable pointer null check 后继续 index/deref。
- raw `signed char` / `short` / `long long` 这类目标相关 spelling、plain `char`、plain `long`、target ABI 宽度推断、完整 integer promotion/usual scalar conversions。
- 除 readonly integer pointer + 无副作用整数 index 的窄化 `*(p+i)` read 外，其他 pointer arithmetic 仍 fail closed。
- condition-position `?:`、expression-statement `?:`、GNU omitted-middle `a ?: b`，以及 then/else 分支内含 call/inc/dec/post-increment/assignment/comma 副作用的 conditional 仍 fail closed。
- short-circuit operand 中含 call/inc/dec/side effect、pointer truthiness、float truthiness、unsupported type 或需要完整 usual scalar conversions 的场景仍 fail closed。
- 非简单 target、value-position 使用、unsupported compute/result 类型组合、pointer arithmetic、floating-point、volatile 或复杂 RHS side effect 的 compound assignment 仍 fail closed。
- `ForStmt` 中的 `continue` / `break` / `goto` / `switch`、condition variable slot、空 condition/step、condition 中 call/inc/dec/side effect、复杂 init/step、非 simple scalar init/step 或 step 里的 prefix inc-dec 仍 fail closed。
- `ForStmt` init 任一 declarator 的 unsupported type/initializer、VLA/incomplete array、重复符号仍 fail closed。
- 无初始化局部变量在赋值前读取、首次赋值读取自身、只在单侧分支或循环体中赋值、address-taken initialization、间接写入和 alias write 仍 fail closed。
- mutable pointer、pointer writes、未建模 alias write。
- function pointer callee、复杂 call side effects、nested calls in conditions。
- volatile、硬件寄存器、跨线程/中断语义。
- 未建模宏副作用、控制流不可恢复、测试 oracle 不足。
- semantic acceptance 未经完整 C/Rust oracle、negative diff、unsafe ledger、final verification 证明。

## 六、结论

方案方向是对的：**验证门禁已经足够严，核心工作要继续补 typed IR translator。**

但 P0 表述要更新：现在不是“先装 clang / 先让 pointer 不 fail”，也不是“`*(p+i)` 仍完全缺失”，而是“在真实 clang 已通的基础上，继续扩 generic typed IR 的可证明子集”。FlashDB 仍是重要用例和门禁样本，但不能反过来把项目写成 FlashDB 专用翻译器。
