英文镜像见 `README.en.md`。

# 华为比赛环境 Profile

本目录是历史 validation 兼容入口。新的默认比赛环境配置入口是 `config/competition-env/`；旧 evidence 或脚本如果已经引用本目录，可以继续读取这里的同名配置文件。

## 环境基线

- OS：Ubuntu 24.04.4 LTS (Noble Numbat)
- Kernel：`5.10.0-182.0.0.95.r194_123.hce2.x86_64`
- APT 镜像源：`http://mirrors.tools.huawei.com/ubuntu`
- Python：`3.12.3`
- pip：`24.0`
- PyPI 镜像源：`https://mirrors.tools.huawei.com/pypi/simple`
- Node.js：`v24.13.0`
- npm：`11.6.2`
- npm registry：`https://mirrors.tools.huawei.com/npm/`
- Java：OpenJDK `21.0.10` (`bisheng_jdk_enterprise`)
- Maven：`3.9.11`
- `MAVEN_HOME`：`/usr/local/maven3`
- Rust：`1.96.0`
- Cargo：`1.96.0`
- Cargo registry：`sparse+http://rust.inhuawei.com/crates.io-index/`
- Go：未安装
- gcc：`13.3.0`
- g++：`13.3.0`
- GNU Make：`4.3`
- CMake：未找到

## 使用方式

新脚本默认使用：

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

兼容旧 validation 路径时也可以使用：

```bash
source validation/environment-profiles/huawei-competition-ubuntu-24.04/env.sh
bash validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh
```

## 适配规则

- 默认构建和验证路径不能依赖 Go。
- 默认构建和验证路径不能依赖 CMake；C/C++ oracle 路径优先使用 `gcc`、`g++` 和 GNU Make。
- Rust 代码必须保持 stable Rust `1.96.0` 兼容，不引入 nightly-only 功能。
- Python 脚本按 Python `3.12.3` / pip `24.0` 适配。
- Node/npm 脚本按 Node `v24.13.0` / npm `11.6.2` 适配。
- 直接依赖必须通过 `environment.json.dependency_admission_policy` 准入。新增 libclang、bindgen、syn、quote、tracing、anyhow 或其他依赖前，必须记录它消除的具体语义风险、生成质量风险或可维护性风险，并证明它不破坏默认 competition profile。
- 新生成的 validation evidence 应记录 `profile_id=huawei-competition-ubuntu-24.04` 和所用 `environment.json` 哈希。
