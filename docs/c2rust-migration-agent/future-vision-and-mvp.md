英文镜像见 `future-vision-and-mvp.en.md`。

# C-to-Rust 未来愿景与 MVP 路线

本文是项目的中文 canonical backlog，也是当前状态、执行顺序和能力边界的唯一入口。详细实现过程由 Git 历史、coverage matrix 和机器可读 evidence 保存，不再把逐日流水账复制到本文。

最后更新：2026-07-15。

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
| 当前 AI 候选状态 | `GLM 0 / fixed auxiliary 6/12 / libuv AI-first 0/1 exact` | 比赛 GLM 仍因余额不足没有 candidate；固定 12 项尚未在 A18c8a 后整套复跑。新 libuv DeepSeek 辅助实跑完成 1 次 initial + 3 次 repair，provider-ready 但 exact 未通过，明确不具备比赛资格 |
| 当前翻译主线 | P0-A19 / P0-A10 / P0-A18c | h5a-h5d 已闭合 compiler/runtime/ABI repair facts 与 compiler-header declaration-only 分类；下一步进入陌生仓库整项目发现、拆解、并行候选、Cargo 集成与项目级 repair，不再围绕单个已知切片扩语法 |
| 外部并行项 | P0-H9 | 在真实比赛主机完成 OpenCode + GLM-5.1 精确合同复验 |
| 最近开发阶段 | P0-A19 BuildIR/frontier/verifier 收口 | 任意仓库 inventory、SCC/DAG、构建闭包、实际 C toolchain 绑定、分页 ContextPack、隔离 OpenCode、SQLite ledger、RustProjectIR/Cargo generation、whole-cohort Cargo 诊断分类、原始字节 CAS、固定 Cargo linker trace、实际 ELF/ar 重开、ABI/顺序/符号门和项目级 native settlement 已落地；合法的接口完整度状态转换、运行时 AI 符号候选、独立 verifier 进程、最终 CompletionCoordinator 接线、显式沙箱 Make 采集、frontier 懒加载和真实 held-out 语义验收仍未完成。易变测试总数只放在 commit-bound 阶段证据，不再写入本状态行 |
| 最近一次严格证据快照 | `25/33` | 不可变历史 run `20260711T-finite-p0-t31`；`stress_loops=0`，该快照仍有 8 项 evidence 漂移。P0-C1 应以新替代运行关闭，不得改写历史 |
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

### 3.1 本轮优先级看板

只从上到下执行；下层事项不能用局部样例成功越级关闭上层事项。

| 顺序 | 待办 | 状态 | 本轮完成判据 |
| ---: | --- | --- | --- |
| 1 | P0-A18c7 跨项目 AI 输入与证据合同闭包 | 完成 | Windows/WSL 125 项回归通过；固定 12 项生成 12 个候选、0 contract failure、6 exact pass |
| 2 | P0-A19 陌生 C 项目整项目 AI harness | 进行中：BuildIR、检索前沿与 verifier capability 收口 | 任意 repo root 的发现、分页 DAG、角色组合、SQLite ledger、Cargo generation、实际 C toolchain 绑定、CMake/Ninja/Meson 只读事实、link/archive 闭包和 fail-closed 沙箱合同已落地；当前先补外部 native-link 可验证解析、显式受限 configure/Make 采集、frontier selection 状态转移和独立 verifier capability，再接 initialization/feature/cfg/ABI 与真实 held-out build/oracle。禁止项目/函数/路径/fixture 身份分派 |
| 3 | P0-A18c8 剩余 exact failure 收敛 | 进行中 | h5a-h5d 已完成且不扩大语义覆盖；保留父项未完成边界，后续只在 P0-A19 项目级 gate 暴露真实阻塞时回收，不再围绕单个已知切片顺序加规则 |
| 4 | P0-A10 有限 held-out 跨项目验收 | 待开始 | 固定 12 项继续作为非回归基线，新增有限的未参与规则开发的整项目验收；只运行有限集合一次，不用重复轮次放大成功率 |
| 5 | P0-H9 比赛主机复验 | 外部阻塞 | 真实主机 attestation、OpenCode preflight、GLM-5.1 session 和发布包全部闭合 |
| 6 | P0-C 阶段收口 | 待开始 | 修复历史 evidence 漂移并清理 all-feature Clippy 剩余项 |

勾选规则：实现完成只勾子项；父项必须在其全部验收门和证据闭合后才能勾选。定向样例、AI 文本、candidate 编译、WSL 模拟或辅助模型成功均不能单独关闭 P0-A18c、P0-A19、P0-A10 或 P0-H9。

### 3.2 P0-T：确定性翻译辅助通道

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

### 3.3 P0-A：AI-first Harness 主线

收口顺序按可执行依赖排列，不因外部模型或 checkout 阻塞本地开发：

| 顺序 | 工作 | 当前停止条件 |
| ---: | --- | --- |
| 1 | P0-A11 provider admission 与零调用证据 | 已完成；后续只修回归 |
| 2 | P0-A12 文件化 prompt transport | 已完成；后续只修 transport/CLI 兼容回归 |
| 3 | P0-A13 内容寻址 AI candidate cache | 已完成；后续只修 cache binding/schema/validator 回归 |
| 4 | P0-A14 受限展开编译 response file | 已完成；后续只修 dialect/schema/binding 回归 |
| 5 | P0-A15 可复算 AI caller/callee 上下文 | 已完成；后续只修 ContextPack/prompt-scope/validator 回归 |
| 6 | P0-A16 透明辅助模型验证 | 已完成；辅助模型只能产生本地评估证据，不能冒充 GLM |
| 7 | P0-A17 隔离辅助套件与严格输入绑定 | 已完成；DeepSeek 等替代模型只进入独立辅助报告 |
| 8 | P0-A19 陌生项目整项目 harness | 当前本地主线；先闭合 BuildIR/toolchain、frontier retrieval、单一状态权威和独立 verifier capability，再扩大 AI 项目推理 |
| 9 | P0-A18c8 剩余 exact failure | 只在 P0-A19 项目级 gate 暴露可复现的通用阻塞时回收，不围绕固定切片追加规则 |
| 10 | P0-A10 有限 held-out 验收 | 依赖上述项目级合同；固定有限集合只运行一次并发布可复核指标 |
| 11 | P0-A6 / P0-H9 比赛主机复验 | 有效资源包和 competition-exact host 可用；不得用模拟结果代替 |

任何阶段都先运行一次有限构造集合，再按失败频率扩展 translator/ContextPack；禁止继续按 FlashDB 行号堆规则，也禁止为了等待外部资源停止可独立完成的 harness 工作。

- [ ] **P0-A6：真实 GLM-5.1 候选生成通道**

  OpenCode `zai/glm-5.1` 读取 hash-bound ContextPack，输出单一结构化 Rust candidate；记录 provider、logical/resolved model、variant、prompt、输入、原始响应、解析结果和候选 SHA-256。模型输出、聊天文本和文件写入本身都保持 `semantic_gate=false`。无凭据、超时、响应格式错误或候选缺失必须结构化 blocked，不得静默回退后冒充 AI 已运行。

  当前进度：候选生成器、schema-v7 manifest、敏感字段/宿主路径清理、严格 JSON 解析、候选物化 SHA 检查、source-span provider readiness、余额/鉴权/启动/超时分类和 `auto_migrate --ai-first-candidate` 已实现。missing、越界、hash 漂移、超限或编码不支持的 source span 会在启动 OpenCode 前结构化为 `context_not_provider_ready`，并记录 `provider_invocations=0`；summary validator 会重开 hash-bound ContextPack 独立复算 preflight 与调用计数。LF/CRLF 等价由 full-source 流式 hash 和 span hash 共同校验；fragment wrapper 还必须通过 carrier、containing-function、真实 upstream fragment 的 SHA/text/claim 合同和 `verbatim_once` 嵌入校验，才标记为 `inline_translation_carrier_bound`，且仍不声明 whole-function 语义。在保留三条 pinned checkout 的 P0-A10 输入工作树中，固定 12 项在 Windows/WSL 均为 provider-ready 12/12；普通新 worktree 未物化这些 ignored checkout 时不具备该前置条件。WSL 能列出并实际启动 `zai/glm-5.1`。OpenCode 会把 provider 错误写入受限日志后继续内部重试，旧 harness 因外层 30/180 秒先到而把空响应记为 `provider_timeout`；2026-07-12 新增的日志偏移诊断覆盖非零退出、超时和首次创建日志，只提取固定哨兵、不保存原始日志或密钥。单次真实调用已把根因还原为 `provider_insufficient_balance`。DeepSeek 辅助通道通过不能替代该证据，因此尚无真实 GLM candidate，本项保持未完成。

- [x] **P0-A7：项目级 ContextPack 与编译上下文闭环**

  从真实 source root、source span、有效 `#include`、`compile_commands.json`/手工 flags、宏、target ABI、依赖声明、Clang AST/诊断、typed-IR/C2Rust 基线和验证失败中生成最小上下文。相对/绝对路径、生成头文件和构建目录必须可解析；禁止密钥、宿主绝对路径和无关大文件进入可发布 artifact。

  完成证据：ContextPack v3 已按职责拆为 source、compile database、compile args、response files、security 和 deterministic artifact 模块；支持显式外部 source root、仓库内相对 source root、真实 span/source SHA、compile command 选择、include/define/ABI 摘要、128 KB 总上限和 32 KB 单 artifact 上限。路径/符号链接逃逸、hash 漂移、密钥及宿主路径均 fail-closed。

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

  2026-07-12 的空 out-root WSL 辅助运行 `ai-auxiliary-p0-a18c8-deepseek-wsl-20260712-02` 完成固定 12 项：12 个 initial candidate 全部生成，4 次证据驱动 repair，共 16 次 provider 调用；6 个 exact pass、6 个 exact failure，contract/execution/provider-block 均为 0。报告 SHA-256 为 `dfff968ad274924b763a8cede749338f37dcca25e38b5148fbeaaef0d09c2927`。这是 DeepSeek 的 `wsl-local-simulation` 质量信号，两个公开 numerator 仍固定为 0；比赛 GLM 资源恢复后的同套件验收和真实比赛主机证据尚未完成，因此 P0-A10 保持未勾选。

- [x] **P0-A11：provider admission 与零调用证据闭环**

  candidate producer 在进程启动前重开 ContextPack 的真实 source/span/carrier 绑定。路径逃逸、hash/声明不完整、读取中途漂移、无效坐标、超限、编码失败或被条件编译屏蔽的 fragment 全部结构化拒绝，并记录 `provider_invocations=0`。summary validator 不信任 manifest 自报，而是重开 hash-bound ContextPack 复算 readiness 和调用数。该门只决定是否值得调用模型，不提升语义状态。

- [x] **P0-A12：文件化 prompt transport**

  candidate 与 repair prompt 先写入 repo-scoped、hash-bound 文件，再使用 OpenCode 的文件输入参数和固定短消息启动，避免 Windows/WSL argv 长度差异。manifest 必须记录 transport、prompt path/hash 和实际命令策略；日志与公开工件不得复制完整 prompt、密钥或宿主路径。完成条件是大 ContextPack/repair candidate 不再进入 argv，现有解析、超时、诊断和严格门禁行为保持不变。

  完成证据：candidate 和 bounded repair 共用 `opencode-file-attachment-v2`，argv 固定为短消息在前、`--file=<prompt-path>` 在后，修复 OpenCode 1.17.18 把短消息吞作第二个文件的问题；完整 prompt 仍以 SHA 绑定文件保留。schema-v7 manifest 与 schema-v3 repair report 记录 file option/style、消息位置、固定消息 SHA 和 `inline_prompt_in_argv=false`；summary 与 exact-evidence validator 均独立拒绝 transport 漂移。

- [x] **P0-A13：内容寻址 AI candidate cache**

  cache key 由 ContextPack payload hash、prompt schema/version、实际 prompt hash、resolved model、agent 名称、repo 内 agent 定义 hash、variant 和解析合同组成。只缓存成功解析且 candidate/raw-response 均可按 SHA 重开的结果；provider failure、超时、拒绝和未通过解析的响应不得缓存。命中后仍需走完整 common gates，记录 `cache_hit` 与零次新增 provider 调用，且保持 `semantic_gate=false`；任何绑定漂移都删除命中资格并重新调用模型。

  完成证据：缓存仅通过 `--cache-root` 或 `--ai-candidate-cache-root` 显式启用，competition runner 只接受 repo 内目录。schema-v4 manifest 绑定八项内容 key，并把命中的 `entry.json` 复制为本次 path/SHA evidence；summary validator 重开 entry、raw response 和初始 candidate，重新解析响应并复算 key。并发同 key 先用 single-flight 二次查缓存，再在跨进程发布锁内通过唯一 staging 目录和 first-writer-wins rename 发布；损坏 entry 会隔离并由一次真实 provider 调用重建。失败、超时、拒绝和解析失败均不缓存。命中记录初始 `provider_invocations=0` 和 metrics-v2 `cache_hits=1`，后续 repair rounds 仍独立计入总调用；common gates 与 `semantic_gate=false` 不变。Windows 124 项合同测试全部通过；WSL 同组 124 项中 123 项通过、1 项 Windows 锁专用用例按平台跳过。

- [x] **P0-A14：受限展开编译 response file**

  仅展开 source root 内的相对 `@file`，限制递归深度、文件数、单文件/总字节并检测环；每个 response file 记录 repo/logical path 与 SHA。解析失败、路径逃逸或预算超限必须 fail-closed，不能静默丢失 include、define、target ABI 等参数。完成后用不同真实 C 项目验证，不新增项目名、函数名或 fixture 特判。

  完成证据：ContextPack v3 与独立 schema 只为 clang/gcc/cc 系列启用 `gnu-v1`，MSVC/未知 dialect fail-closed。相对路径允许 root 内规范化 `..`，真实逃逸、absolute/drive/UNC、cycle、link、非法 UTF-8/NUL/引号、深度 4、展开 16 次、单文件 64 KiB、总计 256 KiB 或 4096 参数超限都会在 provider 前结构化阻断。成功展开会恢复 define/include/target ABI，记录 original/expanded argv SHA，并把每个文件的 logical path/SHA/size/depth 同时绑定到 selected entry 与 ContextPack inputs；response 变化会失效 ContextPack、prompt 和 AI cache key。Windows/WSL 同组各 149 项、148 项通过：Windows 仅跳过无权限 symlink 创建用例，WSL 仅跳过 Windows 锁专用用例。

- [x] **P0-A15：可复算 AI caller/callee 上下文与 prompt scope**

  ContextPack 必须把直接被调函数的签名、定义状态、source binding、stub boundary 和调用表达式合同作为有界事实交给 AI；不能只给 caller 源码后要求模型猜测跨函数语义。candidate manifest 的 `prompt_scope` 必须从实际 ContextPack 计算，不能固定宣称模型看过不存在的 type map、CFG、pointer graph、root cause 或 caller/callee facts。

  完成证据：ContextPack v3 的 16 KiB C boundary 现包含经统一敏感字段/宿主路径清理的 `external_direct_callees` 与 `call_expression_contract`；普通字符串、嵌入 JSON 和转义 JSON 中的带引号 secret assignment 也会清理。独立 `context_scope.py` 只按实际非空 loaded excerpt、真实失败状态和具名直接 callee facts 生成稳定 scope，成功状态下的信息性 diagnostics 不计为 root cause；普通生成与 cache-hit 共用该规则。必需 callee boundary 在单边界或 128 KiB 总 ContextPack 预算中被压缩/截断时，provider admission 都以 `required_callee_context_incomplete` 零调用拒绝。当前 schema-v7 manifest 记录 scope、模型身份与 invocation receipt，fresh-run summary validator 强制 v7、重开 hash-bound ContextPack、逐字节复算 prompt 并拒绝 scope、身份、receipt 或版本漂移；旧版本只保留 schema/accepted-evidence 归档读取能力，不能作为 fresh run 自选降级。该项不含项目名、函数名或 fixture 特判，不提升 semantic numerator。

- [x] **P0-A16：透明辅助模型验证与无工具候选边界**

  GLM 余额不足时允许显式选择替代模型做本地候选质量验证，但模型身份必须从 resolved model 派生并贯穿 generator、candidate、repair、router 和 summary；只有 `zai/glm-5.1` 是 `competition-primary`。任何替代模型都必须标记 `competition_eligible=false`、`evaluation_scope=auxiliary-local-validation`，不能关闭 P0-A6/A10/H9、进入比赛指标或伪装为 `opencode-glm51-1`。

  完成证据：新增统一 model identity 与动态 candidate id，competition summary 从 resolved model 独立派生并交叉核验 generator/candidate 身份，exact router 也会绑定 selected id、唯一 manifest candidate 和完整模型范围；C2Rust repair generator 必须与本次 routed AI generator 一致。候选和 repair 共用受限响应合同：默认使用权限 `*=deny` 的 `c2rust-candidate` agent，未知 repo-local agent 在 provider 启动前拒绝；worker/preflight 继续使用 `c2rust-migrator`，比赛探针逻辑名 `GLM-5.1` 与 candidate resolved id `zai/glm-5.1` 也已分离，`opencode models` 同时接受这两个精确 token 并拒绝近似名。解析器递归审计原始 JSONL，任何层级的 `tool`/`tool_use` 直接拒绝。严格 JSON 和唯一完整 JSON 围栏可解析，多围栏/不完整围栏 fail closed，解析合同提升到 v3。provider 已拆为 474 行 orchestration、218 行 response parsing、282 行 runtime diagnostics 和 121 行 receipt 构造。schema-v7 为每次 provider 调用绑定最小 receipt 与独立 session-export identity projection；两者都有 `additionalProperties=false` 的专用 schema，只保留身份、prompt/response SHA 和内存中完整 export 的 SHA，不落盘完整 session。competition-exact 会实时重开同一 OpenCode session，并同时核对 export SHA、实际身份、附件 prompt 路径与 ContextPack 前缀、assistant response，不能用无关 GLM session 替换 DeepSeek response。WSL OpenCode 1.17.18 在未传 `--ai-agent` 时使用 `opencode/deepseek-v4-flash-free` 真实生成 `opencode-deepseek-v4-flash-1`，候选通过 rustc 与 compile/oracle/replay/schema-diff/negative-diff/unsafe/alias-ABI/final-verification 八类 exact gates；router 保留完整辅助身份且 `semantic_pass=true`，但总 auto manifest 和候选仍保持非比赛 `semantic_pass=false`。Windows 与 WSL 同组各 203 项回归通过，均跳过 1 项平台专用用例。

- [x] **P0-A17：隔离辅助模型套件与严格输入绑定**

  GLM 余额不足时，使用独立辅助 runner 对固定跨项目集合运行 DeepSeek V4 Flash 等非比赛模型；不得把辅助成功率写入比赛或 translator numerator。每次运行必须使用空 out-root，所有路径型 identity 必须安全且 project/slice 唯一，slice spec 在模型启动前后都要复核 SHA。并发 OpenCode 单元使用独立 config/data/cache/state/tmp，避免 SQLite、session、日志和导出身份串线。

  完成证据：`run_ai_auxiliary_cross_project_suite.py` 默认 `opencode/deepseek-v4-flash-free`，拒绝 competition-eligible 模型、accepted evidence、stale out-root、路径逃逸、重复单元和 spec TOCTOU；1..4 个并发单元按批次更新 provider circuit，并固定 `competition_success_numerator=0`、`translation_coverage_numerator=0`。fresh Oracle 的整文件与函数 span 仅接受 exact 或可证明的 LF/CRLF 投影，byte 坐标不能退化为宽松行匹配。candidate/repair prompt 还在完整 ContextPack 前复制精确 C 签名、参数顺序与 Rust pointer/unsafe policy。一次在源代码编辑期间运行的混合版本结果已废弃，不发布其成功率；辅助模型结果仍不能关闭 P0-A6/A10/H9。

- [ ] **P0-A18：replay-compatible Rust API 合同前置**

  在 provider 启动前生成并 hash-bind 精确 Rust 函数合同：函数名、可见性、参数数量与顺序、C 指针到 Rust reference/slice 的映射、长度参数是否保留、返回类型、ABI 与 unsafe 边界。该合同必须由 slice spec、Rust boundary 和 replay generator 的同一逻辑派生，不能由项目名、函数名、fixture 名或模型猜测派生。

  当前根因：高显著性边界摘要已使 DeepSeek 将 `fdb_is_str` 从错误的单 `u8` API 改为语义接近的安全切片实现，但模型仍删除了 replay 需要的 `len` 参数，初始候选因参数数量不匹配失败；隔离环境中的第 1 轮 repair 仍未恢复 `len`，还增加了不必要的 `unsafe`，因此 exact gates 正确拒绝。完成条件是模型调用前可直接看到与 generated replay 一致的 Rust API，repair 也绑定同一合同，并在固定跨项目辅助套件中显著减少首轮 rustc API mismatch；通过率只由 exact gates 统计。

  当前拆成三个可验收子阶段，避免把“某个用例改善”误报为通用合同完成：

  - [x] **P0-A18a：可执行 replay source contract**。`auto_migrate` 在 provider 前生成 replay 草稿；ContextPack v4 完整绑定 replay source、SHA、大小和真实调用次数，供 validator 重开与复算。模型投影不再暴露可能携带 expected/actual 的 replay source，只展示同源 ReplayCallPlan 与 `required_candidate_api`；candidate/repair prompt 各只展示一份合同。provider readiness、manifest v8、cache、scope 和 fresh summary validator 均 fail closed；缺失、敏感、超限、无真实调用或文件漂移都保持 `provider_invocations=0` 或使 fresh run 无效。`_auto_migrate_ai_exact.py` 同阶段按 routing/persistence/validation 拆成 489 行兼容门面和三个职责模块。
  - [x] **P0-A18b：结构化 ReplayCallPlan**。从 replay generator 抽出单一结构化计划，显式携带参数名/顺序/Rust 类型、C 参数映射、length retained、返回类型、ABI、unsafe 和 call args；renderer 与 prompt 只能消费同一计划。已删除专用 legacy fallback dispatch 与 readiness OR 列表，函数名只作为合同数据。
    - [x] **P0-A18b1：声明式 plan 核心**。受限 DSL、plan SHA、ContextPack 子合同 v2、source marker、调用 arity 复算、prompt 单份 payload 与 fresh binding 已完成。`source_function_name` 与 Rust `api_name` 分离，zlib/libuv 已生成真实调用；`fdb_blob_make/kv_to_blob/set/del` 已改为按语义合同选择 renderer。AI 生成 draft 只有在 manifest v8、selected candidate、applied artifact、draft SHA 全部闭合时才能进入 replay。
    - [x] **P0-A18b2：legacy adapter 全部计划化**。已盘点的 scalar、record、external-sequence、record-pointer 与 opaque-context adapter 均消费 ReplayCallPlan；不完整合同 fail-closed，不再回退专用 renderer。
      - [x] **P0-A18b2a：byte-slice/CRC 计划化**。`readonly_byte_slice_bool_return` 通过合同 kind 规范化为同一 plan，不按函数名分派；`fdb_calc_crc32` 声明通用参数/fixture 映射。plan 新增 canonical inline fixture SHA 与 `u8_array` codec，`fdb_is_str`/CRC32 均生成 typed direct call。141 项聚焦测试通过，固定套件预检保持 12/12 ready、0 次模型调用。
      - [x] **P0-A18b2b：record/external plan v2**。盘点出的 9 个 record-state 与 4 个 scripted external/call-continue renderer 已全部迁移。
        - [x] **P0-A18b2b1：record plan v2 核心**。受限 `bindings`、`binding_value/borrow_mut`、递归 record initializer、`binding_path` observations、`u32/usize/bool` typed codec 和 mutable-root noalias 闭包已接入 ContextPack/schema/fresh binding。constant、field add、field+scalar add、postfix increment、interior projection、stats sequence、guarded stats 共 7 个 renderer 已退出 legacy 分发；v2 实现保持薄门面，并按职责拆分为受限片段。
        - [x] **P0-A18b2b2：剩余 state/external**。
          - [x] **P0-A18b2b2a：record-state 9/9**。owner-interior u32→usize add 复用 typed owner observation；reset-add-while-continue 复用多 `binding_path` observation。`direction=input` 的 record 参数生成 `binding_borrow`/`&T`，`inout` 才生成 `binding_borrow_mut`/`&mut T`，noalias 仍覆盖所有并存借用根。
          - [x] **P0-A18b2b2b：scripted external 4/4**。通用 `scripted_runtime` 以 fixture-only claim boundary 声明 scalar/sequence stimulus、reset channel、call count/args/order probe 和 scalar/tuple/array/vector/matrix codec；输出指针作为有界 array binding。plan 只携带闭合的 channel/operation、callee、fixture field 与 API 数据，renderer 将 channel/operation 映射到固定仓库 helper，不能注入任意 Rust helper。4 个 legacy renderer 对应的 7 个真实 slice spec 均进入 plan v2；102 项聚焦测试通过。159 项 `test_auto_migrate` 中仅 2 个既有 CRC32 用例失败、1 项平台跳过；同两个测试方法在干净 `26b6edce` 基线也失败，不计作 scripted runtime 回归。
      - [x] **P0-A18b2c：简单 legacy renderer 清零**。原盘点的 13 个 scalar return、mutable out report、record/pointer identity、opaque context 直接调用 adapter 已全部迁移；专用 fallback dispatch 与 readiness OR 列表已删除。
        - [x] **P0-A18b2c1：scalar-return 4/4**。结构性识别 pure-u32、single-i32、signed-rshift-i32 与 ABI-bound u64，不读取函数名或项目名；统一生成 schema-v3 declarative contract。`status/contract` 等 fixture 元数据进入 hash-bound `fixture_assertions`，并在 plan 构建时校验固定值；`u64` 成为正式 codec。8 个现有 demo spec 均退出 legacy renderer，27 项 plan 回归和 3 项 exact auto-migrate 回归通过。
        - [x] **P0-A18b2c2：mutable-out/report 4/4**。single i32 output、dynamic i32 slice output、input-buffer out0+sum 与 call-metadata 已按 C 签名、参数方向、length companion、call-expression contract 和 fixture observable 闭合生成通用 plan；固定 i32 array、受限 `Vec<i32>` initializer、最多 4096 项的 `i32_slice/i32_vec` codec、whole-binding observation、`usize/string_vec` metadata assertion、fixture relation、完整符号/字段重命名和漂移拒绝均已覆盖。call-metadata 显式声明 `input_fixture_fields`、contexts 与 source_calls，不猜测字段或解析 C 文本。真实 store-add-one、copy-i32-ptr-arith、sum-i32-buffer、sum-i32-ptr-arith 与 call-expression replay 均不再进入对应 legacy renderer。
        - [x] **P0-A18b2c3：record-pointer/opaque 5/5**。record pointer identity、record projection identity、record buffer/length identity、opaque key 与 opaque key/value 均已迁移到通用 v2 producer。opaque context 使用安全 Rust fixture model，不再伪造 FlashDB ABI marker；旧 raw-pointer AI draft 会在 replay 编译门 fail-closed。Windows/WSL 聚焦门禁均为 48/48；WSL 阶段全量 207 项仅保留干净基线已有的 2 个 CRC32 失败和 1 项平台跳过。该阶段仍是 replay/harness 能力，不增加 translation coverage numerator，也不替代 C oracle/Rust replay/diff 语义证据。
    - [x] **P0-A18b3：ReplayCallPlan 按职责拆分**。原 946 行实现已拆为 48 行兼容门面和 dispatch、v1 builder、fixture binding、schema、literal rendering 五个真实模块，不使用 `exec` 或代码片段拼接；提交 `b28d5648` 的兼容门为 87 项通过、1 项 Windows symlink 条件跳过。
    - [ ] **P0-A18b4：ReplayCallPlan v2 退出动态 fragment**。`replay_call_plan_v2.py` 仍动态装载 9 个 `.pyfrag`、约 2,949 行；迁移为显式 builder/schema/fixture/scripted/identity/buffer/string 模块，并逐字保持 plan JSON、plan SHA 和生成 Rust。
  - [ ] **P0-A18c：有限跨项目验收**。固定 12 项必须全部可生成真实 replay call，首轮 rustc API mismatch 相比 A17 明显下降，并继续只按 exact gates 统计质量信号。
    - [x] **P0-A18c1：有界 provider/repair 可靠性**。ContextPack replay 合同提升为 v3，并从 ReplayCallPlan 生成可独立复算的 `required_candidate_api`，包含精确签名、supporting structs、ABI、unsafe 和引用返回生命周期；candidate/repair prompt 只展示一份完整 API。AI manifest 提升为 v9：仅对“合法无工具 JSONL、无 assistant 文本、终止于 `step_finish`、output/reasoning token 均为 0”的空 completion 原样重试一次，两次 response/receipt/session identity 都 hash-bound；余额、鉴权、timeout、非零退出、工具事件和普通 malformed response 不重试。fixture-only Rust compile stub 在检查后逐字节恢复 canonical AI draft，避免 applied artifact SHA 漂移。repair 只接受完整自包含 Rust candidate；fresh oracle 未通过、target contract 缺失或结构化候选失败缺失时零调用跳过。辅助聚合器重开 hash-bound repair report，分别统计 initial、repair 和 total provider invocations；默认 timeout 为 300 秒。161 项 Windows 聚焦回归通过。该项只完成 harness 改造，固定 12 项复跑结果仍由 P0-A18c 追踪。
    - [x] **P0-A18c2：安全语法拒绝 fail-closed**。call-continue、reset-add 和 interior-projection 的 Rust 安全合同抛出 `ValueError` 时，不再使 `auto_migrate` 以 traceback 终止；runner 写入 `replay_safety.kind=generated_rust_safety_contract_failed`、`replay_execution.phase=safety`、失败 mappings 与 `semantic_gate=false`，不执行 rustc/replay，并允许后续 exact/repair 流程继续。新增路径在 Windows/WSL 均为 4/4。
    - [x] **P0-A18c3：闭合 candidate source assembly**。`required_candidate_api` 新增可复算的 `candidate_source_contract`：candidate 必须 self-contained，非空 `supporting_types_source` 必须原样且仅一次出现，harness 不注入缺失类型，compiler-owned fixture types 构成闭合类型环境。candidate/repair prompt 在 required API 后显式重申同一规则，禁止用替代 extern/FFI/opaque 类型覆盖；规则不读取项目名或函数名。Windows 62 项、WSL 55 项 API/prompt/provider 聚焦测试通过。
    - [x] **P0-A18c4：未观测 null pointer 默认值安全投影**。record pointer identity 合同中未进入 observable、仅以 `null/null_mut` 默认值补全 proxy record 的字段，不再生成 raw pointer，而是生成 `Option<NonNull<c_void>>` 与 `None` initializer；record buffer/length 和实际 pointer identity 字段不走该路径。ReplayCallPlan validator、renderer、ContextPack schema 与 required API 同步支持 `optional_non_null_none`，规则不读取项目或函数名。34 项聚焦测试通过。
    - [x] **P0-A18c5：safe `NonNull` 类型与 raw-pointer operation 分离**。exact alias gate 只在候选无 `unsafe` 且 `core/std::ptr::NonNull<T>` 出现在泛型类型位置时屏蔽该安全类型路径；`NonNull::<T>` 构造、其他 `ptr` API、`as_ptr/as_mut_ptr/from_raw/into_raw`、raw pointer 类型与任何 `unsafe` + `NonNull` 组合仍 fail-closed 要求 current-candidate alias proof。规则不读取项目、函数或字段名；Windows/WSL 53 项相关门禁均通过。
      - 提交 `ecbb2ef3` 后，DeepSeek 0-repair 单项验证中 `kv_to_blob`、`tsl_to_blob` 均为 1-call AI exact pass；router SHA-256 分别为 `4f753f9cd00359d46ed13044f9845b9dff04702c84a4c9ede0aacfc85de31cac`、`93f7b5fe6d2f7f3d903d7042d2a78236b96b86afa491faeea5c971ed00d7a68b`。这关闭了两个 record identity 候选的 alias 误报，不提升 competition numerator。
    - [x] **P0-A18c6：通用、源码支撑的 external-callee behavior contract**。当待翻译函数调用当前 slice 外的函数时，模型只能从 SHA 绑定的 C 定义、宏、枚举和结构字段恢复行为；fixture expected/actual 和携带 oracle 的 replay source 对模型及 repair 都不可见。禁止读取项目名、函数名、路径或固定 fixture 值选择翻译行为。
      - [x] **P0-A18c6a：外部 callee 源码上下文**。按声明的 direct callees 从 source root 提取有界函数定义，并对路径、文件 SHA、span、TOCTOU、数量和字节预算 fail closed；不按目标名称分派。
      - [x] **P0-A18c6b：源码行为解析与独立绑定**。从 SHA 绑定源码解析否定 guard、函数式宏字段投影和 enum ordinal，生成独立 `behavior_sha256`；fixture expected 只由 validator 交叉核对，不参与规则构建。effective fixture SHA 同时绑定源 fixture 和 spec overlay。
      - [x] **P0-A18c6c：模型输入去 oracle 与删除专用语义桩**。candidate/repair prompt 隐藏 replay source、expected/actual/observed/mismatch 和 gate value；已删除 `flashdb_kv_set_fixture_model_allowed`、`flashdb_kv_del_fixture_model_allowed`、`rust_check_harness_only_external_stub` 及固定 `7i32` 路径。Windows 聚焦合同门 41 项通过、1 项平台条件跳过。
      - [x] **P0-A18c6d：跨平台阶段门**。schema 解析、fresh binding、`git diff --check` 和直接受影响的 auto-migrate 路径已闭合；最终聚焦合同组在 Windows 完成 96 项（95 通过、1 项平台跳过），在 WSL 为 96/96；删除专用桩的 7 个 auto-migrate 用例在两端各 7/7。readiness 会复算 rule/behavior hash、核对全部真实 callee 及 source bindings，注释伪控制流和 `oracle_contract` 回灌均有 fail-closed 负例。Windows 252 项阶段组只保留 2 个已在干净基线登记的 CRC32 失败和 2 个平台跳过，不计作本阶段回归。
      - [x] **P0-A18c6e：辅助模型精确复验**。空 out-root `ai-auxiliary-p0-a18c6-kv-set-deepseek-wsl-20260712-02` 使用 `opencode/deepseek-v4-flash-free`、1 initial、0 repair；独立 validator 重开 16 个 hash-bound artifacts 后为 AI exact pass。router SHA-256 `3d71be46e6d8530842397547a9011c1e65b1dc500922ee0d7f69daa12f7514e2`，candidate SHA-256 `9e9b78cac94f05e6cd23ee6aafd9e4598be415df325e8b4e77e803f75c292230`。该结果保持辅助模型身份与两个公开 numerator 为 0，不能替代固定 12 项和 GLM 比赛复验。
      - [x] **P0-A18c6f：实现按职责拆分**。external-callee 源码块提取/输入绑定与 guard/macro/enum 行为解析分别位于 260 行和 307 行模块；通用 provider readiness 与 callee hash/binding readiness 分别为 309 行和 164 行。不使用 `exec`、`.pyfrag` 动态装载或项目专用分派。

    - [x] **P0-A18c7：跨项目 AI 输入与证据合同闭包**。repair 完成后重新计算 eligibility；manifest schema 接受实际 external-source/typed-IR scope 和两类 context-boundary 状态；fixture-only scripted callee 不再被误要求仓库函数源码；目标函数 guard/return 从文件 SHA 与严格 source span 重新提取并与宏/枚举依赖共同生成高显著性行为规则；translation-carrier 真实 fragment 成为 fresh-oracle span。TypeMap `mappings`、CFG `functions` 和有界 clang typed-IR summary 进入 prompt scope，超长 diagnostics 独立截断。规则均按结构、声明和源码哈希驱动，不读取项目、函数、fixture id 选择翻译。Windows 与 WSL 聚焦回归均为 125/125。
      - 固定 12 项空目录辅助运行生成 12/12 candidates，12 initial + 4 repair，0 contract failure、0 execution failure、0 provider block，exact pass 从上一阶段 3/12 提升到 6/12。新增通过 `tsl_to_blob`、`kv_set`、`kv_del`；报告 SHA-256 为 `dfff968ad274924b763a8cede749338f37dcca25e38b5148fbeaaef0d09c2927`。辅助身份和两个公开 numerator 均保持 0。
      - 剩余失败边界已净化：4 个真实 fragment 的 fresh oracle 均通过，只剩 generated replay 行为不一致；zlib-ng 与 libuv 两项仍因 generated header/include 和整 translation unit 链接闭包不足而 fresh oracle 失败。它们进入 A18c8，不取消 A18c7 已关闭的合同修复。

    - [ ] **P0-A18c8：剩余 exact failure 的通用语义闭包**。
      - [x] **P0-A18c8a：carrier/scripted source behavior digest**。从真实 fragment、ReplayCallPlan scripted runtime、CFG/effect/typed IR 生成 source-backed 分支、调用顺序、字段写入和返回摘要；禁止把 fixture expected/actual 回灌给模型。
        - 有序 typed-IR 投影保留 assignment target/RHS、嵌套 `If/While/DoWhile`、call 顺序、`continue`、固定 return、无符号 wrapping 与 all-ones sentinel，并带独立 `projection_sha256`。未知节点、超过 64 项、节点/深度预算耗尽、投影截断或 hash 漂移会在 provider 启动前结构化拒绝；不会把部分投影描述为 exact semantics。
        - candidate 与 repair 共用同一份高显著性 source-semantics 合同；scripted callee 被声明为 harness-owned 且已在词法作用域，模型必须调用但不得声明、定义、mock 或 inline。候选自带 scripted callee 时，rust-check 生成结构化失败工件，不再 traceback；合法 trailing-comma Rust 签名不再被误拒绝。
        - artifact bounding 为完整 clang excerpt 预留元数据外预算，修复 6.3 KiB 有序投影被通用限深器改写后 SHA 失配的问题。Windows/WSL 聚焦门均为 131/131，`git diff --check` 通过。
        - `wsl-local-simulation` 的 4 项 DeepSeek 0-repair 定向运行全部 provider-ready 且各调用 1 次；interior projection 与 stats sequence 从旧 replay failure 转为八类 gate 全绿，独立验证器各重开 16 个工件后 `semantic_pass=true`。router SHA-256 分别为 `1d40a293cd63acee5a8eab1c72c155a879bf932ec5bbe68da9e15e965c394e31`、`7bfbc41e2803d72415c4035ab5068eb4b6bbe02eec5966b1e845556e941b2ae1`。
        - zero-start 与 read-kv-body-call 的初始候选及各 1 轮修复仍未 exact：DeepSeek 继续改写 nested loop/return/sentinel 或 required API mutability。该事实不回灌 fixture 值、不增加轮次，也不冒充固定 12 项成功率；默认流水线仍由通用 typed-IR fallback 与 exact gates 兜底，父项保持未完成。
      - [x] **P0-A18c8b：真实项目 fresh C oracle 构建闭包**。优先消费绑定的 compile database、generated include 和构建产物/链接合同；缺失时 fail closed，不按 zlib/libuv 名称添加语义桩或测试专用链接参数。
        - 新增 `linked_artifacts_v1` resolver 与独立 manifest schema，只按 schema/mode/字段工作，不读取 target/project/function/slice/name 选择逻辑。closure 绑定 source tree、规范化 compile DB、source/generated include 目录树、静态库、系统链接参数、source/link symbol、CMake 配置、toolchain 和 target ABI；路径必须 repo-relative，父路径、绝对路径、symlink、缺失和 SHA 漂移均拒绝。
        - producer 与 validator 从同一 closure 重建有序 argv；closure 无效时 producer 写 `native_build_closure_invalid`、零 argv 和结构化诊断。slice spec/build profile 与 ContextPack 声明 closure manifest path/SHA；fresh oracle 会重新解析 closure，并把 compile DB/include/library/link/symbol/config/toolchain/ABI 身份计入 flags/reuse key。
        - repo-owned 最小闭包位于 `validation/native-build-closures/`：zlib-ng 使用 `ZLIB_COMPAT=OFF` 的 `libz-ng.a`，显式绑定 `adler32_z -> zng_adler32_z` 与 generated headers；libuv 使用 `libuv.a` 及 `-lpthread -ldl -lrt -lm`。两份 compile DB 已去除宿主绝对路径，静态库 SHA 与实际 `nm` 符号一致。
        - WSL `runs-05` 中两项均为 `compile_succeeded_not_oracle`、return code 0、harness `exited_zero_not_oracle`，oracle compile contract 重算通过；libuv 完整 auto-translation schema validator 通过。fresh proof 仅剩 `oracle_output_mismatch/oracle_output_unproven`，不再有 header/link/build-profile/closure mismatch。Windows/WSL 聚焦合同测试均为 61/61，固定 12 项离线 preflight 12/12 ready、0 模型调用。
        - zlib 的空 CFG 现在以 `blocked` 合法表达，完整 auto-translation schema validator 已通过；这只证明拒绝证据完整，不是翻译或语义通过。旧的 `adler32_step` AST fixture 已移除，不能恢复合成样例冒充真实 `adler32_z`。
      - [x] **P0-A18c8b1：hash-bound 真实 TU translator 编译上下文**。从已验证 closure 投影 repo-relative source/include/define/compile-DB/ABI 上下文；compile DB 必须 SHA 匹配且唯一命中目标源文件，编译器、输入、输出、依赖生成参数和捕获的 include 路径会被清洗，再叠加 closure 权威 include/define。无效、歧义或 ABI 冲突均直接阻塞，不回退到 legacy parser。
        - 函数选择同时绑定文件、行、字节区间与规范化片段 SHA；宏改名可解析到展开后的 `FunctionDecl`，输出仍恢复逻辑函数名。LF 规范化偏移会映射到 CRLF 原始偏移，解决 Windows/WSL 工作树与比赛 Linux checkout 的差异；非 NULL 指针 `BitCast` 仍拒绝，只有已证明的 NULL 可安全重定型。
        - WSL `runs-07` 对 zlib-ng 和 libuv 均绑定 commit `0a7831c1`、clang 18.1.3 与各自 compile-DB SHA，原生 oracle harness 均为 `compile_succeeded_not_oracle`/`exited_zero_not_oracle`，两套完整 schema validator 通过。zlib 在运行时函数表成员调用处拒绝，libuv 在缺少记录布局证明的 `sizeof(*addr)` 处拒绝；两项均为 `semantic_pass=false`，未增加成功率分子。Rust lib 253/253、聚焦 Python 50/50 通过。
      - [x] **P0-A18c8c：通用可执行 C oracle call plan**。从 C 签名、fixture codec、observable outputs 与 ABI 生成数据驱动的 harness 调用、输入初始化、返回/结构字段编码和 stdout 比较；禁止按项目/函数名选择 adapter。只有执行 fixture target call 且 output gate 全匹配后，fresh oracle 才能进入 AI repair/exact 路径。
        - [x] **P0-A18c8c1：直接返回值调用计划**。ReplayCallPlan v1 的标量、字符串、十六进制/字节数组、派生长度与 `null_default` 可通用渲染为 C fixture 存储、按签名排序的实参、一次真实 target 调用及直接返回值比较；renderer 不读取项目、slice、函数或 fixture 身份来选择 adapter。case 数、ID、字符串、缓冲区和生成源码均有 fail-closed 上限，规范化后相同的 case ID 仍生成不冲突的变量。
        - validator 与 fresh-oracle 会从 hash-bound spec 重新生成 call plan，严格核对 plan SHA、声明和完整调用/断言语句；仅保留 marker 或伪造 matched 文本无法通过。WSL competition-like `runs-02` 中 zlib-ng 两个 fixture 均执行 `adler32_z`，编译与运行返回码均为 0，output gate 匹配且完整 schema validator 通过。
        - 该阶段仍为 `semantic_pass=false`、translation coverage numerator 不增加。当前 libuv 因省略的 C 输出参数和未声明的记录字段 C 投影明确拒绝；输出参数初始化、记录字段/字节序投影与 C/Rust diff 仍属于 A18c8c 后续项。
        - [x] **P0-A18c8c2：严格结构化 C oracle 输出协议**。`generated` call plan 每个 case/field 只输出一条规范 JSON 记录，绑定 ReplayCallPlan SHA、case 序号/ID、field、encoding 与规范字符串实际值；输出总量必须落在持久化 stdout 上限内。解析器拒绝缺失、重复、额外、乱序、错误值/SHA、未知键、畸形 JSON、重复 JSON key 与非规范编码，普通诊断行不参与协议。
        - output gate v2、fresh-oracle 和完整 evidence validator 使用同一解析器从保存的 stdout 重算，不再信任生产者填写的 matched/missing 列表；`not_used` 历史 harness 仍保留旧门禁，`generated` 合同不能降级。WSL competition-like `runs-03` 中 zlib-ng 两条实际值记录精确匹配，invalid/unexpected 均为 0，编译/运行和完整 schema validator 通过；仍为 `semantic_pass=false`，不增加成功分子。
        - [x] **P0-A18c8c3：声明式输出参数与记录投影**。独立 `c_oracle_contract` 只接受安全 header basename、零初始化单层 struct pointee、`address_of`、return、标量映射、字段、BE16 与固定长度对象字节枚举；不接受原始 C 表达式或项目/函数 adapter。output binding 必须精确闭合 omitted C 参数，观测顺序必须与 ReplayCallPlan assertion 和 fixture observable 完全一致，C call-plan SHA 绑定 replay plan、有效 fixture、目标 ABI 与完整合同。
        - renderer 为指针/`int`/`CHAR_BIT` 和每个观测字段生成 `_Static_assert`，header 必须唯一对应 `c_boundary.files(role=header)`；完整重命名 target/slice/function/output parameter 后仍走同一路径。实现已拆为 70 行 façade、direct renderer、output renderer、output schema 和 output protocol 小模块，均低于 400 行。
        - WSL competition-like libuv `runs-02` 实际编译/运行返回 0，`loopback`/`invalid` 两个 case 的 return/status/family/host-port/port-bytes/address-bytes 共 12 条严格记录全部匹配，invalid/unexpected 均为 0，完整 schema validator 通过。该闭环只完成 fresh C oracle harness；translator 仍在 `sizeof(*addr)` 记录布局处 fail closed，`semantic_pass=false`，不增加翻译成功分子。
      - [x] **P0-A18c8d：`sizeof(expression)` operand type 恢复**。真实 clang JSON 对表达式形式不提供 `argType`；frontend 现在仅在 `inner` 精确包含一个且该 operand 携带 `type.qualType` 时恢复类型。显式 `argType` 路径不变，缺失 type 或多 operand 继续 `unsupported_sizeof_operand`。WSL libuv `runs-03` 已从旧 operand blocker 推进到 `unsupported_sizeof_type: sizeof(struct sockaddr_in) requires explicit C layout/ABI provenance`，fresh C oracle 仍为 12 条严格记录匹配；该阶段不生成 Rust，不增加成功分子。
      - [x] **P0-A18c8e：hash-bound 记录布局 provenance**。只有 hash-bound compile DB 路径会以同一清洗后编译参数单独执行 clang `-fdump-record-layouts-complete`；原始 stdout、diagnostics、共享参数、compile DB 和完整目标 ABI 分别绑定 SHA/值。`sizeof` 仅放行唯一命名 `struct` 的完全匹配布局，`_Alignof`、union、缺失/重复布局、类型/ABI/hash 冲突继续 fail closed；实现不读取项目、函数或记录名称选择大小。
        - WSL competition-like libuv `runs-06` 捕获 `struct sockaddr_in` 的 `size=16, align=4`，但该值来自 clang dump 而不是身份分派；dump SHA 为 `a6c4e578f594579408d716a1cfbf48ed02169d05630167f2fbabb8c02e7c432b`，compile-DB SHA 为 `f81a760815fb8618d3856e9f376a89d0e9c76234d3af0dd9e7840d8319f40638`。fresh C oracle 仍为 12 条严格记录全匹配，完整验证器通过，translator blocker 推进为 `memset destination BitCast operand struct sockaddr_in * is not mutable unsigned 8-bit pointer`。
        - 该证据只证明当前运行内部绑定一致和持久化报告可重开复核；没有外部预期 dump SHA 时，不宣称检测到了跨运行 clang/environment 漂移。该阶段仍为 candidate context，`semantic_pass=false`，不增加翻译成功分子。
      - [x] **P0-A18c8f：通用可变记录指针零填充**。仅接受语句位置的标准 `memset`、直接非空可变单层记录参数、字节值精确为 0，以及由同一 hash-bound 布局证明生成的完整 `sizeof(record)`。frontend 将其降为专用 `IrStmt::RecordMemset`，完整保留记录类型、size/alignment、四个 SHA 与目标 ABI；普通数值相等的 `IrExpr::Call` 不能冒充该路径。typed emitter 二次校验 provenance，并只对整数、定长整数数组和递归完整记录生成安全 `*dest = Record { ...零值... }`，不把 Rust 记录转为原始字节切片、不生成 `unsafe`。readonly、nullable、非零/部分写入、指针字段、类型/ABI/hash 漂移、`memcpy` 和自定义函数均拒绝；规则不读取项目、记录或函数身份。
        - WSL `runs-09` 使用 clang 18.1.3 和默认 Cargo 缓存完成 local simulation；旧 `memset destination BitCast operand struct sockaddr_in *` blocker 已消失，记录布局仍绑定 dump SHA `a6c4e578f594579408d716a1cfbf48ed02169d05630167f2fbabb8c02e7c432b` 与 compile-DB SHA `f81a760815fb8618d3856e9f376a89d0e9c76234d3af0dd9e7840d8319f40638`。fresh C oracle 继续编译/执行并匹配 12/12 严格记录，完整验证器通过；新 blocker 为 `sa_family_t is outside the current type skeleton`。该名称只记录真实现象，不作为后续分派键。
        - competition-env repo-local Cargo 镜像本轮返回空响应，故 `runs-09` 明确为 `wsl-local-simulation`，不能冒充 `competition-exact`。本阶段仍未生成真实 libuv Rust candidate，`semantic_pass=false`，不增加成功分子。
      - [x] **P0-A18c8g：通用 typedef canonical/desugared 类型恢复**。clang type-object 候选仍按 `qualType -> desugaredQualType -> canonicalQualType` 尝试，但当全部因目标 ABI 暂缺而 unsupported 时，保留最后、最深的 canonical spelling，供后续 ABI 绑定恢复精确宽度/符号性；不再错误保留无法解析的表层 alias。translation-unit `TypedefDecl` inventory 同时进入函数体 AST type-object 和命名/匿名记录字段解析，字段节点即使省略 desugaring 也能由唯一 alias provenance 恢复。alias 与显式 desugared/canonical 类型不一致、重复冲突、未知 alias、目标 ABI 宽度缺失继续 fail closed；实现不读取项目、头文件、函数、字段或 typedef 名称。
        - 当前提交在 WSL 使用 clang 18.1.3、同一 hash-bound libuv compile DB 与 `x86_64-unknown-linux-gnu` ABI 直接复跑 translator；旧 `sa_family_t is outside the current type skeleton` blocker 已消失。新 blocker 为 `CallExpr: argument 2: ... mutable void * BitCast address target in_addr_t * is not a mutable record pointer`，即尚未建模“完整可变标量 lvalue 地址作为 `void *` 写入参数”。观察到的两个 typedef 名称只用于记录真实推进结果，不作为规则分派键。
        - 本轮 probe 是 `target/` 下未发布的 WSL local-simulation 诊断，不包含 Rust candidate、C/Rust replay/diff 或语义通过；`semantic_pass=false`，翻译成功分子不增加。
      - [ ] **P0-A18c8h：通用可变标量地址到 `void *` 调用参数**。仅对可证明为完整整数标量 lvalue 的直接/记录字段地址、直接外部函数调用和明确的 mutable `void *` 参数建模临时可变借用；要求别名、存活期、对齐、宽度、调用签名和写后读取路径可验证。const、nullable、位域、packed/volatile/atomic、指针算术、跨调用逃逸和重叠可变借用继续拒绝，禁止按 `in_addr_t`、libuv 或固定 callee 名称放行。
        - [x] **P0-A18c8h1：记录指针字段地址的安全适配器候选**。前端保留专用 `MutableVoidPointerAddress` provenance，仅接受一个直接 mutable 记录指针根、首跳 `->` 后仅 `.` 的完整记录字段路径、固定宽度整数终点、源整数指针同宽同符号、直接 `FunctionDecl` 和对应位置的 mutable `void *` 形参。typed IR 再验证完整字段 inventory、根所有权、非 nullable、同调用重叠借用和源/目标类型，并只向可编译的安全适配器发射 `&mut root.path`；普通 `AddrOf` 或手写数值相等节点不能进入该路径。原始 `*mut c_void` extern 绑定不会被伪装成安全接口，缺少适配器时由 rustc/链接门禁继续 fail closed。
        - [x] **P0-A18c8h2：显式 noalias 前置合同与等价整数 typedef**。旧 libuv slice spec 已补齐通用 `pointer_contract`，声明 `ip` 只读输入、`addr` 可变输出及完整 `ip -> addr` noalias 前置条件，同时保持 `aliasing_proven=false` 和“无全程序别名证明”边界；translator 不从项目名、函数名或不同 C 类型推断 noalias。A18h 专用校验现在仅在 const 属性、signedness 和 width 全相同时接受 typedef/基础整数的不同 spelling，signed-32 与 width-16 漂移继续拒绝。
        - [x] **P0-A18c8h3：外部直接调用 compile context 与指针适配**。libuv slice spec 以真实 C 签名声明 `__bswap_16` 和 `uv_inet_pton`，`inet.c` 绑定规范化 SHA；system-header inline 只绑定调用点与 header 来源，不冒充源码实现。通用 rustc-only 桩对每个 C 指针参数使用独立泛型 pointee，保留 `const`/mutable 方向，并在报告中写入 `compile_only_pointer_pointee_erasure`。该适配只用于 `rustc_compile_only`，fixture/replay 专用模型仍保留精确签名。
        - WSL clang 18.1.3、同一 hash-bound libuv compile database 和 `x86_64-unknown-linux-gnu` ABI 的 `target/a18c8h-probe-07` 已生成 `GenericTypedIr` candidate，两个 callee 均为 `generated_compile_only`，`blocked_count=0`、stub contract 通过且 `rust_check.status=passed`。replay 明确以 `compile_only_external_bindings_not_executable` 跳过，C oracle 本轮也由 `--skip-c-oracle` 跳过，因此 `semantic_pass=false`、成功计数仍为 38。
        - [x] **P0-A18c8h4a：compile-only candidate/replay API 编译预检**。只要 rust-check 报告包含 `rustc_compile_only` 绑定，harness 就把注入桩后的 candidate 与 generated replay 合并执行一次 `rustc --test`，持久化 stdout/stderr、返回码和 `candidate_replay_compile_preflight`；无论预检成败都保持 `execution_allowed=false`，不运行桩、不产生 replay pass。改名正例证明 API 匹配时预检通过但仍跳过执行，改名负例证明 API 不匹配时保存编译诊断且语义保持 false。
        - [x] **P0-A18c8h4b：candidate-required external callee 过滤**。rust-check 先以 `--json=diagnostic-short` 对未注入桩的原始候选执行一次结构化诊断，避开长 rendered diagnostic 在多未解析调用下的编译器渲染崩溃；只接受 code 精确为 `E0425`、message 精确为 `cannot find function \`NAME\` in this scope` 且 `NAME` 属于 slice 已声明/已阻塞 external callee 集合的交集，再仅为这些名称建立 compile-only context。完全自包含的 AI 候选不再因原 C 调用图仍含外部依赖而被无条件注桩和跳过 replay；部分内联候选只注入实际未解析的声明函数。诊断文本字符串、其他错误码、`cannot find value` 和未声明名称均不能伪造选择结果。该阶段不放宽 compile-only 执行边界，不把 rustc/replay 单独计为语义通过，成功计数仍为 38。
        - `target/a18c8h-probe-10` 的 WSL local simulation 使用 clang 18.1.3、Rust 1.95.0-dev、同一 hash-bound libuv compile database 和 `x86_64-unknown-linux-gnu` ABI。原始候选诊断精确选择 `__bswap_16` 与 `uv_inet_pton` 两个已声明函数，两个 compile-only binding 注入后 `rust_check.status=passed`；candidate+replay 预检仍因安全 API 形状返回 101，`execution_allowed=false`，replay 以 `compile_only_external_bindings_not_executable` 跳过。本轮使用 `--skip-c-oracle`，因此 `semantic_pass=false`，不增加成功计数，也不冒充 `competition-exact`。
        - [x] **P0-A18c8h4c：AI repair 多诊断稳定性**。generated replay 与 non-executing preflight 统一使用 `--json=diagnostic-short`，不改变编译、执行或语义门禁，只去除易触发 Rust 诊断 renderer ICE 的长 rendered snippet。中立回归在一个 replay 中同时制造缺失类型和参数类型不匹配并要求两类结构化诊断均持久化。`target/a18c8h-probe-11` 的 WSL local simulation 对同一真实候选返回正常失败码 1、两个 `E0425` 与两个 `E0061`，`compiler unexpectedly panicked=false`；这些错误可进入既有 AI exact repair loop，但本轮没有调用模型、使用 `--skip-c-oracle`，`execution_allowed=false`、`semantic_pass=false`、成功计数仍为 38。
        - [x] **P0-A18c8h4d：exact compiler diagnostics 到 AI repair facts**。新增独立、名称无关的诊断归一化层，从 exact rustc 的 `errors` 或 replay compile JSONL 中最多提取 8 条 error，仅保留受限 `code` 与去主机/敏感元数据后的 `message`，去重后绑定到对应 candidate SHA。compile gate 只有 candidate/target binding 匹配时转发，replay gate 还要求 replay/fixture binding 匹配且 phase 精确为 compile；SHA 或合同漂移时不信任 runner 诊断。repair facts 再次重验该白名单并丢弃额外字段，rendered source、span、fixture 值和 oracle 值不会进入模型提示。harness 不自动拼 wrapper 或改写候选；OpenCode 只能返回完整自包含 Rust candidate，随后重新执行 rustc、fresh oracle、replay、schema diff、negative mutation、unsafe、alias、ABI 和 final verification。该阶段只改善 AI 修复输入，成功计数仍为 38。
        - [x] **P0-A18c8h4e：AI ContextPack typed-IR 扩展节点投影闭合**。新增独立投影扩展模块，以结构和类型合同而非项目/函数/字段名称识别 `RecordMemset` 与 `MutableVoidPointerAddress`：记录清零必须携带完整哈希绑定布局和 ABI，写入长度必须等于记录大小；可变地址必须由同宽整数指针转换为可变 `void *`，并保留嵌套成员路径。中立改名测试覆盖两套根变量/字段名称，布局大小、完整 ABI、整数宽度、const 性或未知节点漂移均 fail-closed。使用既有真实 libuv WSL 产物重建 ContextPack 后，typed-IR 从 `invalid` 变为 `ready` 且 unsupported 节点清零，provider readiness 准确推进到下一项 `external_callee_source_context_incomplete`。本阶段没有模型调用、没有候选语义验收，成功计数仍为 38。
        - [x] **P0-A18c8h4f：外部被调函数源码跨平台换行绑定**。抽出独立 hash-bound UTF-8 source reader，让外部 callee 定义、目标行为块和宏/枚举行为依赖复用主源码已有的 LF/CRLF 等价规则。每个 source block 和输入 binding 都保留 checkout 实际 SHA、slice 声明 SHA 与 `exact/newline_equivalent` 模式，provider readiness 逐项重算身份；仅换行风格变化可通过，内容、声明 SHA、匹配模式、span 或绑定漂移继续 fail-closed。中立测试用完全改名的 CRLF checkout 对 LF 声明哈希验证 callee 与行为依赖绑定。真实 libuv 的 `uv_inet_pton` 由原 `source_file_sha256_mismatch` 变为 `newline_equivalent` bound，系统头 `__bswap_16` 仍以非仓库来源明确记录但不冒充 real-source，整体 provider readiness 从 blocked 变为 `ready`。本阶段仍未调用模型，成功计数仍为 38。
        - [x] **P0-A18c8h4g：真实 AI-first/repair 阶段验收与瓶颈重排**。全新 `target/a18c8h-ai-deepseek-02` 在 WSL competition-like lane 使用 clang 18.1.3、fresh C oracle、`opencode/deepseek-v4-flash-free`、受限 `c2rust-candidate` agent、`max` variant 和 3 轮 repair。provider preflight 为 `ready`，完成 1 次 initial + 3 次 repair；第 2/3 轮候选均通过 rustc、fresh oracle、unsafe scan/ledger 和 alias，replay 从 initial/round-1 的 link compile failure 推进到 round-2/3 的 runtime failure，但 ABI、diff 和 final gate 未闭合。独立 `validate_ai_exact_evidence.py` 重开 29 个 hash-bound artifacts，结构校验通过且 `semantic_pass=false`；该辅助结果不计比赛或翻译成功分子。实跑同时证明 h4d 只在 direct runner 单测闭合，真实 `exact_replay_runner` 仍丢弃 `compile_stderr`，而 runtime repair 只收到泛化 `replay_failed`，因此下一阶段不再盲目扩展翻译语法，先修反馈信息闭包。
        - [x] **P0-A18c8h5a：真实 exact replay compiler/linker facts 闭包**。`validate_auto_migrate_candidate` 的 replay 结果投影拆入独立 50 行级小模块，只在 phase=`compile` 时转发 `compile_stderr`；exact gate 继续先核对 candidate、replay、fixture 和 target SHA，任一漂移都丢弃 compiler facts。从 rustc JSON 只接受严格 `linking with ... failed` error 下、note child 中完整匹配 `rust-lld: error: undefined symbol: <C identifier>` 的名称，输出受限 `{code: linker_undefined_symbol, message}`；路径、rendered、命令、secret、任意 child 文本和非法符号均不跨边界。真实 WSL 对本轮 DeepSeek initial candidate + generated replay 重放得到 `undefined external symbol uv_inet_pton`，Windows 非目标 linker 仅保留泛化 compile_error。真实 wrapper、名称中立 linker、spoof、敏感信息和四类绑定漂移回归均通过；阶段 62 项 AI exact/repair/provider 测试全绿。全量 auto-migrate 163 项保持原有 3 个 CRC32 失败与 1 个平台跳过，没有新增失败。该项只提高 repair 信息质量，不执行 compile-only stub、不产生语义通过，成功计数仍为 38。
        - [x] **P0-A18c8h5b：无 oracle 值的 replay case/field 失败定位**。ReplayCallPlan 派生完整 assertion inventory，v1/v2 renderer 用 opaque guard 代替携带值的断言；真实 runner 只接受固定 `<generated-replay>` 别名、单个 Windows/POSIX 分隔符、可选数字线程 id、精确组合源码行和 replay-owned 唯一 marker。auto-migrate wrapper 从 spec/replay 重建 inventory，exact gate 在 candidate/replay/fixture/target/plan/inventory 全绑定后才映射 `{case_id, observable_field}`，repair 合同拒绝任何额外字段。expected/actual、fixture 内容、replay source、panic、路径、行号和 raw stderr 均不跨边界；unknown/duplicate/spoof、三类 envelope 漂移和四类执行绑定漂移退回泛化失败。negative mutation 优先翻转 opaque observable guard，不再误测剩余 metadata assertion；旧 replay 保留受限 fallback，无可识别断言则拒绝。v2 多字段 scripted probe 暂不定位，继续 fail closed。Windows 阶段组 67 通过/1 平台跳过，WSL 为 67/67；Windows 全量 163 项仅保留既有 3 个 CRC32 失败/1 跳过，WSL 全量仅保留其中 `missing_clang_path` 路由失败/6 平台跳过，均无新增失败。该项只改善 repair 信息，不产生语义通过，成功计数保持 38。
        - [x] **P0-A18c8h5c：安全 Rust 候选 ABI 门禁精确化**。独立 121 行分类模块只扫描去注释/字符串后的候选源码，不读取项目、函数、路径或 fixture 身份。无 ABI 依赖的安全 Rust 以 `required=false/proof_class=not_required` 独立通过，replay failure 不再复制为 `abi_target_binding_failed`；`usize/isize`、pointer-width cast、target cfg、native endian 和平台 FFI 类型要求 candidate/target SHA 一致的 rustc/oracle/replay execution bindings；`repr(C/transparent/packed/align/integer)`、raw pointer、extern/linkage、layout intrinsic、transmute、union 和 assembly 在没有 current-candidate layout/FFI proof 时明确 `abi_layout_proof_missing`。repair 只接收 dependency kind 列表，不含源码、路径或布局值。真实 libuv repair-01 分类为 `repr_c/raw_pointer/extern_abi/ffi_platform_type`，repair-02/03 仅为 `repr_c`，替代旧的无差别 ABI 噪声。Windows 合并阶段 76 通过/1 平台跳过，WSL 76/76；Windows 全量 163 项仅保留既有 3 个 CRC32 失败/1 跳过。其他 exact/final gates 未放宽，成功计数保持 38。
        - [x] **P0-A18c8h5d：compiler-header declaration-only 来源分类**。新增独立 121 行、名称无关的分类模块，并把 readiness 重算拆入独立小模块；仅在 `definition_status`、严格 `compiler-header:<relative-header>#<symbol>`、无重复且含来源 header 的 inventory、唯一 `signature_ref` 及其 role/function/status/source_ref、`stub_boundary=compile_only` 全部一致时生成 hash-bound declaration。ContextPack 将其放入独立 `declarations`，明确 `allowed_use=compile_context_only`、`execution_allowed=false`、`semantics_verified=false`，不生成 repository source block 或文件 binding；prompt 也不再把 declaration-only 说成仓库定义。provider readiness 从 `c_boundary` 重算完整 declaration 并拒绝 namespace 大小写、绝对/父级/反斜杠 header、symbol、inventory、signature、hash、status、block 注入或 stub boundary 漂移。两套完全改名正例和真实 libuv 混合上下文证明 `__bswap_16` 与 `uv_inet_pton` 分别进入 declaration/source block，且不再产生 `repository_source_path_required`。Windows 合并阶段 95/95，WSL 功能阶段 91/91；WSL 的 2 个 doc 扫描仅受 Windows worktree `.git` 路径限制。全量 163 项保持 Windows 既有 3 个 CRC32 失败/1 跳过、WSL 既有 1 个 `missing_clang_path` 失败/6 跳过，没有新增失败。该项没有执行 compile-only stub、没有模型调用或语义验收，成功计数仍为 38。
        - `target/a18c8h-probe-08` 的真实 WSL local simulation 仍为 `rust_check.status=passed`，但预检返回 101 和 `candidate_replay_api_compile_failed`，明确报告缺少 `Ip4AddrReport` 及调用形状不匹配；replay 仍以 `compile_only_external_bindings_not_executable` 跳过。该阶段只改善 repair 诊断，不增加成功计数。
        - A18h 父项保持未完成：required safe candidate API 适配、可执行 external-callee 语义/no-escape、直接局部/参数标量地址、原始 extern 边界和调用写后字段初始化仍需独立收敛。const、nullable、可变参数、间接调用、signedness/width 漂移、不完整记录和同根兄弟读取已有 fail-closed 回归测试。

      前序失败证据：同配置 `kv_set` router `4a6b7b99095e2c91fde2c40a9eac9ca141a9bb276d4c981dd886115350d6f6a0` 的 rustc/unsafe/oracle 通过，但候选把外部 callee 结果实现为 `-1`，与 oracle 的 `7` 不一致。三项 WSL worktree 运行均报告 `repo_commit=UNKNOWN0`，因此只属于本地 hash-bound AI 路由证据。

  历史辅助运行只保留决策所需索引；详细 artifact 以对应 report 和 Git 历史为准。所有运行均为 `wsl-local-simulation`，两个公开 numerator 均为 0。

  | 阶段 / run id | exact | 关键结论 | 绑定证据 |
  | --- | ---: | --- | --- |
  | A18b2b2a / `ai-auxiliary-p0-a18b2b2a-wsl-20260712-160700` | 2/12 | 12 calls、8 candidates；2 contract failure、1 execution failure、1 provider block，不能声明通用提升 | run id + unit artifacts |

  | A18b2c2 / `ai-auxiliary-p0-a18b2c2-deepseek-wsl-20260712-180000` | 1/12 | 12 calls、8 candidates；相对前一轮退化，不能声明 replay 计划化提高成功率 | report SHA `bc26d70321086cd5a6e27b9e5d13912aaa29c32445160536364fe9ad00f27458` |

  | A18b2c3 / `ai-auxiliary-p0-a18b2c3-deepseek-wsl-20260712-192612` | 2/12 | 12 initial + 6 repair；修复旧聚合误报，但仅回到 2-pass 基线 | report SHA `7e8bd77b9afd6c5883d007a47c5058d47a12d1a5d973b86e5ff042b908e2d5c0` |

  | A18c1 / `ai-auxiliary-p0-a18c1-deepseek-wsl-20260712-204206` | 2/12 | 12 initial + 4 repair、11 candidates；contract failure 降至 0，首轮 API mismatch 3→1，但 exact 未提升 | report SHA `512641d1ece1d6dcf8b5bc20af3208da467a1c5284931d3c2a32bdb5cf8551c1` |

  | A18c3 / `kv_to_blob` targeted | 0/1 exact | rustc/replay 通过，因 `alias_proof_missing` 保持 semantic false；定向样例不是固定套件成功率 | router SHA `0c5f8f7130f4b6b8c163f1007af130cc6016f48234a54e6dde4485a8a7b31316`；manifest SHA `16a7fa57a8038cb9c66a57c8f8a8eeb04cb171dba68a5cc9b6802aa55529f18b` |

- [ ] **P0-A19：陌生 C 项目整项目 AI harness 泛化**

  目标不是继续增加已知函数的 translator 分支，而是让比赛平台把一个此前未见的 C 仓库交给 OpenCode 后，harness 能自动形成可审计的项目级翻译计划、隔离并行候选、可编译 Rust 项目和验证驱动 repair。所有决策只允许读取源码/AST/编译数据库/构建文件/类型/调用图/ABI/诊断和 hash-bound evidence；项目名、函数名、目录名、slice id、fixture 常量和 golden case 身份不得选择翻译器、prompt、adapter、stub 或修复策略。

  **当前边界（2026-07-15）**：A19 已完成一次真实 WSL DeepSeek 辅助 worker，并完成有界 Ninja/CMake 链接与静态归档闭包、实际 rustup toolchain 内容绑定、不可降级 SandboxBackend requirements/VerificationPlan、bubblewrap host capability probe、candidate/project Cargo 证据重开、不可变 coordinator receipt epoch、项目级 repair CAS/event/artifact ledger、最小相关 IR 上下文、隔离 Provider 合同模拟、宿主重建 IR 与重新协调、CompletionCoordinator 单步确定性调度，以及 schema v7 的 host Cargo project-diagnostic intake。已验证 compile intake 现在进入兼容 schema v7 数据库的 coordinator receipt v2 和共享 project repair queue；AI 候选只能进入 `pending-reverification`，同 gate 必须在新 managed generation 上产生更高 epoch 的 pass，才能由原子结算事务关闭历史义务。Cargo check/test 还会在任何 repair 落账前完成 whole-cohort gate/order/owner/error 分类，未知、混合、toolchain/environment 或 stale 结果整批零准入。Cargo stdout/stderr、分类回执和受限 unresolved-link intake 已可内容寻址重开；但 initialization/feature/cfg/ABI 专属入口、A19e7 独立 verifier capability/nonce 与 process-issued raw output、global planner、正向全项目 semantic gate 和真实 held-out 语义验收仍未闭合。父项保持未勾选，translator numerator 仍不增加；已有 Provider 合同模拟和本地 WSL smoke 都不是 `competition-exact`。

  **A19a 任意仓库入口与构建闭包发现**

  - [x] 自动选择显式或唯一 compile database，识别 Make/CMake/Meson 构建事实，展开有界 response files，保留 C 编译变体并安全跳过 C++ 翻译单元。
  - [x] 对仓库根、源码、数据库、输出、include/response 路径执行 repo confinement、link/junction、大小、数量和 SHA-256 漂移检查；外部路径和敏感 defines 不进入模型事实。
  - [x] 对 CMake `link.txt`、generated include、compile output、target、response file、搜索目录和有序系统链接参数建立 repo-confined 内容绑定；`required` 策略在闭包缺失时把所有 ready worker 转成不可启动的 deferred，`bounded-source` 只能生成非语义候选。
  - [x] 以不执行命令的有界解析器读取仓库内 `build.ninja`、递归 `include/subninja`、变量、rule/build edge、compiler link edge 和 response file；所有支持文件与输入输出都做内容绑定并在执行前复查漂移。
  - [x] 从 CMake 多行 `link.txt` 与 Ninja archive rule 解析 `ar`/`ranlib` 静态归档闭包，绑定操作、归档目标、成员顺序和同目标 `ranlib`，不执行构建命令。
  - [ ] **A19a6：Meson 与受限生成事实闭环**。
    - [x] A19a6a：只读解析仓库内已有 `meson-info/intro-targets.json`、`intro-buildoptions.json` 与编译器/依赖 metadata，绑定 target、source、generated source 和 introspection 文件 SHA；compiler/link/dependency metadata 目前只以有界摘要和非权威来源保存，schema、路径或闭包不完整时 fail closed。
    - [ ] A19a6b：仅在明确启用时由宿主在无网络、超时、资源和仓库边界约束下执行一次 configure/generate，输出到独立临时根后再只读提取事实；Meson/configure 缺失或失败属于环境/构建发现阻塞，禁止猜测参数或进入语义 repair。
      - [ ] A19a6b1：从 canonical BuildIR 及已绑定的 Ninja/CMake/Meson producer graph 识别 compile database 引用但尚未物化的生成源码；仅在 A19e8 沙箱能力闭合、producer argv 固定且输出路径逐项受限时执行最小 producer target，随后重新发现并重开所有输入。禁止执行任意 shell、自动猜测 target，或把人工预生成文件冒充 harness 已闭环。

    A19a6a 已由固定 `meson-info` 路径、严格 schema、路径/重解析点限制、内容绑定和漂移复验覆盖；固定 curl 提交的真实 WSL 规划还发现 4 个已进入 compile database、但默认构建未生成的 unity C 源。显式执行 Ninja 已声明的 4 个 producer target 后规划可以继续；当前 harness 只会在阻塞证据中报告仓库相对源路径，尚不会自行执行 producer，因此 A19a6b/A19a6b1 保持未勾选。
  - [ ] **A19a7：canonical BuildIR 与构建 adapter 收敛**。
    - [x] A19a7a：定义带 schema version 和 canonical serialization 的 BuildIR，统一表达 target、翻译单元变体、source/generated input、compiler/toolchain、compile arguments、include/define、archive/link 顺序、外部依赖和 ABI facts；每个字段都绑定原始路径/SHA、提取器版本和 provenance。
    - [x] A19a7b：所有构建 adapter 只允许向下游暴露 BuildIR；adapter-specific raw facts 只能作为 BuildIR 引用的审计附件，planner、DAG、ContextPack、Rust 重建和 verifier 不得读取 adapter 私有 shape。无法无损归一化的事实必须显式 blocked/refused，禁止猜测或静默丢弃。
      - [x] A19a7b1：compile database、Ninja/CMake 与只读 Meson facts 已进入 canonical BuildIR/attachment 验证路径。
      - [x] A19a7b2：把 Make dry-run 报告接入同一 BuildIR adapter/validator，并以静态导入门禁证明没有下游读取 Make 私有 shape。
        - [x] A19a7b2a：显式选择的 canonical Make 报告已进入共享 BuildIR/attachment reopener；计划和 worker admission 会重开原始报告并重新投影，同一语义在仓库根重命名后保持稳定，任一报告或仓库输入漂移均 fail closed。
        - [x] A19a7b2b：planner、discovery、CLI 与 verifier 已改走通用 `BuildInputSelection`、BuildIR stage 和 reopener facade；Git-tracked AST 门禁以精确 source→facade→symbol 和 facade→private-adapter import 图拒绝直接/别名/相对/star import、私有符号逃逸及动态 loader/`exec`/`compile`/`eval`/`__import__` 引用。门禁直接枚举仓库生产 `.py/.pyi`，不依赖 Windows worktree 的宿主 Git 路径；legacy `MakeReportSelection` 仅在 adapter facade 内转换。
    - [x] A19a7c：由单一 BuildIR validator 重开并复算所有 provenance/hash、generated-input closure、target/TU 唯一性和有序 link/archive closure；源文件、构建 metadata、toolchain 或 canonical projection 漂移时，必须在 worker 启动和最终验证前 fail closed。
      - [x] A19a7c1：重开 raw attachments 并复算 compile database、source/generated bindings、Meson facts、TU/target 唯一性、有序 target DAG 和 canonical projection；CMake/Ninja link input/search root 与 archive member 现在按 argv 原顺序保留，重复项不再被静默排序去重，并由 BuildIR ordinal/semantic hash 回归锁定。计划与 worker admission 前任一仓库事实漂移均 fail closed。
      - [x] A19a7c2：在比赛 profile 下绑定并重开 C compiler/archiver/linker 的实际二进制、版本、target/sysroot 与环境指纹，并由 CompletionCoordinator 在 `project-final` 前再次执行同一 BuildIR verifier；compile-database driver token 不能单独关闭 toolchain drift。
        - [x] A19a7c2a：从 compile database、CMake/Ninja/Meson 与 Make raw facts 统一导出 compiler driver/wrapper、linker driver/linker、archiver/ranlib 角色；每个 TU、compile/link/archive target 必须引用存在的 canonical toolchain id，比赛 profile 拒绝 token-only 或孤立工具记录。
        - [x] A19a7c2b：用 host-owned 固定 resolver/probe 绑定 PATH snapshot、selected/resolved executable、稳定 binary SHA/size、version、effective target/sysroot/resource roots、host/WSL 与环境白名单指纹；禁止 shell、项目 argv 和调用方 probe argv，超时、洪泛、子进程残留、wrapper/路径别名或能力不足均 fail closed。
        - [x] A19a7c2c：把 canonical C toolchain evidence 作为 BuildIR raw attachment；同一个 BuildIR verifier 必须重开二进制和原始 probe CAS、重跑固定 probe、重新导出角色映射并逐字节重投影，PATH、symlink/reparse、binary、version、target、sysroot、environment 或 profile 漂移一律阻塞。
        - [x] A19a7c2d：`CompletionCoordinator` 从 immutable migration manifest 取得唯一 BuildIR reference；比赛 `complete` 的 repo root 仅作重开 locator，在任何候选/AI/Cargo 执行前和写入 host project-final 前各运行一次同一 verifier，并把两次内容寻址 receipt 绑定到 completion receipt。
        - [x] A19a7c2e：补齐身份无关的 Windows 合同测试、WSL/Linux 真实 GCC/Clang/binutils probe、跨 host/profile 拒绝和 project-final 零后续调用断言；A19e7/A19e8 未完成前保持 `semantic_gate=false`，不得把本机 probe 称为独立 verifier 或 `competition-exact`。
        - [x] A19a7c2f：从可重开环境指纹中排除每次 WSL 会话都会变化的 `WSL_INTEROP` socket 值，但仍保留其 presence 参与 WSL 身份判断，并继续严格绑定 PATH、compiler binary/version/target/sysroot 与固定探针。两个独立 WSL login 进程复算相同证据 SHA；PATH、binary 或探针变化仍按原合同 fail closed。
    - [x] A19a7d：用不含项目身份的等价构建 fixture 证明各 adapter 对同一构建语义产生相同 canonical projection，并用静态边界测试拒绝下游导入 adapter 私有字段；有限 held-out 项目必须先通过 BuildIR 验证才能进入迁移 DAG。
      - [x] A19a7d1：Git-tracked 同源 fixture 已证明 compile-database+CMake 与 compile-database+Ninja 产生完全相同的 canonical BuildIR/`semantic_sha256`；Make 路径经同一 validator 重开，只在严格受限、test-only、非语义的公共合同上与二者相等。compile target id 已统一使用 canonical `kind=object`，define 漂移会改变公共合同；status、boundaries、raw refs、物化、toolchain、direct argv/link args 与 provenance 差异全部保留并显式断言不等。
      - [x] A19a7d2：把同源 fixture 扩展到 Meson、multi-TU、archive/ranlib、多输入和 external dependency/toolchain 语义，并让有限 held-out 项目通过 BuildIR validator 后再进入迁移 DAG。
        - [x] A19a7d2a：Git-tracked 扩展 fixture 以相同两个 TU、object、static archive、ranlib、最终多输入 link 和 `-pthread` 事实证明 CMake、Ninja、Meson 三条路径产生逐字段相同的 canonical projection/`semantic_sha256`；repository rename 不改变语义，compile/link 事实从 clang 切到 GCC 时三者共同改变 toolchain 语义。
        - [x] A19a7d2b：BuildIR schema/extractor 已升为 v2；Meson target type/source summary 只保存在被 semantic projection 排除的 provenance；canonical target kind、ordered input、archive operation/ranlib count、声明式 external dependency 和生成源使用 adapter-independent 字段。静态边界测试禁止所有下游生产模块读取 Meson 私有字段，Meson 自报 compiler metadata 漂移不能覆盖 compile/toolchain 权威事实。
        - [x] A19a7d2c：两个随机身份的有限 held-out 项目在 CIndex、migration graph、ContextPack、portfolio 和 ledger 之前连续重开同一 BuildIR 引用；首次验证失败或 worker-admission 时 source/hash 漂移均立即 blocked，后续 DAG、ledger、model 零调用。
        - [x] A19a7d2d：闭合仓库外 native library 输入边界。把严格识别的宿主绝对库参数净化为有序位置、可移植 basename/format 和原参数 SHA，投影为 `unresolved-native-library` 与 `native_link_config_unresolved`；宿主目录漂移不改变 BuildIR `semantic_sha256`。仓库外 object、未知路径和路径夹带的 `-l`/`DEFAULTLIB` 参数继续 fail closed；GeneratedClosure 从完整绑定输入重解析，BuildIR 复算依赖类型、id、边界、计数和 resolved 声明。该边界可进入 AI 规划，但 CompletionCoordinator 在解析证据出现前阻止 project semantic pass。
        - [ ] A19a7d2e：把 `unresolved-native-library` 交给身份中立的 AI/Cargo 重建流程，产出可复算的 Cargo dependency、`build.rs`/link directive 或 FFI 边界候选；宿主 verifier 必须按 target ABI、toolchain、portable library identity、实际解析结果和 Cargo raw evidence 独立判定，模型声明不能直接把 resolved 改为 true。至少两个具有不同 native dependency 形状的 held-out 项目完成真实 Cargo build/test 与 C oracle 对照后才能关闭，禁止按项目或库名称特判。
          - [x] A19a7d2e1：规划阶段从已验证 BuildIR 生成内容绑定的 `native-link-model-context`，按 portable name/format 聚合重复 dependency，只暴露 requirement 数量与集合 SHA，不暴露宿主绝对路径；无 native dependency 时不生成模型工作。模型响应必须逐 requirement 精确覆盖，只能选择 `rustc-link-lib`、FFI boundary 或 defer，始终保持 candidate-only、`resolved=false`、`cargo_executed=false`、`semantic_gate=false`。BuildIR 候选执行门只容许 `native_link_config_unresolved` 这一类 blocker；但 canonical RustProjectIR 目前仍固定保留 7 类非 native 接口未决项，CompletionCoordinator 不会越过该边界进入 Cargo，最终完成门禁未放宽。
          - [x] A19a7d2e2：RustProjectIR 升为 v2 并从绑定 BuildIR 复算 `native_link_requirements`，AI candidate 只能绑定为 `native_link_plans`；缺 plan、未实现策略、需求集合漂移或 host path 注入均在 Cargo 生成前 fail closed。已验证的 direct-link candidate 可确定性生成无 search path 的 `build.rs`，last-good manifest 保留 candidate/build-script SHA 且 `resolution_gate=false`。新增独立 host `native-link-resolution-receipt` schema/重算合同，逐 requirement 绑定 Cargo raw refs、toolchain、ABI、linker trace 和 actual artifact portable metadata；模型不能签发 receipt 或把状态提升为 resolved。
          - [ ] A19a7d2e3：闭合固定 native resolver/linker trace、独立验证、最终门禁与 held-out 语义证据。
            - [x] A19a7d2e3a：Cargo 沙箱计划固定完整环境、`--jobs 1`、受信 `cc`/`ld` 内容绑定和 linker-message trace；stdout/stderr 以原始字节 CAS 持久化，只有 trace JSON 层执行 strict UTF-8/重复 key/非标准常量检查。宿主按固定 guest-root 映射重开实际对象并防 TOCTOU，纯 Python ELF/ar parser 核验格式、machine、位宽、端序及 archive 成员；link order、target ABI、FFI import 与实际 export 的有界 AI-symbol context/evidence、以及项目级 settlement 均内容寻址并接入 `verify_project_cargo`。缺 symbol candidate、缺 raw/trace、对象漂移、顺序/ABI/符号不符均明确 blocked；所有 artifact 仍固定 `semantic_gate=false`、translation numerator 0。
            - [ ] A19a7d2e3b：闭合 native AI 候选、宿主接口晋升、候选项目验证与最终 CompletionCoordinator checkpoint；任何模型输出、Cargo 成功或字符串 issuer 都不能自行提升接口完整度、resolution 或 semantic 状态。
              - [x] A19a7d2e3b1：缺失 `native_link_plans` 现在生成身份中立、确定性的 project-level repair diagnostic，并复用现有隔离 OpenCode preflight/attempt/receipt worker；schema v3 prompt 只暴露按 portable identity 聚合的 model context，完整 BuildIR context 作为模型不可见的内容寻址引用单独绑定。模型只能返回一条覆盖全部 requirement 的 plan-set bind 操作；ingest 由宿主重开不可变 migration contract、完整 native context 与 BuildIR，复算 candidate 后才写入 RustProjectIR。缺项、重复、绝对路径、引用越界、context 漂移或普通 repair 注入 native section 均 fail closed；该路径不增加直连模型入口，仍固定 `resolved=false`、`semantic_gate=false`、numerator 0。
              - [ ] A19a7d2e3b2：实现不可伪造的 host interface transition 与最小状态机 `IR_PARTIAL -> CANDIDATE_PROJECT_VERIFIED -> IR_PROMOTED -> PROJECT_FINAL_VERIFIED -> COMPLETED`。逐 section closure receipt 必须深重开 DAG、全部 BuildIR、candidate/source CAS、固定 validator 版本和七类接口事实；candidate Cargo check/test/trace 只能运行在 quarantine generation，不得更新 final `CURRENT` 或 final project gate。canonical RustProjectIR v3 只允许宿主从完整 closure evidence 原子晋升；晋升后必须按新的 `verification_context_sha256` 与 `promotion_epoch` 重新生成并重跑 final integration/Cargo，禁止旧 Cargo evidence、ABA epoch 或 post-Cargo settlement 回写 IR 形成自引用。
                - [x] A19a7d2e3b2a：新增 project-final 候选域与隔离整项目验证底层 API。宿主在 Cargo 前深重开 RustProjectIR、完整 DAG 和全部 BuildIR，重算 run contract、project-final candidate-set 全集与 domain context；只在 detached immutable quarantine generation 运行一次整项目 `cargo check/test`，native dependency 存在时强制 raw output 与 linker trace。Cargo observation、raw CAS、native settlement 和 `verification_context_sha256` 写入独立 candidate-only receipt 并可深重开；该路径不更新 final `CURRENT`、不写 `project_gate_records`、不授予 semantic gate 或 coverage numerator。缺可信 native linker 时在任何 Cargo 启动前 fail closed。该 API 尚不授予 promotion，也不在 b2b/b2c 完成前接入 CompletionCoordinator。
                - [ ] A19a7d2e3b2b：实现七类真实宿主 section validator。每个 validator 必须从 deep-reopened C/BuildIR/DAG、candidate source 与编译器事实独立复算对应事实；任意 JSON、模型声明、固定 issuer 字符串或只有哈希一致均不得签发 closure。当前简单 Rust symbol regex、空 section 和 `unresolved-before-compiler` 不能用于关闭 public signature、type layout、global ownership 或 init/destroy。
                  - [x] A19a7d2e3b2b1：落地严格但非权威的接口事实生产器，并加深 candidate generation 重开。宿主可从 Cargo JSONL 复算 compiler-artifact 集合，从 `cargo metadata --no-deps` 复算保留 package/target 语义身份但剔除宿主路径的 workspace/feature/target 拓扑，从 Clang AST JSON 提取 source-bound 顶层 function/global/record/init 候选事实，并从 Clang record-layout 原始输出提取字段 offset/size/align；重复 key、非有限数、未知事件/target/crate type、隐式或无效声明、匿名/union/bitfield/flexible layout、输入洪泛、工具链/target 漂移均 fail closed。candidate receipt 重开时还会复核无 link/junction 的 generation 全树、last-good/quarantine manifest、generator、IR/interface/candidate-set 绑定；即使攻击者同步重写内外哈希也不能改变候选集。所有这些 artifact 固定 `semantic_gate=false`、numerator 0，不能签发 section closure。
                  - [ ] A19a7d2e3b2b2：把 b2b1 parser 接到固定宿主 runner、原始输出 CAS 和完整 deep-reopen domain，补齐 Rust post-cfg public signature/layout witness、cfg/feature target matrix、global owner/access、init/destroy 顺序图与 C/Rust 对照器，再由七个独立 validator 签发可重算 receipt。parser 单测、Cargo build-finished、正确哈希或空事实均不能关闭本项。
                    - [x] A19a7d2e3b2b2a：完成候选 Cargo 事实子链。宿主仅在 detached quarantine generation 内按固定 argv 运行 `cargo metadata --no-deps --format-version 1`，并复用固定 `cargo check --message-format=json`；metadata/check/test 的原始 stdout/stderr 全部进入分 gate CAS。candidate receipt 升级为 v2，绑定同一 generation、sandbox contract、toolchain、probe、execution plan、metadata topology 和 compiler-artifact 集合；深重开会读取原始字节、重跑两个严格 parser 并逐字段比较，旧 v1、命令漂移、跨 generation、stderr 或 derived CAS 漂移均 fail closed。本项仍固定 `interface_closure=false`、`semantic_gate=false`、numerator 0。
                    - [ ] A19a7d2e3b2b2b：为 Clang AST 与 record-layout 增加固定隔离 runner、原始输出 CAS，并建立会重开 run contract、父/子 DAG、全部 BuildIR 及原 C 仓库绑定、candidate/source CAS、base v2 IR、quarantine generation、b2a receipt 和固定 toolchain/target 的公共 D0 validation domain。
                    - [ ] A19a7d2e3b2b2c：实现 Rust post-cfg typed/layout witness、cfg/feature target matrix、module/target ownership、global access 与 init/destroy 图，再由七个独立 C/Rust comparator/validator 对非空覆盖域签发可重算 section receipt；普通空数组不能关闭任何 section。
                - [ ] A19a7d2e3b2c：实现 append-only transition ledger、单调 `promotion_epoch`、不可复用的进程内 transition permit 与 canonical RustProjectIR v3 原子晋升；每次晋升必须绑定 b2a receipt、七类 b2b receipt、base IR/domain bindings 和新的 `verification_context_sha256`，拒绝旧 evidence、跨 run/candidate set 复用和 ABA epoch。
                - [ ] A19a7d2e3b2d：将 CompletionCoordinator 改为只对 promoted v3 发布 final `CURRENT`；promoted IR 必须重新 materialize、执行 final integration/Cargo/semantic gates 和末次 BuildIR checkpoint，candidate Cargo 结果只能作晋升前证据，不能直接复用为 final pass。
                  - [x] A19a7d2e3b2d1：最终 generation publisher 已在任何 stage/CURRENT 写入前重开 IR 并拒绝 `interface_completeness != complete` 或仍有 unresolved section 的 v2 candidate；公开 `integrate-verified`、CompletionCoordinator 和其他调用方不能再把 partial v2 写入 final `CURRENT`。依赖旧行为的验证器测试夹具改用显式 test-only generation，生产门禁没有放宽。
                  - [ ] A19a7d2e3b2d2：完成 promoted v3 detached final generation、epoch/context-bound final gate、末次 BuildIR/Cargo/semantic 重跑与通过后 `CURRENT` CAS 发布。
              - [ ] A19a7d2e3b3：把实际 selected static-archive member/symbol、ABI、toolchain、link order/trace、actual artifact、独立 verifier process/capability 与全量 CAS 重开绑定到当前 promoted IR 和最终 BuildIR checkpoint；任一证据缺失、交换、过期或仅 mock 可达都必须阻断完成。
            - [ ] A19a7d2e3c：至少两个不同 native dependency 形状的身份中立 held-out 项目完成真实 Cargo build/test、对应 C build/oracle/replay-diff 与全部项目级 semantic gates；缺失、部分成功、模型自报或仅本机合同测试不得聚合为 resolved。

        A19a7d2e1/e2 有限阶段证据（2026-07-15）：Windows `test_project_migration*.py` 678 项通过、5 项平台条件跳过；WSL 同组 678 项通过、3 项平台条件跳过。新增测试覆盖同库多路径分组、无依赖零模型工作、response 缺项/重复/路径注入/伪造 resolved、BuildIR-to-RustProjectIR 漂移、candidate-only `build.rs`、未物化策略拒绝，以及 Cargo/toolchain/ABI/linker-trace/actual-artifact receipt 篡改。该阶段没有调用 provider/model，没有执行真实 held-out Cargo、linker trace 或 C oracle，`semantic_gate=false`、translation numerator 仍为 0，不能关闭 A19a7d2e。

        A19a7d2e3a 有限阶段证据（2026-07-15）：Windows 与 WSL 对同一 `test_project_migration*.py` 集合均运行 790 项且 0 failure，Windows 有 5 项、WSL 有 3 项平台条件跳过。新增 100 项 native 聚焦回归覆盖真实字节 CAS、trace 解析、actual object 重开、ELF/ar 边界、ABI、link order、symbol context/candidate/evidence、settlement 和篡改闭锁；CompletionCoordinator 与 native trace 已按职责拆分，新增/修改生产 Python 文件均不超过 300 行。该阶段没有调用 provider/model，没有完成真实 held-out Cargo/C oracle，也没有独立 verifier 进程；发现并删除了 canonical RustProjectIR 无法接受的不可达 `interface_candidate_ready` 分支，因此 A19a7d2e3/A19a7d2e 继续未勾选。

        A19a7d2e3b1 有限阶段证据（2026-07-15）：Windows 与 WSL 对同一 `test_project_migration*.py` 集合均运行 796 项且 0 failure，Windows 有 5 项、WSL 有 3 项平台条件跳过；6 项聚焦用例覆盖 model-safe prompt、完整 plan-set 绑定、BuildIR 重开、缺项拒绝、绝对路径/引用越界拒绝，以及一次经过隔离 OpenCode runtime、preflight、attempt ledger、provider receipt 和 host ingest 的 fake-provider 闭环。project repair 50 项回归全部通过，新增/修改生产 Python 文件均不超过 300 行。该证据没有真实调用 provider/model，没有执行 held-out Cargo/C oracle，也没有实现 host interface promotion 或独立 verifier，因此只勾选 A19a7d2e3b1，A19a7d2e3b/A19a7d2e3/A19a7d2e 继续未勾选，`semantic_gate=false`、numerator 0。

        A19a7d2e3b2a/b2d1 有限阶段证据（2026-07-15）：Windows `test_project_migration*.py` 813 项通过、5 项平台条件跳过；WSL 同组 813 项通过、3 项平台条件跳过。WSL Rust translator `--all-features` 为 267 + 688 + 4 项通过、133 项明确 ignored、0 failure。新增候选域、隔离 Cargo、candidate-only receipt 及篡改闭锁测试，并验证缺少可信 native linker 时不会启动 Cargo；生产 final publisher 在写 stage/CURRENT 前拒绝 partial v2，旧验证器夹具改为显式 test-only generation。新增/修改生产 Python 文件均不超过 300 行。该阶段没有真实调用 provider/model，没有完成 held-out Cargo/C oracle、七类接口 validator、RustProjectIR v3 晋升或独立 verifier，因此只勾选 b2a/b2d1；b2、b2b、b2c、b2d/b2d2、b3、e3 和 e 继续未勾选，`semantic_gate=false`、numerator 0。

        A19a7d2e3b2b1 有限阶段证据（2026-07-15）：Windows `test_project_migration*.py` 852 项通过、6 项平台条件跳过；WSL 同组 852 项通过、3 项平台条件跳过，0 failure/error。新增并由主线程复核的 Cargo compiler-artifact、Cargo metadata、Clang interface AST、Clang record-layout 事实解析与 candidate generation 深重开测试覆盖严格 JSON/UTF-8、边界洪泛、语义身份保留、宿主路径消除、隐式/无效声明、布局拒绝、工具链/target 外部绑定、manifest 自洽伪造和链接逃逸；所有新增/修改生产 Python 文件均不超过 300 行。该阶段没有调用 provider/model，没有把 parser 接入固定 compiler runner 或七类 closure receipt，也没有 Rust post-cfg signature/layout、真实 held-out Cargo/C oracle、v3 晋升或独立 verifier；因此只勾选 b2b1，b2b 及其余上层完成项继续未勾选，`semantic_gate=false`、numerator 0。

        A19a7d2e3b2b2a 有限阶段证据（2026-07-15）：Windows `test_project_migration*.py` 共 867 项，其中 861 项通过、6 项因 Linux live gate 或 Windows 符号链接权限而平台条件跳过；WSL 以 `C2R_RUN_LIVE_TOOLCHAIN_TESTS=1` 显式开启 live gate 后 867/867 全通过，0 skip/failure/error。固定 Cargo metadata runner、metadata/check/test raw CAS、metadata/compiler-artifact derived CAS、candidate receipt v2、同 generation/sandbox 绑定、旧 v1 拒绝及 raw/derived/stderr 深重开已接入候选整项目路径；编译失败时已执行命令的 stdout/stderr 会先进入 CAS 再阻断事实解析，CAS 写入/hash 绑定失败会把 `raw_output_bound` 复算为 false，native trace 阻断会在 ready facts 前保留诊断早退，raw CAS 已绑定后的 metadata/compiler 派生失败也会保留引用并精确阻断；receipt 会复算 execution status、`cargo_executed` 与 `semantic_gate`，通用 candidate compile verifier 仍维持原两门行为且不宣称 topology facts。新增/修改 Python 文件均不超过 300 行。该阶段没有调用 provider/model，没有接入 Clang runner、完整 D0、Rust typed/layout witness、七类 section receipt、真实 held-out Cargo/C oracle、v3 晋升或 final CURRENT 发布；因此只勾选 b2b2a，b2b2/b2b 及所有上层完成项继续未勾选，`interface_closure=false`、`semantic_gate=false`、numerator 0。

        A19a7d2d 有限 held-out 证据（2026-07-15）：固定 libevent 提交 `e1f0335d2f3af1235421c939c62943bb99b3d652` 的 WSL competition-profile 本地模拟 run `hard-libevent-native-06` 得到 ready GeneratedClosure、`ready_with_boundaries` BuildIR、5,906 个 unit、23,600 个 assignment 和 4 个 initial-ready worker；168 个 `libcrypto.so`/`libssl.so`/`libz.so` 依赖被净化为 unresolved native boundary。独立 project-final 重开后唯一 blocker 为 `native_link_config_unresolved`，不再出现 C toolchain evidence drift；耗时 778.33 秒、峰值 RSS 1,549,408 KiB，ContextPages/portfolio/portfolio-DAG 分别为 185,683,579/245,224,312/37,335,598 字节。该运行没有调用 model、Cargo 或 oracle，`semantic_gate=false`、numerator 0；单体 artifact 与逐 catalog NTFS 发布成本继续由 A19b4c2 收敛，不得把 plan 成功写成翻译成功。

        同阶段最终有限门禁：Windows `test_project_migration*.py` 660 项通过、5 项平台条件跳过；WSL 同组 660 项通过、3 项平台条件跳过；WSL Rust translator `--all-features` 为 267 + 688 + 4 项通过、133 项明确 ignored、0 failure；双语文档镜像与源码布局 5/5。ignored Rust case、held-out plan 和未执行的 model/Cargo/oracle 都不计入成功翻译。

        该完成项只证明受绑定构建事实的 canonical adapter convergence、漂移拒绝和 DAG 入场顺序；不证明命令已执行、build 成功、程序语义、独立 verifier 身份、真实 held-out 翻译成功或 `competition-exact`。真实 host toolchain 身份仍由 A19a7c2 证据链负责。
  - [ ] **A19a8：显式启用、强隔离的 Make dry-run 构建事实采集**。
    - [ ] A19a8a：仅在 compile database、可验证生成事实和只读 metadata 均无法闭合 BuildIR 时，才允许用户显式选择 `collect-make-facts`；禁止自动 fallback。采集前必须证明无网络、源码只读、独立输出根、子进程约束、环境白名单、超时、CPU/内存/文件/进程数与输出上限及退出清理均生效；能力不足时在执行 Make 前 fail closed。
      - [x] A19a8a1：当前入口只接受显式 path/SHA/size 绑定的预采集 Make 报告；不会从 compile database 或普通发现自动 fallback，双输入会在 discovery/CLI 前置校验中阻塞。
      - [ ] A19a8a2：实现 host-owned `collect-make-facts`，只在前序 adapter 无法闭合且 A19e8 能力探针全部通过时执行；当前预采集入口不能冒充生产采集器。
    - [ ] A19a8b：固定调用 `make -B -n -j1 --no-print-directory -f <makefile> -- <targets>`，不接受任意 command、flag、环境、shell、configure 或生成脚本。
      - [x] A19a8b1：固定 argv/目标合同、受限 stdout parser 与非语义报告 schema 已实现；报告只能从成功且清理完成的 typed runner outcome 构造，并绑定 execution plan 与 raw stdout/stderr。它会拒绝 recursive Make、shell control、command chain、libtool/configure、歧义 compile+link 和路径逃逸，固定 `semantic_gate=false`、numerator 0。
      - [ ] A19a8b2：在 A19e8 已证明能力的沙箱中实际执行固定命令，持久化并重开 raw stdout/stderr、toolchain、sandbox 和输入引用；覆盖 `$(shell ...)`、included Makefile 重建、超时、输出洪泛与退出清理。当前 parser/report 合同不能冒充 runner 已接通。
    - [x] A19a8c：只把可无损解析的直接 compiler、archiver、ranlib、link invocation 归一化为 BuildIR；报告绑定 Makefile/source/leaf input/toolchain/preflight/plan/raw output，未生成输出固定为 `materialized=false`。BuildIR 明确写入 header、生成物物化和外部依赖解析边界，只声明直接 command graph 完整；`required` 完整闭包策略会让 worker deferred，显式 `bounded-source` 才允许进入迁移 DAG。报告与 BuildIR 均固定为非语义证据、numerator 0。
    - [ ] A19a8d：用不含项目身份的等价 fixture 验证 Make dry-run 与 compile database/Ninja/CMake adapter 产生相同 canonical projection，并覆盖 shell/configure/递归 Make 拒绝、timeout/output flood、路径/link escape、输入漂移和 sandbox receipt 漂移。
      - [x] A19a8d1：无项目身份的 Make fixture 已覆盖仓库根重命名等价、固定 argv、shell/configure/递归 Make 拒绝、timeout/output flood/cleanup、报告及每类绑定输入/preflight 漂移，并验证 worker admission 会再次重开证据。
      - [ ] A19a8d2：补齐 Make 与 compile database/Ninja/CMake 对同一构建语义的跨 adapter canonical projection 等价测试，以及生产沙箱中的 included-Makefile/`$(shell ...)` 对抗用例。
        - [x] A19a8d2a：同源 CMake/Ninja lane 已达到完整 canonical BuildIR 等价；Make lane 已达到受限公共构建合同等价，并保留所有 adapter/evidence 差异和 define 漂移负例，固定 `semantic_gate=false`、numerator 0。
        - [ ] A19a8d2b：在 A19e8 生产 sandbox 中补 included-Makefile rebuilding、`$(shell ...)`、真实 timeout/output flood/cleanup，以及 Meson、archive/ranlib、多输入 link、external dependency 和 toolchain 等价/差异矩阵；未完成前不得把 bounded common contract 写成完整 canonical 等价。

  **A19b 项目级依赖图与有界分解**

  - [x] 建立内容绑定的函数/翻译单元节点、直接调用解析、SCC/wave DAG、共享全局状态 context group 和 parser-boundary 路由。
  - [x] 把仓库内 include closure、编译 defines、顶层声明、全局初始化和翻译单元覆盖记录放入去重 ContextPack；单页预算、组级总预算和页数分别受限。
  - [ ] 用 clang AST/type/layout/preprocessor 事实替换 lexical-only 缺口，覆盖宏展开、函数指针、复杂声明和 ABI 布局；无法证明的 span 必须进入明确 boundary/refusal。
  - [ ] **A19b3：canonical CIndex、内容寻址证据与精确 provenance**。
    - [x] A19b3a：区分原始 source/header blob SHA 与规范化 semantic fact SHA；header/include 只保存可重开的内容引用，多个 TU 共用同一 header 时存储增长接近线性于唯一内容而不是引用次数。
    - [x] A19b3b：每个 parser/preprocessor/include blocker 绑定 source path、source SHA、可用时的 directive SHA、offset/range 和可重开的 evidence-set 引用；摘要只能压缩展示，不能丢失同 offset 不同文件的来源，也不能让 dangling/tampered evidence 通过验证。
    - [ ] A19b3c：把当前等长空白投影的 top-level context 替换为 AST/preprocessor 驱动的声明 span、类型布局、宏定义/展开与初始化事实；无法确定边界时明确阻塞，不向 AI 伪造完整上下文。
    - [ ] A19b3d：增加同 offset 不同 header provenance、证据引用悬空/篡改、共享 header 线性增长、source drift 与 canonical hash 重算测试；所有下游只消费经统一 validator 重开的 CIndex projection。
  - [ ] **A19b4：确定性分层检索、选择回执与按前沿懒加载的 ContextPack**。
    - [ ] A19b4a：建立版本化 retrieval catalog/query/selection receipt；回执绑定 policy、query seed、当前 unit/SCC、required/selected/omitted fact refs、materialized page refs、预算与 SHA。排序必须确定，任一必需事实缺失、引用漂移、预算不足或 unresolved symbol 均阻塞 assignment。
      - [x] A19b4a1：宿主 catalog、确定性 symbol selection 和 selection/materialization receipt 已绑定 policy、query seed、SCC、required/selected/omitted 集合 SHA、字节预算与 materialized page-set SHA；引用、预算或 receipt 漂移 fail closed。
      - [ ] A19b4a2：把 unresolved symbol、AST type/layout/macro 与 verifier failure facts 纳入统一 query/required-fact 合同；缺失时进入可恢复 retrieval 阻塞，而不是只依赖 lexical identifier seed。
        - [x] A19b4a2a：`unresolved_external` call/global 会派生版本化 `host-required-symbol-facts-v1` 查询；回执绑定 SCC、来源事实、查询 SHA、匹配集合和未解析集合。只有当前 required/selected facts 中的结构化同名声明或受限 lexical declaration 能关闭请求，普通调用文本不能冒充声明；声明缺失、因预算未选中、回执漂移以及零 deferred-fact 绕过都会阻断 assignment，且不启动模型。
        - [ ] A19b4a2b：接入 A19b3c 的 AST declaration/type/layout/macro producer 和 verifier-owned failure fact，并把缺失状态从当前静态 `blocked` 提升为 A19b4c2 可恢复的 `pending_retrieval -> ready` 前沿转移；在此之前 A19b4a2 保持未勾选。
    - [ ] A19b4b：required 层固定包含当前源码、compile context、直接 call/global、blocker summary；exact 层按符号和类型匹配声明、宏、布局及 direct-include segment；expansion 层只按 include adjacency、dependency SCC interface 和已验证失败事实扩展，禁止把完整仓库或无关 header 塞回 prompt。
      - [x] A19b4b1：当前 source/direct-call/global/blocker facts 保持可见，deferred header/top-level chunk 按确定性精确 identifier、直接 include binding 与相邻 chunk 选取；未选择事实只以 host-withheld 摘要暴露给模型。
      - [ ] A19b4b2：改用 A19b3c 的 AST/type/layout/macro facts，并只沿 include adjacency、dependency SCC interface 与已验证 failure facts 扩展；补全 unresolved symbol 的 fail-closed 规则。
    - [ ] A19b4c：调度器只计算当前可运行 frontier，先检索并 materialize 当前 assignments 的最小页面；状态为 `pending_retrieval`、required facts 不完整或 receipt 未验证的 group 不得租约或启动 worker。完成一波后按新 DAG/验证事实再计算下一波，禁止启动前一次性展开全项目 ContextPack。
      - [x] A19b4c1：为每个 SCC 生成内容绑定且有大小上限的宿主 catalog；plan 阶段不再写 prompt 页面或 worker request，dispatch 只对最新 `schedule.ready` 重开 catalog/receipt/page-set，在租约前增量物化页面，并把不可变 frontier receipt 绑定到 request 与 attempt。同一 frontier 首次执行与恢复会产生相同的内容寻址回执；模型启动前再次重开回执，逐项核对 worker/assignment/catalog/retrieval/page 绑定。已有页面、group index、catalog、receipt 或部分落盘漂移时 fail closed；主路径不复制 omitted fact store。
      - [ ] A19b4c2：把 selection 计算本身也改为当前 frontier 的 `pending_retrieval -> ready` 状态转移，完成一波后从最新 DAG、失败证据和扩展查询重算下一波；移除计划期全项目 selection/CIndex JSON 单体和重复 portfolio context，保持分片 CAS 近线性增长。
        - [x] A19b4c2b：host-owned single-SCC refresh 已通过私有 permit、CAS 重开、runtime overlay 和 dispatch/request/prelaunch 复验闭合 `pending_retrieval -> ready`；漂移时零 attempt、零 provider。
        - [x] A19b4c2c：wave input、受限 selection directives、原子整波失效与可恢复逐 SCC refresh 已接入生产 CLI；失败证据、expansion query、query epoch、跨 SCC scope 和 caller authority 均 fail closed。父项仍因计划期单体 CIndex/重复 context 移除与近线性规模验收未完成而保持未勾选。
        - [x] A19b4c2d：持久化的根 `project-migration-plan.json` 改为 compact、hash-bound portfolio 摘要，不再复制完整 assignments/ledger units/context；dispatch 在同一文件句柄上流式复验 path/size/SHA，要求 canonical UTF-8 JSON，并核对 run/status/DAG/portfolio-plan 身份后再进入 immutable-ledger 复验。完整 portfolio 仍是单体，故该项不关闭 A19b4c2 父项。
        - [x] A19b4c2e：计划期按 SCC 重建 ContextPages，完成页面绑定后立即释放 page/catalog payload，只向 portfolio 传递宿主签发的 group closure。闭包绑定 group、context、catalog、canonical profile、页面顺序、logical/artifact SHA 和大小；所有 catalog 先写同盘临时 staging，全部组验证成功后才 write-once 发布，后续组失败不会留下可见的半成品或污染重试。主 JSON 写入、content hash 和 ledger portfolio 绑定统一使用流式 canonical metadata，CIndex、ContextPages 和 graph 也在最后一次使用后显式释放。完整 CIndex/ContextPages/portfolio artifact 和全项目 selection 仍为单体，故父项保持未勾选。
    - [ ] A19b4d：为 planner、translator、reviewer、repairer 定义不同的最小上下文合同；translator 必须获得完整 required facts，planner 只看项目级摘要和接口风险。若模型需要更多事实，只能提交结构化 retrieval query，由宿主选择、记账并返回新 receipt，模型不得直接读文件或自行声明事实。
    - [ ] A19b4e：对超过单次预算的超大函数实行层次化分解：先提取签名、控制流区域、局部类型/宏依赖和状态摘要，再按可验证 region 生成候选并在函数级重组；若跨 region 语义或 ABI 无法证明，必须整体 deferred/refused，禁止截断后假装完整翻译。
    - [ ] A19b4f：增加 exact macro/type 命中、确定性顺序、required-budget 阻塞、receipt 篡改、selected-only materialization、frontier lazy loading、角色隔离、显式 expansion 与超大函数拒绝测试；有限 held-out 项目必须证明 token/页面下降且 build/oracle 结论不退化。

  当前已有 header 去重、blocker 摘要、可恢复函数 span、callee signature、未解析外部符号 required-fact 回执、确定性 selection receipt、retrieval segment/seed-page 分离、dispatch 前沿物理物化、模型启动前回执复验，以及 verifier-failure/include-adjacency/dependency-interface 的前沿选择和可恢复 wave refresh；根计划对完整 portfolio 的重复嵌入、计划期 ContextPages payload 的全量常驻和 catalog 的双份常驻已经移除，但计划期仍一次性计算全项目 selection，CIndex/ContextPages/portfolio artifact 仍是单体，角色合同与超大函数分解也未闭合，因此 A19b3/A19b4 及 A19b4c2 父项保持未勾选。

  A19b4a2a 有限阶段证据（2026-07-14）：Windows `test_project_migration_*.py` 525 项通过、5 项平台条件跳过；WSL 同组 525 项通过、3 项平台条件跳过。该阶段未调用 provider/model，也未执行项目 semantic gate；它只证明 required-symbol 查询、回执重算和 assignment fail-closed，translator numerator 仍为 0。

  A19b4c1 有限阶段证据（2026-07-13）：Windows `test_project_migration*.py` 254 项通过、2 项平台条件跳过，WSL 同组 254 项全部通过。固定 mbedTLS 提交 `9e9eb069d6aa3db84bef07b6d83a78bdee9b1da6` 的 WSL 本地模拟在 `required` build-closure 策略下完成 plan：2,410 个 ledger unit、9,252 个 assignment、97 个结构化 blocked group 和 4 个 ready worker；计划期只写 2,410 个分片 catalog，prompt page/group/assignment request/attempt/model invocation 均为 0。该运行耗时 8 分 47 秒、峰值 RSS 约 1.15 GB，且 CIndex、ContextPages、portfolio 仍分别约 50.6 MB、181 MB、96.1 MB，因此它不是比赛等价语义验收，也不能关闭 A19b4c2 或增加翻译成功计数。

  A19b4c2b/c 有限阶段证据（2026-07-14）：Windows `test_project_migration*.py` 619 项通过、5 项平台条件跳过；WSL 同组 619 项通过、3 项平台条件跳过。frontier/CLI/security 聚焦回归 114/114 通过，Rust translator 全特性测试通过；judge entrypoint dry-run 为 4/4 planned。WSL competition smoke 仍受本机镜像版本偏差、既有 FlashDB oracle call-plan 证据缺口和 OpenCode agent 长度门禁阻断，因此只记为 `wsl-local-simulation`，不宣称 `competition-exact`、semantic pass 或 translator numerator 增量。

  A19a6b1/A19b4c2d held-out 阶段证据（2026-07-15）：固定 curl 提交 `6546ffeda4f1e81f68db6af721398148b5c74317` 在显式生成 4 个 Ninja producer 输出后完成 494 个 TU 的 WSL 规划，得到 4,476 个 ledger unit 和 17,700 个 assignment；根计划为 71,191 字节，完整 portfolio 为 194,295,931 字节。固定 mbedTLS 提交 `9e9eb069d6aa3db84bef07b6d83a78bdee9b1da6` 的 BuildIR 达到 580 个 target、383 个 TU、0 个 boundary 且 required build closure 完整；规划得到 11,637 个 ledger unit、44,808 个 assignment 和 4 个 initial-ready worker，耗时 47 分 24 秒、峰值 RSS 约 5.30 GiB。其根计划仅 5,087 字节，但 CIndex、ContextPages、portfolio 分别为 175,890,287、819,814,295、512,488,719 字节；最终 canonical 流式 dispatch 耗时 2 分 24 秒、峰值约 3.02 GiB，物化 26 个当前前沿页面并生成 4 个 launch descriptor，未调用 model/provider。该结果只证明本地 WSL 的 BuildIR/plan/dispatch 与 compact-root 重开，不是项目 Rust 重建、semantic gate 或 `competition-exact`，translator numerator 仍为 0；超大单体和内存峰值明确要求 A19b4c2 父项继续保持未勾选。

  同阶段有限门禁：Windows `test_project_migration*.py` 631 项通过、5 项平台条件跳过；WSL 同组 631 项通过、3 项平台条件跳过；双语文档镜像 4/4 通过；WSL Rust translator `--all-features` 命令成功且 0 failure。16 MiB canonical artifact 微基准把 loader 峰值从 50,337,122 字节降至 33,688,912 字节，但真实 dispatch 总峰值仍由 portfolio 对象和前沿物化主导。该门禁不把 ignored Rust case 或未运行的 semantic project gate 计为成功翻译。

  A19b4c2e 有限内存/等价性证据（2026-07-15）：32 组、每组 256 KiB 的合成计划把 `tracemalloc` 峰值从保留 payload 路径的 18,139,218 字节降至流式闭包路径的 2,087,339 字节，下降约 88.49%。固定 mbedTLS 提交的阶段重跑复用了既有 819,814,295 字节 ContextPages 和 33,160,149 字节 graph，重新生成 11,637 个 ledger unit 与 44,808 个 assignment，耗时 17 分 21 秒、峰值 RSS 4,584,668 KiB；旧的从仓库开始完整 plan 峰值为 5,555,644 KiB，差值 970,976 KiB（约 17.48%），但两次测量边界不同，不能把它当作严格的端到端对照。DAG 与旧基线逐字节一致；portfolio 的 44,814 个差异行全部由本次显式 `max_attempts=5` 相对旧基线的 `1` 及其派生 plan SHA 解释，规范化后 SHA/大小与 512,488,719 字节旧基线完全一致，其他差异为 0。该阶段没有调用 model/provider，没有执行 semantic gate，`translation_coverage_numerator=0`，并且不能关闭 A19b4c2 父项。

  A19b4c2e 最终有限门禁（2026-07-15）：文档镜像与新增流式写入、catalog 安全、closure 防伪、staging 失败恢复、ledger 流式绑定聚焦回归 21/21；Windows `test_project_migration*.py` 648 项通过、5 项平台条件跳过，WSL 同组 648 项通过、3 项平台条件跳过；WSL Rust translator `--all-features` 完成且 0 failure。既有 ignored Rust case、阶段内存重跑和未执行的项目 semantic gate 均不计作成功翻译。

  **A19c OpenCode 多 worker 候选组合**

  - [x] 生成 planner/translator/reviewer/repairer 角色组合、独立 config/data/state/cache/tmp/out-root、DAG 依赖和 SQLite assignments/leases/attempts/artifacts。
  - [x] 关闭 plan/preflight/request/attempt 漂移、租约重入、heartbeat、非原子 ingest、工具事件、secret 输入、父环境泄漏、agent 权限覆盖、spawn 前误记 command-started 和 provider evidence 未落 ledger；当前有限回归为 Windows 351 项（349 通过、2 项条件跳过），WSL 351/351。
  - [x] 在 WSL 通过固定项目 preflight 真实调用一次 `opencode/deepseek-v4-flash-free`：1 次 provider invocation，preflight report SHA `f0bc76b6b2489597e782cd1f0e532b7483f03658680b4352401ee12c814913c0`，session export `verified`，execution report SHA `9e04b437135aa9f1e2171a180f2e77272374fc8bba3c1257d314e8a963c10b5d`，candidate SHA `359cb2ef234f85d9aa1cbdf2d77e07a296f55cb8bd7d4ad9dd37afe4d9ea72ef`；状态仅为 `candidate-ready` / `auxiliary-local-validation`。GLM-5.1 仍只有真实比赛主机精确合同才能关闭 P0-H9。
  - [ ] **A19c4：最大化 AI 项目推理、候选多样性与信息增益**。
    - [ ] A19c4a：增加跨完整 BuildIR、Migration DAG、RustProjectIR 和历史失败事实工作的 global AI planner；它按依赖、接口风险、验证可用性和项目阻塞生成可重算迁移策略，并在新证据到达后局部重规划，禁止按项目名或固定测试身份选择路线。
    - [ ] A19c4b：同一高风险 unit 可在共享总预算内生成有明确策略标签的多样候选/接口提案，经 source SHA 去重后由相同 host gates 比较；reviewer/critic 只能提出结构化风险和修复假设，模型投票、自评分或多数意见不得产生 pass。
      - [x] A19c4b1：按初始生成及 compile/oracle/negative/unsafe/ABI/final failure family 选择固定、内容绑定的通用策略变体，并随既往 translator/repairer 尝试轮换；策略进入 request、prompt 和 candidate metadata，明确禁止模型自评分和语义验收。
      - [ ] A19c4b2：让同一高风险 unit 在一个共享 token/时间预算内保留多个并行或顺序候选，按 source SHA 去重并在同一 cohort 上运行完全相同的 host gates；选择结果必须由 gate evidence 决定并可恢复重放。
    - [ ] A19c4c：调度器按 failure fingerprint、未决不确定性、依赖关键路径、预期信息增益、token/时间成本和历史收敛率决定下一次 planner/translator/reviewer/repairer 调用；输入与失败不变、低信息重复或预算耗尽时停止，不机械运行所有角色或固定轮数。
      - [x] A19c4c1：增加只接受 `external-verifier` evidence 的确定性信息增益排序，并由绑定 DAG 重算关键路径；新失败、输入/策略变化、不确定性、token 估算和收敛次数参与优先级，失败/输入/策略均未变化的重复 repair 被停止，模型自评分或调用方自报关键路径不能改变 fallback 顺序。
      - [ ] A19c4c2：从 ledger、BuildIR/DAG 和 verifier receipt 自动派生上述 facts，增加跨 worker 的共享 token/时间预算、策略覆盖率和收敛窗口，并把预算耗尽写成可恢复 blocked/deferred evidence。
    - [ ] A19c4d：建立有界、内容寻址的项目知识记忆，只保存经 host 提取或验证的 API/type/ABI/ownership/build facts、失败分类和候选决策；按当前 unit/接口/repair 查询最小相关上下文，禁止把 oracle 答案、fixture expected/actual、密钥或无关完整仓库反复喂给模型。
      - [x] A19c4d1：实现严格 allowlist、内容 SHA、evidence SHA、主题相关性、entry/byte 上限和 artifact/request/prompt 绑定；oracle/expected/actual、密钥、原始源码正文和完整仓库字段在入模前 fail closed。
      - [ ] A19c4d2：由 BuildIR、RustProjectIR、TransitionAuthority 和专属 verifier 自动写入事实，按当前 unit/interface/repair 查询并持久化复用命中率；禁止调用方直接构造知识 pass 或绕过 provenance。
    - [ ] A19c4e：global planner 与 project-level repair queue 协同处理跨单元 API、共享类型、初始化、链接和 feature 冲突；AI 可以提出成组候选补丁和迁移顺序，但每次落地仍受文件/预算边界、quarantine、回滚和 project-final 全量复验约束。

  **A19d Rust 项目重建与增量集成**

  - [x] 按内容生成稳定 Cargo module tree、Cargo.lock、符号依赖和 unsafe budget，并以不可变 generation + 原子 `CURRENT` 指针保存 last-good，启动时可恢复中断投影。
  - [x] 集成报告改为绑定 ledger 权威 candidate set；host adapter 可重开不可变 generation，验证 accepted group/source SHA，再记录固定 authority 的 integration gate。
  - [ ] **A19d3：canonical RustProjectIR 与跨单元协调**。
    - [ ] A19d3a：定义内容绑定、可版本化和可重算的 RustProjectIR，统一表达 crate/module tree、public API、shared type、global ownership、初始化顺序、FFI/link boundary、`cfg`、feature、target 和 unsafe obligation；每个声明必须回指 BuildIR、Migration DAG 与候选源码证据。
      - [x] A19d3a1：RustProjectIR v1 已绑定并重开 canonical BuildIR、完整 Migration DAG 或其内容寻址依赖闭包、候选源码与逐声明 evidence；host 会从当前源码复算 public/required/unsafe/FFI facts，IR/source/metadata 任一漂移均阻断。wave IR 额外回指不可变完整 DAG，project-final IR 必须覆盖全部单元；固定 completeness 边界会把尚未提取的接口层声明为 partial，并阻止其进入 project-final gate 和 completed receipt，候选 generation 本身仍可发布供隔离检查。
      - [ ] A19d3a2：把完整 Rust signature、shared-type layout、global ownership、初始化/析构、link/target 与条件配置事实接入 host extractor 或受验证 AI interface proposal；当前自动派生的 public signature 明确保持 unresolved，不得冒充完整接口证明。
    - [ ] A19d3b：增加唯一 project interface coordinator，在单元候选合并前协调跨单元 API、共享类型布局、符号可见性、全局状态所有权、初始化/析构顺序和 FFI 边界；worker 不得各自生成互相冲突的公共 glue 或 Cargo feature。
      - [x] A19d3b1：固定 host coordinator 已检测虚拟/候选 crate root、未知 parent、parent/init cycle、orphan/unknown module reference，以及 API/type/global/FFI/feature/cfg/init duplicate/conflict；canonical receipt SHA 在任何 Cargo generation 前复算，冲突时零 generation。
      - [ ] A19d3b2：让 global planner 和每个 translator/interface proposal 在合并前消费同一 coordinator receipt，并把已解决接口决策作为不可变项目事实回投后续 ContextPack；模型意见本身仍不能授予 pass。
        - [x] A19d3b2a：现有 unit planner、translator 与 repairer 在事实物化时统一读取 ledger 最新不可变 coordinator receipt epoch，只接收与自身 group 相关的 diagnostics；context、request 与 prompt 对 epoch、receipt SHA、group 和内容 SHA fail closed。真正 global planner 与已解决接口事实回投仍留在父项。
    - [ ] A19d3c：把无法归属单个 unit 的类型、链接、初始化和 feature 诊断放入独立 project-level repair queue，基于完整 RustProjectIR 生成有界修复；不得随机归因、复制共享类型或通过 fixture-specific shim 绕过冲突。
      - [x] A19d3c1：coordinator 已生成有界、内容哈希的 project-only repair queue；每项绑定 IR SHA、interface SHA、diagnostic SHA、可解析的受影响 module/unit、unresolved module ID 与 attempt cap，并固定禁止随机 unit 归因、generated glue 和 fixture-specific shim。
      - [ ] A19d3c2：把 queue/event/attempt 持久化进 TransitionAuthority ledger，由 project repairer 只消费最小相关 IR/diagnostic 并产出新的 IR candidate；恢复、预算耗尽、回滚和重新协调必须形成可重放事件。
        - [x] A19d3c2a：项目 receipt、queue、item、attempt、CAS event 与 artifact 自 schema v5 起进入 ledger；专属 repair worker 只读取受影响 module/interface 记录，模型只能提交 allowlist patch，宿主重开完整绑定、重建 RustProjectIR、重新协调并决定 resolve/rollback/retry/exhausted。启动意图先于子进程写入 ledger，未启动恢复受 owner/租约约束，已启动但结果未知进入 `failed/manual-reconcile`；终态响应、IR candidate 和 rollback 证据绑定同一 attempt 的不可变 artifact，普通 worker 启动时也必须重验最新 coordinator epoch。request/preflight/fence、隔离运行根、失败恢复、command replay、证据不可变和 IR unit-domain/recomputation 防伪均有有限回归。
        - [ ] A19d3c2b：由唯一 CompletionCoordinator 从最新 receipt 自动调度、执行或恢复未完成项目队列，把无法定位到 unit 的真实 verifier 诊断统一送入该队列；本层只产出新的 RustProjectIR/receipt 并移交 A19e6，不拥有晋升或完成权限，低层 API 与模型结果也不能直接完成项目。
          - [x] A19d3c2b1：在 Cargo generation 前接入 host-owned 最新 receipt 调度内核；每次只选择 canonical queue 中第一个可执行项，权威 RustProjectIR 用通用内容寻址路径持久化并可在重启后重开。双 coordinator 并发时只有首次 CAS 应用者获得模型启动权；过期且未启动的 attempt 可确定性恢复后重派，已启动但结果未知必须人工对账，budget/exhausted 和孤立 candidate 均 fail closed。该内核只物化 request、从不启动模型或完成项目；未排空最新 queue 时 completion 被拒绝，重复 runtime 也不能二次启动同一 attempt。有限回归覆盖并发、latest-only、租约、预算和低层绕过。
          - [x] A19d3c2b2：schema v6 已增加稳定 diagnostic lineage/observation、跨 receipt attempt 继承以及每 run 64 次 provider call/65 个 receipt epoch 的硬上限。CompletionCoordinator 先做零 attempt 观察与隔离 preflight，再签发绑定精确 receipt/queue/status/version/model/agent/runtime 的 host permit；每次 resume 最多启动一次 provider。provider 结果先完整写入 ledger，摄取崩溃后只做零模型调用的 evidence reopen/ingest，终态重放不二次调用，证据不全或结果未知进入人工对账。公开 integration/低层 API 无 dispatch、晋升或 complete 权限；有限回归覆盖双执行器、旧 permit、跨 epoch 预算、preflight 阻断、provider-result 崩溃恢复与终态重放。
          - [ ] A19d3c2b3：把专属 host verifier 无法可靠映射到 unit 的 compile/link/init/feature/ABI 诊断规范化为 project diagnostic，并绑定当前 cohort、generation、raw observation 和 verifier receipt 后进入同一 queue；环境/沙箱故障不得伪装成 repair 诊断。
            - [x] A19d3c2b3a：schema v7 新增不可变、内容寻址的 project diagnostic intake，并与 host project gate 在同一事务落账。Cargo 路径冻结当前 candidate set，重开 managed generation 与 canonical RustProjectIR，只把结构化 rustc `error` 分区；唯一 unit 路径进入 unit repair，带项目内位置的 project `E####` 编译错误绑定 cohort、IR/interface、project input、raw observation 和 verifier receipt。warning、generic failure、超过 64 条 compiler error、环境/沙箱阻塞、旧或歧义 unit 路径均零 intake、零 AI 调用；artifact/ledger/source evidence 漂移会在重开时拒绝。有限门禁为 Windows 371 项通过路径（其中 2 项平台条件跳过）和 WSL 371/371；没有真实 provider 调用，也不是 `competition-exact`。
            - [x] A19d3c2b3b：已验证 intake 进入兼容 schema v7 数据库的 coordinator receipt v2，并与静态接口诊断共用 project repair queue；receipt 显式绑定规范化 intake 引用集合、集合 SHA 和 verifier diagnostic SHA，外部诊断优先调度。request 物化与 provider 启动前会重开 intake、当前 candidate set、原始 managed generation、RustProjectIR/interface 和 verifier receipt；代际漂移在零 provider call 下恢复。AI 候选对外只成为 `pending-reverification`，内部 `candidate-ready` 不代表 resolved，普通静态 receipt 和低层 resolve API 均不能关闭 verifier-origin item。只有同 gate 在新 managed generation 上产生更高 epoch 的 ledger-authoritative pass，且内容寻址 revalidation receipt 能重开 raw observation/evidence、当前 cohort、候选 IR/interface 和当前 generation 时，单一事务才会注册 successor、resolve 目标并取消被取代的同队列项；失败复验会回滚旧候选、登记 successor 并继承预算。CompletionCoordinator 会拒绝所有未 `resolved/cancelled` 的历史项目 repair 义务。有限门禁为 Windows 386 项（其中 2 项平台条件跳过）和 WSL 386/386；仅使用 mock provider，没有真实模型调用，也不是 `competition-exact`。
            - [ ] A19d3c2b3c：将 whole-cohort verifier 诊断先做全批次唯一归属，再按独立证据生产者接入 link/init/feature/ABI repair；任何未分类、混合或环境故障均应整批零准入。完成 b3b/b3c 前不得勾选 b3。
              - [x] A19d3c2b3c1：Cargo check/test 已改为两阶段 whole-cohort 准入：先冻结并分析 gate 顺序、执行状态、完整 candidate identity/content owner 和每条 error，再允许逐 gate 落账。unit owner 由 canonical RustProjectIR `modules.rust_path/unit_id/candidate_sha256` 与 candidate set 交叉构建，不再把固定文件名当作唯一事实；明确命中其他 module 实体的 unresolved symbol 进入 project diagnostic。规范化 event SHA 消除了同码同文件的诊断身份碰撞；toolchain-sensitive rustc、未知/generic、混合、重复 owner、stale 路径和 sandbox/environment blocker 均使整批 project/unit repair 零准入。project-derived candidate failure 在 verifier-record 与 retry 状态事务中分别重验原 candidate set，cohort 漂移不能改变新状态。有限门禁为 Windows 400 项（2 项平台条件跳过）和 WSL 400/400；没有 provider 调用，也不是 `competition-exact`。
              - [x] A19d3c2b3c2：闭合 Cargo 原始输出到 whole-cohort 分类回执的进程内证据链，并且只把能由当前 RustProjectIR 唯一绑定的 unresolved project symbol 规范化为 link diagnostic；缺失 linker/toolchain/native library、offline dependency、权限、资源和其他环境故障保持 blocker，零 intake、零 provider call。
                - [x] A19d3c2b3c2a：Cargo check/test 的有界 stdout/stderr 以私有内容寻址 artifact 落盘，绑定 gate、stream、SHA、size 和受限 repo-relative path，重开时拒绝 symlink、越界、大小或内容漂移。observation v3 绑定分类回执；旧 v1/v2 仅保持只读兼容。分类器从原始引用重新解析完整 diagnostics，并交叉绑定 run、candidate set、project input、RustProjectIR/interface、unit partition、whole-cohort admission 和 intake diagnostic SHA；原始文本不进入模型上下文，也不构成 semantic pass。该回执仍由当前 host 进程签发，不能替代 A19e7/A19e8b2 的独立 verifier process/capability 边界。
                - [x] A19d3c2b3c2b：共享 linker parser 只接受受限 rustc parent 与 GNU/lld/MSVC unresolved-symbol 形态；每个 symbol 必须由当前 RustProjectIR 的 public API、global owner、initialization function 或 export FFI link name 唯一映射到一个 module。unknown、ambiguous、FFI import、mixed batch、环境故障和诊断/符号溢出均整批零准入。阶段门禁为 Windows 425 项（2 项平台条件跳过）和 WSL 425/425；没有 provider/model 调用，也不是 `competition-exact`。
              - [ ] A19d3c2b3c3：为 initialization、feature/cfg 与 ABI 分别增加 host-owned 专属 verifier 和独立 process-issued raw output/receipt；补齐 stale cohort、raw-output/receipt 篡改、复验与零 provider-call 正反测试。在 A19e7/A19e8b2 的原始证据边界闭合前不得用 Cargo 文本猜测这些语义诊断。
          - [ ] A19d3c2b4：`candidate-ready` 只允许移交 A19e6 的新 `project-final` cohort/generation；只有整项目全门禁与 invariant audit 通过才能晋升/complete，任何 repair API、模型响应或旧 receipt 都没有该权限。
    - [ ] A19d3d：Cargo generation 只能从已验证 RustProjectIR 确定性生成，并复验所有迁移单元、依赖边、公共接口和配置均被覆盖；IR 漂移、孤立模块、重复符号、临时手写 glue 或真实多文件 build 失败时禁止晋升。
      - [x] A19d3d1：生产 generation API、`integrate-verified` 与 candidate quarantine 已移除 manifest+descriptor 写入口，只消费重开且无协调冲突的 RustProjectIR；direct `integrate` CLI 已删除。generation 内嵌 canonical IR，并绑定 domain/coordinator/interface SHA；integration verifier 会从原 artifact root 重建同一 generation 逐字节比较，旧 descriptor-only 生成器仅留在测试 support。
      - [ ] A19d3d2：从当前 flat library module 投影扩展到经验证的嵌套 module tree、多 crate/bin/example、完整 target/feature/cfg、初始化/析构和 native link 配置，并在真实多文件 Cargo build/test 与 project-final 全门禁通过后才关闭 A19d3。
        - [ ] **A19d3d2a：把目标 C 仓库 `tests/` 下的测试作为一等 test target 完整迁移，而不是仅因其出现在 `compile_commands.json` 就当作普通 library module 翻译。** host 必须从 BuildIR 及 CMake/CTest/Meson/Make 测试元数据中发现并内容绑定每个测试目标、C 测试源码、runner、fixture/data、工作目录、环境、参数、expected exit/signal 与 timeout；RustProjectIR 再确定性投影为 `#[test]`、`tests/*.rs` 或显式 Rust test binary，并保持目标依赖和执行语义。每个发现的 C test target 必须一一对应 Rust test target，或者产生带证据的 fail-closed refusal；验收必须同时运行原 C suite oracle 与 Rust suite，比较测试集合与逐项结果，并拒绝 `cargo test` 为 0 项、漏测、静默删除断言或只编译不执行。至少用两个 held-out C 项目证明不存在 `tests/` 路径、测试名称或项目身份硬编码。

  **A19e 项目级验证与精确 repair**

  - [x] 候选 Cargo 命令只允许进入 Linux bubblewrap 无网络沙箱；实际 `cargo/rustc/rustdoc` 由 `rustup which` 解析，toolchain 树受大小/数量约束、完整内容哈希、执行前复算并只读挂载。当前 WSL 缺 bubblewrap 时返回 `bubblewrap_unavailable` 且零候选执行，不把 `--offline` 冒充沙箱。
  - [x] 完成固定 host authority、内容寻址证据、最新 gate epoch、不可变 candidate set、Schema DDL 指纹和 current last-good 复算；CLI 已移除调用方 pass/verifier/candidate-set 权限参数。
  - [x] 接入 host-owned integration 与 Cargo check/test adapter，并把受限 Cargo JSON 模块诊断回投到对应 candidate compile gate 触发 repair；WSL 当前缺 `bwrap`，因此真实 smoke 零候选执行且不产生 pass。
  - [ ] **A19e4：正向 candidate verifier、quarantine 与完成路径**。
    - [x] **A19e4a：不可替换的 run contract 与 DAG cohort**。
      - [x] A19e4a1：在创建 ledger 前生成 integration manifest，并把其 path/SHA/size、完整 dependency edges 和 DAG SHA 固化到 run metadata/schema；CLI/worker 不再接受可替换 manifest。
      - [x] A19e4a2：只从当前 active roots、最新完成的 Rust candidate 与有效 last-good 依赖计算传递闭包，写入不可变 verification candidate set；成员缺失、candidate 非最新、依赖不闭合、无关成员或 cohort 漂移均 fail closed。
      - [x] A19e4a3：区分 `wave-provisional` 与 `project-final` cohort；完成前对全量 last-good 执行 final revalidation barrier，禁止早期 wave gate 冒充最终全项目 gate。
    - [x] A19e4b：用 verification candidate set 生成独立、不可变的 quarantine Cargo generation；它不得改写 `CURRENT`/last-good，且只能在已证明的无网络 OS 沙箱中执行 `cargo check/test`。
    - [x] **A19e4c：不可伪造的宿主 compile 结论**。
      - [x] A19e4c1：由固定宿主 adapter 从实际执行结果派生 candidate compile pass/fail；CLI/API 不接受调用方提供的 pass、verifier id、candidate-set id、manifest 或任意 command。
      - [x] A19e4c2：compile evidence 同时绑定并在 final/promotion 重开 candidate source、integration manifest、quarantine manifest/generation state、verification candidate-set、固定 Cargo command、toolchain 和 sandbox contract；任一漂移拒绝晋升。
    - [x] A19e4d：把可定位 Rust 模块的编译诊断回投给对应 repairer；沙箱/工具链/超时/资源等环境阻塞保持 blocked/deferred，不能写成候选语义失败。无法定位到单元的项目错误进入项目级 repair，不得随机归因。
    - [ ] A19e4e：为 C oracle/Rust replay/diff、negative、unsafe/alias、ABI 与 candidate final gate 接入专属 host-owned runner 和专属 raw observation schema；底层通用 ledger API 不允许写入调用方构造的 pass。promotion 前重新派生同一 verification context，任一 gate、源码、generation 或 cohort 过期均拒绝 last-good。
      - [x] A19e4e1：四类 candidate semantic runner 已具备固定计划、严格 raw schema、调用方 authority 拒绝和 stale-context 重开；未配置真实后端时 fail closed，不产生 pass。
      - [ ] A19e4e2：接入可实际执行的 oracle/replay/diff、negative、unsafe/alias 与 ABI 后端，并由 A19e7/A19e8 receipt 支撑 promotion 和 `project-final` 复验。
    - [ ] A19e4f：CLI 完成命令只编排固定 adapter，并在所有单元 last-good 后运行 integration、Cargo、项目 oracle/negative/unsafe-ABI 和 project final；任何 model JSON、测试构造 ledger 或仅 compile 通过都不能完成项目。
  - [ ] **A19e5：单一状态转移权威、声明式 FSM 与 invariant audit**。
    - [ ] A19e5a：用声明式 FSM 列出 unit/run 的状态、合法命令、前置条件、事件和后置状态；只有 `TransitionAuthority` 持有更新 `migration_units` 及其他 semantic projection 的数据库能力，lease、worker、verifier、repair、promotion、project gate 和 CLI 模块只能提交 typed command，禁止直接 `UPDATE` 或绕过转移表。
      - [x] A19e5a1：集中 `migration_units`/`project_runs` 状态投影到 `TransitionAuthority`，增加 typed unit/run command、幂等 command-id/evidence 绑定和静态扫描，拒绝其他生产模块直接更新这两个 projection。
      - [ ] A19e5a2：增加 command-kind/前置不变量、单调 state version 和数据库 capability 隔离；禁止任意合法边冒充完成命令，禁止删除/修改历史 transition，并把 candidate/project pass 等 semantic tables 一并收口到唯一权威。
        - [x] A19e5a2a：ledger schema v4 为 run/unit 增加不可变初始状态和单调 `state_version`；所有生产转移改用注册 command-kind/factory，由 kind 固定 edge、reason、attempt 与 last-good 权限，错误 kind 不能借合法状态边完成单元或项目。
        - [ ] A19e5a2b：隔离数据库写 capability，并把 candidate/project pass 等 semantic tables 收口到同一唯一权威，禁止低层模块持有可直接改写语义投影的连接能力。
    - [ ] A19e5b：每次合法转移先原子追加不可变事件，再以 expected state/version、幂等 command id 和绑定证据投影当前状态；并发、过期 epoch、重复回放、部分事务和 crash recovery 不得产生双 active attempt、倒退状态或幽灵 pass。
      - [x] A19e5b1：unit/run 转移在同一事务中先追加显式不可变事件，再用 expected state/version CAS 投影；trigger 拒绝事件 `UPDATE`/`DELETE`，每次转移和完成前从 initial state 重放并核对 current state/version/last-good；prelaunch cancel 只从不可变 start event 恢复原状态，保留 cancelled attempt/event 且不消耗重试预算。
      - [ ] A19e5b2：把 assignment、attempt、lease、candidate 与 project-gate 语义投影纳入同一可重算事件体系，并补齐并发、部分事务及 crash 点的系统 fault-injection 覆盖。
    - [ ] A19e5c：在 candidate promotion、`project-final` 和 completed 前运行同一 host-owned invariant audit，至少复算 DAG/BuildIR/RustProjectIR、active attempt 唯一性、latest gate epoch、candidate/generation/cohort 绑定、全单元 last-good、project-final 新鲜度和 project gate 完整性；任一未知或不一致均 fail closed。
    - [ ] A19e5d：用静态扫描、数据库能力测试、非法转移表测试和 fault-injection/replay 测试证明生产模块不能直接改 semantic 状态，且任意中断点恢复后的事件序列与 projection 可确定性重算。
  - [ ] **A19e6：唯一 CompletionCoordinator 与强制 project-final 完成链**。
    - [ ] A19e6a：只保留一个可改变整项目 semantic 生命周期的 `migrate/resume` 主入口，由 CompletionCoordinator 固定执行 discover/BuildIR、plan/DAG、dispatch/repair、promotion、RustProjectIR/Cargo generation、`project-final` revalidation、project gates 和 complete；其他入口不能跳步或自行选择 gate。
    - [ ] A19e6b：所有单元形成 last-good 后，Coordinator 必须生成新的完整 `project-final` cohort 和 quarantine generation，并在该同一 cohort 上重新执行 compile、oracle/replay/diff、negative、unsafe/alias、ABI、integration、Cargo 和 project final；`wave-provisional` 或旧 generation 的 pass 一律不得复用为完成证据。
    - [ ] A19e6c：低层 debug/admin CLI 只能读取证据、解释计划或在不连接权威 ledger 的临时副本中诊断；它们不得写 semantic tables、插入 pass、晋升 candidate、移动 `CURRENT` 或设置 completed，且 CLI/API 权限测试必须证明这一边界。
    - [ ] A19e6d：Coordinator 在每个阶段写入幂等 checkpoint 和 hash-bound completion receipt；中断恢复必须从 FSM/事件重新派生下一步，最终 receipt 绑定状态序列、project-final candidate set/generation、所有 verifier receipt、project gates 和 invariant-audit 结果。
    - [ ] A19e6e：增加单调 `completion_epoch` 与 `active -> finalizing -> completed`；进入 finalizing 后拒绝新 lease/attempt，只在同一 cohort/generation 的全部 gate 和 invariant audit 通过后两阶段发布 verified receipt 与 `CURRENT`，任一失败或崩溃均可幂等恢复且不得提前移动 last-good。
  - [ ] **A19e7：host verifier 进程级 capability 边界**。
    - [ ] A19e7a：把 semantic verifier 运行在独立、最小权限的宿主进程中，仅授予只读输入、专属沙箱执行和向 TransitionAuthority 提交 verifier receipt 的能力；AI worker、普通 CLI、测试 fixture 和编排进程均不持有产生 pass 或写 semantic projection 的能力。
    - [ ] A19e7b：pass 只能由 verifier 进程按固定 VerificationPlan 实际执行后派生，并绑定进程启动合同、输入快照、命令/toolchain、sandbox receipt、原始输出和退出状态；schema 合法、调用方 observation、model JSON、退出码零或可伪造 verifier id 单独均不能产生 pass。
      - [x] A19e7b1：已为 initialization、feature/cfg 与 ABI 三类独立 gate 建立严格的非权威 envelope/raw-receipt 基础，绑定 run capability、issuer/nonce、run/cohort/generation、RustProjectIR/interface、VerificationPlan、toolchain、sandbox、固定 argv、原始 stdout/stderr 与退出状态；原始证据内容寻址、大小受限且可重开，当前合同只能记录 `failed/blocked`，固定 `semantic_gate=false`、numerator 0。
      - [ ] A19e7b2：把该合同放入真正独立的 verifier 进程，由一次性 capability channel 签发执行结果并原子消费 nonce；只有真实执行才能派生 pass。当前 schema 绑定不构成身份认证，也不能提交 TransitionAuthority 或晋升任何 semantic 状态。
    - [ ] A19e7c：TransitionAuthority 只接受经当前 run capability channel 返回、可重算且未使用过的 verifier receipt，并重开其全部内容哈希和当前 cohort/context；缺失、重放、跨 run、进程异常、通道伪造、源码/计划漂移或未执行 observation 均记录 blocked/failure，不得提升 semantic 状态。
    - [ ] A19e7d：增加恶意调用方、伪造 schema/pass、替换 raw observation、receipt 重放、verifier kill/timeout 和并发竞争测试，证明只有真实 host runner 的当前执行结果能够通过状态转移权威。
  - [ ] **A19e8：不可降级的 SandboxBackend 能力接口**。
    - [ ] A19e8a：定义与实现无关的 SandboxBackend capability contract，至少要求网络隔离、仓库/候选只读输入、独立可写输出、进程/子进程约束、环境白名单、超时、CPU/内存/文件/进程数限制、工具链只读绑定和退出后清理；VerificationPlan 显式声明每项所需能力。
      - [x] A19e8a1：新增实现无关的严格 capability 集、环境白名单、资源上限与 canonical `VerificationPlan`；计划固定 purpose/argv/input/timeout/requirements SHA，shell/control syntax、超限输入或任一能力缺失均在执行前拒绝。
      - [ ] A19e8a2：为内存/CPU/进程树增加 cgroup v2 或比赛环境等价的聚合约束与实机证明；当前 rlimit 只证明进程继承上限，不能冒充整个进程树的聚合配额。
    - [ ] A19e8b：每个 bubblewrap 或等价后端必须在候选执行前运行 host-owned capability probe/conformance suite，并把 backend identity/version、实际隔离机制、mount/process/resource policy 和 probe hash 写入 sandbox receipt；命令行 flag、自报 capability 或 `--offline` 不构成隔离证明。
      - [x] A19e8b1：bubblewrap discovery 在返回 backend 前运行固定 host probe，实测 user/pid/mount/network namespace、零 capability、只读项目/工具链、隔离 HOME/tmp/runtime、环境白名单、rlimit 和退出清理，并把 backend version、contract/requirements/probe/raw-observation SHA 与逐能力结果写入 receipt。
      - [ ] A19e8b2：把 probe 原始文件、launcher/toolchain manifests 与执行 stdout/stderr 写成独立 verifier 进程签发的内容寻址引用；当前 in-process receipt 只能证明 canonical 绑定，不能替代 A19e7 capability channel 的不可伪造性。
    - [ ] A19e8c：所有等价后端必须满足同一最小保证和对抗测试，禁止因平台、权限、工具缺失或后端失败自动减少能力、改用普通 subprocess、开放网络/宿主写权限或放宽资源限制；缺少任一必需能力时在启动候选前 fail closed 为环境阻塞。
      - [x] A19e8c1：Linux 以外、`bwrap`/toolchain/probe 缺失或失败均返回固定环境 blocker，零候选执行且无 subprocess fallback；Windows 288 项通过（2 项条件跳过）、WSL 288/288，真实 WSL smoke 在缺 `bwrap` 时得到 `bubblewrap_unavailable` 与 `cargo_executed=false`。
      - [ ] A19e8c2：增加至少一个非 bubblewrap 等价 backend，并让所有实现通过同一不含 backend 身份特判的实机 conformance/对抗套件；在此之前不能声明跨平台等价沙箱。
    - [ ] A19e8d：compile、semantic runner、final/promotion 与 held-out 复验必须重开同一 sandbox receipt 并复算 backend/plan/toolchain/input 绑定；后端漂移、probe 过期、清理失败或保证不等价时拒绝 pass 和完成。
      - [x] A19e8d1：candidate compile 与 project Cargo raw observation 共用一个严格 reopener，复算 contract/probe/plan/command-start/input/cleanup；project final/completion 重新打开原始 observation，并要求 check/test 输入等于最新 integration managed-generation manifest SHA。旧四字段 Cargo observation、probe/plan/input/cleanup 漂移均不能授予 pass。
      - [ ] A19e8d2：让 oracle/negative/unsafe/ABI/final、promotion 与 held-out 全部消费 A19e7 独立进程签发的同一一次性 receipt，并重开 raw output 与 issuer/nonce；完成前仍不得勾选 A19e8 父项。

  **A19f 泛化防特判与有限 held-out 验收**

  - [x] 生产编排包与相关 agent 配置通过已知项目/函数/路径身份静态扫描，覆盖 raw text、常量拼接、bytes、SHA 前缀/全值、hex/base64 编码；图结构与 Cargo 输出已有重命名等价测试，并新增无项目身份的双翻译单元规划用例。
  - [x] 建立固定有限 held-out 合同工具：5–20 个不重复项目、至少 12 个 construct family、至少 2 个未参与规则开发项目，显式绑定 repo/commit/tree/compile DB，并拒绝身份分派和近重复项目。真实模式禁止 case 自报 translation evidence，只能按 plan 推导 ledger 路径后只读重开 SQLite，复验原仓库树、compile DB、source/generated closure、AI provider evidence、每个 candidate gate、不可变 candidate set 和 project final bundle；资源数量/大小有界，离线合同通过不能冒充翻译成功。
  - [ ] 在不超过 20 个有限 case 中覆盖至少 5 个真实项目、整项目构建和 12 个不同 construct family；至少 2 个项目不得参与对应规则开发。禁止 1,000/10,000 轮和重复近似切片放大成功率。

  P0-A10 的现有 12 项是函数/fragment 输入与 exact 路径非回归基线；A19f 是未知仓库的整项目 BuildIR、迁移 DAG、Cargo 重建和项目级语义验收。两者共享反特判规则，但任何一方通过都不能替另一方关闭。

  **下一执行顺序（按完成条件推进，不按测试用例身份推进）**：

  1. A19a7c-A19a8：先闭合 canonical BuildIR validator、真实 toolchain 绑定与显式沙箱 Make 采集；A19a6/A19a7d 可按 adapter 分线程推进，但任何下游不得消费 adapter 私有 shape，也不得把 dry-run 采集冒充语义证据。
  2. A19b3-A19b4：闭合可重开的 CIndex blocker/source CAS、声明/type/macro facts、确定性选择回执和 frontier 懒加载；required facts、预算或 receipt 未闭合的 assignment 不得启动 AI worker。
  3. A19e5a-A19e5d：建立 TransitionAuthority、声明式 FSM、事件投影和 invariant audit；并行定义 A19e7 verifier IPC/receipt 与 A19e8 SandboxBackend capability contract，但在单一状态写入权威闭合前不接入 pass。
  4. A19c4c 与 A19e8：以已闭合的 A19e4a-A19e4d candidate-set/quarantine/宿主 compile/repair 链为基线，在不可降级沙箱上用 verifier-owned failure、critical-path、cost 和 convergence facts 驱动信息增益调度；模型自评分不得进入优先级。SandboxBackend 可按 bubblewrap/等价实现分线程开发，所有实现共享同一 conformance suite。
  5. A19d3c2b3c3、A19e7、A19e8b2 与 A19d3d2：Cargo raw stdout/stderr、可重算 classification receipt 和受限 unresolved-link intake 已闭合；下一步接入 initialization、feature/cfg、ABI 的独立 process-issued verifier receipt，并扩展 RustProjectIR/Cargo 到真实多 target/feature/native-link 项目。不得从 Cargo 文本猜测这些语义 family，也不得绕过 RustProjectIR。
  6. A19d3c2b4、A19c4a-A19c4e、A19e4e、A19e6 与 A19e7：在 BuildIR/RustProjectIR 上接通 global AI planner、多策略候选、角色化最小检索、可审计 expansion、知识记忆和 project-level repair，同时接通进程隔离的 semantic verifier 与唯一 CompletionCoordinator，强制生成全量 `project-final` cohort/generation 并重跑全部 candidate/project gates；关闭所有可改变 semantic 状态的低层 debug CLI。
  7. 完成上述合同后再用固定有限清单执行 A19f 真实 held-out 整项目 build/oracle 验收，并按 A19g 做有限 Windows/WSL 门禁、提交、push 与远端 SHA 核对；开发阶段不在每个小改动后启动模型，也不运行 1,000/10,000 轮。

  **A19g 阶段交付规则（每个独立阶段重复执行）**：完成一个可复核阶段后，先运行一次有限 Windows/WSL 门禁与 `git diff --check`，确认没有凭据、宿主缓存、`target/` 运行产物或测试身份特判进入提交；随后创建范围单一的 commit、push 当前分支，并核对本地 `HEAD` 与远端分支 SHA 完全一致。未测试、未提交、未 push 或远端未核对的阶段不得在待办中标成完成。

  **A19h 代码精简与模块边界**

  - [ ] 删除 P0-A19 生产路径中经调用关系、静态扫描和有限回归证明不再使用的重复实现、过期兼容层与不可达入口；不得以“精简”为由删除 fail-closed 校验、证据绑定、拒绝路径或仍被 CLI/测试/发布入口引用的代码。
  - [x] P0-A19 `_project_migration_harness` 生产模块、`test_project_migration_*.py` 和共享 test-support 已按职责拆到每个文件不超过 300 行，并由 source-layout 门禁持续检查；后续触及该目录仍必须保持此约束。仓库其余 Python 大文件统一由 P0-C4 追踪，禁止通过压缩排版、重复薄包装或搬到未检查目录规避门禁。
  - [x] A19h1：删除 dispatch 专用的整文件 bytes 收集路径，统一复用流式 artifact verifier 与 canonical JSON metadata；Ninja link command 回归从 generated-closure 大测试文件拆到独立 36 行模块。本阶段触及的生产与测试文件均保持不超过 300 行，未引入项目身份 adapter。
  - [x] A19h2：从旧 `context_index_store.py` 拆出页面绑定、计划期 closure proof 和 catalog staging/publish 三个独立职责模块，删除不再调用的 materialization helper；artifact 写入、content hash 与 ledger portfolio 绑定共用流式 canonical metadata。所有本阶段触及的生产/测试 Python 文件均不超过 300 行，生产路径未加入项目、函数、目录或 fixture 身份分派。

  完成判据：同一入口可对 held-out 仓库从零生成 translation inventory、迁移 DAG、hash-bound ContextPacks、候选/repair 证据和可复现 Cargo 输出；至少一个此前未参与开发的多文件 C 项目通过项目级 build 与声明边界内 semantic gates。任何按身份分派、手写项目 adapter、未绑定模型输出或只通过函数级 demo 的结果都不能关闭本项，也不能增加 translator numerator。

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

### 3.4 P0-B：比赛主机与 OpenCode

- [ ] **P0-H9：真实 OpenCode + GLM-5.1 比赛合同复验**

  当前 WSL 已能解析 provider-qualified `zai/glm-5.1`，但完整 preflight/worker marker 尚未在真实比赛主机闭合。OpenCode + GLM-5.1 是新的比赛翻译默认通道；本地无法调用时必须明确标为 blocked/unavailable，不能用确定性结果冒充 AI 比赛路径。

  完成条件：真实主机设置 `COMPETITION_EXACT_HOST=1`，`opencode models` 精确列出 GLM-5.1；P0-A19 project preflight/worker 使用 `opencode` + `GLM-5.1` + `c2rust-candidate` + `max` 并形成完整 hash-bound probe/session/worker artifacts。保留的切片级 `opencode_agent_harness` 命令执行通道若进入发布包，则另行复验 `c2rust-migrator` + `max`；judge bundle 和 public packet 必须重新验证通过。

  WSL、本机和 CI 结果只能分别标为 `wsl-local-simulation`、`local-simulation` 和 `ci-approximation`，不能关闭 H9。

- [ ] **P0-H10：CRC32 competition-exact before/after 发布**

  依赖 P0-H9。仅在真实比赛主机复跑已闭合的 CRC32 C2Rust+repair before/after，并发布 hash-bound workflow metrics 后关闭。

### 3.5 P0-C：阶段收口

- [ ] **P0-C1：历史 evidence 漂移**。`20260711T-finite-p0-t31` 是不可变、commit-bound 的历史结果，不得原地改写其 hash-bound artifacts。按 artifact 所有权生成新的替代运行，复算 validator/ledger，明确把旧运行标成 superseded；以新运行 33/33 严格通过作为关闭条件，并与翻译层功能改动分开提交。
- [ ] **P0-C2：全功能 Clippy**。不要继续引用会随 HEAD 漂移的固定“剩余 8 个”计数；先为各实际 Cargo manifest 运行仓库支持的 `--all-features --all-targets` 命令，生成绑定 HEAD、toolchain、argv 和原始输出的清单，再逐类收敛。新切片不得增加告警；仓库根不存在 Cargo workspace 时禁止用虚假的根级 `cargo clippy --workspace` 作为证据。
- [x] **P0-C3：第一方 Rust 大文件拆分闭环**。`crates/c2r-translator`、`flashDB_rust` 和 `validation/l2_slices` 中所有 Git 跟踪的第一方 `.rs` 文件经格式化后均不超过 400 行；拆分只发生在完整 item/test 边界，单个超限报告函数已提取独立 helper，测试源码自检会递归覆盖拆分叶子。唯一豁免是 `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/` 下两份 733/704 行的 hash-bound C2Rust 历史证据快照，禁止为满足行数门禁改写证据内容。
- [ ] **P0-C4：第一方 Python 大文件按职责拆分**。
  - [x] P0-A19 新增的 `_project_migration_harness` 生产模块、`test_project_migration_*.py` 与共享测试支持文件均不超过 300 行；本轮已把 controller、gate-authority、sandbox 测试和 provider runtime/session/process/readiness 按职责拆开，并由源码布局测试持续约束。
  - [x] AI exact 入口已拆为 236 行兼容 facade 和 6 个不超过 189 行的职责模块，并由专属 source-layout 测试锁定公开导入与拆分边界。
  - [x] AI candidate provider 已拆为 61 行兼容 facade 和 command/generation/cache/manifest 职责模块；原 1,282 行 candidate harness 测试拆为 225 行主文件及多个不超过 291 行的测试/支持模块，25 个原测试保持唯一，新增 source-layout 门禁拒绝动态装载和再次超限。
  - [x] AI candidate cache 测试已按纯缓存、provider 生命周期和并发执行拆为最大 239 行的模块；过期 fixture 改为真实源码绑定的 external-callee context，没有放宽生产 readiness。9 个原缓存测试保持唯一，连同 2 个布局门禁共 11 项通过，完整 `test_ai_candidate*.py` 为 72/72。
  - [x] BuildIR adapter 边界新增 126/52 行通用 facade，AST import-graph 门禁拆为 279 行支持模块和 124 行测试；跨 adapter fixture 支持/测试为 282/298 行，顺序保留测试为 173 行，均保持在 300 行门禁内。拆分没有把私有 Make shape、动态 loader 或 test-only common contract 暴露给生产下游。
  - [ ] 对 `validation/tools` 其余活跃生产模块和测试建立 Git-tracked 行数清单并逐模块降到 300 行以内，优先 AI candidate/context/repair/provider 与有限套件调用链。拆分必须保持公开导入和测试发现兼容；hash-bound evidence、生成快照和 canonical 文档不因行数门禁改写。

  2026-07-14 本阶段有限门禁：AI candidate 72/72、host-verifier/provider 19/19、文档镜像 4/4；项目迁移套件在 Windows 为 450/450（2 项平台跳过），在 WSL 为 450/450（无跳过），`git diff --check` 通过，Git 跟踪文件的凭据片段扫描为 0 命中。这些结果只证明当前合同与回归在两个本地环境一致，不是比赛主机 exact 证明，也不关闭 A19f held-out 整项目 build/oracle 验收。

  2026-07-14 A19a7b2b 有限门禁：合并后聚焦回归 44/44；项目迁移套件在 Windows 为 462/462（2 项平台跳过），最终宿主无关边界门禁在 Windows/WSL 各 6/6，WSL 全量为 462/462（无跳过）。第一次 WSL 运行准确暴露 Windows-created worktree `.git` 路径不可移植，改为仓库源码目录枚举后复跑通过；该修复没有跳过门禁。以上仍是本地合同证据，不是模型调用、held-out build/oracle 或比赛主机 exact 证明。

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
| 全功能 Clippy | commit `81a772d1` 是历史清理点 | 当前 HEAD 尚缺 manifest/toolchain/argv/raw-output 绑定的新清单；P0-C2 保持未关闭，不沿用历史固定告警数 |

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
9. AI 输入以源码、编译上下文、类型/API 合同和失败分类为准；不得向 candidate 或 repair 暴露 fixture expected/actual、oracle 输出、首个 mismatch 或携带这些值的 replay source。validator 可以读取完整 hash-bound 证据，但不能把验证答案回灌给模型。

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
