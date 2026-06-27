# L0-L4 路由、证据流与验证门禁设计

本文档详细解释 `validation/tools/auto_migrate.py` 的 L0-L4 路由决策、证据流拓扑和验证门禁的设计思路。英文镜像见 `l0-l4-routing-and-evidence-gates.en.md`。

## 1. 概述

自动翻译管线从真实 C 源函数出发，经过 slice 抽取、clang AST lowering、typed IR construction、Rust candidate generation，最终由多层验证门禁判定是否接受。

整个管线由两条主轴交叉构成：

- **路由轴（route decision）**：决定候选生成路径和上下文预算（L0-L4）。
- **验证轴（validation profile + evidence gates）**：决定本次运行必须通过的验证门禁，以及最终语义是否通过。

两条轴**独立但绑定**：route decision 记录"候选是怎么产生的"；validation profile 回答"产生了之后能不能接受"。

## 2. L0-L4 路由定义

```
L0: Catalog 目录校验                           (catalog 层)
    或 typed IR 确定性零 token 标量候选路由       (翻译 candidate 层)

L1: Native C 编译和测试烟测                     (基线层)
L2: 受限迁移切片编译 + 安全证据                  (编译层 + 边界证明)
L3: 行为级别等价性证据                          (语义层)
L4: 显式拒绝翻译 / accepted evidence authoritative (拒绝对)
```

### 2.1 两层 L0 的区别

| | Catalog L0 | Translation L0 |
|---|---|---|
| 来源 | `validate-c-project-catalog.ps1` | `auto_migrate.py` |
| 含义 | catalog 格式有效、目标可到达 | scalar-only `GenericTypedIr` + `token_cost=0`，不需要额外 AI/token 路线 |
| 证明 | 目录册完整性 | 候选生成路径为确定性零 token |
| 是否证明语义 | 否 | 否 |

Translation L0 只表示 typed IR candidate generation 的路径分类；真正的语义等价由 C oracle、Rust replay、schema diff、negative diff、unsafe ledger 和 final verification 决定。

### 2.2 各层含义

**L0 (Catalog)**：`projects.json` 是合法 JSON，至少 12 个目标，必填字段齐全。Optional remote HEAD probe 可到达。

**L0 (Translation)**：切片无 pointer surface（scalar-only），typed IR emitter 成功生成 `GenericTypedIr` candidate 且 `token_cost=0`。这是确定性翻译路径，不需要 AI 或额外 token 预算。

**L1**：pinned C checkout 在外部工作空间能编译并运行简单 smoke test。环境 profile、构建命令、工具版本都记录在案。L1 通过只表示 C baseline 可复现，不表示任何 Rust 翻译成功。

**L2**：输入 `auto_migrate.py`，translator 生成 Rust candidate，Rust 通过编译检查（`rustc` 或 `cargo check`）。pointer graph 记录指针依赖和 alias 风险。unsafe ledger 统计 first-party non-test unsafe。negative diff 证明 diff gate 能抓到故意错配。

**L3**：完整的语义等价证据链。C oracle 是 ground truth（可以是真实 C harness 输出、golden fixture 或 accepted C oracle report）。Rust replay 对相同输入执行 Rust candidate 并比较输出。schema-aware diff 比较 C oracle 与 Rust replay。negative diff 故意篡改一个期望值并确认 diff 失败。final verification 汇总所有 gate 结果。validation profile 要求无 skipped gate。

**L4**：两种形态：
1. **refused**：route decision 决定 L4/refused。translator.kind=refuse。candidate_generation_allowed=false。例如函数签名不匹配、pointer graph 不可解、环境不支持。
2. **accepted evidence authoritative**：slice spec 显式声明 `claim_boundary.accepted_evidence_authoritative=true`。route 仍是 L4/refused，但语义通过绑定到外部 accepted C oracle / Rust report / diff / negative diff / unsafe evidence，不是 generated draft。

## 3. 路由决策逻辑

`auto_migrate.py` 的 `route_level()` 函数按以下顺序判定路由等级：

### 3.1 硬拒绝条件（最高优先级）

以下条件直接返回 L4/refused：
- slice spec 无 `c_boundary` 或函数签名
- `--accept-existing-evidence` 下找不到可绑定的 accepted evidence
- `fixture_contract` 要求 accepted C oracle 但缺失

### 3.2 Typed IR Candidate Signal

如果 `clang-lowering-report.json` 有 `typed_ir_candidate`：

- `status=generated` + `route=GenericTypedIr` + `rust_draft_generated=true`：
  - scalar-only 且 `token_cost=0`：返回 L0（确定性零 token 候选路由）
  - 有 pointer surface 或 token_cost≠0：返回 L1
- `status=unsupported`：保留 `unsupported_reason`，返回 L2

Typed IR signal 不覆盖 alias risk floor（见 3.3）。

### 3.3 Alias/Risk Floor

typed IR 候选路由前，先检查 pointer graph 的 alias 状态：

- `alias_contract.decision=blocked`：保持 L3
- `requires_noalias_contract` 或 `unknown_alias`：保持 L2
- pointer ownership role 为 `unknown`：保持 L2

这些 floor 优先级高于 typed IR signal，避免 `GenericTypedIr` 把 alias 不安全的指针翻译误降到 L0/L1。

### 3.4 旧标量/指针启发式（fallback）

无 typed IR candidate 时，使用旧 heuristic 判断 L0/L1/L2/L3/L4，基于 pointer graph 的 surface 分析。

### 3.5 Accepted Evidence Authoritative Override

当 `--accept-existing-evidence` 且 slice spec 声明 `accepted_evidence_authoritative=true` 时，即使 typed IR 或旧 heuristic 给出 L4/refused，route policy 仍写入：
- `accepted_evidence_authoritative=true`
- `generated_draft_semantic_pass=false`
- `verification_profile=L4-accepted-evidence`

semantic pass 走外部 accepted evidence 绑定，不是 generated draft。

## 4. 验证门禁（Validation Profile）

Validation profile 决定本次运行必须通过的 gates。核心字段：

- `profile`: 例如 `L0-dev`, `L1-dev`, `L2-dev`, `L3-dev`, `L4-dev`, `L4-accepted-evidence`
- `status`: `passed`, `blocked`, `incomplete`
- `gates`: 每项 gate 的 required / actual / skipped 状态
- `generated_draft_semantic_pass`: 生成草稿本身是否通过语义。当前必须保持 `false`；即使 `final_verification.semantic_pass=true`，语义来源也是 accepted/named-slice evidence bundle，不是 generated draft 自身。

### 4.1 Gate 清单

| Gate | 说明 | required 条件 |
|------|------|--------------|
| `c_oracle` | C oracle 存在且状态为 `C_ORACLE_GENERATED` | L3 |
| `rust_report` | Rust replay report 状态为 `passed` | L3 |
| `schema_diff` | Schema-aware C/Rust diff 状态为 `passed` | L3 |
| `negative_diff` | Negative diff mutation 被正确检测 | L2-L3 |
| `unsafe_scan` | First-party non-test unsafe 计数 ≤ 阈值 | L2-L3 |
| `candidate_generation` | 候选生成路径（typed IR, string, C2Rust baseline） | L2-L3 |
| `competition_environment` | 比赛环境 profile 绑定 | L1, L3 |

### 4.2 Semantic Pass 判定

`semantic_pass_for_run()` 判定规则（简化）：

1. 所有 required gates 都有 `required_actual_status` 匹配 `required_expected_status`
2. `skipped_gates` 为空（没有被跳过但 required 的 gate）
3. 顶层 `status=passed`
4. L4/refused 默认不通过，除非 slice spec 声明 `accepted_evidence_authoritative=true`
5. `generated_draft_semantic_pass` 必须是 false（generated draft 本身不直接 claim 语义）
6. 当 L4/refused 通过 `accepted_evidence_authoritative=true` 绑定外部证据时，报告必须同时说明 `source=accepted_evidence_binding` 和 `generated_draft_semantic_pass=false`。

### 4.3 Profile 与 Route 的关系

```
route_decision       →   解答"候选从哪来、预算多少"
validation_profile   →   解答"需过哪些门、实际过了没"
semantic_pass        →   由 profile + gates 共同决定，不由 route 单独决定
```

route 被记录为证据流中的一个 artifact；validator 在 semantic pass 校验时会回查 route 是否与 profile 一致。

## 5. 证据流拓扑

完整的自动翻译证据目录包含以下文件，形成一条交叉引用链：

```
validation/evidence/<target>/auto-translation/<slice>/
├── l3-<slice>-translator-input.json          # 翻译输入
├── l3-<slice>-translation-plan.json          # 翻译计划（rules, call_expressions）
├── l3-<slice>-type-map.json                  # C→Rust 类型映射
├── l3-<slice>-cfg.json                       # 控制流图
├── l3-<slice>-pointer-graph.json             # 指针依赖图（v2 含 effect_graph）
├── l3-<slice>-rust-draft.rs                  # Rust 候选草稿
├── l3-<slice>-rust-check.json                # Rust 编译检查结果
├── l3-<slice>-test-translation-generated.json# Rust replay 执行结果
├── l3-<slice>-c-oracle-status.json           # C oracle 状态（含 harness draft/编译/执行）
├── l3-<slice>-c-oracle-harness-draft.c       # C oracle harness 草稿
├── l3-<slice>-rust-report.json               # Rust replay report
├── l3-<slice>-diff.json                      # Schema-aware diff
├── l3-<slice>-negative-diff.json             # Negative diff
├── l3-<slice>-c2rust-baseline-manifest.json   # C2Rust baseline
├── l3-<slice>-route-decision.json            # 路由决策
├── l3-<slice>-validation-profile.json        # 验证 profile
├── l3-<slice>-auto-translation-manifest.json  # 自动翻译 manifest
├── l3-<slice>-auto-cache-metadata.json        # 缓存元数据
├── l3-<slice>-evidence-manifest.json          # L3 evidence manifest
├── l3-<slice>-final-verification.json         # 最终验证
└── l3-<slice>-clang-dry-run.json              # Clang dry-run（可选）
└── l3-<slice>-clang-lowering-report.json      # Clang lowering report（可选）
```

### 5.1 引用链一致性

每个 artifact 的关键字段（sha256, status, path）被多个其他 artifact 交叉引用。Validator 会检查：

1. **Manifest refs 一致**：auto manifest、L3 evidence manifest、final verification 中的 `schema_diff.sha256`、`negative_diff.sha256` 等与实际文件一致。
2. **Route↔Profile 一致**：`route_decision` 的 route level 与 `validation_profile` 的 profile 类型匹配；`candidate_generation` 内容完全一致。
3. **Cache identity 一致**：`cache_metadata` 的各类 identity（baseline、route、profile、effect_graph、competition_environment）与实际 artifact hash 匹配。
4. **C Oracle 绑定一致**：`c-oracle-status.accepted_oracle.sha256` 和 `auto_manifest.accepted_evidence_binding.path_sha256.c_oracle` 指向的 root C oracle 文件实际 hash 必须匹配。

### 5.2 Global Dependency 追踪

如果 slice spec 的 `c_boundary.direct_dependencies` 中有 `kind=global` 依赖：
- context-pack、type-map、pointer graph、C oracle status、harness draft 都必须同步声明该依赖
- cache metadata 必须包含 `global_dependency_identity`
- validator 按 canonical object（含 source_span, sha256, definition_status, linkage_requirement, semantic_status）校验，不只是 name 匹配

### 5.3 Effect Graph (v2)

`pointer-graph.schema.json` 升级到 v2 后，alias-sensitive 读写指针图必须包含：
- `effect_graph.effects[]`：每个指针节点的 read/write effects
- `effect_graph.edges[]`：alias risk 对应的 `requires_noalias` 或 `may_alias` 边
- cache metadata 中的 `effect_graph_identity`
- validator 要求每个 alias risk 都能在 effect graph 中找到对应边

Legacy v1 指针图可缺省 effect_graph，避免破坏历史 evidence。

### 5.4 Competition Environment Binding

新生成的 evidence 必须绑定比赛环境 profile：
- `validation_profile.competition_environment` 记录 `profile_id`、路径和 SHA256
- `cache_metadata.competition_environment_identity` 记录同一份信息
- `cache_input_fields` 中必须有 `competition_environment_identity`
- validator 要求两处一致

### 5.5 External Direct Callee Binding

当 slice spec 声明 `external_direct_callees` 时：
- plan `translation_summary.call_expressions` 必须包含对应 call site
- context-pack `direct_call_edges` 必须有对应 call edge
- 每个 declared callee 必须有 `call_edge_to_callee_binding`
- signature binding、source hash、stub status、semantics verified 都必须一致
- 默认 validator 和 semantic-pass validator 都执行此检查
- 这是 evidence integrity hardening，不表示 external callee 语义已通过

## 6. 翻译候选路由 vs 证据路由决策

这是整个管线中最容易被误解的地方。两者的关系如下：

| | 翻译候选路由 (Candidate Route) | 证据路由决策 (Evidence Route Decision) |
|---|---|---|
| 定义位置 | `crates/c2r-translator/src/translation_route.rs` | `validation/tools/auto_migrate.py` |
| 含义 | typed IR 候选是用哪个生成器产生的？| 整个 slice 的迁移路径和预算是什么？ |
| 字段 | `CandidateRoute::GenericTypedIr` / `Unsupported` | `route_decision.level: L0-L4` |
| 决定语义接受？ | 否。始终 `semantic_pass=false` | 否。语义接受由 validation profile + gates 决定 |
| 记录在哪里 | `clang-lowering-report.typed_ir_candidate` | `route-decision.json` |

关键原则：
- Candidate route 只选择候选生成实现，不决定语义接受。
- Evidence route decision 把候选 provenance 纳入 route rationale，但 alias/pointer risk floor 优先。
- 只有 validation profile + gates 全部通过 + no skipped required gate 时，才能声明 semantic pass。

## 7. Fail-Closed 设计原则

整个管线遵循 fail-closed 原则：不确定时宁可拒绝，不可假装成功。

### 7.1 翻译层 Fail-Closed

- typed IR emitter 遇到不支持的 IR 节点时返回 `IrEmitError`，不生成 Rust
- 旧 crc32 matcher 和 canned template 已删除；无 globals 的 crc32 IR 直接 fail closed
- clang frontend 遇到不支持的 AST 节点时记录 `unsupported_clang_stmt/expr/type`
- 数组初始化元素数量不匹配、类型不匹配、call/inc/dec operand 等全部拒绝
- `const void *` 只在 proven byte cursor 场景下映射为 `&[u8]`

### 7.2 验证层 Fail-Closed

- schema 要求所有 required properties 存在
- route 和 profile 中的 `candidate_generation` 必须完全一致
- `semantic_pass=true` 在任何 candidate/draft evidence 中都被拒绝
- L4/refused 下不允许残留 `candidate_generated`、`accepted_after_gates` 等状态
- `--require-semantic-pass` 下强校验所有 manifest ref 的 sha256/status
- accepted C oracle 文件的实际 hash 必须同时匹配 `c-oracle-status.accepted_oracle.sha256` 和 `auto_manifest.accepted_evidence_binding.path_sha256.c_oracle`

### 7.3 环境层 Fail-Closed

- 比赛环境 profile 路径和 SHA256 必须可复算
- cache metadata 和 validation profile 的环境 identity 必须一致
- `--skip-c-oracle` 时编译执行写 `skipped_by_flag`，不伪造 `C_ORACLE_GENERATED`
- 编译器不可用时写 `compiler_not_found`，不进入 subprocess

## 8. 完整验证命令

```powershell
# 翻译器 Rust 测试
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report

# Python 工具测试
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence

# Schema 合同测试
python -m unittest validation.tools.test_template_schema_contracts

# OpenSpec 全量 validation
openspec validate --all --strict

# FlashDB real-fdb-calc-crc32 证据验证
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json

# FlashDB semantic pass 验证
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass

# 全量回归
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 1 -SkipLongStress
```

## 9. 边界与限制

- L0-L4 路由只决定候选生成路径，不是"L3 = 已完成迁移"
- accepted evidence authoritative 路径是显式 opt-in，不能绕过 spec claim boundary
- FlashDB crc32 是第一个真实 C 源函数通过 typed IR → Rust draft → rustc smoke 的案例，但不表示所有 C 子集都能翻译
- pointer graph 的 alias gate 是风险门禁，不是完整 alias solver
- C2Rust baseline 仍是 `candidate_context_only`，不是语义等价证明
- `route_decision.level=L0` 与 catalog L0 是不同的证据概念，不能互相替代
