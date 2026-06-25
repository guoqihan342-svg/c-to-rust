## Context

`scripts/run-full-regression.ps1` 会在每轮重新生成 L2、libuv、FlashDB 等 evidence，并把动态 per-round 报告写入 `target/full-regression/<run-id>/`。现有 `git diff --check` 可以发现空白错误，但不会因为 tracked evidence 内容被生成器改脏而失败。

这个检查不能直接强制默认开启：本地开发时，开发者经常需要先改生成器或 fixture，再生成新的 committed evidence。默认强制 clean 会让开发中的合法更新无法跑完 full regression。因此本 change 把 cleanliness gate 设计为显式开关，适合提交后、CI 或“确认 evidence 可复现”的场景。

## Goals / Non-Goals

**Goals:**
- 增加一个可执行 evidence cleanliness gate。
- 在显式启用时，full regression 检查 tracked `validation/evidence/**` 没有未提交内容差异。
- 失败时输出可定位的 changed evidence 路径。
- 保持默认本地开发 full regression 语义不变。

**Non-Goals:**
- 不把整个工作区 clean 作为默认要求。
- 不检查 `target/full-regression/**` 动态报告，因为该目录是每轮输出目录。
- 不阻止开发者提交新的 evidence；只在显式 gate 下要求运行时 evidence 与已提交状态一致。
- 不引入新依赖或在线服务。

## Decisions

1. 使用 PowerShell 参数显式开启 cleanliness gate。

   Rationale: 该 gate 是“提交后可复现性”检查，不是开发中每轮都应强制的行为。显式参数可用于 CI、release branch 或人工确认。

   Alternative considered: 默认加入最后一步。Rejected because it fails during legitimate evidence refresh work before commit.

2. gate 使用 Git 对 `validation/evidence` 做路径限定检查。

   Rationale: 需要证明 committed evidence 没有被生成器改脏，而不是要求整个 repo 没有任何开发修改。OpenSpec change 文件、源码修改和目标目录不应该影响这个 gate。

   Alternative considered: 使用 `git status --porcelain` 检查全仓。Rejected because it conflates evidence drift with normal development edits.

3. gate 先输出 `git diff --name-only -- validation/evidence`，再用 `git diff --exit-code -- validation/evidence` 失败退出。

   Rationale: 失败日志需要能直接定位漂移文件；`--exit-code` 提供机器可判定状态。

## Risks / Trade-offs

- [Risk] 开发者误开 gate 后，因为正在生成新 evidence 而失败。→ Mitigation: 参数名和文档明确它用于 committed evidence cleanliness。
- [Risk] 只检查 tracked evidence 内容，不覆盖未跟踪新 evidence。→ Mitigation: 后续可加 `git ls-files --others --exclude-standard validation/evidence`，本 change 先覆盖 generator drift 的主风险。
- [Risk] Git 路径语义在 PowerShell 下容易受 shell expansion 影响。→ Mitigation: 使用参数数组调用 `git`，避免字符串拼接。

## Migration Plan

1. 为 full regression 增加显式参数。
2. 添加一个小 gate step，只有参数开启时加入 round steps。
3. 更新 `validation/gates.md`，说明该 gate 的适用场景和边界。
4. 跑 targeted PowerShell/full regression smoke 验证默认路径不受影响，并用显式参数跑一次 committed evidence cleanliness。
