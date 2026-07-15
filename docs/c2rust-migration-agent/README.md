英文镜像见 `README.en.md`。

# C2Rust Migration Agent

`docs/c2rust-migration-agent/` 是 C2Rust migration agent 的专题文档文件夹，收纳架构合同、运行手册、能力边界和唯一全局待办，供 OpenCode、Codex 或其他智能体分阶段执行 C 到 Rust 迁移。英文镜像见 `README.en.md`。

## 当前状态

- 唯一全局待办：`future-vision-and-mvp.md`
- 第一目标：FlashDB
- 源码克隆：`sources/FlashDB`
- 源码 commit：`f9d0421315c564fb890a1b14eee77b290e0d7bbe`
- Rust 输出项目名：`flashDB_rust`
- 当前 harness 分支：`codex/flashdb-rust-skeleton`
- OpenCode harness：`opencode_agent_harness.py run-worker` 已支持 `--mode deterministic` 调用 repo-local `scripts/c2rust-migrator.py --phase migrate --input ...`，也支持 `--mode opencode --opencode-variant max` 包装同一 request；`competition-run-summary.json` 存在时自动入 SQLite ledger。OpenCode 在第一条 shell command 前遇到 `database is locked` 时会做窄口径启动重试，并记录 `opencode_process_retries`；命令合同和 summary validation 仍然 fail-closed。
- 评委 runner：`run_judge_entrypoints` 已把 competition smoke、before/after、显式多 worker 和 OpenCode 入口收敛到一条命令，并在全量通过后生成 `judge-milestone-bundle.json` 与 `milestone-release-notes.md`。两个 `evaluate --profile` 入口还会生成 `harness/resume-manifest.json`，把 SQLite ledger、context pack、agent index、worker summary、repair hints 和续跑入口收敛成 current-state 索引。bundle 输出 `core_translation_quality`、`harness_architecture_summary`、`claim_scope`、`proof_classes`、`publishability`、`quantitative_evaluation`、`publication_manifest`、`known_gaps`、`must_not_claim` 和复现命令，供评委一屏审阅；Markdown release notes 由 bundle 渲染，只作为人类可读 public packet。`quantitative_evaluation` 汇总 workflow units、accepted/blocked/repair/unsafe 指标以及 raw C2Rust、C2Rust+repair、typed-IR、OpenCode/LLM worker、handwritten reference 的边界对比；`publication_manifest` 绑定 repo commit、FlashDB source pin、judge config、competition config archive、run-report/bundle、supported subset、known gaps/non-goals 和 claim boundary。bundle、release notes、resume manifest 均不替代 validator/oracle，也不扩大 semantic pass、competition-exact proof 或 translation coverage。
- C2Rust baseline 状态现在进入评委 scorecard：`route-governance-metrics-report.json` 读取每个 `*-c2rust-baseline-manifest.json` 的 status/output/compile-only 结果，`judge-milestone-bundle.json` 按 evidence root 去重后放进 `raw_c2rust.c2rust_baseline_rollup`，release notes 展示 manifest/source/compile-pass 数；该 rollup 仍是 candidate context only，不是 semantic gate。
- 公开 release packet：全量评委 runner 成功后还会生成 `summary/public-release-packet.json`，hash 绑定 run report、readiness report、milestone bundle、Markdown release notes 和 competition config archive，并由 `validation.tools.validate_public_release_packet` 校验 schema、hash、claim boundary、本机路径泄漏，检查 packet 中复制的 publication manifest、known gaps、reproduction commands、must-not-claim 覆盖是否与被绑定的 bundle 一致，并要求 release notes 等于该 bundle 渲染出的 Markdown；它只是评委发布包索引，不是 semantic gate，也不增加 `translation_coverage_numerator`。
- 评委入口本地 artifact 校验现在会对非 smoke `competition_summary` 组合既有 competition summary validator，因此 workflow metrics、before/after refs、repair history、unsafe 账本、final-gate 规则和 slice counts 必须先通过合同，评委入口才会通过。
- FlashDB accepted evidence：`real-fdb-blob-make` 仍通过 L4 accepted-evidence-authoritative 语义绑定；`real-fdb-calc-crc32`、`real-fdb-blob-make`、`real-fdb-is-str`、`real-fdb-kv-del`、`real-fdb-kv-set`、`real-fdb-kv-to-blob`、`real-fdb-new-kv-alloc-compare` 和 `real-fdb-tsl-to-blob` 的 exact typed-IR generated Rust draft 均已达到 `generated_draft_acceptance.status=passed`。coverage matrix 还计入 `zlib-ng/adler32-step` 与一组 demo exact typed-IR drafts，当前派生 `translator_generated_semantic_pass_count=24`。raw C2Rust baseline 仍是 `candidate_context_only`，不得写成 translator-generated accepted draft。
- FlashDB KV/TSL 边界：`real-fdb-kv-set` 与 `real-fdb-kv-del` 只关闭各自未初始化 DB fixture，initialized path 与完整 callee 语义仍开放；`real-fdb-kv-to-blob` 只关闭 3-case `kv->addr/value_len` 到 `blob->saved.*` 字段复制与 identity return；`real-fdb-tsl-to-blob` 只关闭 3-case `tsl->addr/log_len` 到 `blob->saved.*` 合同、clang-proven `uint32_t -> size_t` widening 与 identity return。两条 slice 都不证明完整 record layout/ABI、非标量 leaf 或通用 alias/provenance。
- C2Rust 角色：只作为 baseline/oracle，不作为最终交付代码
- 安全目标：first-party non-test unsafe 低于 10%
- 入口 unsafe claim 边界（P0-162）：unsafe < 10% 或 0 findings 只表示当前扫描/ledger 未超出预算或未发现已建模问题，不证明 C ABI、FFI、flash hardware、volatile register、RTOS、多线程或中断语义已经解决。这些能力进入实现前，必须先有 unsafe ledger span、safe/typed 替代方案、target/test evidence 和人工 review 状态。
- 固定宽度整数和窄 raw spelling：clang 前端当前会把 `int8_t`、`int16_t`、`int32_t`、`int64_t`、`uint8_t`、`uint16_t`、`uint32_t`、`uint64_t` lowering 成 typed IR 的对应整数类型；精确 `signed char` spelling 现在也可作为 signed 8-bit integer 进入 typed IR，例如 `signed char value; return value + 1;` 会依赖 clang-preserved `IntegralCast` 发射 `(value as i32) + 1i32`。`short` / `long long` 这类其他目标相关 spelling、plain `char`、plain `long`、完整 usual scalar conversions 和 semantic acceptance 仍保持 fail-closed。
- 多声明展开：普通 compound body 和 scoped `ForStmt` init 中的 `DeclStmt` 现在可把多个简单 `VarDecl` 按源码顺序展开成连续 typed IR `Decl`，例如 `int a = 1, b = 2;` 和 `for (int i = 0, j = 0; i < limit; i++)`；unsupported type/initializer、VLA/incomplete array、重复符号、复杂 init/step 和 semantic acceptance 仍保持 fail-closed。
- 无初始化标量局部声明：普通 scalar local `int tmp; tmp = 7; return tmp;`，以及“会继续执行的路径都赋值、未赋值分支直接 return”的直接 `if` 分支，现在可由 typed IR emitter 发射；读取前未赋值、首次赋值读取自身、仅在循环中赋值、可能继续执行的单侧分支、数组/指针/record/function 等非标量声明和 semantic acceptance 仍保持 fail-closed。
- 按值 record 字段读取/简单赋值/字段 compound assignment/statement inc-dec/本地 copy/whole-record return：真实 clang AST 中的 `struct point p; return p.x;`、`p.x = value; return p.x;`、`p.x += value; return p.x;`、`p.x++; return p.x;`、`struct point q = p; q = r; return q.x;`、`struct point identity(struct point p) { return p; }` 现在可 lowering 成 typed IR record candidate；generic emitter 可生成最小/唯一具名完整直接标量字段清单驱动的 Rust `Point` struct、字段读写、RHS 为简单整数变量/字面量/整数 cast 的字段 compound assignment、statement 位置按值 dot-field inc/dec、本地 copy 和 `return p;`。这只是 candidate generation，不表示 C record layout/ABI 等价；value-position 字段 inc/dec、字段 compound assignment 复杂 RHS、窄化 mutable record pointer 子集之外的指针/alias-sensitive 字段写、同名 tag、self-pointer 字段、union/bitfield/volatile/packed/非标量字段或 semantic acceptance 仍 fail closed。
- Mutable record pointer 字段写/update/read-after-write/statement inc-dec：在现有 single-pointer-param gate 下，直接、非 nullable 的 `struct T *p` 标量字段操作（例如 `p->x = value`、`p->x += value`、`p->x++; ++p->x; p->x--; --p->x`、`p->x = value; return p->x;`，以及“会继续执行的路径都写 `p->x`、未写分支直接 return”的直接 `if` 分支）可 lowering 到 typed IR，并发射为 `p: &mut T` 加直接 Rust 字段操作。inc/dec 只支持 clang 把 value-discarded statement 降成 `p->x = p->x +/- 1` 后的形状；raw/value-position `IrExpr::IncDec`、`return p->x++`、`for (...; p->x++)`、缺少 alias/noalias 证明的多 pointer 参数、nullable mutable pointer、read-before-write、普通 maybe-write 后读取、只在 returning 分支写入、loop/复杂路径 return、复杂 base/target/RHS、非标量字段、C layout/ABI 声明和 semantic acceptance 仍 fail closed。
- 核心翻译架构和证据状态：见 `core-translation-architecture.md` / `core-translation-architecture.en.md`；typed IR candidate generation 当前是 `GenericTypedIr` / `Unsupported` 两路线模型，generic emitter 已覆盖局部固定长度整数数组读取/写入、readonly `static const` 固定长度整数全局数组下标读和受限 sparse/designated initializer lowering、窄化标量整数二元 `+`、`-`、`*`、`/`、`%`、`&`、`|`、`^`、`<<`、`>>`、signed unary `-value`，compound assignment family `+=`、`-=`、`*=`、`/=`、`%=`、`&=`、`|=`、`^=`、`<<=`、`>>=` 的 clang-lowered desugar，并包含 simple scalar variable target 和 RHS 为简单整数变量/字面量/整数 cast 的 standalone 按值 record dot-field target；simple scalar variable target 上还有 clang-proven integer promotion/truncation 的窄化路径，declaration initializer、assignment RHS 和 return value 中由 clang 保留下来的 value-position integer implicit casts，binary operand 上 clang-preserved integral cast 对齐后的普通整数二元运算，例如 `uint32_t acc + uint8_t byte` 和 `signed char value + 1`，comparison expression 的条件位置和窄 value-position C `int` 0/1 结果 candidate generation，logical not `!expr` 的条件位置和窄 value-position C `int` 0/1 结果 candidate generation，short-circuit `&&` / `||` 的条件位置和窄 value-position C `int` 0/1 candidate generation，纯整数 value-position `ConditionalOperator` / `?:` 的 return value、assignment RHS 和 declaration initializer 发射，窄化 scoped `ForStmt` 的 simple scalar declaration/assignment init（含多个简单 `VarDecl` declarator）、condition、assignment/compound-assignment/postfix-or-prefix inc-dec step 和 body 发射，窄化 `DoStmt` / `do-while` 发射，`while` / `do-while` / `for` loop body 中的 `break` 和窄化 `continue` 语句发射，readonly integer pointer 参数的 null presence check，例如 `values != NULL -> values: Option<&[i32]>` 加 `.is_some()`，readonly direct deref read，例如 `return *p -> return p[0usize]`，以及 bounded readonly pointer offset-deref read，例如 `return *(p+i) -> return p[i as usize]`；新 evidence 可绑定 `candidate_generation.typed_ir`，clang-lowered direct call 也会进入 `call_expressions` / `direct_call_edges` 证据；scalar-only 且 `GenericTypedIr` candidate 的 `candidate_route.token_cost=0` 时，确定性候选现在作为 L0 route signal，非 scalar pointer surface 仍至少 L1，alias risk floor 仍优先；external direct callee 的 call-site/signature/source binding 已有默认 validator 一致性校验，但这只证明证据链一致，不表示 external callee 语义已通过；semantic acceptance 仍由 validation gates 决定。
- direct call / stdlib 模型边界：显式最小模型包括 `assert(int)`、`abs(int)`、target-ABI-bound `strlen(const char *)`、bounded `strnlen(const char *, size_t)`、`memcmp(const void *, const void *, size_t)`、statement-only `memset(dst, byte_literal, size)` 和 statement-only `memcpy(out, src, size)`；direct call 实参当前只额外允许唯一实参是单标量 inc/dec，或唯一实参是一条单链 nested direct call 且最内层唯一实参是单标量 inc/dec；多 sibling nested call、任意层混入普通实参、复杂 target 或其它 side effect 仍 fail-closed。其它 C macro / stdlib / extern surface 仍需要单独模型或 signature/source binding，否则 fail-closed。完整支持面以 `COVERAGE.md` 和 `validation/translator-coverage-matrix.json` 为准；这些模型仍是 candidate generation，尚不能声明对应 named-slice L3 C/Rust diff 或 semantic pass。
- Standalone inc/dec statement：普通 `value++`、`++value`、`value--`、`--value` 在表达式值被丢弃的 statement 位置可 lowering 成 typed IR assignment，并发射为 `value = value +/- 1`；direct by-value record dot-field statement target（例如 `p.x++` / `--p.x`）和 direct mutable record pointer field statement target（例如 `p->x++` / `--p->x`）也可在各自 gate 下 lowering 成 `field = field +/- 1`。这只覆盖简单整数变量 target、direct by-value record dot-field integer target、direct single-pointer mutable record pointer scalar field target；不表示通用 value-position inc/dec、condition/return 中 inc/dec、call argument 中除单标量 direct-call 或单链 nested direct-call 子集之外的 inc/dec、`ForStmt` step 中 pointer-arrow/nested/复杂 record-field inc/dec、nested/array/复杂 field target 或完整 C 自增表达式语义已支持；direct by-value record dot-field inc/dec 只在简单 value-discarded `ForStmt` step 子集中支持。
- 核心翻译边界：上述 bitwise OR `|` / left shift `<<`、signed unary minus、compound assignment family、value-position integer implicit cast preservation、binary operand integral cast preservation、comparison expression、logical not、condition/value-position short-circuit `&&` / `||`、纯整数 value-position `ConditionalOperator` / `?:`、窄化 scoped `ForStmt`、loop-body `break`、窄化 loop-body `continue`、pointer-null presence、readonly direct deref read 和 bounded readonly pointer offset-deref read 都只是 candidate generation only；bitwise OR `|` / left shift `<<` 目前仅覆盖窄化标量整数候选生成，不代表完整 C 位运算或位移语义；compound assignment 目前接受 simple scalar variable target 和 standalone 按值 record dot-field target，其中 record dot-field target 的 RHS 只接受简单整数变量、字面量或整数 cast；要求 clang target/result 类型一致、compute lhs/result 类型一致，且所有相关类型都是受支持整数；如果 compute type 不同于 target type，会显式 cast 到 compute type 计算，再 cast 回 target type 赋值；value-position 和 binary operand implicit cast preservation 目前只接受 clang `IntegralCast` / `IntegralPromotion` 节点，且 typed IR emitter 必须能证明 source/target 都是可支持整数类型并且 cast 后 operand/result 类型严格对齐；函数指针 decay、pointer/float cast、隐藏副作用转换和完整 usual scalar conversions 不在这个子集内；comparison 目前覆盖条件位置和窄 value-position C `int` 0/1 materialization，例如 `return x > 0`、assignment RHS 和 declaration initializer，也覆盖 comparison operand 上 source/target 都是可发射整数类型且 cast 后两侧类型完全一致的 integral cast、readonly direct deref read operand，以及 bounded readonly pointer offset-deref read operand；pointer-null presence 仅限 readonly integer pointer 参数只出现在 `== NULL` / `!= NULL` 检查中，发射为 `Option<&[T]>` 加 `.is_none()` / `.is_some()`；logical not 目前覆盖整数条件零比较、readonly direct deref read operand、bounded readonly pointer offset-deref read operand，以及窄 value-position C `int` 0/1 结果语义；short-circuit 目前覆盖 `if` / `while` 条件中的 `&&` / `||`，以及 return value、assignment RHS 和 declaration initializer 中的窄 value-position C `int` 0/1 materialization，左右操作数递归复用当前条件表达式子集并保留 Rust `&&` / `||` lazy 求值；conditional `?:` 目前只覆盖纯整数 value-position，并拒绝 condition-position `?:`、expression-statement `?:`、GNU omitted-middle `a ?: b`、分支副作用、pointer/floating/aggregate 结果和未建模 usual scalar conversions；scoped `ForStmt` 目前只覆盖 simple scalar declaration/assignment init（含多个简单 `VarDecl` declarator）、condition、scalar variable 的 assignment/compound-assignment/postfix-or-prefix inc-dec step、direct by-value record dot-field inc/dec step、现有 statement body 子集、loop-body `break` 和窄化 loop-body `continue`；同一层 scoped `ForStmt` body 内的 `continue` 会先发射当前 step 再发射 Rust `continue;`，嵌套循环里的 `continue` 只作用于内层循环。`goto` / `switch`、condition variable slot、空 condition/step、condition 中 call/inc/dec/side effect、复杂 init/step、direct-call 参数子集之外的通用 value-position inc/dec、parenthesized/comma/complex step、pointer-arrow/nested/复杂 record-field step target、非 simple scalar 或 direct by-value dot-field step target、以及完整 C for-loop control-flow semantics 仍 fail closed。除 bounded readonly `*(p+i)` read 外的任意 pointer arithmetic、任意 pointer comparison、float comparison、未由 clang-preserved 或显式整数 cast 对齐的 mixed-width/unsigned conversions、未支持的 compound target、record field compound assignment 复杂 RHS、未被上述 compound-assignment guard 证明的 promotion/truncation、admitted direct-call 或单链 nested direct-call 形状之外的 call/inc/dec/side-effect operand、pointer truthiness、null check 后继续 deref/index 使用、float truthiness、unsupported type、完整 usual scalar conversions、无效 shift count、signed shift/overflow UB parity、unsigned/wrapping 取负、浮点取负、特殊 literal/min-value 边界、完整 C for-loop control-flow semantics 和 semantic acceptance 仍 fail closed。

## 最新算术边界

- typed IR 对 C unsigned `+` / `-` / `*` 发射显式 `wrapping_add` / `wrapping_sub` / `wrapping_mul`，避免 debug/release 溢出行为分叉；这仍是 candidate generation，semantic pass 仍由 C oracle 和 validation gates 决定。

## 最新路由来源边界

- 启用 `clang-lowering-report` 但 clang-lowered typed IR 不能生成 Rust draft 时，fallback 到 legacy string translator 不再是静默行为。translator 原始 artifacts 和 `auto_migrate.py` 归一化 evidence 都记录 `translation_source`，JSONL 包含 `translation_fallback`；route/profile 中 legacy 只允许出现在 `compatibility_sources` 和 `compat:legacy-string-translator` candidate 里，不能作为 `primary_candidate` 或 `selected_candidate_id`。这只是 provenance，不代表 C2Rust/LLM 多候选 router 已完成。
- route/profile evidence 现在还会记录 `selection_policy.stage=post_generation_provenance`、`selected_candidate_id` 和 `candidate_set`，把 primary Rust draft、typed-IR signal 与 C2Rust baseline context 放进同一份可审计清单；C2Rust baseline candidate 会绑定 baseline manifest 与 generated output ref/hash，validator 会拒绝候选集合 id 漂移、C2Rust baseline 冒充语义来源、baseline manifest/status/reason/output 漂移，以及任何 candidate 自称 `semantic_pass=true`。`selection_policy.full_router=false`，说明 score/hard gate、C2Rust/LLM 调度和语义接受仍未完成。

## 双语文档约定

- 面向用户或 Agent 的新增文档，默认使用中文主文档 `.md` 和英文镜像 `.en.md`。
- 修改已有文档时，如果改动超过小修小补，应同步维护对应英文镜像。
- 架构决策维护在本目录的中英文文档中；实施状态、顺序和剩余工作只写入 `future-vision-and-mvp.md` 及其英文镜像。
- 本目录仍有早期文档采用“中文说明 + English summary”混合格式；后续触及时按上述约定拆成完整双语版本。
- 全局待办唯一来源是 `future-vision-and-mvp.md`；`future-vision-and-mvp.en.md` 只是同步镜像，不另立待办来源。

## 文档地图

- 入口与状态：见 `index/README.md`。核心入口是 `README.md` / `README.en.md`，评委 before/after 演示入口是 `judge-demo.md` / `judge-demo.en.md`，机器可读状态见 `baseline-record.json`。
- 架构与合约：见 `index/architecture.md`。覆盖 `agent-contract.md`、`baseline-and-versioning.md`、`context-store-and-self-healing.md`、`core-translation-architecture.md` / `core-translation-architecture.en.md`、`l0-l4-routing-and-evidence-gates.md` / `l0-l4-routing-and-evidence-gates.en.md`。
- 运行与验证：见 `index/operations.md`。覆盖 `quickstart.md` / `quickstart.en.md`、`opencode-agent-harness-design.md` / `opencode-agent-harness-design.en.md`、`build-and-c2rust-baseline.md`、`bounded-auto-translation-pipeline.md` / `bounded-auto-translation-pipeline.en.md`、`evidence-governance.md` / `evidence-governance.en.md`、`testing-unsafe-cache-and-milestone.md`、`full-regression-runner.md`、`../../config/competition-env/`。
- 覆盖与路线：见 `index/roadmap.md`。覆盖 `COVERAGE.md` / `COVERAGE.en.md`、`future-vision-and-mvp.md` / `future-vision-and-mvp.en.md`。
- FlashDB 用例边界：见 `index/flashdb.md`。覆盖 `baseline-record.json`、`build-and-c2rust-baseline.md`、`flashdb-rust-skeleton-and-milestone.md`、`full-regression-runner.md`。
- 分析：见 `index/archive.md`。覆盖 `analysis/translator-strengthening-analysis.md` / `analysis/translator-strengthening-analysis.en.md`。


## 快速使用

```bash
```

然后运行 Agent phase，例如：

```bash
c2rust-migrator --phase index --input request.json
```

当前评委展示路径见 `judge-demo.md`，首选从 `config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json` 生成真实 FlashDB before/after exhibit、judge report、context pack、agent index 和 milestone release report。该 profile 已接入 `real-fdb-calc-crc32` 的真实 `baseline_repair_gate`：第 1 轮记录 `unsafe_baseline_requires_repair`，第 2 轮携带 repair hint 复验 accepted safe evidence；repo-local demo profile 仅作为保底路径。

## 运行原则

- 实现前先核对唯一全局待办和机器可执行验证合同。
- context local-first，并限制 token。
- 只在只读任务或不相交写入任务上并行多个 subagent。
- 先用确定性规则，再使用 AI。
- AI 输出只能作为候选，不能作为证据。
- C2Rust 输出只作 baseline/oracle。
- 优先迁移小的、可编译通过的 slice。
- 用 Rust 测试和 C/Rust differential evidence 证明行为。
- 跟踪 unsafe，并把比例控制在 10% 以下。
- 不把 unsafe < 10% 或 0 findings 解读为 C ABI、FFI、flash hardware、volatile register、RTOS、多线程或中断语义已解决；这些能力进入实现前必须具备 unsafe ledger span、替代方案、target/test evidence 和人工 review 状态。
- 只有显式 invalidation 和 equivalence gates 时才加 cache。

## Native Windows 工具说明

当前主机已有 native LLVM `clang`（默认路径 `C:/Program Files/LLVM/bin/clang.exe`），本轮真实 clang AST smoke 已使用它验证。PATH 仍可能缺少 native `c2rust`、`cmake`、`bear`、`intercept-build`、`cargo-nextest`、`cargo-llvm-cov`、`cargo-fuzz` 和 `cargo-geiger`。设计仍然有效，但这些 gate 需要 WSL/Linux 或后续工具安装后才能声称完整迁移验证完成。
