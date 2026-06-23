#ifndef FLASHDB_RUST_ORACLE_FDB_CFG_H
#define FLASHDB_RUST_ORACLE_FDB_CFG_H

#include <stdio.h>

#define FDB_USING_KVDB
#define FDB_USING_TSDB
#define FDB_USING_FILE_POSIX_MODE
#define FDB_WRITE_GRAN 1

/* Keep FlashDB diagnostics off stdout so oracle JSON remains machine-readable. */
#define FDB_PRINT(...) fprintf(stderr, __VA_ARGS__)

#endif
