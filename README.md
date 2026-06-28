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
│  │  - readonly global const array 收集                            │  │
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

- **typed IR emitter**: `GenericTypedIr` 覆盖 scalar 算术（无符号 `+`/`-`/`*` 显式 wrapping）/控制流、bitwise、comparison、logical not、short-circuit、`?:`、scoped `for`/`do-while`、`break`/`continue`、readonly pointer slice、mutable pointer write、global/local array、record field read、bounded direct call
- **clang 前端**: 真实 `fdb_calc_crc32` 已能经 clang AST dump → skeleton → typed IR → global table → Rust draft 生成 `GenericTypedIr` candidate
- **FlashDB crc32**: accepted evidence 已通过 semantic pass（L4 authoritative 路径），generated draft 仍是 candidate
- **旧 crc32 特例代码**: typed IR canned matcher 和旧 string recognizer crc32 模板已删除；正向路径只走 clang-lowered typed IR + globals

## 核心目录

| 目录 | 说明 |
|------|------|
| `crates/c2r-translator/` | Rust 翻译器 crate（clang 前端 + typed IR + emitter） |
| `validation/tools/` | Python 工具：`auto_migrate.py`、`validate_auto_translation_evidence.py`、`extract_source_slice.py` |
| `validation/slice-specs/` | 切片规格定义（FlashDB、demo slices 等） |
| `validation/evidence/` | 生成证据（demo、flashdb、libuv、zlib-ng 及 40+ 项目） |
| `validation/*-template/` | JSON Schema 和模板（pointer graph、slice spec、route、profile、L3 manifest 等） |
| `validation/l2_slices/` | Rust L2 参考实现和 C oracle fixture |
| `docs/c2rust-migration-agent/` | 设计文档、架构说明、contract |
| `docs/superpowers/` | 设计 specs 和 plans |
| `openspec/` | OpenSpec 治理（specs、changes、config） |
| `scripts/` | 自动化脚本（全量回归等） |
| `config/competition-env/` | 比赛环境配置（Ubuntu 24.04、华为镜像、工具链版本） |
| `codex/` | 分析文档 |

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

# 全量回归
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
openspec validate --all --strict
```

## 设计原则

1. **OpenSpec 治理**：需求 → 设计 → 任务 → 验收，所有改动先走 OpenSpec change。
2. **Candidate ≠ Correctness**：C2Rust、LLM、手写规则都只提供候选；正确性由 C oracle + evidence gates 决定。
3. **Fail-closed**：不确定时拒绝翻译并记录原因，不可假装成功。
4. **真实源码优先**：从真实 C 源文件抽取 slice/context，不能继续堆手写 `c_source` demo。
5. **证据链可审计**：每个函数的迁移证据包含 typed IR route、validation profile、diff、unsafe ledger、cache identity。
6. **Unsafe 控制**：Rust first-party non-test `unsafe` 比例目标 < 10%，但不把 0% 当硬性验收条件。
7. **比赛环境可追溯**：所有自动翻译证据绑定 `config/competition-env/environment.json` 的 profile identity。

## 贡献与文档

- 会话上下文（最新状态）：`CONTEXT.md`
- 验证框架：`validation/README.md`
- 验证门禁：`validation/gates.md`
- 核心翻译架构：`docs/c2rust-migration-agent/core-translation-architecture.md`
- L0-L4 路由与证据门禁设计：`docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md`

## 代码分支

- 主开发分支：`codex/flashdb-rust-skeleton`
- GitHub: `https://github.com/guoqihan342-svg/c-to-rust`
