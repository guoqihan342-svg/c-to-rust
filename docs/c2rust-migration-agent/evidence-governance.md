# Evidence Governance

本文件说明 evidence 可移植性、成本和保留策略的当前工具入口。英文镜像见 `evidence-governance.en.md`。

## 目标

`validation/tools/evidence_governance.py` 是非破坏性报告工具，用来回答两个问题：

- 新 milestone evidence 是否把本机绝对路径、旧 WSL/Windows 工作目录或临时目录当成跨机器 claim anchor。
- evidence 目录目前有多少文件、占用多少字节、包含哪些 runtime 记录，以及哪些 artifact 属于 release、CI smoke、diagnostic-only 或 historical archive。

报告会抓出问题，但不会删除、压缩或改写历史 evidence。历史问题可以保留为 audit 记录；新的 milestone evidence 必须优先使用 repo-relative path、profile id/hash 和 artifact hash。

## 命令

```bash
python validation/tools/evidence_governance.py
```

可指定输出文件：

```bash
python validation/tools/evidence_governance.py --output validation/evidence-governance-report.json
```

单元测试：

```bash
python -B -m unittest validation.tools.test_evidence_governance
```

## Portability 规则

硬问题：

- `evidence`、`source_artifacts`、`artifact_refs`、`generated_artifacts`、`dependent_artifacts`、`accepted_paths` 或 `paths` 等 claim-anchor 区域出现 `C:\...`、`F:\...`、`/mnt/c/...`、`/tmp/...` 等绝对/临时路径。
- `translator.artifact_paths` 或 `source_boundary.files` 出现本机绝对路径。
- `competition_environment` / `competition_environment_identity` 缺少 `sha256`。

诊断元数据：

- `clang_path`
- `metadata.source_root`
- `lowering_report.arguments`
- `source_file`
- skipped C2Rust baseline 的 `reference_tree`
- stdout/stderr/log excerpts

这些字段可以记录宿主机事实，但不能作为 release claim 的可复现入口。

## Retention 分类

- `committed_release`：外部 milestone 或 named-slice claim 需要的 evidence，必须保留 artifact hash。
- `ci_smoke`：可重跑的短生命周期 CI smoke evidence。
- `diagnostic_only`：调试日志、stdout/stderr、host-local 诊断信息，不作为语义 claim anchor。
- `historical_archive`：旧 L1/L2 catalogue、旧实验记录和广义审计材料，仅用于历史追溯。

## 当前边界

当前工具是 report/validator 基础层，不是清理器。它会把历史 absolute path 暴露出来，但不会强制全仓库立即通过 portability gate。要把它提升为 release gate，必须先完成历史 evidence 分类、保留策略确认和 milestone evidence 刷新。
