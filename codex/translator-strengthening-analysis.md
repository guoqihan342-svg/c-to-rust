# c-to-rust 翻译器加强分析

> 日期：2026-06-27  
> 基于当前 `codex/flashdb-rust-skeleton` 分支代码审查

## 一、现状

### 翻译器双路径

| 路径 | 代码 | 输入 | 覆盖范围 |
|------|------|------|----------|
| 字符串 translator | `lib.rs` `emit_rust()` | 手写 C 字符串 + 逐字符正则解析 | 基础语句级（decl/assign/if/while/for），不支持 struct/bitfield/volatile |
| typed IR translator | `typed_ir.rs` `emit_rust_from_ir_with_globals()` | clang AST dump JSON → typed IR | scalar + 数组 + 全局 const 表 + call，拒绝 pointer/record/function/array 类型 |

两条路径的共同天花板：**只支持纯标量整数运算 + 基本控制流 + 受限指针缓冲**。任何 pointer type、struct、switch/goto、函数指针、内存分配都会 fail。

### 真实翻译状态

`real-fdb-calc-crc32` 当前状态：

- `auto manifest status: candidate_refused`
- `route level/status: L4 / refused`
- `validation profile: L4-dev / blocked`
- `semantic pass: false`
- `C2Rust baseline: skipped`（本机无可用 C2Rust 工具链）
- `C oracle toolchain_status: DRAFT_NOT_EXECUTED`

**零个真实 C 函数通过语义门禁。** 验证体系的 fail-closed 纪律严格执行中。

---

## 二、瓶颈分析（按严重度排序）

### P0 — 类型系统是天花板

typed IR 的 `emit_scalar_type()` 明确拒绝四种类型：

```rust
// typed_ir.rs:486-497
IrTypeKind::Pointer { .. } => Err("pointer type ... is unsupported")
IrTypeKind::Array { .. }   => Err("array type ... is unsupported")
IrTypeKind::Record { .. }  => Err("record type ... is unsupported")
IrTypeKind::Function       => Err("function type ... is unsupported")
```

这意味任何有指针参数/返回值的真实 C 函数无法走 typed IR 路径。`fdb_calc_crc32(uint32_t crc, const void *buf, size_t size)` 的 `const void *buf` 就卡在这里。

**加强方向：**

1. **`const T*` → `&[T]` 切片**：`emit_param_type` 已做 `const void*` → `&[u8]`，但限定在 `context.is_byte_slice_param()` 内。泛化：任何 `const T*` → `&[T]`，不限定 void/u8
2. **非 const 指针**：至少支持单元素 `&mut T`，而不是直接拒绝
3. **简单 struct/record**：最低支持 flat struct（无嵌套指针）逐字段展开。FlashDB 的结构体如 `struct fdb_kv` 被任何函数参数引用就会卡住

### P0 — clang 前端是骨架

```rust
// clang_frontend.rs:73-74
"LIBCLANG_PATH is configured but real libclang parsing 
 remains disabled in this dry-run skeleton"
```

`clang_frontend.rs` 3255 行有完整的 `lower_function_from_clang_ast_dump_report()`，但因为本机无真实 clang 工具链，从未被端到端调通过。clang-frontend 是 conditional feature，不激活时整个 typed IR 路径降级回字符串解析。

**加强方向：**
- 装真实 `clang` + `LIBCLANG_PATH`
- `clang -Xclang -ast-dump=json` 跑通真实 C 文件
- `ast_dump_json_to_skeleton()` 从骨架推进到实际调用

### P1 — 字符串 translator 架构性缺陷

`lib.rs` 的 `parse_statements()` 是手写状态机逐字符扫描 C 源码：

```rust
fn parse_statements(body: &str) -> Vec<ParsedStatement> {
    let mut index = 0;
    while index < body.len() {
        index = skip_whitespace(body, index);
        if starts_with_token_at(body, index, "if") { ... }
    }
}
```

**无法处理**：typedef 别名类型识别、struct 成员访问链、函数指针调用、嵌套宏展开。

**方向**：不修补字符串解析器。加速 clang 前端到可用状态，让 typed IR 成为主路径。字符串路径退化为纯 demo 验证工具。

### P1 — 跨文件语义上下文缺失

当前 `SliceSpec` 只拿单个函数的 `c_source` 字符串。缺少：
- 头文件解析（`-I` include path 下定义的类型/宏/struct）
- 跨文件 callee signature 复用
- `-D` 宏定义的展开值

`fdb_calc_crc32` 依赖同文件 `crc32_table[256]`，这个已经 trace 到了。但 FlashDB 真实调用链（A → B → C）里 A 需要知道 B 的 Rust 签名，当前完全没有。

**方向**：把 clang `compile_commands.json` 真正喂进去，让 clang 做完整预处理 + parse，提取函数 slice 的完整 typed context（类型/宏/callee signatures）。

### P2 — 控制流只支持结构化子集

typed IR 现有 `IrStmt::If` + `IrStmt::While`。

明确缺失：`do-while`（嵌入式 C 常见）、`switch-case` + fallthrough（标记为 unsupported，直接 fail）、`goto`（直接 fail）。

### P2 — 内存模型空白

typed IR 有 `IrExpr::AddrOf` / `Deref`，但 `emit_scalar_type` 拒绝 pointer type。后果：
- `*p = 42` → fail
- `&x` → fail
- `malloc/calloc/realloc/free` → 完全不可见

这不是优化旁路，而是决定"翻译器到底承诺翻译什么 C 子集"的核心约束。

---

## 三、优先级路线图

| 优先级 | 加强点 | 预计投入 | 效果 |
|--------|--------|----------|------|
| **P0-立即** | 装 clang + 激活 clang-frontend | 1 次安装配置 | typed IR 从 dead code → 可用 |
| **P0-立即** | 指针类型 emit（`const T*` → `&[T]`） | 2 天 | `fdb_calc_crc32` 不再因 pointer type fail |
| **P1-短期** | struct/record flat 展开 | 3 天 | FlashDB struct 类函数可进入 pipeline |
| **P1-短期** | 跨文件类型上下文（compile_commands.json） | 3 天 | 不再手写 `c_source`，真正从源文件抽取 |
| **P2-中期** | switch/goto/do-while 控制流 | 5 天 | 覆盖嵌入式 C 常见控制流模式 |
| **P2-中期** | 内存模型边界定义 | 2 周设计 | 决定翻译器语义承诺边界 |

---

## 四、核心判断

**当前验证体系（fail-closed 证据链 + schema-aware 跨 artifact 一致性校验）已经是 C→Rust 领域最严谨的实现。**

但翻译器能力严重落后于门禁标准。门禁说「不合格」，翻译器说「我认」，两个都诚实——但没有一条真正通过的路径。

做 P0 两项（clang + pointer type emit），至少能让 `fdb_calc_crc32` 从 `L4/refused` → `candidate_generated`。做完 P1，第一次 L3 `semantic_pass=true` 会成为可能。

**根本方向不是再加门禁，而是让翻译器追上已经建好的门禁。**
