## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `run-supercomplex-wave2-l1-native-validation`.
- [x] 1.2 Validate the change with `openspec validate "run-supercomplex-wave2-l1-native-validation" --strict`.

## 2. Runner

- [x] 2.1 Add a WSL-friendly wave2 L1 runner under `validation/tools`.
- [x] 2.2 Smoke-check runner metadata mode without cloning projects.

## 3. Parallel L1 Execution

- [x] 3.1 Run network-protocol worker for HAProxy, memcached, libpcap, tcpdump, and OpenVPN.
- [x] 3.2 Run security-parser worker for libxml2, wolfSSL, OpenSSH Portable, and libgit2.
- [x] 3.3 Run media-data worker for x264, HDF5, ImageMagick, and MuPDF.
- [x] 3.4 Run system-virt worker for Vim, QEMU, systemd, and Linux.
- [x] 3.5 Run messaging worker for librdkafka.

## 4. Evidence Aggregation

- [x] 4.1 Aggregate worker `results.json` files into per-project L1 evidence.
- [x] 4.2 Update `validation/evidence/l1-native-summary.json`.
- [x] 4.3 Add wave2 L1 summary evidence.
- [x] 4.4 Update README with wave2 L1 status.

## 5. Validation and Delivery

- [x] 5.1 Run `powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1`.
- [x] 5.2 Run `openspec validate "run-supercomplex-wave2-l1-native-validation" --strict`.
- [x] 5.3 Run `openspec validate --all`.
- [x] 5.4 Run `cargo test` in `flashDB_rust`.
- [x] 5.5 Run `cargo test` in `validation/l2_slices`.
- [x] 5.6 Run `git diff --check`.
- [x] 5.7 Commit and push the branch.
