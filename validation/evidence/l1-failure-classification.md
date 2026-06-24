# L1 Failure Classification

中文：本报告只对 L1 native C build/test smoke 失败进行诊断分类，不代表项目已经修复，也不代表 Rust 迁移或语义等价已经证明。

English: this report only classifies failed L1 native C build/test smoke attempts. It does not claim remediation, Rust migration, or C/Rust semantic equivalence.

## Summary

- Generated at UTC: `2026-06-24T04:31:27Z`
- Failed project count: `17`

| Category | Count |
|---|---:|
| `bootstrap-required` | 2 |
| `build-config-conflict` | 1 |
| `build-environment-clock-skew` | 1 |
| `clone-or-network-failure` | 1 |
| `environment-restriction` | 1 |
| `evidence-gap` | 1 |
| `invalid-build-recipe` | 1 |
| `missing-assembler` | 1 |
| `missing-build-tool` | 2 |
| `missing-built-artifact-or-command-mismatch` | 1 |
| `missing-dev-package` | 3 |
| `missing-vendored-dependency` | 1 |
| `timeout` | 1 |

## Projects

| Project | Category | Confidence | Failed step | Exit | Recommendation |
|---|---|---|---|---:|---|
| `ffmpeg` | `missing-assembler` | `high` | `02_build_1` | 1 | Install or update nasm, or change the FFmpeg L1 recipe to disable x86 assembly explicitly. |
| `freertos-kernel` | `invalid-build-recipe` | `high` | `02_build_1` | 1 | Add a minimal FreeRTOS app/config wrapper that provides freertos_config and FreeRTOSConfig.h. |
| `hdf5` | `timeout` | `high` | `04_test_1` | 124 | Create a bounded smoke subset or raise timeout only after measuring where the test stalls. |
| `libevent` | `evidence-gap` | `high` | `cmake_build` | 0 | Regenerate this L1 evidence with an explicit smoke command or failed step before attempting remediation. |
| `libgit2` | `build-config-conflict` | `high` | `02_build_1` | 1 | Adjust the libgit2 L1 recipe so NTLM crypto is not enabled with the HTTPS backend disabled. |
| `libpcap` | `bootstrap-required` | `high` | `02_build_1` | 127 | Run the project's bootstrap/autogen step for git checkouts or use a release tarball with generated configure. |
| `librdkafka` | `missing-built-artifact-or-command-mismatch` | `medium` | `04_test_1` | 127 | Inspect build output and adjust the smoke binary path or build target in a separate command-repair change. |
| `libuv` | `environment-restriction` | `high` | `smoke_ip4_addr` | 1 | Rerun this smoke under a non-root WSL user or choose a root-safe smoke command. |
| `linux` | `clone-or-network-failure` | `medium` | `01_clone` | 128 | Retry with a fresh external work root; if repeated, use a pinned mirror or non-shallow clone policy. |
| `mbedtls` | `build-environment-clock-skew` | `medium` | `build` | 2 | Retry in a fresh work root after normalizing filesystem timestamps; then classify remaining compiler errors. |
| `micropython` | `missing-dev-package` | `high` | `04_build_3` | 2 | Install libffi development/pkg-config files or disable the MicroPython unix FFI option in a separate change. |
| `mupdf` | `missing-vendored-dependency` | `high` | `02_build_1` | 2 | Clone or initialize MuPDF third-party dependencies recursively, or disable tool targets that require MuJS. |
| `openvpn` | `missing-dev-package` | `high` | `03_build_2` | 1 | Install libnl-genl-3 development/pkg-config files or disable OpenVPN DCO if it is outside L1 scope. |
| `qemu` | `missing-dev-package` | `high` | `02_build_1` | 1 | Install glib-2.0 development/pkg-config files before retrying QEMU L1 configure. |
| `systemd` | `missing-build-tool` | `high` | `02_build_1` | 127 | Install or expose Meson, or use a project-supported Python/venv Meson entrypoint. |
| `tcpdump` | `bootstrap-required` | `high` | `02_build_1` | 127 | Run the project's bootstrap/autogen step for git checkouts or use a release tarball with generated configure. |
| `zephyr` | `missing-build-tool` | `high` | `02_build_1` | 127 | Install or provide Zephyr west/toolchain prerequisites in a separate dependency-prep change. |

## Boundary

L1 failure classification is diagnostic only. It does not change project L1 status, prove remediation, or imply C/Rust semantic equivalence.
