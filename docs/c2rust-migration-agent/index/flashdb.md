英文镜像见 `flashdb.en.md`。

﻿# FlashDB 用例边界

- 当前 accepted evidence：`real-fdb-calc-crc32`、`real-fdb-blob-make`；二者均为 L4 accepted-evidence authoritative 语义绑定，generated draft 仍不是 semantic pass。
- 当前 blocked evidence：`real-fdb-kv-set`；external direct callee shim/model/oracle 语义未关闭。
- [baseline-record.json](../baseline-record.json)
- [build-and-c2rust-baseline.md](../build-and-c2rust-baseline.md)
- [flashdb-rust-skeleton-and-milestone.md](../flashdb-rust-skeleton-and-milestone.md)
- [full-regression-runner.md](../full-regression-runner.md)
