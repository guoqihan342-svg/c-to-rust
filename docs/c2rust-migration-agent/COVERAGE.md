英文镜像见 `COVERAGE.en.md`。

# C 构造覆盖清单

本文诚实列出当前 typed IR + clang frontend + generic emitter 管线"已支持"和"显式不支持"的 C 语言构造。英文镜像见 `COVERAGE.en.md`。

> 原则：坦诚的边界比夸大的 demo 可信。本文件由最新代码状态手动整理，若有疏漏以 `crates/c2r-translator/tests/bounded_translation.rs` 中的 fail-closed 测试为准。
>
> 矩阵门禁：本人工清单只是阅读入口；覆盖声明现在由 `validation/translator-coverage-matrix.json` 和 `validation/tools/translator_coverage_matrix.py` 约束，要求代表性正例、负例、fail-closed reason、runtime/evidence 维度和可解析链接。该矩阵不是完整 C99/C11 支持率，也不是语义通过证明。

## 类型系统

| C 类型 | 状态 | 说明 |
|--------|------|------|
| `int` | 已支持 | 无 target profile 时按既有 C baseline 映射为 `i32`；profile-aware clang lowering 会绑定 `build_profile.target.int_width`，避免 `sizeof(int)` 等 ABI 语义固定猜成 32-bit |
| `unsigned int` / `uint32_t` | 已支持 | `uint32_t` 固定映射为 `u32`；`unsigned int` 无 target profile 时按既有 C baseline 映射为 `u32`，profile-aware clang lowering 会绑定 `build_profile.target.int_width` |
| `uint8_t` / `unsigned char` | 已支持 | 映射为 `u8` |
| `int8_t` / `signed char` | 已支持 | 映射为 `i8` |
| `int16_t` | 已支持 | 映射为 `i16` |
| `uint16_t` | 已支持 | 映射为 `u16` |
| `int64_t` / `uint64_t` | 已支持 | 映射为 `i64` / `u64` |
| `size_t` | 窄支持 | 仅在 `build_profile.target` 提供明确 target ABI 宽度证据时映射为 `usize`；无 profile 的 clang frontend 仍 fail-closed，禁止猜成固定 64-bit |
| `enum T` | 窄支持 | 仅完整 `EnumDecl`、唯一命名、enum 常量值可由显式非负 `int` `ConstantExpr.value` 或同一 `EnumDecl` 声明顺序从已知前值推导、值可放入 `i32`，且 `build_profile.target.int_width=32` 时，标量参数/返回值/局部值位置可按 `i32` 降入 typed IR；无 target ABI、负值/计算 enum 常量、非 i32 ABI、enum pointer/array/field 和 Rust enum 生成仍 fail-closed |
| `void` | 已支持 | return type 和 pointer pointee |
| `const void *` (byte cursor) | 窄支持 | 仅在 proven byte cursor 场景映射为 `&[u8]` |
| `const T *` (readonly integer pointer) | 窄支持 | 仅在有 `*p` / `p[i]` / `*(p+i)` / `*p++` 等只读访问证据、未写入、不 escape 且长度/索引边界可推断时映射为 `&[T]`；未使用或仅声明的 8-bit readonly pointer 参数可作为 raw `*const core::ffi::c_void` candidate 保留，但不会自动降为 slice；非 8-bit 或被读取的 readonly pointer 仍需显式证据/alias gate |
| `T *` (mutable output pointer) | 窄支持 | 仅在作为写目标时映射为 `&mut [T]` |
| `T *`（函数体证明只读） | 窄支持 | 仅 direct `p[i]` 整数读取，且参数从未写入、重绑定、返回、逃逸、作为 call argument 或参与 nullable 分支时，才可作为 candidate 映射为 `&[T]`；与 mutable output 并存必须有显式 noalias/restrict 证明。`*p`、pointer arithmetic、inout 和复杂 alias 仍 fail-closed |
| `struct T *` (mutable record pointer) | 窄支持 | 仅在 direct single-pointer scalar field 写/update/read-after-write、direct if-return fallthrough write、statement/simple `ForStmt` step inc-dec、direct integer field 的窄 value-position inc-dec prelude，以及 explicit noalias/restrict 证据下的 nested record pointer 标量字段路径 copy/identity return 时映射为 `&mut T`；statement-position inc-dec 只按返回值丢弃的字段赋值处理；不是通用 ownership 或 alias 模型 |
| `plain char` | 不支持 | 符号未知，clang 前端拒绝 |
| `short` / `unsigned short` | 不支持 | target-dependent spelling，拒绝 |
| `long` / `unsigned long` | 窄支持 | 仅在 `build_profile.target.long_width` 明确时按该宽度建模；无 profile 仍 fail-closed |
| `long long` / `unsigned long long` | 不支持 | 如不是 typedef alias，拒绝 |
| `float` / `double` / `long double` | 不支持 | 浮点类型完全未支持 |
| `_Bool` | 窄支持 | 支持 literal 和非 literal 整数 `IntegralToBoolean`/C-style truthiness，并归一化为 Rust `bool`；target-dependent `long` 仍要求 ABI profile，`PointerToBoolean`、更广的 bool 存储/指针/ABI 和 bool/int 混合值语义保持 fail-closed |
| `enum` 其他类型面 | 不支持 | enum pointer/array/field、底层 ABI/layout 和 Rust enum 生成仍未建模；参数、返回值和局部标量值仅限上方 target-ABI-bound i32 子集，显式整数 enum 常量引用见下方“enum 常量引用” |
| `union` | 不支持 | 未建模 |
| `struct` (按值传递) | 窄支持 | 支持既有 dot-field、fixed integer array、whole-record 窄子集；具名 nested record 字段只在对应 `RecordDecl` 唯一且完整时递归进入 inventory，clang 显式 anonymous record 保留原匿名字段合成，缺失/冲突/cycle fail-closed。complete local record 纯 nested dot path 可作为 `do-while` 尾 target，direct mutable record-pointer arrow-rooted pure dot path integer leaf 可作为 `if` assignment-call target；nullable/volatile/atomic/incomplete/non-scalar、未证明 alias、第二 pointer hop 与通用 layout/ABI 仍不支持。既有 accepted named-slice 语义不外推为通用 record 证明 |

## 声明与初始化

| 构造 | 状态 | 说明 |
|------|------|------|
| 单变量标量声明 + 初始化 | 已支持 | `int x = 1;` |
| 本地 `enum T` 标量声明 + 初始化 | 窄支持 | `enum mode current = MODE_A;` 仅在上方 target-ABI-bound i32 enum 子集内降为 `i32` 局部变量；已用 no-clang AST fixture 覆盖声明、`if` 条件比较、赋值和返回；隐式/负值/计算 enum 常量、非 i32 ABI、enum pointer/array/field 仍 fail-closed |
| 单变量无初始化 | 窄支持 | 仅在读取前有赋值证明时支持，包括会继续执行的路径都赋值的 direct if-return 分支 |
| 本地 record 声明 + copy 初始化 | 窄支持 | `struct point q = p;`，仅在后续访问已建模标量字段时作为候选 |
| 多声明 `int a = 1, b = 2;` | 已支持 | compound body 和 for-init |
| `const` 局部变量 | 未显式支持 | clang 降级至 non-const |
| `static` 局部变量 | 不支持 | 需要静态存储模型 |
| `extern` 声明 | 不支持 | 需要跨文件模型 |
| compound literal | 不支持 | `(struct point){1, 2}` |
| designated initializer | 窄支持 | 仅支持局部固定长度整数数组和顶层 readonly `static const` 固定长度整数全局数组的 clang 已语义化 index-designated / sparse initializer，例如 `int table[3] = { [1] = 7 };`；未指定元素按 C 零初始化补齐；struct/union 字段 designator、嵌套 initializer、GNU range designator、VLA/不完整数组、未展开 `DesignatedInitExpr` 和非整数字段仍 fail-closed |

## 表达式

| 构造 | 状态 | 说明 |
|------|------|------|
| 整数字面量 | 已支持 | 含 unsigned suffix |
| 字符字面量 | 窄支持 | Clang `CharacterLiteral` 已提供非负 `int` 数值且不超过 `i32::MAX` 时，按该 compiler/target 已解析的数值降为整数字面量；缺值、负值、越界或非 `int` 类型 fail-closed。该路径不声称通用 execution-character-set 或跨 compiler 字符编码等价 |
| 变量引用 | 已支持 | 局部变量和参数 |
| enum 常量引用 | 窄支持 | clang AST 中 `DeclRefExpr -> EnumConstantDecl` 仅在值可由显式非负整数 `ConstantExpr.value` 加匹配直接 `IntegerLiteral` child 证明，或可由所属 `EnumDecl` 声明顺序从已知前值推导时，才会在 skeleton 边界重写为 typed IR 整数字面量；同一受证明常量也可出现在顶层 readonly `static const` 固定长度整数全局数组的 literal-like initializer 中；负值、计算表达式、缺少完整顺序 inventory 的孤立隐式常量仍 fail-closed；`enum T` 类型本身只有上方 target-ABI-bound i32 标量子集 |
| `+` `-` `*` `/` `%` | 窄支持 | 标量整数，要求 operand 同型；clang-proven usual arithmetic `IntegralCast`/`IntegralPromotion` 会以显式 IR cast 参与运算，缺少该 cast 的混合宽度/符号 operand 会 fail-closed，不由 emitter 猜转换；无符号结果的 `+` / `-` / `*` 发射显式 `wrapping_add` / `wrapping_sub` / `wrapping_mul`；有符号结果的 `+` / `-` / `*` 发射 `checked_add` / `checked_sub` / `checked_mul` + `expect(...)`，将 no signed overflow 作为 runtime precondition；literal `/ 0` 和 `% 0` fail closed |
| `&` `\|` `^` `<<` `>>` | 窄支持 | 标量整数，shift 的 lhs/result 同型；literal 负数 shift count、`shift_count >= width` 和无 contract 的 signed right shift fail closed |
| `~` (bitwise not) | 窄支持 | 仅整数；简单标量 inc/dec operand 可通过有序 Rust prelude 参与 value-position candidate emission |
| `-value` (unary minus) | 窄支持 | 仅 signed integer；简单标量 inc/dec operand 可通过有序 Rust prelude 参与 value-position candidate emission |
| `+value` (unary plus) | 窄支持 | 仅整数；clang-proven `IntegralPromotion` 会保留为显式 IR cast，operand/result 类型不匹配或非整数 fail-closed |
| `!expr` (logical not) | 窄支持 | 条件和 value-position C int 0/1；简单标量 inc/dec operand，以及包含单个标量 inc/dec 参数的 side-effect direct-call operand，可通过有序 Rust prelude 参与 candidate emission，更复杂的 side-effect/conflict 形状仍 fail-closed |
| `==` `!=` `<` `<=` `>` `>=` | 窄支持 | 条件和 value-position C int 0/1；value-position、`if`、`while`、`do-while` 及 `for` condition 允许恰好一个 direct scalar inc/dec operand 与不读取同一标量的纯 scalar sibling 通过 ordered prelude 发射；各循环在正确的 per-iteration condition 点重放 prelude，`continue`/`break` 顺序由 runtime 测试锁定；call/deref/member inc-dec、双 side-effect operand、复杂 target 和同变量 sibling read 仍 fail-closed |
| `&&` `\|\|` (short-circuit) | 窄支持 | 条件和 value-position C int 0/1 |
| `?:` (conditional) | 窄支持 | 仅纯整数 value-position；condition 中 clang-proven integral `ImplicitCastExpr` 仅作为显式 IR cast 保留 |
| 整数 cast (显式/隐式) | 窄支持 | clang-proven `IntegralCast` / `IntegralPromotion` 与整数 `NoOp` 会按现有 value/argument/condition 规则保留；非 literal 整数 `IntegralToBoolean` 和 C-style 整数 truthiness 归一化为 `!= 0` 的 Rust `bool`，target-dependent source 需要 ABI profile。`FloatingToIntegral`、`IntegralToFloating`、`PointerToBoolean`、unknown/missing cast kind、pointer/record/general lvalue read 仍 fail-closed |
| 函数调用 (direct call) | 窄支持 | 仅直接标识符 callee；除既有 integer/record scalar/member 和 modeled callee 子集外，允许恰好一个已由函数体证明为 mutable-record owner 的完整 record pointer 直接变量参数。该调用不得再含第二个 mutable record borrow，也不得有 sibling 读取同一 record；nullable、复杂 pointer expression、多 pointer borrow/noalias 未证明、variadic/indirect/signature-conflict 和额外 call 仍 fail-closed |
| 嵌套 direct call | 窄支持 | 普通 nested direct call 仍只支持一层单个 nested arg；带 inc/dec leaf 的 side-effect 形状只支持单链多层 `outer(middle(inner(++value)))` / `outer(middle(inner(value++)))`，leaf 仅限简单标量或 direct single-pointer mutable record pointer scalar field，每层只能有一个 nested direct-call 参数，任意层混入普通参数、多 sibling nested call、非单链 nested call、复杂 inc/dec target、其它 pointer/member/deref side effect 仍 fail-closed |
| `*p` (deref read) | 窄支持 | readonly integer pointer，无副作用 |
| `*(p+i)` / `*(i+p)` (offset deref) | 窄支持 | readonly integer pointer，integer offset |
| `p[i]` (array subscript) | 窄支持 | readonly pointer slice、local/global array，以及 readonly record-pointer fixed integer array field；mutable integer pointer/local fixed integer array 的 statement compound assignment 只允许纯 index 和纯 integer RHS，effectful index/RHS 与 pointer-element field 保持 fail-closed |
| `p->field` (arrow member) | 窄支持 | readonly 与受证明的 mutable scalar field read/write/inc-dec/compound/call argument 已有窄路径；strict direct non-nullable mutable record-pointer 后可跟一个或多个 pure by-value record dot hop，并以 fixed-width integer leaf 作为 `if ((target = direct_call(...)) compare sentinel)` target。第二 arrow/pointer hop、nullable、readonly target、volatile/atomic、复杂/effectful base、第二 call、未证明 alias、layout/ABI 和 semantic acceptance 仍不支持 |
| `p.field` (dot member access) | 窄支持 | 支持 direct by-value field read/assignment/inc-dec/compound assignment；compound RHS 还可读取 direct by-value 或 readonly/noalias-proven record scalar member。complete local record 的纯 nested dot path 仅在 `do-while` 尾 assignment-call target 中支持；同形 `if` local-member target、complex/effectful base/RHS 与未证明 pointer alias 保持 fail-closed |
| `assert(int)` | 窄支持 | 仅 modeled C assert macro 直接调用，返回类型必须为 `void`，恰好一个 bounded integer/condition argument；pointer、record、nested call、inc/dec、deref/member 等参数仍 fail-closed |
| `abs(int)` | 窄支持 | 仅 modeled C `int abs(int)` 直接调用，参数和返回类型必须都是 `i32`；发射为 `checked_abs().expect(...)`，把 `INT_MIN` 作为 runtime precondition 暴露出来；`labs`、`llabs`、`fabs`、errno/locale 或其它 stdlib 变体仍 fail-closed |
| `strlen(const char *)` | 窄支持 | 仅 modeled C `size_t strlen(const char *)` 直接调用；需要 target ABI profile 绑定 `size_t`/`char`/pointer 宽度，实参必须是直接 readonly 8-bit char/byte pointer 参数；Rust candidate 在 `&[u8]`/`&[i8]` 中查找首个 NUL byte，并用 `expect("C strlen precondition violated")` 暴露 NUL 终止前置条件；NULL、非 8-bit pointer、复杂表达式、非 `size_t` 返回和其它字符串函数仍 fail-closed |
| `strnlen(const char *, size_t)` | 窄支持 | 仅 modeled C `size_t strnlen(const char *, size_t)` 直接调用和一层用户 direct-call 参数；实参必须是直接 readonly 8-bit char/byte pointer 参数和 `size_t`/`usize` bound；Rust candidate 对输入 slice 使用 `.get(..max).expect("C strnlen precondition violated")` 暴露长度前置条件，并在该 bounded 范围内查找首个 NUL byte，找不到时返回 bound；它会参与 readonly/mutable pointer noalias gate；NULL、非 8-bit pointer、复杂表达式、非 size bound、非 `size_t` 返回、`strnlen_s`/其它字符串函数仍 fail-closed |
| `memcmp(const void *, const void *, size_t)` | 窄支持 | 仅 modeled C `int memcmp(left, right, count)` 直接调用；返回类型必须为 `i32`，前两个实参必须是直接 readonly 8-bit pointer 参数，第三个实参必须是 `size_t`/`usize`；Rust candidate 对两侧 slice 使用 `.get(..count).expect("C memcmp precondition violated")` 暴露长度前置条件，并按 C `memcmp` 的 unsigned-byte 语义返回首个不同 byte 的 `i32` 差值或 `0`；NULL、mutable/non-byte pointer、复杂 pointer 表达式、非 size 参数、statement-position 之外的 `memcpy`/`memset`、`memmove` 和其它 memory 函数仍 fail-closed |
| `memset(void *, int, size_t)` | 窄支持 | 仅 statement-position `memset(out, byte_literal, count)`；返回类型可为旧 IR `void` 或真实 clang/C `void *`，但返回值必须被丢弃且不得观察/传播；目标必须是直接 mutable unsigned 8-bit pointer 参数，byte value 只支持能无截断放入 unsigned char 的 literal `0..=255`，count 必须是 `size_t`/`usize`；Rust candidate 对目标 slice 使用 `.get_mut(..count).expect("C memset precondition violated").fill(byte as u8)` 暴露长度前置条件；表达式位置、非 literal byte、会截断的 byte 值、`void *`/signed char/non-byte 目标、复杂目标表达式、非 size 参数、`memmove`、statement-position 之外的 `memcpy` 和完整 alias/overlap/FFI ABI 语义仍 fail-closed |
| `memcpy(void *, const void *, size_t)` | 窄支持 | 仅 statement-position `memcpy(out, src, count)`；返回类型可为旧 IR `void` 或真实 clang/C `void *`，但返回值必须被丢弃且不得观察/传播；目标必须是直接 mutable unsigned 8-bit pointer 参数，source 必须是直接 readonly 8-bit pointer 参数，count 必须是 `size_t`/`usize`，且 readonly source + mutable dest 必须有 `restrict` 或等价 noalias 证明；Rust candidate 对目标 slice 使用 `.get_mut(..count).expect("C memcpy destination precondition violated").copy_from_slice(src.get(..count).expect("C memcpy source precondition violated"))` 暴露长度前置条件和非重叠 slice 合同；表达式位置、复杂 pointer 表达式、非 byte pointer、无 noalias/overlap 证明、`memmove` 和完整 FFI ABI 语义仍 fail-closed |
| `++` / `--` (value-position) | 窄支持 | 简单标量 direct-call/nested direct-call 参数已有窄 prelude，也可作为 unary `-` / `~` / `!` 的直接 operand，或作为 unary `!` 下 direct-call 的单个 leaf 参数；direct single-pointer mutable record pointer scalar field 现在支持 declaration initializer、assignment/return value 和 direct-call argument prelude；通用 condition、复杂 target、同 base sibling read、by-value field value-position 和语义验收仍 fail-closed |
| `p++` / `p--` (statement) | 窄支持 | 仅简单整数变量 target |
| `++p` / `--p` (statement) | 窄支持 | 仅简单整数变量 target |
| `p->field++` / `--p->field` (statement/value) | 窄支持 | 仅 direct single-pointer mutable record pointer scalar field target；statement 和 simple `ForStmt` step 走 value-discarded assignment desugar，declaration initializer、assignment/return value 和 direct-call argument 可走 typed IR value prelude；复杂 base/target、同 base sibling read、非标量字段和 semantic acceptance 仍 fail-closed |
| `*p++` (byte cursor post-increment) | 窄支持 | 仅在 proven byte cursor 上下文 |
| `&x` (address-of) | 不支持 | |
| `sizeof` | 窄支持 | 支持 clang `UnaryExprOrTypeTraitExpr` 的 ABI-bound integer type operand、完整定长整数数组 type operand、带 `argType.qualType` 的 expression operand，以及带 target `pointer_width` 的 pointer type operand，例如 `sizeof(int)`、`sizeof(long)`、`sizeof(size_t)`、`sizeof(int[3])`、`sizeof(value)`、`sizeof(const int *)`；降为 `size_t`/`usize` 整数字面量，并要求结果能放入目标 `size_t` 宽度；缺少 `argType` 的 expression operand、缺少 pointer width profile 的 pointer operand、incomplete/VLA array、enum/record/struct layout、需要布局证据的 object operand、packing/alignment 仍 fail-closed |
| `_Alignof` | 窄支持 | 支持 clang `_Alignof(int)`，但必须由 `build_profile.target.int_align` 提供显式 target alignment 证据；降为 `size_t`/`usize` 整数字面量，并要求结果能放入目标 `size_t` 宽度。缺少 alignment profile、非 byte-addressable alignment、非整数类型、record/struct layout、packing 和 object alignment 仍 fail-closed；alignment 绝不从 width-only evidence 推导 |
| `(type){init}` compound literal | 不支持 | |
| 函数指针 | 窄支持 | 支持简单函数指针参数作为 direct callee，例如 `int (*fp)(int)` 参数调用 `fp(value)` 可降为 Rust `fn(i32) -> i32` 参数并发射 `fp(value)`；也支持直接函数名 decay 作为简单函数指针参数传递、简单本地函数指针初始化/赋值后调用，以及从直接函数名 decay 返回简单函数指针；签名只接受简单标量/`void`，未赋值本地函数指针调用、复杂 callee、间接来源/存储、ABI/FFI 和其它 argument/value 位置的 `FunctionToPointerDecay` 仍需 explicit function-pointer lowering evidence 并 fail-closed |
| 逗号表达式 | 不支持 | |
| 赋值表达式 (value-position) | 不支持 | 仅 statement |
| compound assignment (value-position) | 不支持 | 仅 statement |
| whole-record return | 窄支持 | 仅唯一具名 `RecordDecl`/`FieldDecl` 字段清单且全部直接字段为受支持标量时作为 candidate；同名 tag、bitfield、volatile/packed/self-pointer/non-scalar field 继续 fail closed；不是 layout/ABI proof |

## 语句与控制流

| 构造 | 状态 | 说明 |
|------|------|------|
| 表达式语句 | 已支持 | `value++;`、`++value;` |
| `return` (with/without value) | 已支持 | |
| `if` / `if-else` | 已支持 | 含 comparison condition 和单个 direct scalar inc/dec ordered prelude。窄形状 `if ((target = exactly one direct call) compare pure_sentinel)` 支持 direct fixed-width integer scalar，或 strict direct mutable record-pointer arrow-rooted pure dot-path integer leaf，并提升为前置 `Assign` + 纯目标读取；六种比较与 else-if 归属均有测试。local/by-value member、第二 pointer hop、readonly/volatile/atomic/effectful target、逻辑组合、第二 call 及 `while` 同形继续 fail-closed；新增 nested target 仍只有 candidate evidence |
| `while` | 已支持 | 含 postfix `size--`、窄形状 prefix `--size`，以及单个 direct scalar inc/dec comparison operand 的 per-iteration ordered prelude；`continue`/`break` runtime 测试锁定重新判断与退出语义；condition 中 clang-proven integral `ImplicitCastExpr` 仅作为显式 IR cast 保留 |
| `do-while` | 已支持 | 支持 direct scalar inc/dec condition prelude，以及 assignment-call comparison 归一化并在当前层 `continue` 前克隆尾赋值；assignment-call comparison 后可追加读取独立纯 scalar 的 `&&` suffix。complete local record 的纯 nested dot target 也可用于该尾赋值；effectful suffix、`||`、复杂/volatile/atomic target、第二 side effect 和 nested-loop 下钻继续 fail-closed |
| `for` (scoped) | 窄支持 | 顶层 init 支持 direct integer scalar assignment comma chain；condition 支持一个受限 direct scalar inc/dec ordered prelude，step 可缺省。memory target、call/deref/member inc-dec、双副作用、volatile 读写及 condition/step comma 仍 fail-closed |
| 空语句 (`NullStmt`) | 窄支持 | compound body 内精确 `NullStmt` 会忽略，作为单语句 loop/if body 时生成空 body；仅按精确 AST kind 匹配，未知 statement 不会被吞掉 |
| `break` | 窄支持 | 仅在 loop body 内 |
| `continue` | 窄支持 | 仅在 loop body 内 |
| `switch` | 不支持 | 已有 schema-bound CFG/relooper/route 拒绝证据、clang AST `source_range` refusal diagnostics、归一化 `switch-0 -> case/default` edges 和最小 structured-recovery precondition/refusal evidence；仍需完整 CFG + relooper + Rust candidate lowering 才能支持 |
| `goto` | 不支持 | 已有 schema-bound CFG/relooper/route 拒绝证据、clang AST `source_range` refusal diagnostics、归一化 `goto-* -> label-*` edges 和最小 structured-recovery precondition/refusal evidence；仍需完整 CFG + relooper + Rust candidate lowering 才能支持 |
| label | 不支持 | 仅作为 `goto` refusal 的 schema-bound CFG/relooper evidence 记录；clang AST fixture 已要求拒绝原因带 `source_range` |
| `case` / `default` | 不支持 | 仅作为 `switch` refusal 的 schema-bound CFG/relooper evidence 记录；clang AST fixture 已要求拒绝原因带 `source_range` |

真实 named-slice 验收补充（2026-07-10）：`real-fdb-tsl-to-blob`、`real-fdb-is-str` 与 `real-fdb-new-kv-alloc-compare` 的 exact generated draft 均已通过各自绑定的 C oracle、generated Rust replay、schema diff、negative diff、unsafe scan/ledger、route/profile 与 final verification。新增 alloc-compare 切片只证明 `fdb_kvdb.c:1076` fragment 在 fixture-scripted external u32 返回合同下的赋值、比较、调用次数和参数，不证明完整 `new_kv` 或真实 `alloc_kv` 语义；其它切片也不外推为通用 record layout/ABI/alias/provenance、locale 或任意字符串证明。`translator_generated_semantic_pass_count` 当前为 24。

## 数组

| 构造 | 状态 | 说明 |
|------|------|------|
| 局部固定长度整数数组声明 | 窄支持 | `uint32_t table[3] = {1, 2, 3};`；包括连续 initializer 和受限 index-designated sparse initializer；未指定元素按声明长度补零，initializer 长度/下标必须与固定数组长度一致并可验证 |
| 局部数组下标读 | 窄支持 | `table[i]` |
| 局部数组下标写 | 窄支持 | `table[i] = value;` |
| 全局 const 整数数组 | 窄支持 | 顶层 readonly `static const uint32_t table[3] = {...};`；包括连续 initializer、clang 已语义化 `array_filler` 的受限 index-designated sparse initializer，以及显式非负整数 enum 常量引用，生成 `IrGlobalInit::IntegerArray` 和 Rust `const`；非 `static const`、不完整数组、非整数元素、隐式/负值/计算 enum 常量、未展开 `DesignatedInitExpr`、嵌套/struct/union/range designator 仍 fail-closed |
| 全局数组下标读 | 窄支持 | `CRC32_TABLE[index as usize]` |
| 全局数组下标写 | 不支持 | readonly global |
| 变长数组 (VLA) | 不支持 | |
| 不完整数组 (无 initializer) | 不支持 | |
| array-to-pointer decay | 窄支持 | `ArraySubscriptExpr` base 中的 decay 在既有下标访问窄路径里被消费；`*(local_fixed_array)` 这类 unary deref of direct complete fixed array DeclRef 会降为 `local_fixed_array[0]`；`*(local_fixed_array + integer_expr)` / `*(integer_expr + local_fixed_array)` 会降为 fixed-array index read 并走 fixed-array index emitter；其它普通 `ArrayToPointerDecay` 会先进入显式 typed IR `IrExpr::ArrayToPointerDecay`，但 pointer arithmetic、call argument、非 direct DeclRef、incomplete/VLA/multi-dimensional array、复杂表达式和一般 pointer value 在缺少 explicit lowering evidence 时仍 fail-closed |
| 多维数组 | 不支持 | |
| 数组作为函数参数 | 不支持 | 由 pointer lowering 间接覆盖部分场景 |

## 指针

| 构造 | 状态 | 说明 |
|------|------|------|
| `const T *` readonly slice | 窄支持 | 仅参数上的实际只读访问可降为 slice；缺少 read-access evidence 时不会降为 `&[T]`，未用 8-bit readonly pointer 只允许 raw pointer candidate，非 8-bit/被读取形状仍 fail-closed |
| `T *` body-proven readonly slice | 窄支持 | 仅 direct `p[i]` 读，且全函数无写入、重绑定、return/escape/call-argument/nullable 使用；存在 mutable output 时必须绑定 noalias/restrict。边界由 `fdb_is_str` no-clang fixture 和相邻负例覆盖，但仍只是 candidate generation |
| `T *` mutable output slice | 窄支持 | 参数上的只写访问 |
| `*p` deref read | 窄支持 | readonly pointer only |
| `*(p+i)` bounded offset deref | 窄支持 | readonly, integer offset |
| `*out = v` deref write | 窄支持 | mutable pointer only |
| `out[i] = v` index write | 窄支持 | mutable pointer only |
| `*(out+i) = v` offset write | 窄支持 | mutable pointer, integer offset |
| `p == NULL` / `p != NULL` | 窄支持 | readonly pointer presence check |
| pointer arithmetic (general) | 不支持 | 仅 bounded offset read/write |
| pointer subtraction | 不支持 | |
| pointer comparison (general) | 不支持 | 仅 NULL 比较 |
| void pointer (general) | 不支持 | 仅 proven byte cursor 场景 |
| 函数指针 | 窄支持 | 简单标量签名的函数指针参数 direct call、直接函数名 decay 参数传递、简单本地函数指针初始化/赋值后调用，以及从直接函数名 decay 返回简单函数指针；未赋值本地函数指针调用、间接来源/存储、ABI/FFI 和复杂签名仍 fail-closed |
| pointer value 作为函数参数/返回值 | 不支持 | 普通 pointer value 不能自动映射成 slice/reference/raw pointer；需要显式 ownership/lifetime/ABI lowering |
| double/triple pointer | 不支持 | `T **` |
| pointer cast (non-integer) | 不支持 | |
| `const T *` write | 不支持 | |
| mutable pointer read | 窄支持 | 两条互斥窄路径：`T *out` 在同一路径 definite write 后可 direct `*out` zero-slot read；或整个函数证明 direct `p[i]` only-read 时把该参数降为 shared slice。read-before-write、其它 offset/deref read、nullable、inout、escape 和未证明 alias 仍 fail-closed |
| nullable pointer deref after check | 不支持 | null check 后不能继续使用 |

## 预处理器

| 构造 | 状态 | 说明 |
|------|------|------|
| `#include` | 间接支持 | clang 预处理后 AST 不保留 |
| `#define` 简单常量 | 间接支持 | clang 展开 |
| `#define` 宏函数 | 不支持 | clang 展开后语义不可逆 |
| `#ifdef` / `#if` | 间接支持 | 由 build profile defines 控制 |

## C 标准库

| 函数/头文件 | 状态 | 说明 |
|-------------|------|------|
| 其它标准库函数 | 不支持 | 无 stub / extern callee 证明；`assert(int)`、`abs(int)`、`strlen(const char *)`、`strnlen(const char *, size_t)`、`memcmp(const void *, const void *, size_t)`、statement-only `memset(dst, byte_literal, size)` 和 statement-only `memcpy(out, src, size)` 是上方单独列出的最小模型例外 |

## 关键边界说明

1. **所有 typed IR 成功生成都是 candidate generation，不表示 semantic pass。** `semantic_pass=false` 始终为真，直到独立 validation gates 接受 exact draft。
2. **旧 crc32 特例模板和 string recognizer crc32 路径已删除。** 不能恢复。
3. **无符号加减乘**：C unsigned `+` / `-` / `*` 会发射显式 wrapping Rust 运算，避免 debug/release profile 分叉；这仍只是 candidate generation，不替代 C oracle。
4. **有符号加减乘**：C signed `+` / `-` / `*` 发射 `checked_*().expect(...)`，用于把 no-overflow 前置条件显式带入 candidate Rust；这仍只是 candidate generation/runtime precondition，不证明输入满足该 precondition，也不替代 slice contract、evidence 字段、C oracle 或 C/Rust diff。
5. **除法/取模**：literal zero divisor 已 fail closed；只有在 divisor 非零由 literal 或 fixture contract 约束时，才能进入后续 semantic gate 讨论。非 literal divisor 仍需要 slice precondition 或 evidence contract。
6. **bitwise/shift**：literal 负数 shift count、`shift_count >= width` 和无 contract 的 signed right shift 已 fail closed；这不代表完整 C 位运算语义、usual arithmetic conversions 或 signed overflow UB parity。
7. **pointer-to-slice lowering**：需要 audit 指针存在实际只读访问证据（`*p`、`p[i]`、`*(p+i)`、`*p++` 等）、不 escape、不写入（const case）、长度/索引边界可推断；只有 `const T *` 声明而没有访问证据时不能自动 lowering 成 `&[T]`。当前只允许未读取/未提及的 8-bit readonly pointer 作为 raw `*const core::ffi::c_void` candidate 保留，非 8-bit 或已读取的 readonly pointer 仍必须通过 slice/noalias 证据或 fail-closed。
8. **mutable pointer write/read**：单个 output pointer 或带显式 `restrict`/slice-spec noalias pair 的 readonly-input + mutable-output 形状已有窄路径；direct `*out` 已 definite write 后可作为 zero-slot read 发射为 `out[0usize]`。没有 noalias 证明、多 pointer/inout、nullable、escape、volatile/hardware、复杂 offset/index read 或复杂交互时仍 fail-closed，没有完整 alias 分析。
9. **record/struct**：dot-field 路径的 struct definition 仍是从实际读取到的字段派生的 minimal Rust struct，不是 C layout/ABI proof；whole-record return 的完整字段清单路径会拒绝同名 tag、bitfield、volatile/packed、自引用指针和非标量字段；union、nested/anonymous record 仍 fail closed。
10. **本清单是手动维护**。最终权威来源是 `crates/c2r-translator/tests/bounded_translation.rs` 中的 fail-closed tests。
