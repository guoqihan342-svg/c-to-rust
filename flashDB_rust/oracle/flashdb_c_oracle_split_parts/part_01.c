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
    }
    state->kv_open = true;
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_string("image_hash", "accepted-difference");
    putchar('}');
}

static void exec_kv_image_hash(const struct operation *op, bool *first)
{
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_string("image_hash", "accepted-difference");
    putchar('}');
}

static void exec_ts_append(struct oracle_state *state, const struct operation *op, bool *first)
{
    struct fdb_blob blob;
    fdb_err_t err;
    long timestamp;
    uint64_t entry_id;

    if (!op->has_timestamp || !op->has_value) {
        step_error(first, op, "PARSE", "ts.append requires timestamp and value");
        return;
    }
    if (!parse_long_field(op, "timestamp", op->timestamp, &timestamp)) {
        step_error(first, op, "PARSE", "invalid timestamp");
        return;
    }
    fdb_blob_make(&blob, op->value, strlen(op->value));
    err = fdb_tsl_append_with_ts(&state->tsdb, &blob, (fdb_time_t)timestamp);
    if (err != FDB_NO_ERR) {
        step_error(first, op, err_name(err), err_name(err));
        return;
    }
    entry_id = state->next_ts_entry_id++;
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_u64("entry_id", entry_id);
    json_field_long("timestamp", timestamp);
    json_field_string("value", op->value);
    putchar('}');
}

static void exec_ts_query(struct oracle_state *state, const struct operation *op, bool *first)
{
    struct ts_entry entries[ORACLE_MAX_ENTRIES];
    struct ts_query_ctx ctx;
    long from;
    long to;

    if (!op->has_from || !op->has_to) {
        step_error(first, op, "PARSE", "ts.query requires from and to");
        return;
    }
    if (!parse_long_field(op, "from", op->from, &from) ||
        !parse_long_field(op, "to", op->to, &to)) {
        step_error(first, op, "PARSE", "invalid query range");
        return;
    }

    ctx.db = &state->tsdb;
    ctx.entries = entries;
    ctx.count = load_ts_entries(&state->tsdb, entries, ORACLE_MAX_ENTRIES);
    ctx.first = true;

    step_begin(first, op->id, op->op, "ok", "OK");
    fputs(",\"entries\":[", stdout);
    fdb_tsl_iter_by_time(&state->tsdb, (fdb_time_t)from, (fdb_time_t)to, ts_query_print_cb, &ctx);
    fputs("]}", stdout);
}

static void exec_ts_count_status(struct oracle_state *state, const struct operation *op, bool *first)
{
    fdb_tsl_status_t status;
    long from;
    long to;
    size_t count;

    if (!op->has_from || !op->has_to || !op->has_status) {
        step_error(first, op, "PARSE", "ts.count_status requires from, to, and status");
        return;
    }
    if (!parse_long_field(op, "from", op->from, &from) ||
        !parse_long_field(op, "to", op->to, &to)) {
        step_error(first, op, "PARSE", "invalid count range");
        return;
    }
    if (!parse_ts_status(op->status, &status)) {
        step_error(first, op, "PARSE", "unknown TS status");
        return;
    }

    count = fdb_tsl_query_count(&state->tsdb, (fdb_time_t)from, (fdb_time_t)to, status);
    step_begin(first, op->id, op->op, "ok", "OK");
    printf(",\"count\":%zu", count);
    putchar('}');
}

static void exec_ts_set_status(struct oracle_state *state, const struct operation *op, bool *first)
{
    struct ts_entry entries[ORACLE_MAX_ENTRIES];
    struct ts_find_ctx find_ctx;
    fdb_tsl_status_t status;
    uint64_t entry_id;
    size_t count;
    size_t i;
    fdb_err_t err;

    if (!op->has_entry_id || !op->has_status) {
        step_error(first, op, "PARSE", "ts.set_status requires entry_id and status");
        return;
    }
    if (!parse_u64_field(op, "entry_id", op->entry_id, &entry_id)) {
        step_error(first, op, "PARSE", "invalid entry_id");
        return;
    }
    if (!parse_ts_status(op->status, &status)) {
        step_error(first, op, "PARSE", "unknown TS status");
        return;
    }

    count = load_ts_entries(&state->tsdb, entries, ORACLE_MAX_ENTRIES);
    memset(&find_ctx, 0, sizeof(find_ctx));
    for (i = 0; i < count; i++) {
        if (entries[i].entry_id == entry_id) {
            find_ctx.addr_index = entries[i].addr_index;
            break;
        }
    }
    if (i == count) {
        step_error(first, op, "INVALID_RANGE", "unknown TS entry id");
        return;
    }

    fdb_tsl_iter(&state->tsdb, ts_find_cb, &find_ctx);
    if (!find_ctx.found_it) {
        step_error(first, op, "INVALID_RANGE", "unknown TS entry id");
        return;
    }
    err = fdb_tsl_set_status(&state->tsdb, &find_ctx.found, status);
    if (err != FDB_NO_ERR) {
        step_error(first, op, err_name(err), err_name(err));
        return;
    }
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_u64("entry_id", entry_id);
    json_field_string("ts_status", ts_status_name(status));
    putchar('}');
}

static void exec_ts_reopen(struct oracle_state *state, const struct operation *op, bool *first)
{
    struct ts_entry entries[ORACLE_MAX_ENTRIES];
    fdb_err_t err;
    size_t count;

    if (state->ts_open) {
        fdb_tsdb_deinit(&state->tsdb);
        state->ts_open = false;
    }
    err = init_tsdb(&state->tsdb, state->ts_dir);
    if (err != FDB_NO_ERR) {
        step_error(first, op, err_name(err), err_name(err));
        return;
    }
    state->ts_open = true;
    count = load_ts_entries(&state->tsdb, entries, ORACLE_MAX_ENTRIES);
    state->next_ts_entry_id = (uint64_t)count + 1;
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_string("image_hash", "accepted-difference");
    putchar('}');
}

static void exec_ts_image_hash(const struct operation *op, bool *first)
{
    step_begin(first, op->id, op->op, "ok", "OK");
    json_field_string("image_hash", "accepted-difference");
    putchar('}');
}
