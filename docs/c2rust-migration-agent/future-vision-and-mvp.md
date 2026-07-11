英文镜像见 `future-vision-and-mvp.en.md`。

# C-to-Rust 未来愿景与 MVP 路线

本文是项目的中文 canonical backlog，也是当前状态、执行顺序和能力边界的唯一入口。详细实现过程由 Git 历史、coverage matrix 和机器可读 evidence 保存，不再把逐日流水账复制到本文。

最后更新：2026-07-11。

## 1. 当前状态

目标是构建可审计的端到端流水线：

```text
input.c
  -> clang / C2Rust / LLM candidate
  -> typed IR or verified unsafe baseline
  -> Rust candidate
  -> C oracle + Rust replay + diff + negative diff
  -> unsafe ledger + final verification
  -> accepted / refused / blocked
```

| 项目 | 当前值 | 准确含义 |
| --- | ---: | --- |
| `translator_generated_semantic_pass_count` | 32 | 32 个 translator-generated named slice 通过完整语义门禁，不代表全项目翻译完成 |
| `accepted_evidence_semantic_pass_count` | 1 | 独立 accepted-evidence 权威切片数，不进入 translator-generated numerator |
| 当前翻译主线 | P0-T21 | 组合 `fdb_kvdb.c:1868-1874` 的 zero-start 与 next-address 二分支 |
| 外部并行项 | P0-H9 | 在真实比赛主机完成 OpenCode + GLM-5.1 精确合同复验 |
| 最近提交阶段 | P0-T20 | `:1870-:1873` assignment-call、reset/add 和 current-level `continue` 已语义接受 |
| 当前证明等级 | `wsl-local-simulation` | 可用于开发和近似验收，不能冒充 `competition-exact` |

`validation/translator-coverage-matrix.json` 是能力计数的机器可读事实源。native C build、typed-IR 单测、rustc 编译、C2Rust output 或 LLM 输出单独通过都只是 candidate evidence。

## 2. 当前执行队列

### P0-A：翻译层主线

- [ ] **P0-T21：组合 `:1868-:1874` zero-start 与 next-address 二分支**

  把 `kv->addr.start == 0` 时的 `sector.addr + SECTOR_HDR_DATA_SIZE` 写入，与 P0-T20 的 assignment-call else-if、reset、traversed-length add 和 `continue` 放入同一个通用 carrier。

  最小验收状态集：zero-start、sentinel hit、zero miss、ordinary miss。

  必须保留：owner interior alias、局部 sector 副本、精确 `db -> itr` noalias、分支互斥、exact-`u32`/wrapping 语义和 current-level `continue`。

  明确不证明：真实 `SECTOR_HDR_DATA_SIZE` 宏展开、真实 `get_next_kv_addr` callee、line 1875 起的 `read_kv` 循环、完整 `fdb_kv_iterate`、FlashDB 全项目、record layout/ABI。

  完成条件：项目无关实现、正例和相邻负例、C oracle、generated Rust replay、schema diff、实际 negative mutation、unsafe/raw-pointer ledger、route/profile/final verification、严格 validator、coverage matrix 和中英文文档全部通过。

- [ ] **P0-T22：选择下一最小真实 source-backed gap**

  仅在 P0-T21 收口后选定。优先扩展相邻 `fdb_kv_iterate` 控制流或另一个真实项目中的通用 construct family；不得预先承诺完整函数或完整项目翻译。

### P0-B：比赛主机与 OpenCode

- [ ] **P0-H9：真实 OpenCode + GLM-5.1 比赛合同复验**

  当前 WSL 已能解析 provider-qualified `zai/glm-5.1`，但完整 preflight/worker marker 尚未在真实比赛主机闭合。OpenCode 只在能缩短独立任务或执行比赛合同复验时启用，不作为默认开发通道。

  完成条件：真实主机设置 `COMPETITION_EXACT_HOST=1`，`opencode models` 精确列出 GLM-5.1，preflight 使用 `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`，hash-bound probe/session/worker artifacts 完整，judge bundle 和 public packet 重新验证通过。

  WSL、本机和 CI 结果只能分别标为 `wsl-local-simulation`、`local-simulation` 和 `ci-approximation`，不能关闭 H9。

### P0-C：阶段收口

- [ ] 修复全量回归中与当前主线无关的 8 个历史 evidence 漂移项，按 artifact 所有权分批处理，不与翻译层功能改动混交。
- [ ] 清理 `cargo clippy --all-features --all-targets -- -D warnings` 的 17 个历史 feature-gated 告警；默认 Clippy 已通过，新切片不得增加告警。
- [ ] 在真实比赛主机复跑已闭合的 CRC32 C2Rust+repair before/after，并发布 competition-exact workflow metrics。

## 3. 后续 Backlog

### P1：扩大通用翻译能力

1. 建立完整 alias/noalias、pointer provenance 和 escape 模型，覆盖 readonly、mutable out、inout、nullable、跨调用和多 pointer 场景。
2. 把 integer promotion、usual arithmetic conversion、narrowing、array/function decay 和 ABI 相关转换显式保留在 IR。
3. 将组合式 side effect 建模为可组合规则，覆盖 sequence point、求值顺序、`++`/`--`、deref、index、member 和 call。
4. 扩展 CFG：先提供 `switch`/`goto` 的证据和 fail-closed 分类，再引入 relooper 或结构化 lowering。
5. 扩展 compound literal、designated initializer、function pointer、variadic、union、bitfield、VLA 和 flexible array member。
6. 建模 volatile、硬件寄存器、RTOS/中断、文件系统和断电恢复边界；host fixture 不能替代 target evidence。
7. 从 FlashDB、zlib-ng、libuv 等项目增加不同 construct family 的真实切片，避免用同类 checksum/parser 数量夸大覆盖面。

### P2：Agent、路由和发布

1. 把 raw C2Rust、C2Rust+repair、typed IR、LLM candidate 和 refusal 汇入可审计的多候选 router；共同 semantic gates 不得被路由绕过。
2. 维护小型 golden slice 集，记录模型、prompt、输入和候选输出 hash，评估模型升级影响。
3. 发布生成率、编译率、accepted/refused/blocked 比例、unsafe delta、repair rounds、人工介入点、耗时和证据成本。
4. 完成正式 tag/release、外部复核、CONTRIBUTING、ownership 和 release checklist。
5. CFG/SSA/MIR/LLVM/self-hosting 继续作为长期研究项，不抢占 P0/P1。

## 4. 已完成里程碑

| 范围 | 结果 | 语义计数变化 |
| --- | --- | ---: |
| P0-T0..T3 | ordered inc/dec、for-init comma、no-clang AST replay、do-while assignment-call candidate 基础 | 不计入 |
| P0-T4..T9 | `tsl_to_blob`、`fdb_is_str`、do-while continue、if assignment-call named-slice acceptance | 21 -> 24 |
| P0-T10..T13 | 通用 record/call/alias 扩展与 `fdb_kvdb.c:1870` exact fragment | 24 -> 25 |
| P0-T14..T17 | iterator tail call、traversed length、KV reset、sector-start | 25 -> 29 |
| P0-T18 | `kv = &itr->curr_kv` interior reborrow 安全投影 | 29 -> 30 |
| P0-T19 | `:1871-:1873` reset/add/current-level continue | 30 -> 31 |
| P0-T20 | `:1870-:1873` assignment-call condition 与分支体组合 | 31 -> 32 |

最近阶段验证：

- translator `cargo test --all-features` 通过。
- WSL competition-like Python 核心套件：`293 passed, 6 skipped`，另有 `90` 个 subtests 通过。
- 阶段全量回归执行 35 项，27 项通过；FlashDB 代码门禁和 file-backend 10,000 轮压力测试通过，8 项失败属于历史 evidence 漂移。
- P0-T20 严格 validator：`semantic_pass=true`、`generated_draft_semantic_pass=true`。
- 全功能 Clippy 仍有 17 个历史告警；这些告警不位于 P0-T20 新增代码行。

## 5. 架构边界

### 5.1 Candidate 路由

| 层级 | 作用 | 能否单独声明语义通过 |
| --- | --- | --- |
| L0 deterministic | 极小且已证明的机械规则 | 否 |
| L1 generic typed IR | 通用 AST/type/alias 驱动候选 | 否 |
| L2 C2Rust baseline/repair | 提供广覆盖 unsafe baseline 和安全化 before/after | 否 |
| L3 LLM/OpenCode | 生成或修复候选 | 否 |
| L4 refuse | 不确定时 fail-closed 并给出下一步 | 不适用 |

任何候选只有通过第 6 节的共同门禁后，才能成为 declared slice boundary 内的 semantic pass。

### 5.2 IR 分层

1. **Semantic IR**：显式表达 C integer width/signedness、cast、lvalue/rvalue、pointer provenance、volatile/atomic 和 UB/implementation-defined 边界。
2. **Control IR**：表达 block、branch、loop、break/continue/return 和未来 CFG/relooper 信息。
3. **Typed Value IR**：表达 scalar、record、array、pointer、function type、qualifier 和 ABI/layout provenance。
4. **Lowering**：选择 Rust ownership、borrow、slice、wrapping/checked arithmetic、raw pointer 或 refusal；IR 不应提前伪造 Rust 安全性。

## 6. 验收门禁

一个 named slice 只有同时满足以下条件，才能增加 translator semantic numerator：

1. 真实 source span、commit、fixture、carrier 和生成 candidate 的 hash 绑定一致。
2. C oracle 实际编译运行，Rust replay 实际编译运行。
3. schema-aware diff 通过，且至少一个能区分实现错误的 negative mutation 被实际执行并检测。
4. unsafe scan/ledger、route decision、validation profile 和 final verification 相互绑定。
5. 独立 validator 以 `--require-semantic-pass` 通过。
6. coverage matrix 派生计数更新；不得手工填写百分比替代机器结果。

以下结果不能单独提升 numerator：native C build、rustc compile-only、typed-IR 单测、no-clang fixture、C2Rust output、LLM 文本、route metadata、unsafe count 为零或 agent 口头判断。

比赛证明等级固定为：

| proof class | 允许来源 | 能否关闭 competition-exact 待办 |
| --- | --- | --- |
| `local-simulation` | Windows/本机 | 否 |
| `wsl-local-simulation` | WSL | 否 |
| `ci-approximation` | Linux CI | 否 |
| `competition-exact` | 有显式 host attestation 的真实比赛主机 | 是 |

## 7. 开发原则

1. FlashDB 是真实测试用例，不是 translator 特判来源；禁止读取项目名、函数名、路径或固定 fixture 值决定翻译。
2. 先做最小 source-backed slice，再扩相邻结构；每次放宽规则都要有正例和最近邻 fail-closed 负例。
3. C oracle 是声明边界内的 ground truth，但也受 fixture、compiler、flags、ABI 和 observable contract 限制。
4. fail-closed 必须给出 source span、拒绝原因和下一最小实现步骤，不能把拒绝数量当成功率。
5. unsafe 数量是治理指标，不是 FFI、并发、volatile、ABI 或硬件语义的完整安全证明。
6. evidence 使用 repo-relative path、稳定 hash 和明确保留策略；禁止把密钥和宿主绝对路径写入可发布 artifact。
7. 大文件按模块职责拆分；测试、schema、证据和文档改动只在确有行为或验收收益时加入。

## 8. 常用验证命令

```bash
cargo fmt --all --check
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
python3 -B validation/tools/translator_coverage_matrix.py --matrix validation/translator-coverage-matrix.json
python3 -B -m unittest validation.tools.test_doc_mirror_contract
python3 -B -m unittest validation.tools.test_validate_test_translation_coverage
git diff --check
```

比赛配置和 judge-chain 改动还必须运行：

```bash
python3 -B -m validation.tools.resync_sha_bindings --scan-root config/competition-env --dry-run --check
python3 -B -m validation.tools.resync_sha_bindings --scope judge-chain --dry-run --check
```

## 9. 文档维护规则

- 本文只保留当前状态、唯一活动队列、分级 backlog、里程碑摘要和稳定规则。
- 完成一项时更新状态表、活动队列、里程碑表和验证摘要，不追加逐日长日志。
- 精确 artifact、hash、case 和 validator 结果写入 coverage matrix/evidence；本文只写结论和边界。
- 中文文件是 canonical backlog；英文镜像必须在同一改动中同步。
- 旧状态需要追溯时使用 Git 历史，不新建第二份全局 TODO、handoff 或 roadmap。
