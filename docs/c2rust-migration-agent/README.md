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
- 固定宽度整数和窄 raw spelling：clang 前端当前会把 `int8_t`、`int16_t`、`int32_t`、`int64_t`、`uint8_t`、`uint16_t`、`uint32_t`、`uint64_t` lowering 成 typed IR 的对应整数类型；精确 `signed char` spelling 现在也可作为 signed 8-bit integer 进入 typed IR，例如 `signed char value; return value + 1;` 会依赖 clang-preserved `IntegralCast` 发射 `(value as i32) + 1i32`。`short` / `long long` 这类其他目标相关 spelling、plain `char`、plain `long`、完整 usual scalar conversions 和 semantic acceptance 仍保持 fail-closed。
- 多声明展开：普通 compound body 和 scoped `ForStmt` init 中的 `DeclStmt` 现在可把多个简单 `VarDecl` 按源码顺序展开成连续 typed IR `Decl`，例如 `int a = 1, b = 2;` 和 `for (int i = 0, j = 0; i < limit; i++)`；unsupported type/initializer、VLA/incomplete array、重复符号、复杂 init/step 和 semantic acceptance 仍保持 fail-closed。
- 无初始化标量局部声明：普通 scalar local `int tmp; tmp = 7; return tmp;`，以及“会继续执行的路径都赋值、未赋值分支直接 return”的直接 `if` 分支，现在可由 typed IR emitter 发射；读取前未赋值、首次赋值读取自身、仅在循环中赋值、可能继续执行的单侧分支、数组/指针/record/function 等非标量声明和 semantic acceptance 仍保持 fail-closed。
- 按值 record 字段读取/简单赋值/字段 compound assignment/statement inc-dec/本地 copy/whole-record return：真实 clang AST 中的 `struct point p; return p.x;`、`p.x = value; return p.x;`、`p.x += value; return p.x;`、`p.x++; return p.x;`、`struct point q = p; q = r; return q.x;`、`struct point identity(struct point p) { return p; }` 现在可 lowering 成 typed IR record candidate；generic emitter 可生成最小/唯一具名完整直接标量字段清单驱动的 Rust `Point` struct、字段读写、RHS 为简单整数变量/字面量/整数 cast 的字段 compound assignment、statement 位置按值 dot-field inc/dec、本地 copy 和 `return p;`。这只是 candidate generation，不表示 C record layout/ABI 等价；value-position 字段 inc/dec、字段 compound assignment 复杂 RHS、窄化 mutable record pointer 子集之外的指针/alias-sensitive 字段写、同名 tag、self-pointer 字段、union/bitfield/volatile/packed/非标量字段或 semantic acceptance 仍 fail closed。
- Mutable record pointer 字段写/update/read-after-write/statement inc-dec：在现有 single-pointer-param gate 下，直接、非 nullable 的 `struct T *p` 标量字段操作（例如 `p->x = value`、`p->x += value`、`p->x++; ++p->x; p->x--; --p->x`、`p->x = value; return p->x;`，以及“会继续执行的路径都写 `p->x`、未写分支直接 return”的直接 `if` 分支）可 lowering 到 typed IR，并发射为 `p: &mut T` 加直接 Rust 字段操作。inc/dec 只支持 clang 把 value-discarded statement 降成 `p->x = p->x +/- 1` 后的形状；raw/value-position `IrExpr::IncDec`、`return p->x++`、`for (...; p->x++)`、缺少 alias/noalias 证明的多 pointer 参数、nullable mutable pointer、read-before-write、普通 maybe-write 后读取、只在 returning 分支写入、loop/复杂路径 return、复杂 base/target/RHS、非标量字段、C layout/ABI 声明和 semantic acceptance 仍 fail closed。
- 核心翻译架构和证据状态：见 `core-translation-architecture.md` / `core-translation-architecture.en.md`；typed IR candidate generation 当前是 `GenericTypedIr` / `Unsupported` 两路线模型，generic emitter 已覆盖局部固定长度整数数组读取/写入、窄化标量整数二元 `+`、`-`、`*`、`/`、`%`、`&`、`|`、`^`、`<<`、`>>`、signed unary `-value`，compound assignment family `+=`、`-=`、`*=`、`/=`、`%=`、`&=`、`|=`、`^=`、`<<=`、`>>=` 的 clang-lowered desugar，并包含 simple scalar variable target 和 RHS 为简单整数变量/字面量/整数 cast 的 standalone 按值 record dot-field target；simple scalar variable target 上还有 clang-proven integer promotion/truncation 的窄化路径，declaration initializer、assignment RHS 和 return value 中由 clang 保留下来的 value-position integer implicit casts，binary operand 上 clang-preserved integral cast 对齐后的普通整数二元运算，例如 `uint32_t acc + uint8_t byte` 和 `signed char value + 1`，comparison expression 的条件位置和窄 value-position C `int` 0/1 结果 candidate generation，logical not `!expr` 的条件位置和窄 value-position C `int` 0/1 结果 candidate generation，short-circuit `&&` / `||` 的条件位置和窄 value-position C `int` 0/1 candidate generation，纯整数 value-position `ConditionalOperator` / `?:` 的 return value、assignment RHS 和 declaration initializer 发射，窄化 scoped `ForStmt` 的 simple scalar declaration/assignment init（含多个简单 `VarDecl` declarator）、condition、assignment/compound-assignment/postfix-or-prefix inc-dec step 和 body 发射，窄化 `DoStmt` / `do-while` 发射，`while` / `do-while` / `for` loop body 中的 `break` 和窄化 `continue` 语句发射，readonly integer pointer 参数的 null presence check，例如 `values != NULL -> values: Option<&[i32]>` 加 `.is_some()`，readonly direct deref read，例如 `return *p -> return p[0usize]`，以及 bounded readonly pointer offset-deref read，例如 `return *(p+i) -> return p[i as usize]`；新 evidence 可绑定 `candidate_generation.typed_ir`，clang-lowered direct call 也会进入 `call_expressions` / `direct_call_edges` 证据；scalar-only 且 `GenericTypedIr` candidate 的 `candidate_route.token_cost=0` 时，确定性候选现在作为 L0 route signal，非 scalar pointer surface 仍至少 L1，alias risk floor 仍优先；external direct callee 的 call-site/signature/source binding 已有默认 validator 一致性校验，但这只证明证据链一致，不表示 external callee 语义已通过；semantic acceptance 仍由 validation gates 决定。
- Standalone inc/dec statement：普通 `value++`、`++value`、`value--`、`--value` 在表达式值被丢弃的 statement 位置可 lowering 成 typed IR assignment，并发射为 `value = value +/- 1`；direct by-value record dot-field statement target（例如 `p.x++` / `--p.x`）和 direct mutable record pointer field statement target（例如 `p->x++` / `--p->x`）也可在各自 gate 下 lowering 成 `field = field +/- 1`。这只覆盖简单整数变量 target、direct by-value record dot-field integer target、direct single-pointer mutable record pointer scalar field target；不表示 value-position inc/dec、condition/call argument/return 中 inc/dec、`ForStmt` step 中 record-field inc/dec、array/复杂 field target 或完整 C 自增表达式语义已支持。
- 核心翻译边界：上述 bitwise OR `|` / left shift `<<`、signed unary minus、compound assignment family、value-position integer implicit cast preservation、binary operand integral cast preservation、comparison expression、logical not、condition/value-position short-circuit `&&` / `||`、纯整数 value-position `ConditionalOperator` / `?:`、窄化 scoped `ForStmt`、loop-body `break`、窄化 loop-body `continue`、pointer-null presence、readonly direct deref read 和 bounded readonly pointer offset-deref read 都只是 candidate generation only；bitwise OR `|` / left shift `<<` 目前仅覆盖窄化标量整数候选生成，不代表完整 C 位运算或位移语义；compound assignment 目前接受 simple scalar variable target 和 standalone 按值 record dot-field target，其中 record dot-field target 的 RHS 只接受简单整数变量、字面量或整数 cast；要求 clang target/result 类型一致、compute lhs/result 类型一致，且所有相关类型都是受支持整数；如果 compute type 不同于 target type，会显式 cast 到 compute type 计算，再 cast 回 target type 赋值；value-position 和 binary operand implicit cast preservation 目前只接受 clang `IntegralCast` / `IntegralPromotion` 节点，且 typed IR emitter 必须能证明 source/target 都是可支持整数类型并且 cast 后 operand/result 类型严格对齐；函数指针 decay、pointer/float cast、隐藏副作用转换和完整 usual scalar conversions 不在这个子集内；comparison 目前覆盖条件位置和窄 value-position C `int` 0/1 materialization，例如 `return x > 0`、assignment RHS 和 declaration initializer，也覆盖 comparison operand 上 source/target 都是可发射整数类型且 cast 后两侧类型完全一致的 integral cast、readonly direct deref read operand，以及 bounded readonly pointer offset-deref read operand；pointer-null presence 仅限 readonly integer pointer 参数只出现在 `== NULL` / `!= NULL` 检查中，发射为 `Option<&[T]>` 加 `.is_none()` / `.is_some()`；logical not 目前覆盖整数条件零比较、readonly direct deref read operand、bounded readonly pointer offset-deref read operand，以及窄 value-position C `int` 0/1 结果语义；short-circuit 目前覆盖 `if` / `while` 条件中的 `&&` / `||`，以及 return value、assignment RHS 和 declaration initializer 中的窄 value-position C `int` 0/1 materialization，左右操作数递归复用当前条件表达式子集并保留 Rust `&&` / `||` lazy 求值；conditional `?:` 目前只覆盖纯整数 value-position，并拒绝 condition-position `?:`、expression-statement `?:`、GNU omitted-middle `a ?: b`、分支副作用、pointer/floating/aggregate 结果和未建模 usual scalar conversions；scoped `ForStmt` 目前只覆盖 simple scalar declaration/assignment init（含多个简单 `VarDecl` declarator）、condition、assignment/compound-assignment/postfix-or-prefix inc-dec step、现有 statement body 子集、loop-body `break` 和窄化 loop-body `continue`；同一层 scoped `ForStmt` body 内的 `continue` 会先发射当前 step 再发射 Rust `continue;`，嵌套循环里的 `continue` 只作用于内层循环。`goto` / `switch`、condition variable slot、空 condition/step、condition 中 call/inc/dec/side effect、复杂 init/step、value-position inc/dec、parenthesized/comma/complex step、非 simple integer variable target 和完整 C for-loop control-flow semantics 仍 fail closed。除 bounded readonly `*(p+i)` read 外的任意 pointer arithmetic、任意 pointer comparison、float comparison、未由 clang-preserved 或显式整数 cast 对齐的 mixed-width/unsigned conversions、未支持的 compound target、record field compound assignment 复杂 RHS、未被上述 compound-assignment guard 证明的 promotion/truncation、call/inc/dec/side-effect operand、pointer truthiness、null check 后继续 deref/index 使用、float truthiness、unsupported type、完整 usual scalar conversions、无效 shift count、signed shift/overflow UB parity、unsigned/wrapping 取负、浮点取负、特殊 literal/min-value 边界、完整 C for-loop control-flow semantics 和 semantic acceptance 仍 fail closed。

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
- `bounded-auto-translation-pipeline.md` / `bounded-auto-translation-pipeline.en.md`：受限自动翻译管线 Agent 使用文档，包含 pointer graph v2、`effect_graph`、alias gate cache identity 和验证门禁说明。
- `l0-l4-routing-and-evidence-gates.md` / `l0-l4-routing-and-evidence-gates.en.md`：L0-L4 路由决策、证据流拓扑和验证门禁的详细设计文档，解释 route decision、validation profile、candidate route、alias risk floor、fail-closed 原则和证据引用链一致性。
- `future-vision-and-mvp.md` / `future-vision-and-mvp.en.md`：未来愿景与 MVP 路线，包含 IR 三层设计（Semantic IR / Control IR / Typed Value IR）和分阶段计划。
- `COVERAGE.md` / `COVERAGE.en.md`：当前 typed IR + clang frontend + generic emitter 的 C 构造支持/不支持清单，坦诚列出已支持和显式拒绝的 C 语言特性。
- `../../config/competition-env/`：比赛环境配置入口，记录 Ubuntu 24.04.4、Rust 1.96.0、Python 3.12.3、Node 24.13.0、华为镜像源、Go/CMake 缺失边界和自检脚本。


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
