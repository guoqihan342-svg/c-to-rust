## Context

`scripts/run-full-regression.ps1 -RequireCleanEvidence` 已经能检查 unstaged tracked `validation/evidence/**` 内容漂移，但 Git 的普通 diff 不会报告未跟踪文件，也不会报告已经 staged 但尚未提交的 tracked evidence 变化。证据生成器如果新增了 evidence 文件而开发者忘记提交，当前 gate 会通过，后续验证环境就无法复现这部分证据。

该检查仍然不应默认开启。开发过程中生成新 evidence 是正常行为；严格 cleanliness 只适合提交前、CI、发布分支或“确认 committed evidence 可复现”的场景。

## Goals / Non-Goals

**Goals:**
- 显式启用 cleanliness gate 时，检查相对 `HEAD` 的 tracked evidence diff 和 untracked evidence 文件。
- 失败时输出具体未跟踪 evidence 路径。
- 保持默认 full regression 行为不变。
- 增加负向验证，证明未跟踪 evidence 会被捕获。

**Non-Goals:**
- 不检查整个 repo 的未跟踪文件，只限定 `validation/evidence/**`。
- 不检查 `target/full-regression/**` 动态报告。
- 不改变 evidence 生成器或 fixture 语义。
- 不引入新依赖。

## Decisions

1. 在现有 `evidence-cleanliness-check` 命令里使用 `git diff HEAD -- validation/evidence` 并追加 `git ls-files --others --exclude-standard -- validation/evidence`。
   Rationale: `git diff --exit-code -- validation/evidence` 只覆盖 unstaged tracked 内容；`HEAD` 基线能覆盖 staged/unstaged tracked drift，`git ls-files --others` 能精确列出未跟踪 evidence。
   Alternative considered: 使用 `git status --porcelain validation/evidence`。Rejected because it mixes tracked and untracked output formats, making diagnostics less direct.

2. 同一个 step 同时检查 tracked 和 untracked。
   Rationale: 两者都属于 committed evidence cleanliness；拆成两个 step 会增加每轮日志噪声，且修复路径相同：提交 evidence 或修正生成器。
   Alternative considered: 新增 `untracked-evidence-cleanliness-check` step。Rejected because the gate already represents one cleanliness contract.

3. 增加一个轻量 PowerShell 负向检查，而不是为此跑完整回归。
   Rationale: 完整回归已经在正向路径覆盖；负向路径只需证明命令能在未跟踪 evidence 存在时非零退出并打印路径。
   Alternative considered: 每次用 full regression 制造未跟踪 evidence。Rejected because it is slower and risks污染真实 evidence 目录。

## Risks / Trade-offs

- [Risk] 开发者开启 gate 后会因为尚未提交或已 staged 但未 commit 的新 evidence 失败。→ Mitigation: 文档继续强调该 gate 是显式提交后/CI gate，不是默认本地开发 gate。
- [Risk] 负向测试创建临时文件后清理失败。→ Mitigation: 测试使用固定临时子目录并在 `finally` 中删除。
- [Risk] `git ls-files` 输出被忽略规则影响。→ Mitigation: 使用 `--exclude-standard`，与项目实际 Git 忽略语义保持一致。

## Migration Plan

1. 更新 `evidence-cleanliness-check` 命令。
2. 增加一个脚本级负向验证，临时创建未跟踪 evidence 文件并确认命令失败。
3. 更新 `validation/gates.md`。
4. 跑 OpenSpec、负向验证、default smoke、cleanliness smoke 和 diff 检查。
