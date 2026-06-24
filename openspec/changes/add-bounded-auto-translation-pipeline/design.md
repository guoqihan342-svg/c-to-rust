## Context

当前仓库已经完成多层验证资产：L1 多项目 native C smoke、L2 safe Rust slice、FlashDB L3 schema-aware diff、pointer graph、test-translation、unsafe ledger、version manifest、cache metadata 和 evidence manifest。短板不在“能否保存证据”，而在“能否从一个 C 函数 slice 自动产出可编译、可测试、可修复的 Rust 初稿与验证 harness”。

Corrode 证明了通用 C-to-Rust 翻译器可以用较小核心实现覆盖大量 C 语法，但它优先追求“任意 C 都吐 Rust”，常以 unsafe/raw pointer 保守落地，缺少本项目要求的 oracle、unsafe ledger、pointer graph、compile self-healing 和 OpenSpec 证据链。`F:\agent\codex\ctorustpaper\c-to-rust-翻译器嵌入方案.md` 对本项目有实际参考价值：它给出了 crate 化、分层 translator、默认 raw pointer、安全提升、oracle 管线接入的方向；但需要收窄为“受限自动翻译器”，并用现有 gates 管住正确性。

`F:\agent\codex\ctorustpaper\c-to-rust-slice-自动化翻译管线方案.md` 进一步确认了正确方向应从“验证基础设施”推进到“slice 自动化翻译闭环”：选择 L1 target 的函数 slice，抽取 context/type/pointer/CFG，生成 Rust draft，编译自愈，oracle/diff 验证，并输出 evidence。本文采纳其中的 context extractor、candidate translator、build healer、batch slice selection 与 complexity signals 思路；但不采纳“项目继续小而精”、`tree-sitter` 作为语义事实源、DeepSeek 硬依赖、或 LLM 输出直接作为正确性依据。

用户已取消“小而精”的规模限制，允许项目按验证能力扩大为多 crate、多工具、多 target 的自动翻译系统。因此本 design 允许新增 translator crate、context extraction、AI candidate、build healing、batch migration 等模块；但每个迁移结论仍必须是 slice-bounded、evidence-bound、可回滚、可复现，不能把规模扩大解释为放宽 L1-L3 gates 或承诺通用 C99 全量翻译。

## Goals / Non-Goals

**Goals:**
- 输入一个已通过 L1 的 C 函数 slice，自动生成 context pack、type map、pointer graph、CFG、Rust draft、C oracle harness 初稿、Rust replay test 初稿和 L3 evidence manifest。
- 建立“翻译 -> 编译 -> error stack 分类 -> PatchPlan -> 自动补丁 -> 重跑”的 bounded compile self-healing loop。
- 将自动翻译产物接入现有 L2/L3 验证链，继续以 C oracle、Rust replay、schema-aware diff、negative diff、unsafe scan、version manifest 和 OpenSpec validation 判定通过。
- 先支持明确边界的 C 子集：primitive integer/boolean-like expressions、assignment、return、if/while/for、simple calls、struct-by-name、const input pointer、out pointer、固定 fixture 驱动 oracle。
- 让 AI 成为可选候选生成器或修复建议器；离线规则、编译器错误和 evidence 才是事实来源。
- 建立可演进的管线角色边界：context extractor 负责事实抽取，candidate translator 负责 Rust draft 候选，build healer 负责 error stack 到 PatchPlan 的有界修复，evidence emitter 负责 L3 manifest 绑定。
- 为后续批量迁移保留 `auto_select_slice`/`batch_migrate` 扩展：只从 L1 accepted targets 中选择 complexity signals 清晰、oracle 可构造、pointer graph 可审计的 slice。
- 为未来更复杂项目保留扩展点：clang/compile_commands、宏展开差异、Corrode-style CFG relooper、differential fuzzing、code-test 同步翻译。

**Non-Goals:**
- 不承诺通用 C99/C11 全量自动翻译。
- 不承诺宏、VLA、union bitfield、复杂 typedef 链、跨线程语义、inline asm、setjmp/longjmp、非结构化 goto 在第一版被翻译成功。
- 不把 Rust draft 编译通过等同于语义等价。
- 不允许自动修复修改 C oracle 合约、fixture expected behavior、accepted differences、公共 API 边界或扩大 unsafe 预算。
- 不把 async、多线程、并行 replay 当作默认性能优化；只有测到瓶颈并保持确定性后才加入。

## Decisions

### Decision 1: 新增 `c2r-translator` crate，但定位为 bounded draft generator

选择：新增 `crates/c2r-translator/`，公开小 API，如 `translate_c_slice(request) -> TranslationResult`。输出 Rust draft、type map、pointer graph、CFG、unsupported nodes、unsafe summary、generated artifact paths 和 provenance。

理由：把翻译能力从 Python 脚本/手写 slice 中剥离出来，便于测试、版本锁定和作为 OpenCode/Codex/其他 Agent 的可调用内核。它不负责最终正确性，只负责生成可审计候选。

替代方案：
- 直接嵌入 Python 脚本：接入快，但难以形成可测试的 Rust IR 和后续 safe pointer promotion。
- 直接调用 c2rust/corrode：广度更强，但难以满足本项目的受限、安全、证据化、自愈和 unsafe 比例要求。

### Decision 2: compile profile/clang 作为语义事实源，tree-sitter 只做辅助

选择：第一版的 slice request 必须携带 build profile，包括 include paths、defines、target triple/ABI、source commit、fixture contract 和 L1 recipe 来源。能使用 `compile_commands.json`、clang/libclang 或 WSL/Linux clang profile 时，类型、宏展开后 AST、隐式转换、struct layout 和诊断以该 profile 为语义事实源。`tree-sitter-c` 只能作为快速索引、切片定位或容错扫描辅助；不能单独承担类型语义翻译。

理由：tree-sitter-c 适合快速抽语法树，但单独无法证明 typedef、macro、target ABI、隐式转换和声明消歧。Corrode 的有效部分也不是裸语法树遍历，而是预处理后 C AST 加类型环境。第一版要端到端跑通，必须把“无法确定”作为 evidence 失败，而不是猜。

替代方案：
- tree-sitter-only：快，但类型图容易错。
- clang-only：语义更强，但跨 Windows/WSL/CI 和依赖安装成本更高；因此 Windows host 可只做 orchestration，clang-backed 语义抽取可由 WSL/Linux/CI 产出。

### Decision 3: CFG evidence 先覆盖结构化控制流，不急于移植完整 relooper

选择：自动抽取 basic blocks、edges、entry/exit、branch condition、loop back edge 等 CFG evidence。MVP 只翻译结构化 if/while/for/return；发现 goto 或多入口非结构化 CFG 时生成证据并拒绝自动 Rust draft 或降级为 blocked candidate。Corrode-style relooper 作为后续阶段。

理由：验收标准要求自动抽取 CFG，不要求第一版支持所有 goto。直接做 loop 标签会在复杂 goto 上过度自信，反而破坏语义等价目标。

替代方案：
- 先做 loop 标签 goto：实现快，但容易错译非结构化跳转。
- 立即移植 Corrode relooper：价值高，但会吞掉本 change 的端到端闭环目标。

### Decision 4: 指针默认 raw，safe promotion 必须有 pointer graph 证据

选择：低层 draft/IR 默认把未知指针保持 raw pointer 或拒绝 safe promotion；Rust-native public API 默认不得暴露裸指针，必须通过 safe wrapper、newtype、validated buffer 或明确隔离的 FFI/internal 层承接。仅对只读 `const T*`、明确 len companion 的 buffer、out parameter struct/pod 写入等有限模式做 safe wrapper 或受控 unsafe 封装。每次 promotion 都写入 pointer graph 与 unsafe ledger。

理由：Aliasing Limits 类论文已经说明 aliasing 会链式污染安全翻译。项目要求 unsafe <10%，但不能用错误 safe promotion 换低 unsafe 数字。

替代方案：
- aggressive safe translation：unsafe 比例好看，但语义风险高。
- 全 raw pointer：实现稳，但无法逐步逼近安全 Rust。

### Decision 5: Oracle/replay 从 fixture contract 生成，不凭空猜测试输入

选择：`auto_migrate` 输入必须包含 fixture/test vector 或从既有 L2/L3 fixture 选择。工具根据函数签名与 fixture 生成 C oracle harness 初稿和 Rust replay test 初稿；无法映射输入/输出时标记 blocked。

理由：自动生成主干路径测试必须有明确输入域。随机 fuzz 可以补强，但不能替代主 oracle contract。

替代方案：
- 从函数签名随机猜输入：覆盖面看似大，但结果不可审计。
- 继续手写 oracle：正确但没有补齐自动翻译闭环。

### Decision 6: Compile self-healing 只能做局部、可解释、可回滚补丁

选择：编译失败时使用 `cargo check --message-format=json` 采集 error stack，分类 root cause，生成 PatchPlan，再按规则补丁；AI 可用于生成候选 patch，但 PatchPlan 必须列出文件、span、原因、预期 error delta、禁止改动、回滚 id、验证命令。默认最多 3 轮。

理由：库 API 更新、语法不兼容、类型不匹配是迁移常态，需要自动自愈；但自愈不能为了绿灯篡改语义边界。

替代方案：
- 失败即人工：安全但速度慢。
- LLM 直接改到编译过：速度快但不可审计。

### Decision 7: 现有 L3 evidence manifest 是最终门禁

选择：自动翻译闭环最终写入 `validation/evidence/<target>/`，并生成 evidence manifest，引用 context pack、type map、CFG、pointer graph、translation result、C oracle、Rust replay、diff、negative diff、unsafe scan、version manifest、compile self-healing events、AI usage 和 final verification。

理由：项目优势是 gates 和 evidence，不应被新 translator 绕过。

替代方案：
- 为 translator 另建独立验证体系：会导致重复和分裂。

### Decision 8: 采纳新 slice 管线的角色拆分，但不把 LLM 设为硬依赖

选择：逻辑上拆成 `context extractor -> candidate translator -> build healer -> semantic verifier -> evidence emitter`。当前 MVP 可以由 `crates/c2r-translator/` 和 `validation/tools/auto_migrate.py` 承载这些角色，待接口稳定后再拆分为独立 crate 或 provider。AI/LLM 层是 provider-agnostic candidate source，可用 DeepSeek、其他模型或本地规则；默认本地 pipeline 不要求在线 AI。

理由：新方案指出当前“验证基础设施跑得比翻译能力快”，这个判断成立。角色拆分能让 OpenCode/Codex/其他 Agent 接入同一闭环，也能让多智能体分工更清晰。但如果把 LLM 翻译作为唯一引擎，会损害可复现性、token 成本、安全边界和离线验证。

替代方案：
- 硬编码 `c2r-llm-translator` + DeepSeek：接入直观，但 provider 绑定、网络依赖和不可复现风险高。
- 只维护手写规则 translator：可复现，但复杂 slice 覆盖扩展慢；应允许 AI 作为候选层补充。

### Decision 9: 项目规模可扩大，迁移声明仍按 slice 受限

选择：项目层面不再以“小而精”为验收约束，可以增长为多 target、多 crate、多阶段自动化系统。规模扩大通过 batch slice selection 落地：只选择 L1 accepted、fixture/oracle 可构造、unsupported constructs 少、pointer graph 风险可审计、上下文在 token budget 内的 slice；不合格 slice 记录 skipped/blocked evidence。

理由：未来目标包含比 FlashDB 更复杂的项目，自动翻译能力需要规模化验证。真正需要受限的是“每个迁移结论”，而不是整个项目代码量。单个 slice 的证据边界保持小且清晰，项目整体可以逐步扩大。

替代方案：
- 继续限制项目小而精：会阻碍 batch migration、复杂 C 项目验证和 translator 能力补齐。
- 一次性做全项目迁移：会破坏跨文件关系、oracle 边界和语义等价证明。

## Risks / Trade-offs

- [Parser 类型不准] -> MVP 显式记录 unsupported/type ambiguity；优先使用 compile flags 和 fixture contract；后续接 clang-backed extraction。
- [自动 translator 生成可编译但语义错误] -> C oracle/Rust replay/schema diff/negative diff/differential fuzz 阻断通过。
- [safe pointer promotion 引入 aliasing bug] -> 默认 raw 或受控 unsafe；promotion 必须有 pointer graph 证据和测试覆盖。
- [自愈补丁误改语义] -> PatchPlan 禁止修改 oracle、fixture、accepted differences、公共 API 外边界和 unsafe budget；触发即 blocked。
- [项目规模扩大导致复杂度失控] -> 每个新 C 子集必须有 OpenSpec requirement、fixture、translator unit tests 和 L3 evidence；不在 MVP 中默认支持。
- [AI 调用不可复现或泄漏上下文] -> AI 使用必须记录 prompt scope、输入摘要、输出 hash 和是否被采用；默认本地规则优先，AI 不作为事实来源。
- [批量迁移扩大后质量下降] -> batch selection 只产生 candidate queue；每个 slice 仍必须独立通过 slice spec、context/type/CFG/pointer evidence、compile/self-healing、oracle/replay/diff/unsafe/cache/OpenSpec gates。

## Migration Plan

1. 创建 `bounded-auto-translation-pipeline` spec 和 FlashDB L3 delta spec。
2. 新增 translator crate 骨架与 fixture-driven integration test，先让一个已知 L1/L2 slice 走完整链路。
3. 实现受限 C slice extractor，输出 context pack、type map、CFG、pointer graph。
4. 实现 Rust draft emitter、C oracle harness generator、Rust replay test generator。
5. 接入 compile self-healing：采集 rustc JSON、生成 PatchPlan、执行小范围补丁、记录 red/green evidence。
6. 接入现有 L3 evidence manifest、unsafe scan、version manifest、OpenSpec validation。
7. 用至少一个 pointer-bearing slice 和一个纯函数 slice 回归，避免只验证安全区。
8. 保留 `auto_select_slice`/`batch_migrate` 接口与 candidate queue 设计：从 L1 accepted target 中按 complexity signals 产出候选、blocked 和 skipped evidence；当前 change 不以批量执行数量或 pass-rate 为验收条件，后续 change 再扩大批量运行。

Rollback：所有生成物必须带 `generated_by`、input hash 和 cache key。若 translator 输出不可信，可删除本 change 新增的 generated artifacts，并保留原有手写 L2/L3 evidence 不受影响。
