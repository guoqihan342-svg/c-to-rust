# L1 Low-Cost Remediation

中文：本报告只记录 L1 native C build/test smoke 的低成本命令修复重跑结果，不证明 Rust 迁移、unsafe 比例、性能保持或 C/Rust 语义等价。
English: this report only records low-cost command remediation reruns for L1 native C build/test smoke. It does not prove Rust migration, unsafe budget compliance, performance preservation, or C/Rust semantic equivalence.

## Summary

- Generated at UTC: `2026-06-24T05:09:57Z`
- Candidate project count: `9`
- Attempted count: `9`
- Passed count: `8`
- Failed count: `1`
- Other count: `0`

## Attempted Projects

| Project | Status | Failed step | Failure summary |
|---|---|---|---|
| `ffmpeg` | `passed` | `` |  |
| `hdf5` | `passed` | `` |  |
| `libgit2` | `passed` | `` |  |
| `librdkafka` | `passed` | `` |  |
| `openvpn` | `failed` | `03_build_2` | 03_build_2 exited 1 |
| `libpcap` | `passed` | `` |  |
| `tcpdump` | `passed` | `` |  |
| `libuv` | `passed` | `` |  |
| `libevent` | `passed` | `` |  |

## Recipe Changes

| Project | Change |
|---|---|
| `ffmpeg` | Disable x86 assembly and run the repo-local ffmpeg binary. |
| `hdf5` | Replace full upstream ctest with bounded HDF5 tool version smoke commands. |
| `libgit2` | Disable NTLM auth when HTTPS is disabled. |
| `librdkafka` | Build rdkafka_example before running its config-list smoke. |
| `openvpn` | Disable DCO for the L1 smoke; rerun exposed mandatory libcap-ng dependency. |
| `libpcap` | Run autogen for git checkouts and smoke pcap-config. |
| `tcpdump` | Run autogen for git checkouts; dependency on discoverable libpcap remains auditable. |
| `libuv` | Use UV_RUN_AS_ROOT=1 for a root-safe test-list smoke. |
| `libevent` | Use an explicit short CTest smoke to close the previous evidence gap. |

## Deferred Projects

| Project | Reason |
|---|---|
| `freertos-kernel` | Needs an application/config wrapper or an explicit official-example scope decision. |
| `systemd` | Needs Meson availability. |
| `zephyr` | Needs west and Zephyr toolchain setup. |
| `qemu` | Needs glib development package availability. |
| `micropython` | Needs libffi development package or an explicit minimal-variant scope decision. |
| `linux` | Needs network retry or mirror policy. |
| `mbedtls` | Needs fresh filesystem/timestamp normalization before command repair. |
| `mupdf` | Needs third-party submodule remediation in a separate batch. |
| `openvpn` | DCO was disabled, but Linux configure still requires libcap-ng development package availability. |

## Boundary

This L1 summary proves native C baseline build/test smoke only. It does not prove Rust slice compilation, unsafe budget, C/Rust semantic equivalence, or performance preservation.
