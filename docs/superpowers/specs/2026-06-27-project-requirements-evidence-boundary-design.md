英文镜像见 `2026-06-27-project-requirements-evidence-boundary-design.en.md`。

# 项目要求与证据边界对齐设计

本文是设计文档，不是实现计划。下一步实现前，需要再把本设计拆成可执行 implementation plan。

## 背景

当前项目的核心定位是面向 Agent 的 C-to-Rust 渐进迁移管线：翻译器只生成候选代码，正确性必须由原始 C 行为和验证证据决定。近期评审指出的主要风险不是“验证体系完全不存在”，而是项目要求、比赛环境、候选代码、语义通过证据和 OpenSpec 残留之间的边界还不够清楚，容易让读者把窄子集能力理解成真实项目自动迁移能力。

本设计先修正要求和证据口径，不直接扩展翻译器。这样后续做 L0/L1/L2/L3/L4 路由、typed IR、clang 降级或 C2Rust baseline 时，都有统一的项目边界和 claim 规则。

## 目标

1. 固化项目真实要求：Agent-facing、fail-closed、以 C oracle 为准、翻译候选与正确性验证分离。
2. 固化比赛环境入口：`config/competition-env/environment.json` 是默认比赛环境配置，验证证据必须记录 profile id/hash。
3. 修正文档和 OpenSpec 的陈旧上下文，尤其是仍然残留的 DWCCA、archive TBD、模板化 Purpose。
4. 明确 evidence 边界：draft/candidate 不能声明 semantic pass；semantic pass 只能来自已接受的 named-slice 或等价强度证据。
5. 为后续实现留出清晰入口：先做文档和 gate 口径修复，再按 P0 扩翻译覆盖，不新增无验证价值的仪式化 schema。

## 非目标

- 不在本轮修改核心 translator 行为。
- 不在本轮安装或强依赖 clang。
- 不在本轮重新生成全部 validation evidence。
- 不在本轮发布 milestone tag。
- 不在本轮承诺 FlashDB 或任意真实 C 项目已完整自动翻译。

## 设计原则

### 1. 要求来源必须可追踪

项目要求应优先来自这些稳定入口：

- `README.md`：项目定位、fail-closed 原则、L0-L4 路由概念。
- `docs/c2rust-migration-agent/future-vision-and-mvp.md`：MVP 范围、P0/P1/P2 待办、真实 C 覆盖声明边界。
- `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md`：route 与 validation gate 的关系。
- `validation/gates.md`：验证等级、claim language、unsafe ledger、negative diff、semantic evidence 规则。
- `validation/tools/validate_auto_translation_evidence.py`：auto-translation evidence 的机器校验实现。
- `config/competition-env/environment.json` 和 `config/competition-env/README.md`：比赛环境和工具链约束。
- `CONTEXT.md`：当前继续开发的本地交接状态，但它不是长期项目要求的唯一来源。

实现时应避免把历史聊天、旧 evidence 摘要或 archive 后的模板 spec 当成当前要求。

### 2. OpenSpec 上下文先修干净

`openspec/project.md` 若仍描述 DWCCA 或其它旧项目，会误导后续 proposal/spec/tasks。应把它改成当前 C-to-Rust migration agent 的项目上下文，包括：

- 项目目标和非目标。
- 技术栈：Rust workspace、Python validation、clang AST dump JSON、比赛环境配置。
- 证据原则：candidate 不是 correctness source，C oracle 是 ground truth，fail-closed 优先。
- 工作流约束：所有 claim 必须绑定验证等级和证据路径。

`openspec/specs` 下如果存在 archive 自动生成的 `TBD - created by archiving...`、空 Purpose 或明显不再适用的模板内容，应列入清理清单。清理方式不是盲删，而是逐个判断：

- 仍对应当前能力的 spec：补全 Purpose 和 Requirements。
- 已被新文档替代的 spec：标记为历史归档，不作为当前需求入口。
- 完全错误的 spec：后续通过单独变更删除。

已知需要优先检查的残留包括 `bounded-auto-translation-pipeline` 和 `pointer-arithmetic-output-write-l3-demo-slice` 的 archive Purpose 占位。`flashdb-l3-agent-migration-loop` 中的 `stale` 更像场景名，不能仅凭词面当作错误残留。

### 3. Evidence 边界必须 fail-closed

文档和验证输出应统一以下口径：

- auto draft、LLM candidate、C2Rust candidate、typed IR candidate 都只是 candidate。
- candidate/draft ledger 只记录 provenance、diagnostic 和 replay scaffold；accepted/named-slice evidence ledger 才能承载 semantic claim。
- `generated_draft_semantic_pass` 必须默认为 false，除非它明确引用已接受的语义证据；一般情况下不应由 draft 自己给出 true。
- candidate/draft 证据中出现 `semantic_pass=true` 应视为非法或误导；若后续某个 artifact 需要承载语义结论，必须由 accepted/named-slice evidence bundle 独立绑定该 exact artifact 并通过 required gates。
- `semantic_pass=true` 必须绑定 named-slice 或更强验证证据，且证据中需要能追溯到原始 C oracle、Rust candidate、测试/差分输入、环境 profile、pinned source commit 和 manifest-ref hash/status。
- 自动翻译 run 应保证同一个 slice spec hash 贯穿 context pack、type map、CFG、pointer graph、Rust draft、C oracle、Rust replay、cache metadata 和最终 L3 evidence。
- final verification 可以汇总 accepted evidence，但 `final_verification.semantic_pass=true` 只表示 accepted/named-slice evidence bundle 通过；它不能被解读成 `generated_draft_semantic_pass=true`。
- 如果证据只证明 C 项目 native build 通过，只能声明 L1 native baseline，不能声明翻译成功。

这部分应优先通过文档、validator 错误信息和 evidence 字段说明修复。若后续发现 validator 已经能拦住错误，但报告文字容易误导，则先改报告文字，不重复造新门禁。

### 4. 比赛环境只作为适配约束，不污染核心设计

`config/competition-env/environment.json` 是当前默认比赛环境入口。实现和验证需要以它为默认 profile，但核心 translator 不应硬编码某台机器的路径。

后续实现计划应覆盖：

- 读取默认 profile 的路径和 fallback 规则。
- 在 evidence 中记录 profile id/hash。
- 明确缺失工具的策略，例如 Go 和 CMake 缺失时不能把依赖它们的 gate 设为默认必跑。
- clang/LLVM 若不是环境内置能力，应作为可检测的 optional capability，而不是静默假设。

### 5. 后续路线仍以翻译能力为中心

文档修复不是目的。它服务于后续 P0/P1/P2：

- P0：消除明显陈旧上下文和 claim 混淆；保证比赛环境入口、evidence 边界、OpenSpec 项目说明一致。
- P1：扩展 typed IR 和 generic emitter 的真实语法覆盖，减少 brittle 特例和 string path 依赖。
- P2：完善 C2Rust/LLM fallback 的候选生成、repair 和验证编排。

新的 schema、manifest、dashboard 只有在能降低 claim 歧义或提高验证可追踪性时才加入。

## 可选方案

### 方案 A：先做要求与证据边界对齐

这是本设计采用的方案。它先修 OpenSpec 项目上下文、future vision 待办、competition env 引用和 evidence claim language。优点是风险低、能立刻减少误读，并且不会和后续 translator 改动冲突。缺点是不会直接提高翻译覆盖率。

### 方案 B：先改 validator

直接加强 `validate_auto_translation_evidence.py` 和相关 gate，强制拦截所有 draft/semantic 混淆。优点是机器约束更强；缺点是如果项目要求本身仍旧，报错会更硬但不一定更清楚。

### 方案 C：先扩 typed IR/emitter

直接进入核心翻译能力扩展。优点是对比赛展示更有产出；缺点是当前 claim 和环境边界还不清楚，新增能力容易再次被文档或 evidence 夸大。

## 采用方案

采用方案 A。理由是当前最危险的问题是“读者如何理解项目已完成什么”，不是单个语法点能不能继续扩。先把项目要求、比赛环境、evidence 和 OpenSpec 统一，后续每个实现 commit 才能明确声明自己提升的是 L0、L1、L2、L3 还是只是 candidate coverage。

## 验收标准

实施本设计后，至少满足：

- `openspec/project.md` 不再出现 DWCCA 或其它旧项目定位。
- `config/competition-env/environment.json` 被明确标为默认比赛环境入口。
- `future-vision-and-mvp.md` 继续保留 P0/P1/P2 待办，并把“真实 C 项目覆盖”与“curated function slice”区分清楚。
- evidence 文档明确说明 draft/candidate 不是 correctness source。
- final verification 相关文字明确说明绑定 `accepted_evidence_binding` 且保持 `generated_draft_semantic_pass=false` 这一边界，不会把 draft 误读成 semantic pass。
- stale OpenSpec spec 被列出并给出处理策略，不能继续作为当前需求入口。
- 本轮只改文档和必要的 validator/report 文字，不改 translator 行为，除非后续 implementation plan 明确包含并获得确认。

## 建议验证命令

```powershell
git diff --check
rg -n "DWCCA|TBD - created by archiving|generated_draft_semantic_pass|semantic_pass" openspec docs validation
openspec validate --all --strict
cargo test -p c2r-translator --tests
```

其中 `openspec validate --all --strict` 和 `cargo test` 作为实现阶段验证命令；设计文档阶段只要求文档本身无占位、无自相矛盾、范围足够明确。

## 下一步问题

用户确认本设计文档后，下一步进入 implementation plan。计划应优先拆成这些任务：

1. 修 `openspec/project.md` 的项目上下文。
2. 扫描并列出 stale OpenSpec specs，先修仍然有效的 Purpose，历史项标注为非当前需求入口。
3. 对齐 `future-vision-and-mvp.md`、routing docs、validation gates 中的 evidence claim language。
4. 只在必要时补 validator/report 文案，不新增 translator 行为。
5. 运行文档和 OpenSpec 验证，提交一版边界修复。
