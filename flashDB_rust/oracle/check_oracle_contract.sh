#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ORACLE_DIR="$ROOT_DIR/flashDB_rust/oracle"
PINNED_COMMIT="93d175549da579b8abac07bd175ce4c3f9dde829"
CLONE_URL="https://gitcode.com/xwxf/FlashDB.git"

fail() {
    printf 'oracle contract check failed: %s\n' "$1" >&2
    exit 1
}

need_file() {
    test -f "$ORACLE_DIR/$1" || fail "missing $1"
}

need_text() {
    file=$1
    text=$2
    grep -Fq -- "$text" "$ORACLE_DIR/$file" || fail "$file missing text: $text"
}

need_file README.md
need_file generate_c_oracle.sh
need_file Makefile.c_oracle
need_file flashdb_c_oracle.c
need_file fdb_cfg.h

need_text README.md "$PINNED_COMMIT"
need_text README.md "$CLONE_URL"
need_text README.md "SKIPPED_LOCAL_NO_C_TOOLCHAIN"
need_text README.md "sec_size 4096"

need_text generate_c_oracle.sh "$PINNED_COMMIT"
need_text generate_c_oracle.sh "$CLONE_URL"
need_text generate_c_oracle.sh "gcc"
need_text generate_c_oracle.sh "make"
need_text generate_c_oracle.sh "--fixture"
need_text generate_c_oracle.sh '"$BUILD_DIR/flashdb_c_oracle" --fixture "$FIXTURE_FILE" --work-dir "$RUN_DIR"'

need_text fdb_cfg.h "#define FDB_USING_KVDB"
need_text fdb_cfg.h "#define FDB_USING_TSDB"
need_text fdb_cfg.h "#define FDB_USING_FILE_POSIX_MODE"
need_text fdb_cfg.h "#define FDB_WRITE_GRAN 1"

for api in \
    fdb_kvdb_init \
    fdb_kv_set \
    fdb_kv_get \
    fdb_kv_del \
    fdb_kv_iterator_init \
    fdb_kv_iterate \
    fdb_tsdb_init \
    fdb_tsl_append_with_ts \
    fdb_tsl_iter_by_time \
    fdb_tsl_query_count \
    fdb_tsl_set_status
do
    need_text flashdb_c_oracle.c "$api"
done

need_text flashdb_c_oracle.c "ORACLE_SEC_SIZE 4096"
need_text flashdb_c_oracle.c "toolchain_status"
need_text flashdb_c_oracle.c '\"id\"'
need_text flashdb_c_oracle.c '\"op\"'
need_text flashdb_c_oracle.c '\"status\"'
need_text flashdb_c_oracle.c '\"code\"'
need_text flashdb_c_oracle.c "kv.set"
need_text flashdb_c_oracle.c "kv.get"
need_text flashdb_c_oracle.c "kv.delete"
need_text flashdb_c_oracle.c "kv.reopen"
need_text flashdb_c_oracle.c "ts.append"
need_text flashdb_c_oracle.c "ts.query"
need_text flashdb_c_oracle.c "ts.set_status"
need_text flashdb_c_oracle.c "ts.count_status"
need_text flashdb_c_oracle.c "ts.reopen"
need_text Makefile.c_oracle "fdb_file.c"
need_text Makefile.c_oracle "flashdb_c_oracle.c"

printf 'oracle contract check passed\n'
