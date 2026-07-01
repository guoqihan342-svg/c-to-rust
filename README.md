英文镜像见 `README.en.md`。

# C-to-Rust Progressive Migration Pipeline

面向 Agent（Codex / OpenCode）调用的 C 到 Rust 渐进式迁移管线。本项目不是单次手工重写，而是一套可审计、fail-closed 的自动翻译器 + 强验证框架。

## 愿景

把真实 C 项目以**受限自动翻译 + 强验证**的方式渐进迁移到 safe Rust，同时保持业务逻辑不被破坏。核心理念：

- **翻译候选不是正确性来源**：C2Rust、LLM/Agent、手写规则都只能生成 candidate，必须经统一验证门禁。
- **正确性以原始 C 行为为准**：C oracle 是唯一语义 ground truth。
- **Fail-closed 优先**：不确定时宁可拒绝翻译，不可假装成功。
- **证据链可审计**：每一步决策和验证都有机器可读的 evidence manifest。

## 架构概览

```
┌──────────────────────────────────────────────────────────────────────┐
│                        C Source Repository                           │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Source Slice Extraction: extract_source_slice.py                    │
│  - 从真实 C 源文件抽取函数切片                                         │
│  - 识别全局依赖（如 crc32_table）                                     │
│  - 生成 typed slice spec                                             │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Translator: crates/c2r-translator/                                  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  clang_frontend.rs: clang AST dump 前端                        │  │
│  │  - 真实 clang -ast-dump=json 解析                               │  │
│  │  - C AST -> skeleton AST -> typed IR lowering                  │  │
│  │  - readonly global const array 收集（含 clang array_filler sparse initializer） │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  typed_ir.rs: Typed IR + Generic Rust Emitter                  │  │
│  │  - IrFunction / IrStmt / IrExpr / IrType                      │  │
│  │  - scalar / while / if / for / do-while / break / continue     │  │
│  │  - 整数运算、comparison、logical not、short-circuit            │  │
│  │  - readonly pointer slice、mutable pointer write               │  │
│  │  - global/local array、record field read                       │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  translation_route.rs: Candidate Route 元数据                   │  │
│  │  - GenericTypedIr: 通用 emitter 成功                             │  │
│  │  - Unsupported: fail-closed，保留 reason                       │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Auto Migration Pipeline: auto_migrate.py                            │
│  - 翻译器调用、C oracle harness 草稿                                  │
│  - Rust replay test 生成和执行                                       │
│  - route decision（L0-L4）和 validation profile 生成                  │
│  - cache metadata、evidence manifest                                 │
│  - 比赛环境 profile 绑定                                              │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Evidence Validator: validate_auto_translation_evidence.py           │
│  - schema 校验和跨 artifact 一致性检查                                │
│  - semantic pass gate 判定                                           │
│  - alias/effect graph 证据门禁                                        │
│  - external callee signature binding                                 │
│  - competition environment identity 校验                              │
└──────────────────────────────────────────────────────────────────────┘
```

## L0-L4 验证分层

| 层级 | 含义 | 核心证据 |
|------|------|----------|
| L0 | Catalog 目录校验 + 确定性零 token 候选路由 | `projects.json`、typed IR `token_cost=0` scalar-only candidate |
| L1 | Native C 编译和测试烟测 | `l1-native-build.json`、pinned commit、环境 profile |
| L2 | 受限迁移切片编译 + 安全证据 | pointer graph、unsafe ledger、Rust compile、negative diff |
| L3 | 行为级别等价性证据 | C oracle、Rust replay、schema diff、final verification |
| L4 | 显式拒绝对翻译或 accepted evidence authoritative | route `refused` 或 `accepted_evidence_authoritative=true` |

> 重要：`route_decision.level=L0`（typed IR 确定性候选路由）与 catalog L0（目录校验）是两回事。前者只表示翻译候选不需要额外 AI/token 路线，不证明语义等价。

## 当前状态

- **typed IR emitter**: `GenericTypedIr` 覆盖 scalar 算术（无符号 `+`/`-`/`*` 显式 wrapping）/控制流、bitwise、comparison、logical not、short-circuit、`?:`、scoped `for`/`do-while`、`break`/`continue`、readonly pointer slice、mutable pointer write、global/local fixed-length integer array read/write/init（global 仅 readonly `static const` index read，含受限 clang `array_filler` sparse initializer）、record field read、bounded direct call
- **clang 前端**: 真实 `fdb_calc_crc32` 已能经 clang AST dump → skeleton → typed IR → global table → Rust draft 生成 `GenericTypedIr` candidate
- **FlashDB accepted evidence**: `real-fdb-calc-crc32` 和 `real-fdb-blob-make` 已通过 semantic pass（L4 accepted-evidence authoritative 路径），generated draft 仍是 candidate，`generated_draft_semantic_pass=false`
- **FlashDB `fdb_kv_set`**: 已有 source/signature provenance 和 L4 refused/blocked evidence；`strlen`、`fdb_blob_make`、`fdb_kv_set_blob`、`fdb_kv_del` callee 语义仍未由 shim/model/oracle 关闭，不能声明 `fdb_kv_set` semantic pass
- **旧 crc32 特例代码**: typed IR canned matcher 和旧 string recognizer crc32 模板已删除；正向路径只走 clang-lowered typed IR + globals
- **候选清单 provenance**: 新 route/profile evidence 记录 `selection_policy.stage=post_generation_provenance`、`selected_candidate_id` 和 `candidate_set`（primary draft、typed-IR signal、C2Rust baseline context），并由 validator 拒绝任何 candidate 自称 `semantic_pass=true`；C2Rust baseline candidate 还会绑定 baseline manifest 与 generated output ref/hash，防止 route/profile 中的 baseline status、reason 或输出引用漂移。这还不是带 score/hard gate 的完整多候选 router。
- **仓库级 unsafe budget**: `validation/tools/unsafe_budget.py` 现在默认扫描 `crates/c2r-translator/src`、`flashDB_rust/src`、`validation/l2_slices/src`，加载 `validation/unsafe-budget-ledger.json`，并作为 core translator validation CI gate 执行。
- **入口 unsafe claim 边界（P0-162）**: unsafe < 10% 或 0 findings 只表示当前扫描/ledger 未超出预算或未发现已建模问题，不证明 C ABI、FFI、flash hardware、volatile register、RTOS、多线程或中断语义已经解决。任何这类能力进入实现前，必须先有 unsafe ledger span、safe/typed 替代方案、target/test evidence 和人工 review 状态。

## 当前 Harness MVP 状态

- 当前分支：`codex/agent-harness-flashdb-mvp`
- OpenCode harness 已有最小执行器：`python -m validation.tools.opencode_agent_harness run-worker --mode deterministic` 调用 repo-local `scripts/c2rust-migrator.py --phase migrate --input ...`，并在 worker summary 存在时自动入 SQLite ledger。
- OpenCode 包装入口已接好：`run-worker --mode opencode --opencode-variant max` 执行同一份 assignment request；preflight、run-plan、worker report 和 handoff contract 会绑定结构化 launch policy（command/model/agent/variant/skip-permissions），缺失或漂移会在启动 OpenCode 前 fail-closed；OpenCode/LLM 输出仍不是 evidence。
- accepted evidence 复用链路已接好：`assign-slice --reuse-accepted-evidence --accepted-evidence-root validation/evidence --slice-spec <maintained-spec>` 可在 worker 隔离目录下验证已提交 evidence。
- 评委 before/after demo 入口：`docs/c2rust-migration-agent/judge-demo.md`。首选真实 FlashDB profile 生成 `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`，并绑定 competition summary、workflow metrics、before/after exhibit、milestone report 与复制后的 `target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json` 的路径和 sha256；保底 demo profile 仍生成 `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json` 和 `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`。二者展示 baseline unsafe Rust → final safe Rust、accepted patch、oracle evidence、unsafe reduction，以及 planner/worker/verifier/repairer/reporter 五阶段 contract；review gate 只解除 release readiness 的 review blocker，不是 semantic acceptance gate；accepted-evidence before/after artifact 不增加 `translation_coverage_numerator`。
- 评委一键 harness runner：`python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json` 会按配置执行 competition smoke、before/after、显式多 worker 和 OpenCode 入口，并生成 `summary/judge-milestone-bundle.json` 与 `summary/milestone-release-notes.md`。本地 artifact 深校验现在会把 `competition-smoke-summary.json` 绑定到 judge config 的 `environment_profile.profile_id/sha256` 与 entrypoint 的 `proof_class/run_id`，并拒绝 CI/WSL/Windows 本地证据或带 `proof-class-limiting` deviation 的 summary 冒充 `competition-exact`；两个 `evaluate --profile` 入口还会写出 `harness/resume-manifest.json`，把 SQLite ledger、context pack、agent index、worker summary 和续跑入口串成 current-state 索引。`config/competition-env/bundle-manifest.json` 还把比赛配置目录升级为 hash-bound 归档合同，runner 报告会内嵌 `competition_config_archive` 快照。bundle 聚合 `core_translation_quality`、`harness_architecture_summary`、`route_governance_metrics`、`evidence_cost_retention`、`claim_scope`、`proof_classes`、`publishability`、`known_gaps`、`must_not_claim` 和复现命令，作为评委外部审阅索引；Markdown release notes 只是该 bundle 的人类可读投影，便于评委快速看 commit、source pin、scorecard、baseline comparison、known gaps 和禁止声明项。`validation/judge-milestone-bundle.schema.json` 锁定公开 claim boundary，并要求 run report `schema_version=1` 与 validator-owned proof-class contract 防越权；bundle、release notes 和 resume manifest 都不是 semantic gate，也不增加 `translation_coverage_numerator`。
- 公开 release packet：全量 runner 成功后还会写出 `summary/public-release-packet.json`，hash 绑定 run report、readiness report、milestone bundle、Markdown release notes 和 competition config archive，并由 `validation.tools.validate_public_release_packet` 按 `validation/public-release-packet.schema.json` 校验 schema、hash、claim boundary、本机路径泄漏，检查 packet 中复制的 publication manifest、known gaps、reproduction commands、must-not-claim 覆盖是否与被绑定的 bundle 一致，并要求 release notes 等于该 bundle 渲染出的 Markdown；它只是评委发布包索引，不是 semantic gate，也不增加 `translation_coverage_numerator`。
- FlashDB 当前已通过语义证据绑定的切片：`real-fdb-calc-crc32`、`real-fdb-blob-make`。二者均是 L4 accepted-evidence authoritative，generated draft 仍不是 semantic pass。
- FlashDB 当前阻塞切片：`real-fdb-kv-set`。其 direct callees 已有 signature/source provenance，但 `strlen`、`fdb_blob_make`、`fdb_kv_set_blob`、`fdb_kv_del` 的 shim/model/oracle 语义尚未关闭。

- **显式多 worker profile smoke**: `config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json` 会 fan-out 两个带 source pin 的 worker（`real-fdb-calc-crc32`、`real-fdb-blob-make`），并按 planner 顺序 merge。已验证 run `harness-flashdb-explicit-workers-20260701` 通过，accepted-evidence `semantic_pass=2`；同一 profile 的 `evaluate --profile` 入口也通过并生成 `harness/evaluate-report.json` 与 `harness/judge-evidence-index.json`，后者只索引已验证 batch artifacts 的路径与 sha256。语义结论仍来自 accepted-evidence binding、competition summary、workflow metrics 和 validators；它不是新的 semantic gate，也不增加 `translation_coverage_numerator`。tracked run manifest：`validation/evidence/flashdb/harness/l3-flashdb-explicit-workers-harness-run.json`。
- 启用 route-governance metrics 的 profiles 还会产出并绑定 `summary/route-governance-metrics-report.json`；`validation/route-governance-metrics.schema.json` 与 report 内 `retention_policy` 只锁定报告字段、artifact 保留策略和 public-claim boundary，不把 accepted-evidence、before/after 展品或 route-governance 指标升级为 translator-generated semantic pass，也不增加 `translation_coverage_numerator`。

- 评委入口本地 artifact 校验现在也会对非 smoke `competition_summary` 调用 `validate_competition_run_summary.py`，因此 workflow metrics、before/after artifact ref、repair history、unsafe 账本、final-gate 规则和 slice counts 都会走已有 summary 合同深校验，不再只靠 path+sha256 通过。

## 核心目录

| 目录 | 说明 |
|------|------|
| `crates/c2r-translator/` | Rust 翻译器 crate（clang 前端 + typed IR + emitter） |
| `validation/tools/` | Python 工具：`auto_migrate.py`、`validate_auto_translation_evidence.py`、`extract_source_slice.py` |
| `validation/slice-specs/` | 切片规格定义（FlashDB、demo slices 等） |
| `validation/evidence/` | 生成证据（demo、flashdb、libuv、zlib-ng 及 40+ 项目） |
| `validation/*-template/` | JSON Schema 和模板（pointer graph、slice spec、route、profile、L3 manifest 等） |
| `validation/l2_slices/` | Rust L2 参考实现和 C oracle fixture |
| `docs/c2rust-migration-agent/` | C2Rust migration agent 专题文档、分类索引、架构说明、contract、analysis 和 context archive |
| `docs/superpowers/` | 历史设计 specs 和 plans；不作为当前全局待办来源 |
| `openspec/` | OpenSpec 治理（specs、changes、config） |
| `scripts/` | 自动化脚本（全量回归等） |
| `config/competition-env/` | 比赛环境配置（Ubuntu 24.04、华为镜像、工具链版本、OpenCode 单次交互流程） |

## 待办来源

全局 roadmap/backlog 只维护在 `docs/c2rust-migration-agent/future-vision-and-mvp.md`。其它清单只允许是局部用途：OpenSpec `tasks.md` 是单个 change 的交付步骤，`validation/**/checklist.md` 是证据模板验收清单，`docs/superpowers/plans/**` 是历史实施计划，`validation/evidence/**/*.md` 是历史证据记录。

## OpenCode 比赛单次交互

比赛使用 OpenCode 直接调用本仓库，一次交互完成 C→Rust 迁移；若评测方设置 **600 分钟**，它只是外部预算参考，项目目标仍是准确性和证据完整性优先。详见 `config/competition-env/opencode-single-interaction.md`：

- 单次 prompt 模板（可并行处理互不依赖的 slice）
- 管线参考耗时（只用于规划，不作为验收条件）
- Agent 行为约束（不修改源码、并行输出隔离、fail-closed）
- 容错设计和比赛输出结构

## 快速命令

```powershell
# 运行翻译器测试（默认 feature）
cargo test --manifest-path crates/c2r-translator/Cargo.toml

# 运行翻译器测试（含 typed IR + clang frontend）
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report

# 运行 auto migration（以 FlashDB crc32 为例）
python validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root target/tmp --emit-clang-lowering-report

# 验证自动翻译证据
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json

# 语义通过验证
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-blob-make --slice-spec validation/slice-specs/flashdb-real-fdb-blob-make.json --require-semantic-pass

# Harness worker accepted-evidence 复用 smoke
python -m validation.tools.opencode_agent_harness run-worker --db target/competition-out/state/opencode-agent-harness.sqlite3 --run-id run-demo-001 --worker-id worker-a --mode deterministic

# 评委 before/after demo（首选真实 FlashDB 路径）
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
# 输出: target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json
# 证据索引: target/competition-out-flashdb-before-after-exhibit/harness/judge-evidence-index.json
# 保底 demo 输出: target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json

# 评委一键 harness runner（默认执行 competition smoke、before/after、多 worker、OpenCode 入口并深校验本地 artifacts）
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
# 公开审阅 Markdown: target/competition-out-flashdb-judge-entrypoints/summary/milestone-release-notes.md
# 公开 release packet JSON: target/competition-out-flashdb-judge-entrypoints/summary/public-release-packet.json
python -B -m validation.tools.validate_public_release_packet --packet target/competition-out-flashdb-judge-entrypoints/summary/public-release-packet.json
# evaluate 入口续跑索引: target/competition-out-flashdb-*-evaluate-profile-20260701/harness/resume-manifest.json
# 聚焦 before/after 展品时可只跑单入口；competition smoke 只证明环境和轻量 evidence gate，semantic_gate=false
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id before_after_judge_demo --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
# 只检查将要执行的入口，不运行命令或要求本地 artifacts
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --dry-run

# 全量回归
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
python validation/tools/unsafe_budget.py --max-ratio 0.10
openspec validate --all --strict
```

## 设计原则

1. **OpenSpec 治理**：需求 → 设计 → 任务 → 验收，所有改动先走 OpenSpec change。
2. **Candidate ≠ Correctness**：C2Rust、LLM、手写规则都只提供候选；正确性由 C oracle + evidence gates 决定。
3. **Fail-closed**：不确定时拒绝翻译并记录原因，不可假装成功。
4. **真实源码优先**：从真实 C 源文件抽取 slice/context，不能继续堆手写 `c_source` demo。
5. **证据链可审计**：每个函数的迁移证据包含 typed IR route、validation profile、diff、unsafe ledger、cache identity。
6. **Unsafe 控制**：Rust first-party non-test `unsafe` 比例目标 < 10%，但不把 0% 当硬性验收条件；unsafe < 10% 或 0 findings 也不代表 C ABI、FFI、flash hardware、volatile register、RTOS、多线程或中断语义已解决。上述能力进入实现前必须绑定 unsafe ledger span、替代方案、target/test evidence 和人工 review 状态。
7. **比赛环境可追溯**：所有自动翻译证据绑定 `config/competition-env/environment.json` 的 profile identity。

## 贡献与文档

- 会话接手短交接：`CONTEXT.md`
- C2Rust 专题文档索引：`docs/c2rust-migration-agent/README.md`
- 文档分类索引：`docs/c2rust-migration-agent/index/README.md`
- 唯一全局待办：`docs/c2rust-migration-agent/future-vision-and-mvp.md`
- 验证框架：`validation/README.md`
- 验证门禁：`validation/gates.md`
- 核心翻译架构：`docs/c2rust-migration-agent/core-translation-architecture.md`
- L0-L4 路由与证据门禁设计：`docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md`

## 代码分支

- 当前文档更新分支：`codex/agent-harness-flashdb-mvp`
- 主开发基线分支：`codex/flashdb-rust-skeleton`
- GitHub: `https://github.com/guoqihan342-svg/c-to-rust`
