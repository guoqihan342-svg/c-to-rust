## Why

`-RequireCleanEvidence` 当前只检查 tracked `validation/evidence/**` diff，不能发现证据生成器新产出但尚未纳入 Git 的 evidence 文件。这样会让“提交后的 evidence 可复现”仍留下盲区：回归通过，但新证据没有进入提交。

## What Changes

- 扩展 evidence cleanliness gate：显式开启时同时检查相对 `HEAD` 的 tracked evidence diff 和 untracked evidence 文件。
- 失败日志必须列出未跟踪的 evidence 路径，方便判断是需要提交新 evidence，还是修正生成器输出位置。
- 默认本地回归行为保持不变；只有传入 `-RequireCleanEvidence` 时才启用该严格检查。
- 增加一个可自动执行的负向验证，证明未跟踪 evidence 文件会导致 gate 失败。

## Capabilities

### New Capabilities
- `untracked-evidence-cleanliness-gate`: 约束 full regression 在显式开启 committed evidence cleanliness 时，不允许 `validation/evidence/**` 下存在未跟踪 evidence 文件，并把 staged tracked evidence 变化视为尚未提交的 drift。

### Modified Capabilities
- None.

## Impact

- Affected script: `scripts/run-full-regression.ps1`.
- Affected validation/docs: `validation/gates.md`, OpenSpec delta specs under this change.
- Dependencies: no new third-party dependency; the check uses Git commands already required by the project.
