# 华为比赛环境 Profile

本目录是比赛/评测环境的单一配置入口。代码、脚本和验证流水线需要按这里的约束适配；不要把本机 Windows 工具链或历史 evidence 里的版本当作比赛环境。

## 环境基线

- OS：Ubuntu 24.04.4 LTS (Noble Numbat)
- Kernel：`5.10.0-182.0.0.95.r194_123.hce2.x86_64`
- APT mirror：`http://mirrors.tools.huawei.com/ubuntu`
- Python：`3.12.3`
- pip：`24.0`
- PyPI mirror：`https://mirrors.tools.huawei.com/pypi/simple`
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

## 文件说明

- `environment.json`：机器可读环境基线和适配策略。
- `apt/sources.list`：Ubuntu Noble APT mirror 配置。
- `pip/pip.conf`：pip mirror 配置。
- `npm/.npmrc`：npm registry 配置。
- `cargo/config.toml`：Cargo crates.io mirror 配置。
- `rust/rust-toolchain.toml`：Rust `1.96.0` 工具链声明，默认不在仓库根目录生效。
- `env.sh`：比赛机 shell 会话的环境变量入口。
- `toolchain-check.sh`：比赛机环境自检脚本。

## 适配规则

- 默认构建和验证路径不能依赖 Go。
- 默认构建和验证路径不能依赖 CMake；C/C++ oracle 路径优先使用 `gcc` / `g++` / `make`。
- Rust 代码必须保持 stable Rust `1.96.0` 兼容，不引入 nightly-only 功能。
- Python 脚本按 Python `3.12.3` / pip `24.0` 适配。
- Node/npm 相关脚本按 Node `v24.13.0` / npm `11.6.2` 适配。
- 新生成的 validation evidence 应记录 `profile_id=huawei-competition-ubuntu-24.04` 和 `environment.json` 哈希。

## 使用方式

在比赛机 shell 中可先执行：

```bash
source validation/environment-profiles/huawei-competition-ubuntu-24.04/env.sh
bash validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh
```

如果需要把包管理器配置安装到用户目录，按本目录内对应文件同步到工具默认位置；仓库不会自动修改用户全局配置。

## 与当前代码的关系

当前 `c2r-translator` 和 FlashDB Rust 验证路径应优先走 Cargo、Python、gcc/g++、GNU Make。任何新增脚本如果需要 `cmake`、Go、较新的 Rust、较新的 Python、或非华为镜像源，必须显式写入非默认路径，并在 evidence 中标为非比赛默认配置。
