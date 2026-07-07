#include <ctype.h>
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
#define ORACLE_TSL_MAX_LEN 128
#define ORACLE_MAX_LINE 4096
#define ORACLE_MAX_OPS 256
#define ORACLE_MAX_ACCEPTED 32
#define ORACLE_MAX_FIELD 512
#define ORACLE_MAX_ENTRIES 256

struct operation {
    char id[ORACLE_MAX_FIELD];
    char op[64];
    char key[ORACLE_MAX_FIELD];
    char value[ORACLE_MAX_FIELD];
    char timestamp[64];
    char from[64];
    char to[64];
    char status[64];
    char entry_id[64];
    bool has_key;
    bool has_value;
    bool has_timestamp;
    bool has_from;
    bool has_to;
    bool has_status;
    bool has_entry_id;
};

struct accepted_difference {
    char id[ORACLE_MAX_FIELD];
    char reason[ORACLE_MAX_FIELD];
    char fields[ORACLE_MAX_FIELD];
};

struct fixture {
    char name[ORACLE_MAX_FIELD];
    char path[PATH_MAX];
    char hash[16];
    struct operation ops[ORACLE_MAX_OPS];
    size_t op_count;
    struct accepted_difference accepted[ORACLE_MAX_ACCEPTED];
    size_t accepted_count;
};

struct kv_entry {
    char key[ORACLE_MAX_FIELD];
    char value[ORACLE_MAX_FIELD];
};

struct ts_entry {
    uint64_t entry_id;
    uint32_t addr_index;
    long timestamp;
    fdb_tsl_status_t status;
    char value[ORACLE_MAX_FIELD];
};

struct oracle_state {
    struct fdb_kvdb kvdb;
    struct fdb_tsdb tsdb;
    char kv_dir[PATH_MAX];
    char ts_dir[PATH_MAX];
    uint64_t next_ts_entry_id;
    bool kv_open;
    bool ts_open;
};

struct ts_load_ctx {
    fdb_tsdb_t db;
    struct ts_entry *entries;
    size_t count;
    size_t capacity;
};

struct ts_find_ctx {
    uint32_t addr_index;
    struct fdb_tsl found;
    bool found_it;
};

struct ts_query_ctx {
    fdb_tsdb_t db;
    const struct ts_entry *entries;
    size_t count;
    bool first;
};

static fdb_time_t deterministic_time(void)
{
    return 0;
}

static uint32_t crc32_update(uint32_t crc, const unsigned char *bytes, size_t len)
{
    size_t i;

    crc ^= 0xffffffffU;
    for (i = 0; i < len; i++) {
        int bit;
        crc ^= (uint32_t)bytes[i];
        for (bit = 0; bit < 8; bit++) {
            uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1) ^ (0xedb88320U & mask);
        }
    }
    return crc ^ 0xffffffffU;
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

static const char *ts_status_name(fdb_tsl_status_t status)
{
    switch (status) {
    case FDB_TSL_WRITE:
        return "written";
    case FDB_TSL_USER_STATUS1:
        return "user1";
    case FDB_TSL_DELETED:
        return "deleted";
    case FDB_TSL_USER_STATUS2:
        return "user2";
    default:
        return "unknown";
    }
}

static bool parse_ts_status(const char *value, fdb_tsl_status_t *out)
{
    if (strcmp(value, "written") == 0 || strcmp(value, "Written") == 0) {
        *out = FDB_TSL_WRITE;
        return true;
    }
    if (strcmp(value, "user1") == 0 || strcmp(value, "UserStatus1") == 0) {
        *out = FDB_TSL_USER_STATUS1;
        return true;
    }
    if (strcmp(value, "deleted") == 0 || strcmp(value, "Deleted") == 0) {
        *out = FDB_TSL_DELETED;
        return true;
    }
    if (strcmp(value, "user2") == 0 || strcmp(value, "UserStatus2") == 0) {
        *out = FDB_TSL_USER_STATUS2;
        return true;
    }
    return false;
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

static void json_field_string(const char *name, const char *value)
{
    printf(",\"%s\":", name);
    json_string(value);
}

static void json_field_long(const char *name, long value)
{
    printf(",\"%s\":%ld", name, value);
}

static void json_field_u64(const char *name, uint64_t value)
{
    printf(",\"%s\":%llu", name, (unsigned long long)value);
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

static const char *skip_ws(const char *value)
{
    while (*value != '\0' && isspace((unsigned char)*value)) {
        value++;
    }
    return value;
}

static bool field_value(const char *input, const char *name, char *out, size_t out_len)
{
    char pattern[96];
    const char *start;
    const char *colon;
    const char *rest;
    size_t used = 0;

    snprintf(pattern, sizeof(pattern), "\"%s\"", name);
    start = strstr(input, pattern);
    if (start == NULL) {
        return false;
    }
    colon = strchr(start + strlen(pattern), ':');
    if (colon == NULL) {
        return false;
    }
    rest = skip_ws(colon + 1);

    if (*rest == '"') {
        bool escape = false;
        rest++;
        while (*rest != '\0') {
            char ch = *rest++;
            if (escape) {
                switch (ch) {
                case 'n':
                    ch = '\n';
                    break;
                case 'r':
                    ch = '\r';
                    break;
                case 't':
                    ch = '\t';
                    break;
                default:
                    break;
                }
                escape = false;
            } else if (ch == '\\') {
                escape = true;
                continue;
            } else if (ch == '"') {
                break;
            }
            if (used + 1 < out_len) {
                out[used++] = ch;
            }
        }
    } else {
        while (*rest != '\0' && *rest != ',' && *rest != '}' && *rest != ']') {
            if (used + 1 < out_len) {
                out[used++] = *rest;
            }
            rest++;
        }
        while (used > 0 && isspace((unsigned char)out[used - 1])) {
            used--;
        }
    }

    out[used] = '\0';
    return true;
}

static int load_fixture(const char *path, struct fixture *fixture)
{
    FILE *fp = fopen(path, "rb");
    char line[ORACLE_MAX_LINE];
    uint32_t crc = 0;
    bool in_accepted = false;

    if (fp == NULL) {
        fprintf(stderr, "failed to open fixture: %s\n", path);
        return -1;
    }

    memset(fixture, 0, sizeof(*fixture));
    snprintf(fixture->name, sizeof(fixture->name), "fixture");
    snprintf(fixture->path, sizeof(fixture->path), "%s", path);

    while (fgets(line, sizeof(line), fp) != NULL) {
        char trimmed[ORACLE_MAX_LINE];
        char *p;
        size_t len = strlen(line);

        crc = crc32_update(crc, (const unsigned char *)line, len);
        snprintf(trimmed, sizeof(trimmed), "%s", line);
        p = trimmed;
        while (*p != '\0' && isspace((unsigned char)*p)) {
            p++;
        }
        len = strlen(p);
        while (len > 0 && (p[len - 1] == '\n' || p[len - 1] == '\r' || p[len - 1] == ',' || isspace((unsigned char)p[len - 1]))) {
            p[--len] = '\0';
        }

        if (strstr(p, "\"name\"") != NULL && strstr(p, "\"operations\"") == NULL) {
            field_value(p, "name", fixture->name, sizeof(fixture->name));
        }
        if (strstr(p, "\"accepted_differences\"") != NULL) {
            in_accepted = true;
            continue;
        }
        if (in_accepted && p[0] == ']') {
            in_accepted = false;
            continue;
        }
        if (p[0] != '{') {
            continue;
        }
        if (strstr(p, "\"op\"") != NULL) {
            struct operation *op;
            if (fixture->op_count >= ORACLE_MAX_OPS) {
                fprintf(stderr, "too many fixture operations\n");
                fclose(fp);
                return -1;
            }
            op = &fixture->ops[fixture->op_count];
            memset(op, 0, sizeof(*op));
            if (!field_value(p, "id", op->id, sizeof(op->id)) ||
                !field_value(p, "op", op->op, sizeof(op->op))) {
                fprintf(stderr, "fixture operation missing id or op\n");
                fclose(fp);
                return -1;
            }
            op->has_key = field_value(p, "key", op->key, sizeof(op->key));
            op->has_value = field_value(p, "value", op->value, sizeof(op->value));
            op->has_timestamp = field_value(p, "timestamp", op->timestamp, sizeof(op->timestamp));
            op->has_from = field_value(p, "from", op->from, sizeof(op->from));
            op->has_to = field_value(p, "to", op->to, sizeof(op->to));
            op->has_status = field_value(p, "status", op->status, sizeof(op->status));
            op->has_entry_id = field_value(p, "entry_id", op->entry_id, sizeof(op->entry_id));
            fixture->op_count++;
        } else if (in_accepted) {
            struct accepted_difference *accepted;
            if (fixture->accepted_count >= ORACLE_MAX_ACCEPTED) {
                continue;
            }
            accepted = &fixture->accepted[fixture->accepted_count];
            memset(accepted, 0, sizeof(*accepted));
            field_value(p, "id", accepted->id, sizeof(accepted->id));
            field_value(p, "reason", accepted->reason, sizeof(accepted->reason));
            field_value(p, "fields", accepted->fields, sizeof(accepted->fields));
            fixture->accepted_count++;
        }
    }

    fclose(fp);
    snprintf(fixture->hash, sizeof(fixture->hash), "%08x", crc);
    if (fixture->op_count == 0) {
        fprintf(stderr, "fixture has no operations\n");
        return -1;
    }
    return 0;
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

static bool ts_load_cb(fdb_tsl_t tsl, void *arg)
{
    struct ts_load_ctx *ctx = (struct ts_load_ctx *)arg;
    struct ts_entry *entry;
    struct fdb_blob blob;
    char value[ORACLE_MAX_FIELD] = {0};
    size_t read_len;

    if (tsl->status == FDB_TSL_UNUSED || tsl->status == FDB_TSL_PRE_WRITE || ctx->count >= ctx->capacity) {
        return false;
    }

    fdb_blob_make(&blob, value, sizeof(value) - 1);
    read_len = fdb_blob_read((fdb_db_t)ctx->db, fdb_tsl_to_blob(tsl, &blob));
    value[read_len < sizeof(value) ? read_len : sizeof(value) - 1] = '\0';

    entry = &ctx->entries[ctx->count];
    entry->entry_id = (uint64_t)ctx->count + 1;
    entry->addr_index = tsl->addr.index;
    entry->timestamp = (long)tsl->time;
    entry->status = tsl->status;
    snprintf(entry->value, sizeof(entry->value), "%s", value);
    ctx->count++;
    return false;
}

static size_t load_ts_entries(fdb_tsdb_t db, struct ts_entry *entries, size_t capacity)
{
    struct ts_load_ctx ctx;

    memset(entries, 0, sizeof(*entries) * capacity);
    ctx.db = db;
    ctx.entries = entries;
    ctx.count = 0;
    ctx.capacity = capacity;
    fdb_tsl_iter(db, ts_load_cb, &ctx);
    return ctx.count;
}

static bool ts_find_cb(fdb_tsl_t tsl, void *arg)
{
    struct ts_find_ctx *ctx = (struct ts_find_ctx *)arg;

    if (tsl->addr.index == ctx->addr_index) {
        ctx->found = *tsl;
        ctx->found_it = true;
        return true;
    }
    return false;
}

static const struct ts_entry *find_ts_entry_by_addr(const struct ts_entry *entries, size_t count, uint32_t addr_index)
{
    size_t i;

    for (i = 0; i < count; i++) {
        if (entries[i].addr_index == addr_index) {
            return &entries[i];
        }
    }
    return NULL;
}

static bool ts_query_print_cb(fdb_tsl_t tsl, void *arg)
{
    struct ts_query_ctx *ctx = (struct ts_query_ctx *)arg;
    const struct ts_entry *entry = find_ts_entry_by_addr(ctx->entries, ctx->count, tsl->addr.index);
    struct fdb_blob blob;
    char value[ORACLE_MAX_FIELD] = {0};
    size_t read_len;

    if (entry == NULL) {
        return false;
    }

    fdb_blob_make(&blob, value, sizeof(value) - 1);
    read_len = fdb_blob_read((fdb_db_t)ctx->db, fdb_tsl_to_blob(tsl, &blob));
    value[read_len < sizeof(value) ? read_len : sizeof(value) - 1] = '\0';

    if (!ctx->first) {
        putchar(',');
    }
    ctx->first = false;
    fputs("{\"entry_id\":", stdout);
    printf("%llu", (unsigned long long)entry->entry_id);
    fputs(",\"timestamp\":", stdout);
    printf("%ld", (long)tsl->time);
    fputs(",\"status\":", stdout);
    json_string(ts_status_name(tsl->status));
    fputs(",\"value\":", stdout);
    json_string(value);
    putchar('}');
    return false;
}

static int kv_entry_cmp(const void *left, const void *right)
{
    const struct kv_entry *a = (const struct kv_entry *)left;
    const struct kv_entry *b = (const struct kv_entry *)right;

    return strcmp(a->key, b->key);
}

static size_t load_kv_entries(fdb_kvdb_t db, struct kv_entry *entries, size_t capacity)
{
    struct fdb_kv_iterator iterator;
    size_t count = 0;

    fdb_kv_iterator_init(db, &iterator);
    while (count < capacity && fdb_kv_iterate(db, &iterator)) {
        struct fdb_blob blob;
        char value[ORACLE_MAX_FIELD] = {0};
        size_t read_len;
        fdb_kv_t kv = &iterator.curr_kv;

        fdb_blob_make(&blob, value, sizeof(value) - 1);
        read_len = fdb_blob_read((fdb_db_t)db, fdb_kv_to_blob(kv, &blob));
        value[read_len < sizeof(value) ? read_len : sizeof(value) - 1] = '\0';
        snprintf(entries[count].key, sizeof(entries[count].key), "%s", kv->name);
        snprintf(entries[count].value, sizeof(entries[count].value), "%s", value);
        count++;
    }
    qsort(entries, count, sizeof(entries[0]), kv_entry_cmp);
    return count;
}

static void step_begin(bool *first, const char *id, const char *op, const char *status, const char *code)
{
    if (!*first) {
        putchar(',');
    }
    *first = false;
    fputs("{\"id\":", stdout);
    json_string(id);
    fputs(",\"op\":", stdout);
    json_string(op);
    fputs(",\"status\":", stdout);
    json_string(status);
    fputs(",\"code\":", stdout);
    json_string(code);
}

static void step_error(bool *first, const struct operation *op, const char *code, const char *message)
{
    step_begin(first, op->id, op->op, "error", code);
    json_field_string("message", message);
    putchar('}');
}

static bool parse_long_field(const struct operation *op, const char *name, const char *value, long *out)
{
    char *end = NULL;

    errno = 0;
    *out = strtol(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0') {
        fprintf(stderr, "operation %s invalid numeric field %s\n", op->id, name);
        return false;
    }
    return true;
}

static bool parse_u64_field(const struct operation *op, const char *name, const char *value, uint64_t *out)
{
    char *end = NULL;
    unsigned long long parsed;

    errno = 0;
    parsed = strtoull(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0') {
        fprintf(stderr, "operation %s invalid numeric field %s\n", op->id, name);
        return false;
    }
    *out = (uint64_t)parsed;
    return true;
}

static bool valid_key_for_rust(const char *key, const char **code, const char **message)
{
    if (key[0] == '\0') {
        *code = "INVALID_KEY";
        *message = "key must not be empty";
        return false;
    }
    if (strlen(key) > 64) {
        *code = "KEY_TOO_LONG";
        *message = "key length exceeds max 64";
        return false;
    }
    return true;
}

static void exec_kv_set(struct oracle_state *state, const struct operation *op, bool *first)
{
    const char *code = NULL;
    const char *message = NULL;
    fdb_err_t err;

    if (!op->has_key || !op->has_value) {
        step_error(first, op, "PARSE", "kv.set requires key and value");
        return;
    }
    if (!valid_key_for_rust(op->key, &code, &message)) {
        step_error(first, op, code, message);
        return;
    }
    err = fdb_kv_set(&state->kvdb, op->key, op->value);
    if (err != FDB_NO_ERR) {
        step_error(first, op, err_name(err), err_name(err));
        return;
    }
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_string("key", op->key);
    json_field_string("value", op->value);
    putchar('}');
}

static void exec_kv_get(struct oracle_state *state, const struct operation *op, bool *first)
{
    const char *code = NULL;
    const char *message = NULL;
    char *value;

    if (!op->has_key) {
        step_error(first, op, "PARSE", "kv.get requires key");
        return;
    }
    if (!valid_key_for_rust(op->key, &code, &message)) {
        step_error(first, op, code, message);
        return;
    }
    value = fdb_kv_get(&state->kvdb, op->key);
    step_begin(first, op->id, op->op, "ok", "OK");
    fputs(",\"value\":", stdout);
    if (value == NULL) {
        fputs("null", stdout);
    } else {
        json_string(value);
    }
    putchar('}');
}

static void exec_kv_delete(struct oracle_state *state, const struct operation *op, bool *first)
{
    const char *code = NULL;
    const char *message = NULL;
    fdb_err_t err;

    if (!op->has_key) {
        step_error(first, op, "PARSE", "kv.delete requires key");
        return;
    }
    if (!valid_key_for_rust(op->key, &code, &message)) {
        step_error(first, op, code, message);
        return;
    }
    err = fdb_kv_del(&state->kvdb, op->key);
    if (err != FDB_NO_ERR) {
        step_error(first, op, err_name(err), err_name(err));
        return;
    }
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_string("key", op->key);
    putchar('}');
}

static void exec_kv_entries(struct oracle_state *state, const struct operation *op, bool *first)
{
    struct kv_entry entries[ORACLE_MAX_ENTRIES];
    size_t count;
    size_t i;

    count = load_kv_entries(&state->kvdb, entries, ORACLE_MAX_ENTRIES);
    step_begin(first, op->id, op->op, "ok", "OK");
    fputs(",\"entries\":[", stdout);
    for (i = 0; i < count; i++) {
        if (i > 0) {
            putchar(',');
        }
        fputs("{\"key\":", stdout);
        json_string(entries[i].key);
        fputs(",\"value\":", stdout);
        json_string(entries[i].value);
        putchar('}');
    }
    fputs("]}", stdout);
}

static void exec_kv_reopen(struct oracle_state *state, const struct operation *op, bool *first)
{
    fdb_err_t err;

    if (state->kv_open) {
        fdb_kvdb_deinit(&state->kvdb);
        state->kv_open = false;
    }
    err = init_kvdb(&state->kvdb, state->kv_dir);
    if (err != FDB_NO_ERR) {
        step_error(first, op, err_name(err), err_name(err));
        return;
