#include <dirent.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <flashdb.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#define ORACLE_FLASHDB_URL "https://gitcode.com/xwxf/FlashDB.git"
#define ORACLE_FLASHDB_COMMIT "93d175549da579b8abac07bd175ce4c3f9dde829"
#define ORACLE_SEC_SIZE 4096
#define ORACLE_KV_SECTORS 8
#define ORACLE_TS_SECTORS 8
#define ORACLE_TSL_MAX_LEN 64

static fdb_time_t next_time = 100;

static fdb_time_t deterministic_time(void)
{
    fdb_time_t current = next_time;
    next_time += 100;
    return current;
}

static const char *err_name(fdb_err_t err)
{
    switch (err) {
    case FDB_NO_ERR:
        return "FDB_NO_ERR";
    case FDB_ERASE_ERR:
        return "FDB_ERASE_ERR";
    case FDB_READ_ERR:
        return "FDB_READ_ERR";
    case FDB_WRITE_ERR:
        return "FDB_WRITE_ERR";
    case FDB_KV_NAME_ERR:
        return "FDB_KV_NAME_ERR";
    case FDB_KV_NAME_EXIST:
        return "FDB_KV_NAME_EXIST";
    case FDB_SAVED_FULL:
        return "FDB_SAVED_FULL";
    case FDB_INIT_FAILED:
        return "FDB_INIT_FAILED";
    default:
        return "FDB_UNKNOWN_ERR";
    }
}

static const char *tsl_status_name(fdb_tsl_status_t status)
{
    switch (status) {
    case FDB_TSL_UNUSED:
        return "FDB_TSL_UNUSED";
    case FDB_TSL_PRE_WRITE:
        return "FDB_TSL_PRE_WRITE";
    case FDB_TSL_WRITE:
        return "FDB_TSL_WRITE";
    case FDB_TSL_USER_STATUS1:
        return "FDB_TSL_USER_STATUS1";
    case FDB_TSL_DELETED:
        return "FDB_TSL_DELETED";
    case FDB_TSL_USER_STATUS2:
        return "FDB_TSL_USER_STATUS2";
    default:
        return "FDB_TSL_UNKNOWN";
    }
}

static void json_string(const char *value)
{
    const unsigned char *p = (const unsigned char *)value;
    putchar('"');
    while (*p != '\0') {
        switch (*p) {
        case '\\':
            fputs("\\\\", stdout);
            break;
        case '"':
            fputs("\\\"", stdout);
            break;
        case '\n':
            fputs("\\n", stdout);
            break;
        case '\r':
            fputs("\\r", stdout);
            break;
        case '\t':
            fputs("\\t", stdout);
            break;
        default:
            if (*p < 0x20) {
                printf("\\u%04x", *p);
            } else {
                putchar(*p);
            }
            break;
        }
        p++;
    }
    putchar('"');
}

static void json_hex(const uint8_t *data, size_t len)
{
    size_t i;
    putchar('"');
    for (i = 0; i < len; i++) {
        printf("%02x", data[i]);
    }
    putchar('"');
}

static int path_join(char *out, size_t out_len, const char *left, const char *right)
{
    int written = snprintf(out, out_len, "%s/%s", left, right);
    return written > 0 && (size_t)written < out_len ? 0 : -1;
}

static int remove_tree(const char *path)
{
    DIR *dir = opendir(path);
    struct dirent *entry;

    if (dir == NULL) {
        return errno == ENOENT ? 0 : -1;
    }

    while ((entry = readdir(dir)) != NULL) {
        char child[PATH_MAX];
        struct stat st;

        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) {
            continue;
        }
        if (path_join(child, sizeof(child), path, entry->d_name) != 0) {
            closedir(dir);
            return -1;
        }
        if (stat(child, &st) != 0) {
            closedir(dir);
            return -1;
        }
        if (S_ISDIR(st.st_mode)) {
            if (remove_tree(child) != 0) {
                closedir(dir);
                return -1;
            }
        } else if (unlink(child) != 0) {
            closedir(dir);
            return -1;
        }
    }

    closedir(dir);
    return rmdir(path);
}

static int ensure_dir(const char *path)
{
    if (mkdir(path, 0777) == 0 || errno == EEXIST) {
        return 0;
    }
    return -1;
}

static int prepare_work_dirs(const char *work_dir, char *kv_dir, size_t kv_len, char *ts_dir, size_t ts_len)
{
    if (remove_tree(work_dir) != 0 && errno != ENOENT) {
        return -1;
    }
    if (ensure_dir(work_dir) != 0) {
        return -1;
    }
    if (path_join(kv_dir, kv_len, work_dir, "kvdb") != 0 ||
        path_join(ts_dir, ts_len, work_dir, "tsdb") != 0) {
        return -1;
    }
    return ensure_dir(kv_dir) == 0 && ensure_dir(ts_dir) == 0 ? 0 : -1;
}

static void step_prefix(bool *first, const char *id, const char *api)
{
    if (!*first) {
        fputs(",\n", stdout);
    }
    *first = false;
    fputs("    {\"id\":", stdout);
    json_string(id);
    fputs(",\"api\":", stdout);
    json_string(api);
    fputs(",\"observed\":", stdout);
}

static fdb_err_t init_kvdb(struct fdb_kvdb *db, const char *path)
{
    uint32_t sec_size = ORACLE_SEC_SIZE;
    uint32_t max_size = ORACLE_SEC_SIZE * ORACLE_KV_SECTORS;
    bool file_mode = true;

    memset(db, 0, sizeof(*db));
    fdb_kvdb_control(db, FDB_KVDB_CTRL_SET_SEC_SIZE, &sec_size);
    fdb_kvdb_control(db, FDB_KVDB_CTRL_SET_FILE_MODE, &file_mode);
    fdb_kvdb_control(db, FDB_KVDB_CTRL_SET_MAX_SIZE, &max_size);
    return fdb_kvdb_init(db, "ora_kv", path, NULL, NULL);
}

static fdb_err_t init_tsdb(struct fdb_tsdb *db, const char *path)
{
    uint32_t sec_size = ORACLE_SEC_SIZE;
    uint32_t max_size = ORACLE_SEC_SIZE * ORACLE_TS_SECTORS;
    bool file_mode = true;

    memset(db, 0, sizeof(*db));
    fdb_tsdb_control(db, FDB_TSDB_CTRL_SET_SEC_SIZE, &sec_size);
    fdb_tsdb_control(db, FDB_TSDB_CTRL_SET_FILE_MODE, &file_mode);
    fdb_tsdb_control(db, FDB_TSDB_CTRL_SET_MAX_SIZE, &max_size);
    return fdb_tsdb_init(db, "ora_ts", path, deterministic_time, ORACLE_TSL_MAX_LEN, NULL);
}

static void print_kv_iteration(fdb_kvdb_t db)
{
    struct fdb_kv_iterator iterator;
    bool first = true;

    fdb_kv_iterator_init(db, &iterator);
    putchar('[');
    while (fdb_kv_iterate(db, &iterator)) {
        uint8_t value[128] = {0};
        struct fdb_blob blob;
        size_t read_len;
        fdb_kv_t kv = &iterator.curr_kv;

        fdb_blob_make(&blob, value, sizeof(value));
        read_len = fdb_blob_read((fdb_db_t)db, fdb_kv_to_blob(kv, &blob));
        if (!first) {
            putchar(',');
        }
        first = false;
        fputs("{\"key\":", stdout);
        json_string(kv->name);
        fputs(",\"value_hex\":", stdout);
        json_hex(value, read_len);
        printf(",\"value_len\":%zu}", read_len);
    }
    putchar(']');
}

struct ts_iter_ctx {
    fdb_tsdb_t db;
    bool first;
    bool update_first;
    fdb_err_t update_result;
};

static bool print_ts_cb(fdb_tsl_t tsl, void *arg)
{
    struct ts_iter_ctx *ctx = (struct ts_iter_ctx *)arg;
    uint8_t value[ORACLE_TSL_MAX_LEN] = {0};
    struct fdb_blob blob;
    size_t read_len;

    fdb_blob_make(&blob, value, sizeof(value));
    read_len = fdb_blob_read((fdb_db_t)ctx->db, fdb_tsl_to_blob(tsl, &blob));
    if (!ctx->first) {
        putchar(',');
    }
    ctx->first = false;
    fputs("{\"time\":", stdout);
    printf("%ld", (long)tsl->time);
    fputs(",\"status\":", stdout);
    json_string(tsl_status_name(tsl->status));
    fputs(",\"value_hex\":", stdout);
    json_hex(value, read_len);
    fputs("}", stdout);

    if (ctx->update_first) {
        ctx->update_result = fdb_tsl_set_status(ctx->db, tsl, FDB_TSL_USER_STATUS1);
        ctx->update_first = false;
    }
    return false;
}

static int run_kvdb_steps(const char *kv_dir, bool *first_step)
{
    struct fdb_kvdb kvdb;
    fdb_err_t err;
    const uint8_t blob_value[] = {0x00, 0x10, 0x20, 0x7f, 0xff};
    uint8_t blob_read[16] = {0};
    struct fdb_blob blob;
    size_t read_len;
    char *value;

    err = init_kvdb(&kvdb, kv_dir);
    step_prefix(first_step, "kvdb_init", "fdb_kvdb_init");
    printf("{\"return\":");
    json_string(err_name(err));
    printf(",\"sec_size\":%d,\"max_size\":%d}}", ORACLE_SEC_SIZE, ORACLE_SEC_SIZE * ORACLE_KV_SECTORS);
    if (err != FDB_NO_ERR) {
        return 1;
    }

    err = fdb_kv_set(&kvdb, "alpha", "one");
    value = fdb_kv_get(&kvdb, "alpha");
    step_prefix(first_step, "kvdb_set_get_string", "fdb_kv_set/fdb_kv_get");
    printf("{\"set_return\":");
    json_string(err_name(err));
    fputs(",\"value\":", stdout);
    json_string(value == NULL ? "" : value);
    printf(",\"found\":%s}", value == NULL ? "false" : "true");
    putchar('}');

    fdb_blob_make(&blob, blob_value, sizeof(blob_value));
    err = fdb_kv_set_blob(&kvdb, "blob", &blob);
    memset(blob_read, 0, sizeof(blob_read));
    fdb_blob_make(&blob, blob_read, sizeof(blob_read));
    read_len = fdb_kv_get_blob(&kvdb, "blob", &blob);
    step_prefix(first_step, "kvdb_set_get_blob", "fdb_kv_set_blob/fdb_kv_get_blob");
    printf("{\"set_return\":");
    json_string(err_name(err));
    printf(",\"read_len\":%zu,\"value_hex\":", read_len);
    json_hex(blob_read, read_len);
    putchar('}');
    putchar('}');

    err = fdb_kv_set(&kvdb, "alpha", "two");
    value = fdb_kv_get(&kvdb, "alpha");
    step_prefix(first_step, "kvdb_update_string", "fdb_kv_set/fdb_kv_get");
    printf("{\"set_return\":");
    json_string(err_name(err));
    fputs(",\"value\":", stdout);
    json_string(value == NULL ? "" : value);
    printf(",\"found\":%s}", value == NULL ? "false" : "true");
    putchar('}');

    step_prefix(first_step, "kvdb_iterate", "fdb_kv_iterator_init/fdb_kv_iterate");
    fputs("{\"items\":", stdout);
    print_kv_iteration(&kvdb);
    putchar('}');
    putchar('}');

    err = fdb_kv_del(&kvdb, "alpha");
    value = fdb_kv_get(&kvdb, "alpha");
    step_prefix(first_step, "kvdb_delete", "fdb_kv_del/fdb_kv_get");
    printf("{\"delete_return\":");
    json_string(err_name(err));
    printf(",\"found_after_delete\":%s}", value == NULL ? "false" : "true");
    putchar('}');

    err = fdb_kvdb_deinit(&kvdb);
    step_prefix(first_step, "kvdb_deinit", "fdb_kvdb_deinit");
    printf("{\"return\":");
    json_string(err_name(err));
    putchar('}');
    putchar('}');

    err = init_kvdb(&kvdb, kv_dir);
    memset(blob_read, 0, sizeof(blob_read));
    fdb_blob_make(&blob, blob_read, sizeof(blob_read));
    read_len = err == FDB_NO_ERR ? fdb_kv_get_blob(&kvdb, "blob", &blob) : 0;
    value = err == FDB_NO_ERR ? fdb_kv_get(&kvdb, "alpha") : NULL;
    step_prefix(first_step, "kvdb_reopen", "fdb_kvdb_init/fdb_kv_get_blob/fdb_kv_get");
    printf("{\"reopen_return\":");
    json_string(err_name(err));
    printf(",\"blob_read_len\":%zu,\"blob_value_hex\":", read_len);
    json_hex(blob_read, read_len);
    printf(",\"deleted_key_found\":%s}", value == NULL ? "false" : "true");
    putchar('}');
    if (err == FDB_NO_ERR) {
        fdb_kvdb_deinit(&kvdb);
    }

    return 0;
}

static int run_tsdb_steps(const char *ts_dir, bool *first_step)
{
    struct fdb_tsdb tsdb;
    struct fdb_blob blob;
    fdb_err_t err;
    size_t write_count;
    size_t user1_count;
    struct ts_iter_ctx ctx;
    const char first[] = "first";
    const char second[] = "second";
    const char third[] = "third";

    next_time = 100;
    err = init_tsdb(&tsdb, ts_dir);
    step_prefix(first_step, "tsdb_init", "fdb_tsdb_init");
    printf("{\"return\":");
    json_string(err_name(err));
    printf(",\"sec_size\":%d,\"max_size\":%d}}", ORACLE_SEC_SIZE, ORACLE_SEC_SIZE * ORACLE_TS_SECTORS);
    if (err != FDB_NO_ERR) {
        return 1;
    }

    fdb_blob_make(&blob, first, strlen(first));
    err = fdb_tsl_append(&tsdb, &blob);
    step_prefix(first_step, "tsdb_append_time_provider", "fdb_tsl_append");
    printf("{\"return\":");
    json_string(err_name(err));
    fputs(",\"expected_time\":100}", stdout);
    putchar('}');

    fdb_blob_make(&blob, second, strlen(second));
    err = fdb_tsl_append_with_ts(&tsdb, &blob, 200);
    step_prefix(first_step, "tsdb_append_with_ts_200", "fdb_tsl_append_with_ts");
    printf("{\"return\":");
    json_string(err_name(err));
    fputs(",\"time\":200}", stdout);
    putchar('}');

    fdb_blob_make(&blob, third, strlen(third));
    err = fdb_tsl_append_with_ts(&tsdb, &blob, 300);
    step_prefix(first_step, "tsdb_append_with_ts_300", "fdb_tsl_append_with_ts");
    printf("{\"return\":");
    json_string(err_name(err));
    fputs(",\"time\":300}", stdout);
    putchar('}');

    step_prefix(first_step, "tsdb_query_by_time", "fdb_tsl_iter_by_time");
    fputs("{\"from\":100,\"to\":300,\"items\":[", stdout);
    ctx.db = &tsdb;
    ctx.first = true;
    ctx.update_first = false;
    ctx.update_result = FDB_NO_ERR;
    fdb_tsl_iter_by_time(&tsdb, 100, 300, print_ts_cb, &ctx);
    fputs("]}", stdout);
    putchar('}');

    write_count = fdb_tsl_query_count(&tsdb, 0, 1000, FDB_TSL_WRITE);
    step_prefix(first_step, "tsdb_count_write", "fdb_tsl_query_count");
    printf("{\"status\":\"FDB_TSL_WRITE\",\"count\":%zu}", write_count);
    putchar('}');

    step_prefix(first_step, "tsdb_set_status_first", "fdb_tsl_iter_by_time/fdb_tsl_set_status");
    fputs("{\"updated_items\":[", stdout);
    ctx.db = &tsdb;
    ctx.first = true;
    ctx.update_first = true;
    ctx.update_result = FDB_NO_ERR;
    fdb_tsl_iter_by_time(&tsdb, 100, 100, print_ts_cb, &ctx);
    fputs("],\"set_status_return\":", stdout);
    json_string(err_name(ctx.update_result));
    putchar('}');
    putchar('}');

    user1_count = fdb_tsl_query_count(&tsdb, 0, 1000, FDB_TSL_USER_STATUS1);
    write_count = fdb_tsl_query_count(&tsdb, 0, 1000, FDB_TSL_WRITE);
    step_prefix(first_step, "tsdb_count_after_status", "fdb_tsl_query_count");
    printf("{\"user_status1_count\":%zu,\"write_count\":%zu}", user1_count, write_count);
    putchar('}');

    err = fdb_tsdb_deinit(&tsdb);
    step_prefix(first_step, "tsdb_deinit", "fdb_tsdb_deinit");
    printf("{\"return\":");
    json_string(err_name(err));
    putchar('}');
    putchar('}');

    return 0;
}

int main(int argc, char **argv)
{
    const char *work_dir = "oracle_c_work";
    char kv_dir[PATH_MAX];
    char ts_dir[PATH_MAX];
    bool first_step = true;
    int result = 0;

    if (argc == 3 && strcmp(argv[1], "--work-dir") == 0) {
        work_dir = argv[2];
    } else if (argc != 1) {
        fprintf(stderr, "usage: %s [--work-dir DIR]\n", argv[0]);
        return 2;
    }

    if (prepare_work_dirs(work_dir, kv_dir, sizeof(kv_dir), ts_dir, sizeof(ts_dir)) != 0) {
        fprintf(stderr, "failed to prepare oracle work directory: %s\n", work_dir);
        return 1;
    }

    fputs("{\n", stdout);
    fputs("  \"schema_version\":1,\n", stdout);
    fputs("  \"fixture_id\":\"flashdb-c-oracle-contract-v1\",\n", stdout);
    fputs("  \"toolchain_status\":\"C_ORACLE_GENERATED\",\n", stdout);
    fputs("  \"source\":{\"clone_url\":", stdout);
    json_string(ORACLE_FLASHDB_URL);
    fputs(",\"commit\":", stdout);
    json_string(ORACLE_FLASHDB_COMMIT);
    printf(",\"sec_size\":%d,\"write_gran\":1,\"file_mode\":\"posix\"},\n", ORACLE_SEC_SIZE);
    fputs("  \"steps\":[\n", stdout);

    result |= run_kvdb_steps(kv_dir, &first_step);
    result |= run_tsdb_steps(ts_dir, &first_step);

    fputs("\n  ]\n", stdout);
    fputs("}\n", stdout);
    fflush(stdout);

    return result == 0 ? 0 : 1;
}
