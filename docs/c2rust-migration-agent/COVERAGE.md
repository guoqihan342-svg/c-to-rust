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
| `void` | 已支持 | return type 和 pointer pointee |
| `const void *` (byte cursor) | 窄支持 | 仅在 proven byte cursor 场景映射为 `&[u8]` |
| `const T *` (readonly integer pointer) | 窄支持 | 映射为 `&[T]`，只读 |
| `T *` (mutable output pointer) | 窄支持 | 仅在作为写目标时映射为 `&mut [T]` |
| `struct T *` (mutable record pointer) | 窄支持 | 仅在 direct single-pointer scalar field 写/update/read-after-write、direct if-return fallthrough write、statement inc-dec 时映射为 `&mut T`；不是通用 ownership 或 alias 模型 |
| `plain char` | 不支持 | 符号未知，clang 前端拒绝 |
| `short` / `unsigned short` | 不支持 | target-dependent spelling，拒绝 |
| `long` / `unsigned long` | 窄支持 | 仅在 `build_profile.target.long_width` 明确时按该宽度建模；无 profile 仍 fail-closed |
| `long long` / `unsigned long long` | 不支持 | 如不是 typedef alias，拒绝 |
| `float` / `double` / `long double` | 不支持 | 浮点类型完全未支持 |
| `_Bool` | 不支持 | 未建模 |
| `enum` | 不支持 | 未建模 |
| `union` | 不支持 | 未建模 |
| `struct` (按值传递) | 窄支持 | dot-field read、简单 dot-field assignment、按值 dot-field compound assignment、statement 位置 dot-field inc/dec、本地 by-value copy、唯一具名 tag 的完整直接标量字段清单下的 whole-record return；dot-field 路径仍是 minimal field candidate；whole-record inventory 拒绝同名 tag、bitfield、volatile/packed field、self-pointer/non-scalar field；pointer member access 只限 readonly 和 single-pointer mutable 窄子集，不是通用 `->`；value-position field update、多 pointer alias-sensitive field write、嵌套、匿名仍不支持 |

## 声明与初始化

| 构造 | 状态 | 说明 |
|------|------|------|
| 单变量标量声明 + 初始化 | 已支持 | `int x = 1;` |
| 单变量无初始化 | 窄支持 | 仅在读取前有赋值证明时支持，包括会继续执行的路径都赋值的 direct if-return 分支 |
| 本地 record 声明 + copy 初始化 | 窄支持 | `struct point q = p;`，仅在后续访问已建模标量字段时作为候选 |
| 多声明 `int a = 1, b = 2;` | 已支持 | compound body 和 for-init |
| `const` 局部变量 | 未显式支持 | clang 降级至 non-const |
| `static` 局部变量 | 不支持 | 需要静态存储模型 |
| `extern` 声明 | 不支持 | 需要跨文件模型 |
| compound literal | 不支持 | `(struct point){1, 2}` |
| designated initializer | 不支持 | `.x = 1, .y = 2` |

## 表达式

| 构造 | 状态 | 说明 |
|------|------|------|
| 整数字面量 | 已支持 | 含 unsigned suffix |
| 变量引用 | 已支持 | 局部变量和参数 |
| `+` `-` `*` `/` `%` | 窄支持 | 标量整数，要求 operand 同型；无符号结果的 `+` / `-` / `*` 发射显式 `wrapping_add` / `wrapping_sub` / `wrapping_mul`；有符号结果的 `+` / `-` / `*` 发射 `checked_add` / `checked_sub` / `checked_mul` + `expect(...)`，将 no signed overflow 作为 runtime precondition；literal `/ 0` 和 `% 0` fail closed |
| `&` `\|` `^` `<<` `>>` | 窄支持 | 标量整数，shift 的 lhs/result 同型；literal 负数 shift count、`shift_count >= width` 和无 contract 的 signed right shift fail closed |
| `~` (bitwise not) | 已支持 | |
| `-value` (unary minus) | 窄支持 | 仅 signed integer |
| `!expr` (logical not) | 窄支持 | 条件和 value-position C int 0/1 |
| `==` `!=` `<` `<=` `>` `>=` | 窄支持 | 条件和 value-position C int 0/1 |
| `&&` `\|\|` (short-circuit) | 窄支持 | 条件和 value-position C int 0/1 |
| `?:` (conditional) | 窄支持 | 仅纯整数 value-position |
| 整数 cast (显式/隐式) | 窄支持 | clang-proven integral cast，source/target 同为支持整数 |
| 函数调用 (direct call) | 窄支持 | 仅直接标识符 callee；用户函数 `helper`/`observe` 这类 bounded direct call 已有 no-clang AST fixture replay，reserved C macro/stdlib/extern surface 仍需显式模型或 extern binding，否则 fail-closed |
| 嵌套 direct call | 窄支持 | 仅一层单个 nested arg |
| `*p` (deref read) | 窄支持 | readonly integer pointer，无副作用 |
| `*(p+i)` / `*(i+p)` (offset deref) | 窄支持 | readonly integer pointer，integer offset |
| `p[i]` (array subscript) | 窄支持 | readonly pointer slice 或 local/global array |
| `p->field` (arrow member) | 窄支持 | readonly `const struct T *p` scalar field read、null-presence/guarded readonly read，以及 direct non-nullable single-pointer mutable `struct T *p` scalar field assignment/compound update/read-after-write/direct if-return fallthrough write/statement inc-dec 已支持；multi-pointer alias、nullable mutable pointer、read-before-write、普通 maybe-write 后读取、只在 returning 分支写入、loop/复杂路径 return、复杂 base/target/RHS、非标量字段、value-position inc-dec、`ForStmt` step inc-dec、layout/ABI 声明和 semantic acceptance 仍不支持 |
| `p.field` (dot member access) | 窄支持 | 仅按值 record dot-field read、简单 `p.field = value`、statement 位置 `p.field += value`（RHS 仅简单整数变量/字面量/整数 cast）、standalone statement 位置 `p.field++` / `++p.field` / `p.field--` / `--p.field`（base 必须是直接按值 record 变量，field 必须是受支持整数）、本地 copy 后字段访问；value-position `p.field++`、复杂 RHS/复杂 base 和 pointer/alias-sensitive field write 仍不支持 |
| `++` / `--` (value-position) | 不支持 | 仅 statement value-discarded 场景 |
| `p++` / `p--` (statement) | 窄支持 | 仅简单整数变量 target |
| `++p` / `--p` (statement) | 窄支持 | 仅简单整数变量 target |
| `p->field++` / `--p->field` (statement) | 窄支持 | 仅 direct single-pointer mutable record pointer scalar field target；按 value-discarded assignment desugar lowering，不支持 raw inc/dec value 语义 |
| `*p++` (byte cursor post-increment) | 窄支持 | 仅在 proven byte cursor 上下文 |
| `&x` (address-of) | 不支持 | |
| `sizeof` | 窄支持 | 仅支持 clang `UnaryExprOrTypeTraitExpr` 的 type operand，且 operand 是已绑定 ABI 宽度的整数类型或完整定长整数数组类型，例如 `sizeof(int)`、`sizeof(long)`、`sizeof(size_t)`、`sizeof(int[3])`；降为 `size_t`/`usize` 整数字面量，并要求结果能放入目标 `size_t` 宽度；expression operand `sizeof(x)`、incomplete/VLA array、record/struct layout、object operand、packing/alignment 仍 fail-closed |
| `_Alignof` | 不支持 | clang `_Alignof(type)` 会显式 fail-closed；当前 target profile 只有宽度证据，没有 alignment/layout profile，不能猜 alignment |
| `(type){init}` compound literal | 不支持 | |
| 函数指针 | 不支持 | |
| 逗号表达式 | 不支持 | |
| 赋值表达式 (value-position) | 不支持 | 仅 statement |
| compound assignment (value-position) | 不支持 | 仅 statement |
| whole-record return | 窄支持 | 仅唯一具名 `RecordDecl`/`FieldDecl` 字段清单且全部直接字段为受支持标量时作为 candidate；同名 tag、bitfield、volatile/packed/self-pointer/non-scalar field 继续 fail closed；不是 layout/ABI proof |

## 语句与控制流

| 构造 | 状态 | 说明 |
|------|------|------|
| 表达式语句 | 已支持 | `value++;` |
| `return` (with/without value) | 已支持 | |
| `if` / `if-else` | 已支持 | 含 comparison condition |
| `while` | 已支持 | 含 postfix `size--` |
| `do-while` | 已支持 | |
| `for` (scoped) | 窄支持 | init/condition/step 为简单形式 |
| `break` | 窄支持 | 仅在 loop body 内 |
| `continue` | 窄支持 | 仅在 loop body 内 |
| `switch` | 不支持 | 已有 CFG/relooper/route 拒绝证据；仍需完整 CFG + relooper 才能 lowering |
| `goto` | 不支持 | 已有 CFG/relooper/route 拒绝证据；仍需完整 CFG + relooper 才能 lowering |
| label | 不支持 | |
| `case` / `default` | 不支持 | |

## 数组

| 构造 | 状态 | 说明 |
|------|------|------|
| 局部固定长度整数数组声明 | 窄支持 | `uint32_t table[3] = {1, 2, 3};` |
| 局部数组下标读 | 窄支持 | `table[i]` |
| 局部数组下标写 | 窄支持 | `table[i] = value;` |
| 全局 const 整数数组 | 窄支持 | `static const uint32_t table[] = {...};` |
| 全局数组下标读 | 窄支持 | `CRC32_TABLE[index as usize]` |
| 全局数组下标写 | 不支持 | readonly global |
| 变长数组 (VLA) | 不支持 | |
| 不完整数组 (无 initializer) | 不支持 | |
| array-to-pointer decay | 不支持 | 未建模 |
| 多维数组 | 不支持 | |
| 数组作为函数参数 | 不支持 | 由 pointer lowering 间接覆盖部分场景 |

## 指针

| 构造 | 状态 | 说明 |
|------|------|------|
| `const T *` readonly slice | 窄支持 | 参数上的只读访问 |
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
| 函数指针 | 不支持 | |
| double/triple pointer | 不支持 | `T **` |
| pointer cast (non-integer) | 不支持 | |
| `const T *` write | 不支持 | |
| mutable pointer read | 不支持 | 仅有写证明的 pointer 不能读 |
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
| 任何标准库函数 | 不支持 | 无 stub / extern callee 证明 |

## 关键边界说明

1. **所有 typed IR 成功生成都是 candidate generation，不表示 semantic pass。** `semantic_pass=false` 始终为真，直到独立 validation gates 接受 exact draft。
2. **旧 crc32 特例模板和 string recognizer crc32 路径已删除。** 不能恢复。
3. **无符号加减乘**：C unsigned `+` / `-` / `*` 会发射显式 wrapping Rust 运算，避免 debug/release profile 分叉；这仍只是 candidate generation，不替代 C oracle。
4. **有符号加减乘**：C signed `+` / `-` / `*` 发射 `checked_*().expect(...)`，用于把 no-overflow 前置条件显式带入 candidate Rust；这仍只是 candidate generation/runtime precondition，不证明输入满足该 precondition，也不替代 slice contract、evidence 字段、C oracle 或 C/Rust diff。
5. **除法/取模**：literal zero divisor 已 fail closed；只有在 divisor 非零由 literal 或 fixture contract 约束时，才能进入后续 semantic gate 讨论。非 literal divisor 仍需要 slice precondition 或 evidence contract。
6. **bitwise/shift**：literal 负数 shift count、`shift_count >= width` 和无 contract 的 signed right shift 已 fail closed；这不代表完整 C 位运算语义、usual arithmetic conversions 或 signed overflow UB parity。
7. **pointer-to-slice lowering**：需要 audit 指针不 escape、不写入（const case）、长度可推断。
8. **mutable pointer write**：当前没有 noalias 证明或多 pointer 交互的 alias 分析。
9. **record/struct**：dot-field 路径的 struct definition 仍是从实际读取到的字段派生的 minimal Rust struct，不是 C layout/ABI proof；whole-record return 的完整字段清单路径会拒绝同名 tag、bitfield、volatile/packed、自引用指针和非标量字段；union、nested/anonymous record 仍 fail closed。
10. **本清单是手动维护**。最终权威来源是 `crates/c2r-translator/tests/bounded_translation.rs` 中的 fail-closed tests。
