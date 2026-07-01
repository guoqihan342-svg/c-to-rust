英文镜像见 `README.en.md`。

# 历史比赛环境 Profile Redirect

本目录是 README-only 历史 redirect。可执行的比赛环境配置、镜像配置和自检脚本已经统一归档到 `config/competition-env/`，本目录不再保存 `environment.json`、`env.sh`、`toolchain-check.sh`、`smoke.sh` 或包管理器配置副本。

当前默认入口：

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

规则：

- 新脚本和新 evidence 必须使用 `config/competition-env/environment.json` 并记录该文件的 profile id、路径和 SHA256。
- 旧 evidence 中出现的 `validation/environment-profiles/huawei-competition-ubuntu-24.04/` 只能作为历史路径引用，不能作为新的可执行配置来源。
- 修改比赛环境约束时，只更新 `config/competition-env/` 下的 canonical 文件，避免两个配置目录漂移。
