## 1. Planning

- [x] 1.1 Create OpenSpec proposal, design, spec, and tasks for `run-supercomplex-l1-native-validation`.
- [x] 1.2 Validate the change with `openspec validate "run-supercomplex-l1-native-validation" --strict`.

## 2. Worker Execution

- [x] 2.1 Prepare WSL build dependencies and external workspace.
- [x] 2.2 Run storage/runtime L1 worker for SQLite, Lua, and Git.
- [x] 2.3 Run compression/image L1 worker for zstd, zlib-ng, libpng, and libjpeg-turbo.
- [x] 2.4 Run network/event L1 worker for curl, libuv, libevent, and nginx.
- [x] 2.5 Run KV/crypto L1 worker for Valkey, Redis, OpenSSL, and Mbed TLS.
- [x] 2.6 Run heavy/system L1 worker for PostgreSQL, jemalloc, and tmux.

## 3. Evidence

- [x] 3.1 Aggregate worker JSON results into repo-local L1 summary evidence.
- [x] 3.2 Add per-project compact L1 evidence files for all attempted projects.
- [x] 3.3 Record failed or blocked projects without counting them as L1 passed.
- [x] 3.4 Ensure the summary marks the milestone passed only when at least 12 projects pass L1.

## 4. Validation and Delivery

- [x] 4.1 Run catalog validation.
- [x] 4.2 Run `openspec validate "run-supercomplex-l1-native-validation" --strict`.
- [x] 4.3 Run `openspec validate --all`.
- [x] 4.4 Run `cargo test` for the FlashDB Rust crate.
- [x] 4.5 Run `git diff --check`.
- [x] 4.6 Commit and push the branch.
