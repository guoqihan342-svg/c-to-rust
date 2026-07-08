英文镜像见 `flashdb.en.md`。

﻿# FlashDB 用例边界

- 当前 accepted evidence：`real-fdb-calc-crc32`、`real-fdb-blob-make`、`real-fdb-kv-del`、`real-fdb-kv-set`。`real-fdb-kv-set` 是 exact typed-IR generated draft 的未初始化 DB `return_code=FDB_INIT_FAILED` fixture acceptance。
- 当前开放语义：initialized `fdb_kv_set`/delete、blob 持久化、`fdb_kv_set_blob` 和完整 external callee 语义未关闭。
- [baseline-record.json](../baseline-record.json)
- [build-and-c2rust-baseline.md](../build-and-c2rust-baseline.md)
- [flashdb-rust-skeleton-and-milestone.md](../flashdb-rust-skeleton-and-milestone.md)
- [full-regression-runner.md](../full-regression-runner.md)
