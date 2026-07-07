## 154. 2026-06-28 external review triage: clang activation, legacy path, emitter composition

本轮继续处理用户贴出的外部评价，重点核对 typed IR 默认激活、legacy 字符串扫描、CI clang 端到端、signed/UB 语义、组合式 emitter、FlashDB showcase 和 `CONTEXT.md` 体积问题。

判断：
- 评价大方向成立：默认/比赛非 clang 路径仍可能走 legacy string translator；当前 CI 覆盖 all-features 和缺 clang 行为，但不等于真实 clang -> AST -> typed IR -> Rust 的端到端；value-position/raw `IrExpr::IncDec` 和复杂 side effect 仍主要 fail closed 或靠窄形状 helper；`flashDB_rust` 是手写安全 skeleton/验证基线，不是自动翻译产物。
- 需要修正的地方：`--competition-clang-lane` 缺 `CLANG_PATH` 会 fail-fast，不是静默 fallback；signed overflow 不能无条件改成 wrapping，因为 C signed overflow 是 UB，只有 `-fwrapv`/二补码 profile 或 slice contract 明确时才能走 wrapping；写自研最小 C parser 不适合作为主线，容易丢宏展开、类型、ABI 和 implicit cast 事实。
- 最有价值的下一步是让 typed-IR 核心在无 clang 环境也有 fixture replay 回归，同时保留真实 clang lane 做前端集成；再把 legacy string translator 降级为 compatibility-only，并推进组合式 side-effect expression lowering。

文档改动：
- `docs/c2rust-migration-agent/future-vision-and-mvp.md`
- `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

新增/强化的待办：
- 执行规则新增：无 clang 默认 CI/比赛路径不能把 legacy string translator 成功包装成 typed-IR success；typed IR 未运行必须在 evidence/metrics/公开叙述中标记 unavailable 或 compatibility fallback。
- 执行规则新增：`CONTEXT.md` 只能作为短 handoff，长会话日志要拆分或归档，不能当 release 文档、外部评估入口或能力证明。
- P0 新增：no-clang typed-IR fixture replay CI，提交小型 clang AST JSON 或 skeleton fixture，默认 CI 能跑 `AST JSON/skeleton -> typed IR -> generic emitter -> rustc/check`；手写 IR 单测不能替代这条回归。
- P0 新增：signed overflow/division/modulo/shift UB contract。signed wrapping 只能在 `-fwrapv`/二补码 profile 或 slice contract 明确时启用；division/modulo zero、非法 shift count 和实现定义 signed shift 必须有 negative test、evidence 字段和 refusal reason。
- P0 新增：showcase boundary，`flashDB_rust` 是手写安全实现/验证基线，不得当自动翻译产物展示。
- P0 新增：legacy string translator 降级并退役，标成 compatibility-only candidate source，在 route/metrics 中单独计数；no-clang fixture replay 和真实 clang lane 覆盖最小切片后从 primary candidate path 移除。
- P1 新增：组合式 side-effect expression lowering，把 sequence point、求值顺序、value-position/statement-position、`++`/`--`、deref/index/member/call side effect 建模为可组合 IR/emitter 规则；整段语句形状 helper 只作为过渡实现。

当前 roadmap 计数：
- Phase 1: 9/9
- Phase 2: 0/8
- Phase 3: 0/8
- Phase 4: 0/8
- P0: 7/19
- P1: 0/9
- P2: 0/6

边界：
- 可以说：这次把 clang 默认激活、legacy path、CI clang E2E、signed/UB contract、FlashDB showcase 和组合式 emitter 风险明确纳入 roadmap。
- 不应说：no-clang fixture replay、legacy 退役、signed UB contract 或组合式 side-effect emitter 已经实现。

## 155. 2026-06-28 external review triage: engineering debt, unsafe claims, test coverage

本轮继续处理用户给出的附件评价 `d03ac6c6.../pasted-text.txt`。两个只读子智能体分别核对了代码事实和 roadmap 覆盖缺口；评价里有价值的部分已纳入 `future-vision-and-mvp.md` / `.en.md`，过时或过激的结论没有照搬。

判断：
- 成立或部分成立：`typed_ir.rs` / `clang_frontend.rs` 仍是巨文件；`bounded_translation.rs` 也过大；`flashDB_rust` 是 host-verifiable handwritten skeleton，不是完整 FlashDB 语义等价；`ffi.rs` 仍是 placeholder；L1 native build 不等于翻译能力；0 unsafe findings 不能替代 FFI/hardware/ABI/volatile/thread evidence。
- 过时或不准确：`lib.rs` 仍 4232 行不符合当前事实（当前约 69 行，已经拆出多个模块）；“翻译器从未翻译 FlashDB 任何一行 C”已过时，`real-fdb-calc-crc32` 已有 clang AST dump -> typed IR -> Rust draft candidate，但 generated draft 仍是 candidate；“40/40 L1 通过”不符合当前 committed summary；“FlashDB 测试完全流于表面”过重，已有 fixture/diff/negative diff/abnormal data 测试，但覆盖仍需要量化。

文档改动：
- `docs/c2rust-migration-agent/future-vision-and-mvp.md`
- `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
- `flashDB_rust/README.md`

新增/强化的待办：
- P0 新增：拆分 `typed_ir.rs` / `clang_frontend.rs` 巨文件，按 IR 数据类型、validation、emitter、side-effect helpers、clang skeleton/lowering、report/evidence builder 做行为保持拆分。
- P0 新增：依赖与工具链引入原则。继续以 `CLANG_PATH` + clang AST dump JSON 为当前语义前端事实；libclang/bindgen/syn/quote/tracing/anyhow 等依赖只能在解决具体语义/生成/维护风险且符合 competition env 时引入。
- P0 新增：translator coverage matrix，按 IR construct、clang fixture replay、手写 IR、负例、runtime emitted Rust、C/Rust diff、legacy fallback 和 route evidence 统计覆盖。
- P0 新增：拆分 `bounded_translation.rs` 测试巨文件，按能力域拆分，但不能用测试文件数冒充覆盖提升。
- P0 新增：执行 `CONTEXT.md` handoff 收敛，建立短 current-state 入口，归档或标记 superseded 旧段，release/README/roadmap 不得依赖旧会话段作为能力证明。
- P1 强化：扩真实切片池时，FlashDB slice 必须绑定 translator-generated candidate，不能只用 `flashDB_rust` 手写 skeleton 当自动翻译证据。
- P1 新增：FlashDB FFI/C ABI/hardware 路线，`ffi.rs`、C ABI、on-disk layout、FAL/RTOS/Zephyr/hardware backend、错误/日志接口和同步/断电语义必须有 OpenSpec change、unsafe ledger、target evidence 或明确 deferred/L4 refusal。
- P2 新增：开源反馈循环，外部可评估 milestone 前补 `CONTRIBUTING`/issue template/review checklist 或等价文档；社区指标不是能力证明，但没有公开反馈记录时不能写成熟生产工具。
- `flashDB_rust/README.md` 修正：0 unsafe scan 只是当前 skeleton 扫描结果，不是生产安全、硬件安全、C ABI 兼容或完整语义等价证明；手写 skeleton 不算自动翻译产物。

当前 roadmap 计数：
- Phase 1: 9/9
- Phase 2: 0/8
- Phase 3: 0/8
- Phase 4: 0/8
- P0: 7/26
- P1: 0/10
- P2: 0/7

边界：
- 可以说：这次把附件评价中仍符合当前事实的工程债务和治理风险写进 roadmap，并修正了 `flashDB_rust` README 的 unsafe/handwritten 边界。
- 不应说：typed IR/clang frontend 已拆分、coverage matrix 已实现、FFI/C ABI/hardware 路线已实现、或项目已有成熟开源反馈循环。

## 156. 2026-06-28 external review triage: maturity, reproducibility, C2Rust baseline

本轮处理用户新贴的“项目缺点深度分析”。两个只读子智能体分别核查代码/evidence 事实与 `future-vision-and-mvp.md` 覆盖情况。结论是：评价大方向仍有价值，但部分事实混淆了 candidate draft、route refusal 和 accepted evidence。

判断：
- 成立或部分成立：项目还不是大型真实 C 项目自动迁移工具；FlashDB skeleton 是手写 seed/验证脚手架；C2Rust baseline 仍基本 skipped/candidate_context_only；typed IR 覆盖面窄；OpenSpec/validation/evidence 体系重；catalog L1 仍有失败；新手上手和跨平台复现仍需要更直接的入口。
- 不准确或过时：`real-fdb-calc-crc32` 不是仍 `semantic_pass=false`。当前 committed final verification/summary 是 `semantic_pass=true`，但 `generated_draft_semantic_pass=false`，route decision 可为 L4/accepted-evidence-authoritative/refused boundary。正确说法是：accepted evidence 语义通过，generated draft 仍是 candidate。`README.md` 也已存在，不是完全依赖 `CONTEXT.md`。
- 重要细节：代码路径支持 real clang AST dump lowering，但当前 committed evidence 仍缺 durable `clang-lowering-report` artifact；如果没有该 artifact，公开叙述应区分“代码路径支持”和“当前 committed evidence 已包含 real-clang lowering 证据”。

文档改动：
- `docs/c2rust-migration-agent/future-vision-and-mvp.md`
- `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

新增/强化的待办：
- 执行规则新增：C2Rust baseline 为 `skipped`/`blocked`/no output 时必须记录 reason、toolchain/env、input hash 和 `output_ref=null`，不得计入 generated/compiled/accepted/semantic pass。
- 执行规则新增：公开复现路径以 competition Linux/CI 为准；PowerShell/Windows 命令只能作为 local convenience，缺等价路径时标 local-only。
- 执行规则新增：evidence 必须可移植，新 evidence 优先 repo-relative path、profile id/hash、artifact hash，本机绝对路径只能是 diagnostic metadata。
- 目标描述收窄：Phase 1 证明改为“代码路径可支持 real clang lowering，但 committed evidence 还需补 durable real-clang lowering artifact；generated draft 仍是 candidate”。
- Phase 3 新增：catalogue L1 失败治理，报告 success/fail/skipped 比例、top failure classes、可修复/不可修复/环境缺失分类、排除规则和下一步。
- P0 新增：提交 durable real-clang lowering evidence，关键 real-source slice 必须有 real `clang-lowering-report` 或等价 artifact；no-clang/compatibility evidence 不能支撑 real-clang claim。
- P0 新增：evidence portability 清理，检查本机绝对路径、旧 WSL/Windows 工作目录、临时目录和缺失 profile hash。
- P0 新增：OpenSpec/validation 复杂度治理，归档 stale active changes，区分 lightweight release gate、developer smoke gate 和 full-regression gate。
- P2 强化：C2Rust baseline/repair 路线必须至少让一个真实 slice 产生 C2Rust output，并记录 output path/status/sha256，不能长期只有 skipped。
- P2 强化：量化评估必须加入 raw C2Rust、C2Rust+repair、typed-IR route、LLM candidate 和手写参考实现的竞品/基线对比。
- P2 新增：新手 quickstart，README 或 docs/quickstart 提供 10-15 分钟最小复现路径、Linux/CI 命令、可选 PowerShell 命令、第一条可验证 slice、预期 artifacts、常见失败和边界。

当前 roadmap 计数：
- Phase 1: 9/9
- Phase 2: 0/8
- Phase 3: 0/9
- Phase 4: 0/8
- P0: 7/29
- P1: 0/10
- P2: 0/8

边界：
- 可以说：这次把成熟度、C2Rust skipped、复现路径、catalog L1 failure、竞品对比和 quickstart 风险纳入 roadmap，并收窄了 real-clang evidence 表述。
- 不应说：C2Rust 已可执行、durable real-clang evidence 已提交、quickstart 已实现、catalog L1 失败治理已实现或 OpenSpec/validation 复杂度已收敛。

## 157. 2026-06-28 external review triage: fail-closed repair and evidence cost

本轮处理用户新贴的缺点评价。两个只读子智能体分别核查当前仓库事实与 `future-vision-and-mvp.md` 覆盖情况。结论是：评价大方向可参考，但多数风险已经在上一轮 roadmap 中覆盖；本轮只补两个真正缺口，避免重复堆待办。

判断：
- 成立或部分成立：当前语法覆盖仍有限；端到端真实切片案例少；项目不能被包装成生产级通用 C→Rust 工具；严格验证和 fail-closed 会带来人工介入成本；evidence/validation 的时间和存储成本需要治理。
- 已覆盖不需重复：Agent/LLM 只作为 candidate source；社区反馈和 milestone review；quickstart；公开叙述边界；C2Rust skipped；Linux/CI 复现路径；FlashDB 只是用例；复杂 C 特性如 function pointer/union/macro/多文件 TU 仍在 P1/P2/P4 待办。
- 不准确或无法仅凭本地仓库确认：根目录并非没有 `README.md`；`CONTEXT.md` 当前可访问，但不能作为外部评估入口；star/fork/watch 属于 GitHub 社区指标，本地仓库只能把“缺少公开反馈记录不得宣称成熟”写入 release 规则，不能把实时社区数字作为代码事实。

文档改动：
- `docs/c2rust-migration-agent/future-vision-and-mvp.md`
- `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

新增/强化的待办：
- 执行规则新增：fail-closed 不能变成死胡同；拒绝翻译时必须给出 source span、unsupported construct、缺失 IR/lowering 规则、oracle/fixture 缺口、可尝试候选源和人工 review 输入。
- 执行规则新增：evidence 成本必须受控；release evidence、developer smoke、diagnostic logs 和 historical archive 要分级，并记录 runtime、file size、retention/compression/prune policy。
- P0 新增：建立 evidence 成本和保留策略，报告 runtime、artifact count、total bytes、retention class、compression/prune policy。
- P0 新增：建立 fail-closed repair playbook，每个 L4/refused 或 blocked slice 输出 source span、IR feature gap、oracle/fixture gap、可尝试路线、最小下一步测试和人工介入点。
- P2 新增：降低单一维护者风险，外部 milestone 前补 CODEOWNERS/ownership 文档、reviewer rotation、issue triage 规则和 release checklist，关键流程不得依赖单个维护者或单次 Codex 会话记忆。

当前 roadmap 计数：
- Phase 1: 9/9
- Phase 2: 0/8
- Phase 3: 0/9
- Phase 4: 0/8
- P0: 7/31
- P1: 0/10
- P2: 0/9

边界：
- 可以说：这次把 fail-closed 后续修复路径、evidence 成本治理和单一维护者风险补进 roadmap。
- 不应说：repair playbook、evidence retention validator、evidence prune policy、CODEOWNERS 或 reviewer rotation 已经实现。
