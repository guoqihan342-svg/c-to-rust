英文镜像见 `future-vision-and-mvp.en.md`。

# C-to-Rust 未来愿景与 MVP 路线

本文是项目的中文 canonical backlog，也是当前状态、执行顺序和能力边界的唯一入口。详细实现过程由 Git 历史、coverage matrix 和机器可读 evidence 保存，不再把逐日流水账复制到本文。

最后更新：2026-07-12。

## 1. 当前状态

目标是构建可审计的端到端流水线：

```text
input.c + compile context
  -> ContextPack（source / headers / flags / ABI / diagnostics）
  -> GLM-5.1 primary candidate
  -> typed IR / C2Rust alternate candidates
  -> bounded verify-and-repair loop
  -> C oracle + Rust replay + diff + negative diff
  -> unsafe ledger + final verification
  -> accepted / refused / blocked
```

| 项目 | 当前值 | 准确含义 |
| --- | ---: | --- |
| `translator_generated_semantic_pass_count` | 38 | coverage ledger 派生计数；不代表当前全量严格回归全绿，也不代表全项目翻译完成 |
| `accepted_evidence_semantic_pass_count` | 1 | accepted-evidence ledger 派生计数；当前唯一切片仍受历史 SHA 漂移阻塞 |
| 当前 AI 候选状态 | `0 generated` | 已审计的 40 份 AI manifest 均为 `not_used`；现有 OpenCode worker 只转发确定性命令，尚未生成 Rust candidate |
| 当前翻译主线 | P0-A6..A10 | 建立 AI-first candidate、ContextPack、多候选路由和有限跨项目验收；不再以单个 FlashDB 行号扩展作为主线 |
| 外部并行项 | P0-H9 | 在真实比赛主机完成 OpenCode + GLM-5.1 精确合同复验 |
| 最近开发阶段 | P0-T31 | `:1880-1883` ordered stats sequence 已完成 source-backed 严格验收，计数更新为 38 |
| 当前严格回归 | `25/33` | run `20260711T-finite-p0-t31`；`stress_loops=0`，8 项历史 evidence 漂移仍未修复 |
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

当前已在 WSL competition-like lane 验证：P0-T20 的 C oracle、generated Rust replay、diff、negative mutation、unsafe gate 和严格 validator。日常全量回归不执行循环压力测试，压力循环不再是常规验收条件；runner 最多重复 3 轮，单独批准的诊断压力测试最多 100 次，不接受 1,000/10,000 次运行。易变的测试数量只在第 5 节按运行或提交绑定记录。

当前尚未验证：目标 kernel、Rust/Cargo 1.96、Node/npm 目标版本、真实 Huawei host package/runtime 差异、比赛资源上限、真实主机 `COMPETITION_EXACT_HOST=1` attestation、完整 OpenCode preflight marker、GLM-5.1 worker/session artifacts、全入口 competition-exact judge bundle 和 public packet。因此 P0-H9 仍未关闭。

## 3. 当前执行队列

### P0-T：确定性翻译辅助通道

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

- [x] **P0-T25：`fdb_kvdb.c:1876` source-backed 语义闭环**

  已完成 source-bound spec、3 个有限 fixture、fixture-only `read_kv`/`get_next_kv_addr` 双调用合同、C oracle、generated Rust replay、schema diff、body-call suppression negative diff、unsafe ledger、route/profile 和 final verification。WSL competition clang lane 的 strict validator 12 类绑定检查全部通过，`semantic_pass=true`、`generated_draft_semantic_pass=true`，matrix 派生计数由 34 更新为 35。声明只覆盖 line 1876 的调用形状、参数转发和 fixture 顺序；line 1885 仅为 synthetic scaffold，真实 `read_kv`/`get_next_kv_addr` 副作用和完整循环不在范围内。

- [x] **P0-T26：`fdb_kvdb.c:1877-1883` 下一切片决策门**

  - 选择 line 1880 的 `itr->iterated_cnt++`，通用 construct 是 statement-position、结果被丢弃、直接 mutable record-pointer root 的 u32 字段后置自增。
  - 新增独立 no-clang AST fixture，确认 frontend 规范化为 field assignment + unsigned add；Rust candidate 使用 `wrapping_add(1u32)`，运行边界覆盖 `0 -> 1`、普通值和 `u32::MAX -> 0`。
  - 最近邻负例继续固定 const record pointer、nested/non-direct base 和缺失 mutable ownership evidence 的 fail-closed 行为。
  - 停止边界排除 lines 1876-1879、1881-1885、真实 `read_kv` 副作用、条件与 early return、owner-interior-alias 组合、完整循环和 FlashDB ABI；生产 translator 不读取项目名、函数名、slice id、字段名或 fixture 常量。

  当前仅完成 project-independent candidate generation，状态保持 `candidate_context_only`，语义计数保持 35。

- [x] **P0-T27：`fdb_kvdb.c:1880` source-backed 语义闭环**

  已固定 line 1880 source span 和 normalized hash，建立 3 个有限 fixture、C oracle、generated Rust replay、schema diff、`wrapping_add` 到 `wrapping_sub` 的 negative mutation、unsafe ledger、route/profile 和 final verification。WSL competition clang lane 的 12 类严格绑定检查全部通过，`semantic_pass=true`、`generated_draft_semantic_pass=true`，matrix 派生计数由 35 更新为 36。声明仅覆盖一个 mutable record root 上的直接 u32 字段后缀自增及零值、普通值、回绕值；不覆盖外层分支/循环、完整函数、布局、ABI 或 FlashDB 项目。

- [x] **P0-T28：`fdb_kvdb.c:1881` 通用 owner-interior sibling accumulation 候选**

  - 选择 line 1881 的 `itr->iterated_obj_bytes += kv->len`。`kv` 来自 `&itr->curr_kv`，因此不是两个 noalias pointer root，而是单一 mutable owner 的 scoped interior alias 读取与不重叠 sibling 字段写入。
  - 通用 frontend/typed-IR 只在目标 ABI 明确为 LP64、源字段为 u32、目标字段为 `size_t`/usize、alias provenance 来自 pointer typedef、路径不重叠且没有额外 alias 使用或副作用时生成 `wrapping_add(kv.len as usize)`。
  - renamed no-clang AST fixture 与 6 个 focused tests 固定普通值、零值、LP64 回绕，以及 ABI 缺失、路径重叠、二次 pointer hop、alias 重用、类型漂移、虚构 noalias 和终止语句漂移的 fail-closed 行为。

  当前仅完成 project-independent candidate generation，不读取项目名、函数名、字段名、slice id 或 fixture 常量；语义计数仍为 36。

- [x] **P0-T29：`fdb_kvdb.c:1881` source-backed 语义闭环**

  已固定 line 1881 source span、pointer-typedef carrier 和 LP64 ABI，建立 3 个有限 fixture（普通、零增量、usize 回绕）、实际编译执行的 C oracle、generated Rust replay、schema diff、negative mutation、unsafe ledger、route/profile 和 final verification。WSL competition clang lane 的 12 类严格绑定检查全部通过，`schema_status=passed`、`semantic_pass=true`、`generated_draft_semantic_pass=true`，matrix 派生计数由 36 更新为 37。声明只覆盖 line 1881 的单 owner、scoped interior alias、u32-to-usize sibling wrapping add；不覆盖 lines 1882-1883、外层条件/循环、完整函数、真实布局/整体 ABI 或 FlashDB 项目。

- [x] **P0-T30：`fdb_kvdb.c:1882-1883` 与 `:1880-1883` 通用组合候选**

  已实现 project-independent 的有界 ordered sequence：一个 direct u32 wrapping increment、两个来自同一 scoped interior alias 的不同 u32 字段到不同 LP64 usize sibling 字段的 wrapping add，以及固定 `return true`。生产分析只检查 AST/类型/ABI/alias/effect 约束，不读取项目名、函数名、字段名、slice id 或 fixture 常量；renamed no-clang AST、运行时正例和相邻形状/alias/类型/effect 负例通过。该阶段为 candidate only，计数保持 37。

- [x] **P0-T31：`fdb_kvdb.c:1880-1883` source-backed 语义闭环**

  已固定 lines 1880-1883 的 source span、单 owner/interior-alias carrier 和 LP64 ABI，建立 4 个有限 fixture，完成实际编译执行的 C oracle、generated Rust replay、schema diff、negative mutation、unsafe ledger、route/profile 和 final verification。WSL competition clang lane 的 12 类严格绑定检查全部通过，`schema_status=passed`、`semantic_pass=true`、`generated_draft_semantic_pass=true`，matrix 派生计数由 37 更新为 38。声明不覆盖 line 1877 条件、外层分支/循环、完整函数、真实布局/整体 ABI 或 FlashDB 全项目。

- [ ] **P0-T32：组合 `fdb_kvdb.c:1877` 条件与 `:1880-1883` body**

  暂停作为当前主线。该切片保留为 AI-first harness 的真实 golden case，用于比较 GLM-5.1、typed IR 和 C2Rust 候选；只有共同门禁通过时才增加 numerator，已有 stats body 不重复计数。

### P0-A：AI-first Harness 主线

收口顺序按可执行依赖排列，不因外部模型或 checkout 阻塞本地开发：

| 顺序 | 工作 | 当前停止条件 |
| ---: | --- | --- |
| 1 | P0-A11 provider admission 与零调用证据 | 已完成；后续只修回归 |
| 2 | P0-A12 文件化 prompt transport | 已完成；后续只修 transport/CLI 兼容回归 |
| 3 | P0-A13 内容寻址 AI candidate cache | 只复用 hash/策略完全一致且可重开的成功响应；失败不得缓存 |
| 4 | P0-A14 受限展开编译 response file | 在 source root 内按深度、文件数和总字节上限补齐真实编译参数 |
| 5 | P0-A10 固定套件真实验收 | 资源恢复后只运行一次完整套件并发布可复核指标 |
| 6 | P0-A6 / P0-H9 比赛主机复验 | 有效资源包和 competition-exact host 可用；不得用模拟结果代替 |

任何阶段都先运行一次有限构造集合，再按失败频率扩展 translator/ContextPack；禁止继续按 FlashDB 行号堆规则，也禁止为了等待外部资源停止可独立完成的 harness 工作。

- [ ] **P0-A6：真实 GLM-5.1 候选生成通道**

  OpenCode `zai/glm-5.1` 读取 hash-bound ContextPack，输出单一结构化 Rust candidate；记录 provider、logical/resolved model、variant、prompt、输入、原始响应、解析结果和候选 SHA-256。模型输出、聊天文本和文件写入本身都保持 `semantic_gate=false`。无凭据、超时、响应格式错误或候选缺失必须结构化 blocked，不得静默回退后冒充 AI 已运行。

  当前进度：候选生成器、schema-v3 manifest、敏感字段/宿主路径清理、严格 JSON 解析、候选物化 SHA 检查、source-span provider readiness、余额/鉴权/启动/超时分类和 `auto_migrate --ai-first-candidate` 已实现。missing、越界、hash 漂移、超限或编码不支持的 source span 会在启动 OpenCode 前结构化为 `context_not_provider_ready`，并记录 `provider_invocations=0`；summary validator 会重开 hash-bound ContextPack 独立复算 preflight 与调用计数。LF/CRLF 等价由 full-source 流式 hash 和 span hash 共同校验；fragment wrapper 还必须通过 carrier、containing-function、真实 upstream fragment 的 SHA/text/claim 合同和 `verbatim_once` 嵌入校验，才标记为 `inline_translation_carrier_bound`，且仍不声明 whole-function 语义。在保留三条 pinned checkout 的 P0-A10 输入工作树中，固定 12 项在 Windows/WSL 均为 provider-ready 12/12；普通新 worktree 未物化这些 ignored checkout 时不具备该前置条件。WSL 能列出并实际启动 `zai/glm-5.1`。OpenCode 会把 provider 错误写入受限日志后继续内部重试，旧 harness 因外层 30/180 秒先到而把空响应记为 `provider_timeout`；2026-07-12 新增的日志偏移诊断覆盖非零退出、超时和首次创建日志，只提取固定哨兵、不保存原始日志或密钥。单次真实调用已把根因还原为 `provider_insufficient_balance`。因此尚无真实 GLM candidate，本项保持未完成。模型可见、进程已启动和确定性 fallback 通过都不能替代候选证据。

- [x] **P0-A7：项目级 ContextPack 与编译上下文闭环**

  从真实 source root、source span、有效 `#include`、`compile_commands.json`/手工 flags、宏、target ABI、依赖声明、Clang AST/诊断、typed-IR/C2Rust 基线和验证失败中生成最小上下文。相对/绝对路径、生成头文件和构建目录必须可解析；禁止密钥、宿主绝对路径和无关大文件进入可发布 artifact。

  完成证据：ContextPack v2 已按职责拆为 source、compile database、compile args、security 和 deterministic artifact 模块；支持显式外部 source root、仓库内相对 source root、真实 span/source SHA、compile command 选择、include/define/ABI 摘要、128 KB 总上限和 32 KB 单 artifact 上限。路径/符号链接逃逸、hash 漂移、密钥及宿主路径均 fail-closed。

- [x] **P0-A8：验证驱动的有界 AI repair loop**

  每轮只把结构化失败事实反馈给模型：rustc diagnostics、C/Rust schema diff、negative mutation、unsafe/ABI/alias gate。默认最多 3 轮，比赛合同硬上限 5 轮；输入与失败 hash 均未变化时立即停止。每轮保留 candidate、patch、诊断和 hash，不允许模型修改 oracle、expected output、validator 或门禁配置。

  完成证据：有界 repair coordinator、单候选/单文件 patch 合同、每轮 SHA 证据、LF 规范化、输入+失败不变停止和 provider/validator fail-closed 已完成。fresh C oracle proof 会重新核验 harness、fixture、source span、flags 和 ABI；exact validator 对当前 candidate SHA 依次执行 rustc、replay、schema diff、negative mutation、unsafe/ledger、alias、ABI 和 final gate，并把十类有界失败事实反馈给同一 repair 状态机。`--ai-first-candidate` 已与 `--accept-existing-evidence` 互斥，旧 accepted reports 不能为新 AI candidate 背书。独立 `validate_ai_exact_evidence.py --require-semantic-pass` 会重开 auto manifest、router、candidate evidence、gate index 和 canonical draft 的 SHA 绑定；competition runner 只在该严格验证与 router 状态同时通过时计入 compile/semantic pass。2026-07-12 的全新 demo/add-one 证据检查 16 个工件并返回 `semantic_pass=true`。

- [x] **P0-A9：AI-primary 多候选路由**

  比赛翻译路径优先生成 GLM-5.1 candidate；typed IR、raw C2Rust 作为零 token 候选，C2Rust+repair 作为 AI 辅助的替代候选。router 只能依据可重算 gate 结果排序，不能依据项目名、函数名、slice id 或模型自评。任何候选都必须经过相同 compile/oracle/replay/diff/negative/unsafe/final gates。

  完成证据：competition runner 对新翻译默认传递 `--ai-first-candidate`，competition-exact 禁止替换 OpenCode/GLM/agent/variant。纯 router 最多接收 4 个候选，按 artifact SHA 去重，固定调度 `opencode-ai -> typed-ir -> c2rust-repair -> c2rust-baseline`，只有八类 candidate-bound gates 全部通过才允许选择。`auto_migrate` 会先验证 AI、typed IR 和当前运行的 raw C2Rust；任一零 token 候选通过即停止 repair。全部失败时只选择一个 repair base：raw C2Rust 通过的 gate 数严格多于 AI 才修 C2Rust，平局修 AI；整个运行共享默认 3/硬上限 5 轮预算。C2Rust repair 状态机不含项目/函数特判，只允许单 Rust candidate/patch，独立保存 report/round/prompt/response/candidate SHA，再以 `source=c2rust-repair` 重跑 fresh exact gates。unique、duplicate 和无候选三类 audit 均由 strict validator 和 competition metrics 从磁盘重开，repair rounds 计入总模型调用但不膨胀“初始 AI candidate 成功率”。baseline compile/status、repair report 或历史 accepted evidence 本身都不能使候选晋级。

- [ ] **P0-A10：有限跨项目稳定性验收**

  建立不超过 20 个 case 的固定集合：至少覆盖 3 个真实 C 项目和 10 个不同 construct family。阶段验收只运行一次有限集合，不执行 1,000/10,000 轮或循环压力测试。发布 AI invocation、candidate generation、rustc compile、semantic acceptance、refused/blocked、repair rounds 和 route selection 指标；成功率不得用重复同类切片放大。

  当前进度：输入和 harness 闭包已完成。`validation/ai-finite-cross-project-suite.json` 固定 12 个 case、3 个真实项目和 12 个唯一 construct family，其中 8 个为真实 upstream function slice，4 个为绑定真实 upstream fragment 的通用可执行 carrier；synthetic/unbound provenance 均为 0。`project_sources` 固定 repository、repo-relative checkout root 和 commit，validator 离线核验 Git HEAD、origin、tracked-clean 状态、spec/fixture SHA、source file/span SHA 以及 line/byte 对齐；只允许 LF/CRLF 换行等价，不允许内容漂移或项目标签伪造。在保留三条 pinned checkout 的 P0-A10 输入工作树中，Windows 与 WSL `--require-all-ready` 均为 `ready=12/blocked=0`。

  `run_ai_finite_cross_project_suite.py` 现在把 12 个 spec 一次传给同一个 competition runner，禁止 accepted-evidence shortcut 和外层重试；suite/summary 均做 SHA 绑定，底层 summary validator 未通过时上层不复制任何指标。WSL local simulation 可显式使用离线 Cargo cache，但 summary 必须记录 `bypassed_for_local_cache`，`competition-exact` 会拒绝该旁路。余额不足、鉴权失败或 provider 无法启动会在首次失败后打开熔断，timeout 保持连续两次阈值；不同 kind 会重置连续计数。只有实际调用项计入 slices/workflow/AI units，剩余项记录为 skipped，不制造 `not_invoked` 单元；ContextPack preflight 拒绝项则显式记录为零次 provider 调用。

  2026-07-12 的有限熔断演练在约 65 秒内完成：请求 12 项，实际调用 2 项，跳过 10 项；`slices.attempted=2`、`workflow_metrics.units_total=2`、`ai_translation_metrics.units_total=2`、`invocations=2`、`blocked=2`、`abnormal=0`，独立 summary validator 返回 0。该历史运行按当时代码记录为两个 `provider_timeout`；后续受限日志诊断确认底层错误为余额/资源包不足，但不回写旧工件。当前没有 candidate、compile 或 semantic acceptance，所以本项仍未完成，也不得发布跨项目成功率。下一步只在 GLM 资源包恢复后对同一固定套件再运行一次完整阶段验收，再发布 generation、compile、semantic、refused/blocked、repair 和 route 指标；不得为绕过 provider 故障更换测试项或硬编码项目。

- [x] **P0-A11：provider admission 与零调用证据闭环**

  candidate producer 在进程启动前重开 ContextPack 的真实 source/span/carrier 绑定。路径逃逸、hash/声明不完整、读取中途漂移、无效坐标、超限、编码失败或被条件编译屏蔽的 fragment 全部结构化拒绝，并记录 `provider_invocations=0`。summary validator 不信任 manifest 自报，而是重开 hash-bound ContextPack 复算 readiness 和调用数。该门只决定是否值得调用模型，不提升语义状态。

- [x] **P0-A12：文件化 prompt transport**

  candidate 与 repair prompt 先写入 repo-scoped、hash-bound 文件，再使用 OpenCode 的文件输入参数和固定短消息启动，避免 Windows/WSL argv 长度差异。manifest 必须记录 transport、prompt path/hash 和实际命令策略；日志与公开工件不得复制完整 prompt、密钥或宿主路径。完成条件是大 ContextPack/repair candidate 不再进入 argv，现有解析、超时、诊断和严格门禁行为保持不变。

  完成证据：candidate 和 bounded repair 共用 `opencode-file-attachment-v1`，argv 只保留 `--file=<prompt-path>` 与固定短消息；完整 prompt 仍以 SHA 绑定文件保留。schema-v3 manifest 与 schema-v2 repair report 记录 file option/style、固定消息 SHA 和 `inline_prompt_in_argv=false`；summary 与 exact-evidence validator 均独立拒绝 transport 漂移。Windows/WSL 各 167 项 AI candidate、repair、router、exact evidence 和 competition summary 回归通过；WSL 显式使用 `/root/.cargo/bin` 比赛工具链 PATH。

- [ ] **P0-A13：内容寻址 AI candidate cache**

  cache key 只由 ContextPack payload hash、prompt schema/version、resolved model、agent、variant 和解析合同组成。只缓存成功解析且 candidate/raw-response 均可按 SHA 重开的结果；provider failure、超时、拒绝和未通过解析的响应不得缓存。命中后仍需走完整 common gates，记录 `cache_hit` 与零次新增 provider 调用，且保持 `semantic_gate=false`；任何绑定漂移都删除命中资格并重新调用模型。

- [ ] **P0-A14：受限展开编译 response file**

  仅展开 source root 内的相对 `@file`，限制递归深度、文件数、单文件/总字节并检测环；每个 response file 记录 repo/logical path 与 SHA。解析失败、路径逃逸或预算超限必须 fail-closed，不能静默丢失 include、define、target ABI 等参数。完成后用不同真实 C 项目验证，不新增项目名、函数名或 fixture 特判。

- [x] **P0-A1：OpenCode no-progress retry suppression**

  对 effective request/source/spec/repair-trace/launch-policy 计算 `effective_input_sha256`，对结构化 root cause/status/returncode/diagnostics 计算 `failure_sha256`。连续两次确定性失败且当前输入仍无变化时，第三次启动前关闭 repair hint、清空 retry command、记录 `repair_retry_suppressed`，并以 `refused/retry_input_unchanged` fail closed；不调用 runner、不追加伪 attempt、不提升 semantic 状态。timeout、SQLite/OpenCode lock、preflight、credential、contract、环境缺失、未知根因或 hash 缺失/漂移均保留重试。

  该门减少无信息增量的 OpenCode 调用和 token 消耗，但不把 AI 输出当作语义事实，也不替代 C oracle、Rust replay 或 strict validator。

- [x] **P0-A2：`CLANG_PATH` 裸命令名与比赛 PATH 合同一致**

  Rust clang frontend 现在同时接受现有显式路径和由进程 `PATH` 解析的裸命令名，例如 `CLANG_PATH=clang`；带目录分隔符但不存在的显式路径仍保持 fail closed。WSL 上的 clang 18 最小 TU smoke 与 3 个真实 clang auto-migrate 正/负例均通过。该修复只恢复候选生成通道，不提升任何语义计数。

- [x] **P0-A3：deterministic-first admission gate**

  `mode=auto` 只在全部 worker 绑定 accepted evidence、现存 evidence root、source hash、slice spec 且没有 repair policy 时，于 OpenCode preflight 前选择 deterministic。mixed/unbound 输入在 fanout 前以 `auto_route_unbound` 拒绝；`competition-exact`、hostless rehearsal 和显式 OpenCode attestation 不允许自动降级。该路由只减少无增益模型调用，`semantic_gate=false`。

  该项是历史行为。P0-A9 完成后，`mode=auto` 对新翻译任务改为 AI-primary；只有纯 accepted-evidence 复验继续走 deterministic shortcut。

- [x] **P0-A4：精简 OpenCode worker 上下文且保持精确合同**

  `.opencode/agents/c2rust-migrator.md` 从 5408 bytes 精简到 1439 bytes，同时保留 `opencode + GLM-5.1 + c2rust-migrator + max`、Required Preflight、Superpowers 非门禁边界、首个且唯一精确 Command line tool call、禁止探索/编辑/子代理/替代命令、hash-bound handoff/session/contract 校验和 chat 非语义事实边界。bundle manifest 与 profile contract tests 同步更新；该优化只减少模型上下文和歧义，`semantic_gate=false`。

- [x] **P0-A5：OpenCode prompt 只保留一种命令表示**

  worker 与 preflight prompt 删除重复的 `Command: <JSON argv>` 文本，只保留一条可执行 `Command line:`；结构化 argv、命令 hash、session 和 handoff 证据保持不变。代表性 prompt 减少 13.2%-16.1% bytes，完整 harness 测试通过；该项只降低 token 和命令歧义，`semantic_gate=false`。

### P0-B：比赛主机与 OpenCode

- [ ] **P0-H9：真实 OpenCode + GLM-5.1 比赛合同复验**

  当前 WSL 已能解析 provider-qualified `zai/glm-5.1`，但完整 preflight/worker marker 尚未在真实比赛主机闭合。OpenCode + GLM-5.1 是新的比赛翻译默认通道；本地无法调用时必须明确标为 blocked/unavailable，不能用确定性结果冒充 AI 比赛路径。

  完成条件：真实主机设置 `COMPETITION_EXACT_HOST=1`，`opencode models` 精确列出 GLM-5.1，preflight 使用 `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`，hash-bound probe/session/worker artifacts 完整，judge bundle 和 public packet 重新验证通过。

  WSL、本机和 CI 结果只能分别标为 `wsl-local-simulation`、`local-simulation` 和 `ci-approximation`，不能关闭 H9。

- [ ] **P0-H10：CRC32 competition-exact before/after 发布**

  依赖 P0-H9。仅在真实比赛主机复跑已闭合的 CRC32 C2Rust+repair before/after，并发布 hash-bound workflow metrics 后关闭。

### P0-C：阶段收口

- [ ] **P0-C1：历史 evidence 漂移**。修复 run `20260711T-finite-p0-t31` 再确认的 8 个失败项，按 artifact 所有权分批处理，不与翻译层功能改动混交。
- [ ] **P0-C2：全功能 Clippy**。commit `81a772d1` 已清理 9 个低风险告警；当前剩余 8 个（2 个 `large_enum_variant`、1 个 `redundant_guards`、1 个 `needless_lifetimes`、4 个 `too_many_arguments`）。新切片不得增加告警。

## 4. 后续 Backlog

### P1：扩大通用翻译能力

1. 根据 P0-A10 的跨项目失败频率扩展 typed IR，不再按单项目源码顺序堆规则；优先建立完整 alias/noalias、pointer provenance 和 escape 模型。
2. 把 integer promotion、usual arithmetic conversion、narrowing、array/function decay 和 ABI 相关转换显式保留在 IR。
3. 将组合式 side effect 建模为可组合规则，覆盖 sequence point、求值顺序、`++`/`--`、deref、index、member 和 call。
4. 扩展 CFG：先提供 `switch`/`goto` 的证据和 fail-closed 分类，再引入 relooper 或结构化 lowering。
5. 扩展 compound literal、designated initializer、function pointer、variadic、union、bitfield、VLA 和 flexible array member。
6. 建模 volatile、硬件寄存器、RTOS/中断、文件系统和断电恢复边界；host fixture 不能替代 target evidence。
7. 从 FlashDB、zlib-ng、libuv 等项目增加不同 construct family 的真实切片，避免用同类 checksum/parser 数量夸大覆盖面。

### P2：Agent、路由和发布

1. 维护模型/prompt 版本升级策略、回滚策略和离线 replay；golden 集的事实源由 P0-A10 建立。
2. 评估第二模型只用于独立候选或审计，不允许多数投票替代 semantic gates。
3. 发布人工介入点、耗时、token/证据成本和模型升级前后差异。
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
| P0-T25 | `:1876` discarded direct-call body source-backed 严格验收 | 34 -> 35 |
| P0-T26 | 选择并验证 `:1880` u32 mutable record-pointer postfix increment candidate | 35 -> 35（candidate only） |
| P0-T27 | `:1880` u32 mutable record-pointer postfix increment source-backed 严格验收 | 35 -> 36 |
| P0-T28 | 选择并验证 `:1881` owner-interior u32-to-LP64-usize sibling accumulation candidate | 36 -> 36（candidate only） |
| P0-T29 | `:1881` owner-interior sibling accumulation source-backed 严格验收 | 36 -> 37 |
| P0-T30 | 选择并验证 `:1880-1883` bounded ordered stats sequence candidate | 37 -> 37（candidate only） |
| P0-T31 | `:1880-1883` ordered stats sequence source-backed 严格验收 | 37 -> 38 |

验证运行绑定：

| 验证项 | 绑定 | 结果 |
| --- | --- | --- |
| P0-T31 严格 validator | WSL competition clang lane，2026-07-11 | `schema_status=passed`、`semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过；仅运行 4 个有限 fixture，不执行压力循环或重复轮次 |
| P0-T29 严格 validator | WSL competition clang lane，2026-07-11 | `schema_status=passed`、`semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过；仅运行 3 个有限 fixture，未执行 1000/10000 轮或其他循环压力测试 |
| P0-T27 严格 validator | WSL competition clang lane，2026-07-11 | `semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过；仅运行 3 个有限 fixture，未执行循环压力测试 |
| P0-T25 严格 validator | WSL competition clang lane，2026-07-11 | `semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过；3 个有限 fixture 案例覆盖 1/2/3 次 body/tail 有序调用；未执行循环压力测试 |
| P0-T24 / P0-A1 / P0-A2 阶段验收 | WSL local simulation，2026-07-11 | translator library `228`、bounded `665`、integer conversion `4` 全通过，`133` 个 real-clang opt-in 默认忽略；3 个真实 clang focused tests、Python auto-migrate `155`、OpenCode harness `192` 全通过；未执行循环压力测试 |
| P0-T23 严格 validator | WSL competition clang lane，2026-07-11 | `semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过；3 个有限 fixture 案例覆盖 1/2/3 次调用 |
| P0-T22 translator candidate | 当前工作树，2026-07-11 | library `228` 通过；bounded `659` 通过、`133` 个 real-clang opt-in 忽略；integer conversion `4` 通过；coverage matrix passed |
| P0-T21 translator candidate | commit `02067028`，2026-07-11 | library `228` 通过；bounded `657` 通过、`133` 个 real-clang opt-in 忽略；integer conversion `4` 通过 |
| P0-T20 Python core 历史快照 | 2026-07-11 阶段快照 | `293 passed, 6 skipped`，另有 `90` 个 subtests；只证明当时提交 |
| 全量回归 | run `20260711T-finite-p0-t31` | 33 项中 25 项通过；P0-T31 未新增失败，8 项仍为历史 evidence 漂移；`stress_loops=0`、`run_stress=false` |
| P0-T21 严格 validator | commit `8a261787` 生成的 evidence | `semantic_pass=true`、`generated_draft_semantic_pass=true`，12 类语义绑定检查通过 |
| P0-T20 严格 validator | P0-T20 evidence | `semantic_pass=true`、`generated_draft_semantic_pass=true` |
| accepted-evidence 严格状态 | `libuv/ip4-addr` | verified-unsafe-baseline SHA 漂移，ledger 计数不等于当前严格通过 |
| 全功能 Clippy | commit `81a772d1` 加当前测试清理 | `--all-features --all-targets` 剩余 8 个告警，均属于 P0-C2 已列出的 4 类 |

## 6. 架构边界

### 6.1 Candidate 路由

| 层级 | 作用 | 能否单独声明语义通过 |
| --- | --- | --- |
| L0 ContextPack | 绑定真实源码、编译上下文、诊断和候选基线 | 否 |
| L1 AI primary | OpenCode + GLM-5.1 生成或修复候选 | 否 |
| L2 deterministic alternates | typed IR、raw C2Rust、C2Rust+repair 候选 | 否 |
| L3 common verification | 编译、oracle/replay、diff/negative、unsafe/ABI gates | 只有全部通过后 |
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
2. 比赛新翻译任务默认 AI-first；typed IR 和 C2Rust 服务于上下文、替代候选和可验证兜底，不再要求先为每个陌生构造手写 lowering 才能调用 AI。
3. 先做最小 source-backed slice，再扩相邻结构；每次放宽规则都要有正例和最近邻 fail-closed 负例。
4. C oracle 是声明边界内的 ground truth，但也受 fixture、compiler、flags、ABI 和 observable contract 限制。
5. fail-closed 必须给出 source span、拒绝原因和下一最小实现步骤，不能把拒绝数量当成功率。
6. unsafe 数量是治理指标，不是 FFI、并发、volatile、ABI 或硬件语义的完整安全证明。
7. evidence 使用 repo-relative path、稳定 hash 和明确保留策略；禁止把密钥和宿主绝对路径写入可发布 artifact。
8. 大文件按模块职责拆分；测试、schema、证据和文档改动只在确有行为或验收收益时加入。

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
