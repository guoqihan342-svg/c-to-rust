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
| `translator_generated_semantic_pass_count` | 34 | coverage ledger 派生计数；不代表当前全量严格回归全绿，也不代表全项目翻译完成 |
| `accepted_evidence_semantic_pass_count` | 1 | accepted-evidence ledger 派生计数；当前唯一切片仍受历史 SHA 漂移阻塞 |
| 当前翻译主线 | P0-T25 | 为 `fdb_kvdb.c:1876` discarded direct-call body candidate 建立 source-backed 语义证据 |
| 外部并行项 | P0-H9 | 在真实比赛主机完成 OpenCode + GLM-5.1 精确合同复验 |
| 最近开发阶段 | P0-T24 | 已实现 `:1876` interior-reborrow do-while 单一 discarded direct-call body 通用 candidate；尚未计入语义通过 |
| 当前严格回归 | `26/34` | run `20260711T061416Z`；8 项历史 evidence 漂移仍未修复 |
| 当前证明等级 | `wsl-local-simulation` | 可用于开发和近似验收，不能冒充 `competition-exact` |

`validation/translator-coverage-matrix.json` 是能力计数的机器可读事实源。native C build、typed-IR 单测、rustc 编译、C2Rust output 或 LLM 输出单独通过都只是 candidate evidence。

## 2. 比赛环境

### 2.1 官方目标机基线

比赛环境的机器可读事实源是 `config/competition-env/environment.json`，profile id 为 `huawei-competition-ubuntu-24.04`，当前 raw-bytes SHA-256 为 `8f2233e9c8c4e7676524a72bf8db919b83e89366ec3cc76d3673d07f32488160`。开发、CI 和 WSL 可以模拟该配置，但只有真实主机满足 attestation 后才能写成 `competition-exact`。

| 项目 | 比赛目标值 |
| --- | --- |
| OS | Ubuntu `24.04.4 LTS`，codename `noble` |
| Kernel | `5.10.0-182.0.0.95.r194_123.hce2.x86_64` |
| Architecture | `x86_64` |
| Python / pip | `3.12.3` / `24.0` |
| Rust / Cargo | `1.96.0` / `1.96.0` |
| gcc / g++ / Make | `13.3.0` / `13.3.0` / `4.3` |
| Node.js / npm | `v24.13.0` / `11.6.2` |
| Java / Maven | Bisheng OpenJDK `21.0.10` / Maven `3.9.11` |
| `MAVEN_HOME` | `/usr/local/maven3` |
| Go / CMake | 不可用：`go` 未安装，`cmake` 未找到 |
| clang | 默认门禁不要求；typed-IR competition clang lane 显式要求 |

比赛配置固定使用以下镜像：

| 生态 | 镜像 |
| --- | --- |
| APT | `http://mirrors.tools.huawei.com/ubuntu` |
| PyPI | `https://mirrors.tools.huawei.com/pypi/simple` |
| npm | `https://mirrors.tools.huawei.com/npm/` |
| Cargo | `sparse+http://rust.inhuawei.com/crates.io-index/` |

`source config/competition-env/env.sh` 会设置 profile id、镜像、`MAVEN_HOME` 和 repo-local `CARGO_HOME=config/competition-env/cargo`，避免依赖用户全局 Cargo 配置。

### 2.2 比赛源码、clang 和 OpenCode 合同

FlashDB 比赛输入固定为：

| 字段 | 固定值 |
| --- | --- |
| repository | `https://gitcode.com/xwxf/FlashDB.git` |
| branch | `competition` |
| commit | `f9d0421315c564fb890a1b14eee77b290e0d7bbe` |
| checkout | `git checkout -B competition f9d0421315c564fb890a1b14eee77b290e0d7bbe` |

新的 competition-targeted slice extraction 必须同时传入 repository、branch 和 `--require-source-commit`，在生成 slice spec 前核对实际 checkout。历史 evidence 可以绑定旧 commit，但不能冒充新的比赛输入。

competition clang lane 不是默认依赖。启用 `auto_migrate.py --competition-clang-lane` 时，clang 必须来自 `CLANG_PATH` 或以下 repo-local 路径之一：

```text
tools/llvm/bin/clang-18
tools/llvm/bin/clang
tools/clang/bin/clang
```

可用性证明必须同时通过 `clang -print-resource-dir` 和包含 `stdint.h`、`stddef.h` 的最小 TU JSON AST dump。只有 `clang --version` 成功不够；`LIBCLANG_PATH` 不作为该 lane 的输入。缺失时应记录 `missing_clang_path`，不能回退后假装 typed-IR clang lane 已运行。

比赛侧 agent 合同固定为：

| 字段 | 要求 |
| --- | --- |
| command | `opencode` |
| logical model | `GLM-5.1` |
| repo-owned agent | `c2rust-migrator` |
| variant | `max` |
| retry cap | 最多 5 轮，每轮一个最小 patch |
| preflight | 同一 run/runtime env 下 `opencode models` 精确列出 GLM-5.1，并生成 hash-bound passed report/marker |

provider-qualified id 可以作为 resolved model id，但逻辑型号、probe 输出、preflight、worker argv、resume、judge bundle 和 public packet 必须一致。当前 WSL 的 `opencode models` 输出为小写 `zai/glm-5.1`；仓库当前 strict probe 要求最终 token 精确为区分大小写的 `GLM-5.1`，所以 `toolchain-check.sh` 仍报告“GLM-5.1 not listed”。这可以说明 provider 中存在对应模型，不能说明比赛 OpenCode 合同已通过。OpenCode 对话文本也不是 semantic evidence。

### 2.3 当前 WSL 与比赛目标对照

2026-07-11 在当前 WSL 实际探测到：

| 项目 | 当前 WSL | 比赛目标 | 结论 |
| --- | --- | --- | --- |
| OS | Ubuntu `24.04.3 LTS` | `24.04.4 LTS` | 小版本不同 |
| Kernel | `6.6.87.2-microsoft-standard-WSL2` | Huawei HCE `5.10.0-...` | 不同，不能等价 |
| Architecture | `x86_64` | `x86_64` | 一致 |
| Python | `3.12.3` | `3.12.3` | 一致 |
| Rust / Cargo | `1.95.0` / `1.95.0` | `1.96.0` / `1.96.0` | 不同 |
| gcc / g++ / Make | `13.3.0` / `13.3.0` / `4.3` | 同左 | 一致 |
| Node.js / npm | `v22.22.0` / `10.9.4` | `v24.13.0` / `11.6.2` | 不同 |
| Java / Maven | Ubuntu OpenJDK `17.0.19` / Maven `3.8.7` | Bisheng OpenJDK `21.0.10` / Maven `3.9.11` | 不同 |
| Go / CMake | Go 缺失 / CMake `3.28.3` | 两者都不可用 | CMake 不符合 |
| OpenCode | `1.17.18`，models 输出 `zai/glm-5.1` | 未固定二进制版本，strict GLM-5.1 启动合同 | strict model probe 未通过 |
| clang | 系统 `/usr/bin/clang` `18.1.3` | 可选，需显式来源和完整 smoke | 存在但未被 `env.sh` 自动选择 |

当前 WSL 实跑 `source config/competition-env/env.sh && bash config/competition-env/toolchain-check.sh` 返回 exit code 1 和 10 个不匹配项。系统 clang 虽然存在，但 `env.sh` 只自动选择 `CLANG_PATH` 或 repo-local vendored clang；在 WSL 模拟 competition clang lane 时必须先显式 `export CLANG_PATH=/usr/bin/clang`。实测显式设置后 resource-dir 为 `/usr/lib/llvm-18/lib/clang/18`，minimum-TU JSON AST smoke 通过，但其它 10 个环境差异仍使整体自检失败。

因此当前阶段的 WSL 结果只能标为 `wsl-local-simulation`。它能验证 Linux 路径、gcc/显式 clang、Python harness、Rust replay、FlashDB build/smoke 和大部分证据链，但不能证明目标 kernel、Rust 1.96、Node 24、Java/Maven、无 CMake 基线、strict OpenCode/GLM host 或比赛资源约束完全一致。

### 2.4 自检、模拟和正式运行入口

比赛机或 Linux/WSL 会话先执行：

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

`toolchain-check.sh` 会核对工具版本、镜像、Go/CMake 缺失约束、OpenCode model 状态；找到 clang 时还会执行 resource-dir 和最小 TU AST smoke。缺 OpenCode/GLM 默认只报告状态；要求比赛 agent 硬门禁时使用：

```bash
REQUIRE_OPENCODE_GLM=1 bash config/competition-env/toolchain-check.sh
```

当前 WSL 模拟 smoke：

```bash
bash config/competition-env/smoke.sh \
  wsl-local-simulation \
  target/competition-smoke-wsl
```

该 smoke 只验证环境和轻量 evidence gates，不翻译新 slice，也不产生 semantic pass。

真实比赛主机全入口运行：

```bash
export COMPETITION_EXACT_HOST=1
python3 -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --proof-class competition-exact
```

运行完成后必须深校验本地产物：

```bash
python3 -B -m validation.tools.validate_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --require-local-artifacts
```

仅做计划检查可加 `--dry-run`，仅调试单入口可加 `--entrypoint-id`；这两种 focused 结果都不能代替全入口 competition-exact 发布包。

### 2.5 当前已验证与未验证边界

当前已在 WSL competition-like lane 验证：P0-T20 的 C oracle、generated Rust replay、diff、negative mutation、unsafe gate 和严格 validator。日常全量回归不执行循环压力测试，压力循环不再是常规验收条件。易变的测试数量只在第 5 节按运行或提交绑定记录。

当前尚未验证：目标 kernel、Rust/Cargo 1.96、Node/npm 目标版本、真实 Huawei host package/runtime 差异、比赛资源上限、真实主机 `COMPETITION_EXACT_HOST=1` attestation、完整 OpenCode preflight marker、GLM-5.1 worker/session artifacts、全入口 competition-exact judge bundle 和 public packet。因此 P0-H9 仍未关闭。

## 3. 当前执行队列

### P0-A：翻译层主线

- [x] **P0-T21：组合 `:1868-:1874` zero-start 与 next-address 二分支**

  把 `kv->addr.start == 0` 时的 `sector.addr + SECTOR_HDR_DATA_SIZE` 写入，与 P0-T20 的 assignment-call else-if、reset、traversed-length add 和 `continue` 放入同一个通用 carrier。

  最小判别集固定为 5 例：zero-start non-wrap、zero-start wrap、sentinel hit、zero-return miss、ordinary miss。zero-start 必须跳过外部调用且不触发 P0-T20 的 `continue` 观察值。

  必须保留：owner interior alias、局部 sector 副本、精确 `db -> itr` noalias、分支互斥、exact-`u32`/wrapping 语义和 current-level `continue`。

  明确不证明：真实 `SECTOR_HDR_DATA_SIZE` 宏展开、真实 `get_next_kv_addr` callee、line 1875 起的 `read_kv` 循环、完整 `fdb_kv_iterate`、FlashDB 全项目、record layout/ABI。

  | 阶段 | 状态 | 完成判据 |
  | --- | --- | --- |
  | source boundary | 已完成 | 精确绑定 `fdb_kvdb.c:1868-1874`，不扩大到 line 1875 |
  | generic implementation | 已完成 | 项目无关的 typed-IR carrier 与 schema-v2 reporter 已提交 |
  | generic tests | 已完成 | 正例、相邻 fail-closed 负例和 translator 全功能测试通过 |
  | source-backed inputs | 已完成 | spec、fixture 与源片段 hash 可重生成 |
  | semantic evidence | 已完成 | C oracle、Rust replay、diff、negative、unsafe ledger 已生成并交叉绑定 |
  | strict acceptance | 已完成 | 第 7 节全部门禁通过，matrix 派生计数更新为 34 |

- [x] **P0-T22：下一切片决策门**

  - slice id：`real-fdb-kv-iterate-kv-tail`。
  - 真实 source span：固定 FlashDB commit 的 `src/fdb_kvdb.c:1885`，只绑定空 body do-while 尾部 assignment-call。
  - construct gap：owner interior projection 派生的可变别名同时作为 nested-u32 赋值目标和同一 direct call 的唯一同别名实参。
  - 最近邻负例：`typed_ir_rejects_assignment_call_sibling_read_when_owner_is_mutably_borrowed`；不得放宽 same-owner sibling read。
  - 停止条件：只生成 generic candidate；不覆盖 `1876-1884`、真实 `get_next_kv_addr`、完整函数、ABI 或 FlashDB 项目。需要函数名硬编码或弱化 noalias 时立即 fail closed。

  当前已完成 project-independent no-clang AST lowering、Rust emission/runtime 和非空 body/比较漂移负例；状态仍为 `candidate_context_only`，语义计数保持 33。

- [x] **P0-T23：`fdb_kvdb.c:1885` source-backed 语义闭环**

  已生成 source-bound spec、fixture、C oracle、Rust replay、schema diff、negative diff、unsafe ledger、route/profile 和 final verification。WSL `--competition-clang-lane` 下 strict validator 的 12 类语义绑定检查全部通过，`semantic_pass=true`、`generated_draft_semantic_pass=true`；停止边界固定在 line 1885，真实 `get_next_kv_addr` 和完整函数仍不在声明范围内。matrix 派生计数由 33 更新为 34。

- [x] **P0-T24：下一切片决策门**

  - slice id：`real-fdb-kv-iterate-read-kv-body-call`。
  - 真实 source span：固定 FlashDB commit 的 `src/fdb_kvdb.c:1876`，normalized-line SHA-256 为 `10948836c8ce66dea9de8d52dd04882b110c70acdabd785634c9e6d2660f2940`。
  - construct gap：owner interior alias 的 do-while body 中恰好一个有序、返回值被丢弃的 direct-call statement，随后继续执行既有 assignment-call tail。
  - 通用实现：只接受 `[Expr(direct Call), normalized tail assignment-call]`，body call 参数必须是已证明 noalias 的独立 call root 与同一 interior alias；空 body 旧形状继续兼容。
  - fail-closed：第二条 body 语句、非 call、嵌套 call、额外或重复可变根、owner sibling read 和比较漂移继续拒绝。
  - 停止边界：不覆盖 lines 1877-1884、真实 `read_kv` 语义、callee side effects、完整循环或 FlashDB ABI；禁止按项目名、函数名、slice id 或 fixture 常量硬编码。

  当前已完成 project-independent no-clang AST lowering、Rust emission/runtime 顺序验证和相邻负例；状态为 `candidate_context_only`，语义计数保持 34。

- [ ] **P0-T25：`fdb_kvdb.c:1876` source-backed 语义闭环**

  为 P0-T24 candidate 建立 source-bound spec、有限 fixture、fixture-only external call contract、C oracle、Rust replay、schema/negative diff、unsafe ledger、route/profile 和 final verification。只有 WSL competition lane strict validator 全部通过后才能增加语义计数。

### P0-A：AI/Harness 效率

- [x] **P0-A1：OpenCode no-progress retry suppression**

  对 effective request/source/spec/repair-trace/launch-policy 计算 `effective_input_sha256`，对结构化 root cause/status/returncode/diagnostics 计算 `failure_sha256`。连续两次确定性失败且当前输入仍无变化时，第三次启动前关闭 repair hint、清空 retry command、记录 `repair_retry_suppressed`，并以 `refused/retry_input_unchanged` fail closed；不调用 runner、不追加伪 attempt、不提升 semantic 状态。timeout、SQLite/OpenCode lock、preflight、credential、contract、环境缺失、未知根因或 hash 缺失/漂移均保留重试。

  该门减少无信息增量的 OpenCode 调用和 token 消耗，但不把 AI 输出当作语义事实，也不替代 C oracle、Rust replay 或 strict validator。

- [x] **P0-A2：`CLANG_PATH` 裸命令名与比赛 PATH 合同一致**

  Rust clang frontend 现在同时接受现有显式路径和由进程 `PATH` 解析的裸命令名，例如 `CLANG_PATH=clang`；带目录分隔符但不存在的显式路径仍保持 fail closed。WSL 上的 clang 18 最小 TU smoke 与 3 个真实 clang auto-migrate 正/负例均通过。该修复只恢复候选生成通道，不提升任何语义计数。

### P0-B：比赛主机与 OpenCode

- [ ] **P0-H9：真实 OpenCode + GLM-5.1 比赛合同复验**

  当前 WSL 已能解析 provider-qualified `zai/glm-5.1`，但完整 preflight/worker marker 尚未在真实比赛主机闭合。OpenCode 只在能缩短独立任务或执行比赛合同复验时启用，不作为默认开发通道。

  完成条件：真实主机设置 `COMPETITION_EXACT_HOST=1`，`opencode models` 精确列出 GLM-5.1，preflight 使用 `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`，hash-bound probe/session/worker artifacts 完整，judge bundle 和 public packet 重新验证通过。

  WSL、本机和 CI 结果只能分别标为 `wsl-local-simulation`、`local-simulation` 和 `ci-approximation`，不能关闭 H9。

- [ ] **P0-H10：CRC32 competition-exact before/after 发布**

  依赖 P0-H9。仅在真实比赛主机复跑已闭合的 CRC32 C2Rust+repair before/after，并发布 hash-bound workflow metrics 后关闭。

### P0-C：阶段收口

- [ ] **P0-C1：历史 evidence 漂移**。修复 run `20260711T061416Z` 的 8 个失败项，按 artifact 所有权分批处理，不与翻译层功能改动混交。
- [ ] **P0-C2：全功能 Clippy**。commit `81a772d1` 已清理 9 个低风险告警；当前剩余 8 个（2 个 `large_enum_variant`、1 个 `redundant_guards`、1 个 `needless_lifetimes`、4 个 `too_many_arguments`）。新切片不得增加告警。

## 4. 后续 Backlog

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

## 5. 已完成里程碑

| 范围 | 结果 | 语义计数变化 |
| --- | --- | ---: |
| P0-T0..T3 | ordered inc/dec、for-init comma、no-clang AST replay、do-while assignment-call candidate 基础 | 不计入 |
| P0-T4..T9 | `tsl_to_blob`、`fdb_is_str`、do-while continue、if assignment-call named-slice acceptance | 21 -> 24 |
| P0-T10..T13 | 通用 record/call/alias 扩展与 `fdb_kvdb.c:1870` exact fragment | 24 -> 25 |
| P0-T14..T17 | iterator tail call、traversed length、KV reset、sector-start | 25 -> 29 |
| P0-T18 | `kv = &itr->curr_kv` interior reborrow 安全投影 | 29 -> 30 |
| P0-T19 | `:1871-:1873` reset/add/current-level continue | 30 -> 31 |
| P0-T20 | `:1870-:1873` assignment-call condition 与分支体组合 | 31 -> 32 |
| P0-T21 | `:1868-:1874` zero-start 与 assignment-call 二分支组合 | 32 -> 33 |
| P0-T22 | 选择并实现 `:1885` interior-reborrow do-while tail candidate | 33 -> 33（candidate only） |
| P0-T23 | `:1885` owner-interior-alias do-while tail source-backed 严格验收 | 33 -> 34 |
| P0-T24 | 选择并实现 `:1876` discarded direct-call body candidate | 34 -> 34（candidate only） |

验证运行绑定：

| 验证项 | 绑定 | 结果 |
| --- | --- | --- |
| P0-T24 / P0-A1 / P0-A2 阶段验收 | WSL local simulation，2026-07-11 | translator library `228`、bounded `665`、integer conversion `4` 全通过，`133` 个 real-clang opt-in 默认忽略；3 个真实 clang focused tests、Python auto-migrate `155`、OpenCode harness `192` 全通过；未执行循环压力测试 |
| P0-T23 严格 validator | WSL competition clang lane，2026-07-11 | `semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过；3 个有限 fixture 案例覆盖 1/2/3 次调用 |
| P0-T22 translator candidate | 当前工作树，2026-07-11 | library `228` 通过；bounded `659` 通过、`133` 个 real-clang opt-in 忽略；integer conversion `4` 通过；coverage matrix passed |
| P0-T21 translator candidate | commit `02067028`，2026-07-11 | library `228` 通过；bounded `657` 通过、`133` 个 real-clang opt-in 忽略；integer conversion `4` 通过 |
| P0-T20 Python core 历史快照 | 2026-07-11 阶段快照 | `293 passed, 6 skipped`，另有 `90` 个 subtests；只证明当时提交 |
| 全量回归 | run `20260711T061416Z` | 34 项中 26 项通过；P0-T21 未新增失败，8 项仍为历史 evidence 漂移；后续 runner 默认取消循环压力测试 |
| P0-T21 严格 validator | commit `8a261787` 生成的 evidence | `semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过 |
| P0-T20 严格 validator | P0-T20 evidence | `semantic_pass=true`、`generated_draft_semantic_pass=true` |
| accepted-evidence 严格状态 | `libuv/ip4-addr` | verified-unsafe-baseline SHA 漂移，ledger 计数不等于当前严格通过 |
| 全功能 Clippy | commit `81a772d1` 加当前测试清理 | `--all-features --all-targets` 剩余 8 个告警，均属于 P0-C2 已列出的 4 类 |

## 6. 架构边界

### 6.1 Candidate 路由

| 层级 | 作用 | 能否单独声明语义通过 |
| --- | --- | --- |
| L0 deterministic | 极小且已证明的机械规则 | 否 |
| L1 generic typed IR | 通用 AST/type/alias 驱动候选 | 否 |
| L2 C2Rust baseline/repair | 提供广覆盖 unsafe baseline 和安全化 before/after | 否 |
| L3 LLM/OpenCode | 生成或修复候选 | 否 |
| L4 refuse | 不确定时 fail-closed 并给出下一步 | 不适用 |

任何候选只有通过第 7 节的共同门禁后，才能成为 declared slice boundary 内的 semantic pass。

### 6.2 IR 分层

1. **Semantic IR**：显式表达 C integer width/signedness、cast、lvalue/rvalue、pointer provenance、volatile/atomic 和 UB/implementation-defined 边界。
2. **Control IR**：表达 block、branch、loop、break/continue/return 和未来 CFG/relooper 信息。
3. **Typed Value IR**：表达 scalar、record、array、pointer、function type、qualifier 和 ABI/layout provenance。
4. **Lowering**：选择 Rust ownership、borrow、slice、wrapping/checked arithmetic、raw pointer 或 refusal；IR 不应提前伪造 Rust 安全性。

## 7. 验收门禁

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

## 8. 开发原则

1. FlashDB 是真实测试用例，不是 translator 特判来源；禁止读取项目名、函数名、路径或固定 fixture 值决定翻译。
2. 先做最小 source-backed slice，再扩相邻结构；每次放宽规则都要有正例和最近邻 fail-closed 负例。
3. C oracle 是声明边界内的 ground truth，但也受 fixture、compiler、flags、ABI 和 observable contract 限制。
4. fail-closed 必须给出 source span、拒绝原因和下一最小实现步骤，不能把拒绝数量当成功率。
5. unsafe 数量是治理指标，不是 FFI、并发、volatile、ABI 或硬件语义的完整安全证明。
6. evidence 使用 repo-relative path、稳定 hash 和明确保留策略；禁止把密钥和宿主绝对路径写入可发布 artifact。
7. 大文件按模块职责拆分；测试、schema、证据和文档改动只在确有行为或验收收益时加入。

## 9. 常用验证命令

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

## 10. 文档维护规则

- 本文只保留当前状态、唯一活动队列、分级 backlog、里程碑摘要和稳定规则。
- 完成一项时更新状态表、活动队列、里程碑表和验证摘要，不追加逐日长日志。
- 精确 artifact、hash、case 和 validator 结果写入 coverage matrix/evidence；本文只写结论和边界。
- 中文文件是 canonical backlog；英文镜像必须在同一改动中同步。
- 旧状态需要追溯时使用 Git 历史，不新建第二份全局 TODO、handoff 或 roadmap。
