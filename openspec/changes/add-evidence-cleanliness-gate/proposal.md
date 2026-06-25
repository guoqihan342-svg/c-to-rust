## Why

当前 full regression 会重新生成多类 committed evidence，但最后的 `git diff --check` 只检查空白错误，不能证明 evidence 生成器没有让已提交证据漂移。这个缺口会让“每轮 evidence 可复现”退化成人工审查，尤其是在 CI 或提交后回归中不够硬。

## What Changes

- 增加一个显式 evidence cleanliness gate，用于检查 `validation/evidence/**` 在生成器运行后没有未提交差异。
- 默认本地开发回归不强制该 gate，避免正在开发中的合法 evidence 更新被误杀。
- 增加 full regression 参数，使 CI 或提交后验证可以打开 cleanliness gate。
- gate 失败时输出具体 diff 路径，便于判断是需要提交 evidence、修生成器确定性，还是更新 fixture。

## Capabilities

### New Capabilities
- `evidence-cleanliness-gate`: 约束 full regression 在显式开启时验证 committed evidence 生成后仍保持工作区干净。

### Modified Capabilities
- None.

## Impact

- Affected script: `scripts/run-full-regression.ps1`.
- Affected validation/docs: `validation/gates.md`, OpenSpec delta specs under this change.
- Dependencies: no new third-party dependency; gate uses Git already required by the project.
