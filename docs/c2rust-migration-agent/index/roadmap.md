英文镜像见 `roadmap.en.md`。

﻿# 覆盖与路线

- [COVERAGE.md](../COVERAGE.md)
- [COVERAGE.en.md](../COVERAGE.en.md)
- [future-vision-and-mvp.md](../future-vision-and-mvp.md)
- [future-vision-and-mvp.en.md](../future-vision-and-mvp.en.md)

## 评委 Demo / Milestone

当前公开 before/after 演示入口是 `../judge-demo.md`。一键运行：

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

核心 artifact：

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`

边界：该 demo 绑定 accepted-evidence before/after artifact 和 unsafe 3→0，但不增加 `translation_coverage_numerator`。
