## Context

The current L1 native summary has 40 attempted catalog targets, 23 passed, and 17 failed. The previous classification change separated failures into bootstrap, missing tool/package, timeout, command mismatch, evidence gap, environment restriction, and related categories. This change handles only the subset that can be remediated through catalog command changes and fresh reruns.

## Goals / Non-Goals

**Goals:**

- Repair high-confidence command-only failures.
- Rerun the remediated subset in fresh external work roots.
- Refresh per-project evidence and the global L1 native summary.
- Keep deferred failures explicit so later work can handle dependencies, wrappers, mirrors, or submodules separately.

**Non-Goals:**

- Do not install host packages or global build tools.
- Do not mutate WSL/user privileges or rely on a non-root user.
- Do not perform Rust migration, unsafe-ratio analysis, or semantic-equivalence proof in this change.
- Do not convert broad upstream test suites into a claim of full project correctness.

## Decisions

### Decision 1: First remediation batch uses high-confidence command fixes

Accepted first-batch candidates:

- `ffmpeg`: add `--disable-x86asm` and run `./ffmpeg -version`.
- `hdf5`: replace full `ctest` with bounded HDF5 tool version smoke commands.
- `libgit2`: add `-DUSE_AUTH_NTLM=OFF` when HTTPS is disabled.
- `librdkafka`: build `examples/rdkafka_example` before running the existing example smoke.
- `openvpn`: add `--disable-dco` to avoid the libnl-genl DCO dependency.
- `libpcap`: run `./autogen.sh` before `./configure`, and use a short local binary/config smoke.
- `libuv`: use a root-explicit smoke command with `UV_RUN_AS_ROOT=1`.
- `libevent`: rerun with an explicit short CTest smoke to close the evidence gap.

`tcpdump` is a controlled candidate because `./autogen.sh` is clearly required, but it may still depend on a sibling or system `libpcap`. It can be attempted in the same remediation work root as `libpcap`; if dependency discovery still fails, the failure remains evidence rather than a pass claim.

### Decision 2: Defer failures that need environment or larger recipe design

Deferred projects:

- `freertos-kernel`: needs an application/config wrapper or acceptance of the official example scope.
- `systemd`: needs Meson availability.
- `zephyr`: needs west and Zephyr toolchain setup.
- `qemu`: needs glib development package availability.
- `micropython`: needs libffi development package or explicit minimal variant scope decision.
- `linux`: needs network retry/mirror policy.
- `mbedtls`: needs fresh filesystem/timestamp normalization before concluding command repair.
- `mupdf`: needs third-party submodule remediation; useful, but separate from the first high-confidence batch.

### Decision 3: Aggregation remains evidence-first

The remediation run should write a dedicated remediation summary and update `validation/evidence/l1-native-summary.json` only from concrete per-project results. If a candidate still fails, it remains failed and includes the new failed command evidence.

## Risks / Trade-offs

- [Risk] Short smoke commands can prove less than broad upstream suites. -> Mitigation: report them as L1 native smoke only and keep command text explicit.
- [Risk] Disabling optional features may hide dependency problems. -> Mitigation: only disable features already outside the narrowed L1 smoke scope and document the feature reduction in the recipe.
- [Risk] `tcpdump` may still fail without a discoverable `libpcap`. -> Mitigation: attempt it after `libpcap` in the same work root and preserve failure evidence if unresolved.
- [Risk] Fresh reruns can still hit transient network issues. -> Mitigation: record work roots and log paths rather than rewriting historical results.

## Migration Plan

1. Update accepted catalog recipes.
2. Add or generalize aggregation/report tooling for remediation results.
3. Run the accepted candidate batch in a fresh external work root.
4. Aggregate per-project and global L1 evidence.
5. Update README and OpenSpec task status.
6. Validate OpenSpec, catalog shape, Rust tests, and diff cleanliness before commit/push.
