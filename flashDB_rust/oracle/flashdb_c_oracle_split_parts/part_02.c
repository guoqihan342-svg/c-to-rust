static void execute_operation(struct oracle_state *state, const struct operation *op, bool *first)
{
    if (strcmp(op->op, "kv.set") == 0) {
        exec_kv_set(state, op, first);
    } else if (strcmp(op->op, "kv.get") == 0) {
        exec_kv_get(state, op, first);
    } else if (strcmp(op->op, "kv.delete") == 0) {
        exec_kv_delete(state, op, first);
    } else if (strcmp(op->op, "kv.entries") == 0) {
        exec_kv_entries(state, op, first);
    } else if (strcmp(op->op, "kv.compact") == 0 || strcmp(op->op, "kv.image_hash") == 0) {
        exec_kv_image_hash(op, first);
    } else if (strcmp(op->op, "kv.reopen") == 0) {
        exec_kv_reopen(state, op, first);
    } else if (strcmp(op->op, "ts.append") == 0) {
        exec_ts_append(state, op, first);
    } else if (strcmp(op->op, "ts.query") == 0) {
        exec_ts_query(state, op, first);
    } else if (strcmp(op->op, "ts.set_status") == 0) {
        exec_ts_set_status(state, op, first);
    } else if (strcmp(op->op, "ts.count_status") == 0) {
        exec_ts_count_status(state, op, first);
    } else if (strcmp(op->op, "ts.reopen") == 0) {
        exec_ts_reopen(state, op, first);
    } else if (strcmp(op->op, "ts.image_hash") == 0) {
        exec_ts_image_hash(op, first);
    } else {
        step_error(first, op, "CLI", "unknown fixture operation");
    }
}

static void print_accepted_differences(const struct fixture *fixture)
{
    size_t i;

    putchar('[');
    for (i = 0; i < fixture->accepted_count; i++) {
        if (i > 0) {
            putchar(',');
        }
        fputs("{\"id\":", stdout);
        json_string(fixture->accepted[i].id);
        fputs(",\"reason\":", stdout);
        json_string(fixture->accepted[i].reason);
        fputs(",\"fields\":", stdout);
        json_string(fixture->accepted[i].fields);
        putchar('}');
    }
    putchar(']');
}

static int run_fixture(const struct fixture *fixture, const char *work_dir)
{
    struct oracle_state state;
    bool first_step = true;
    size_t i;
    fdb_err_t kv_err;
    fdb_err_t ts_err;

    memset(&state, 0, sizeof(state));
    state.next_ts_entry_id = 1;
    if (prepare_work_dirs(work_dir, state.kv_dir, sizeof(state.kv_dir), state.ts_dir, sizeof(state.ts_dir)) != 0) {
        fprintf(stderr, "failed to prepare oracle work directory: %s\n", work_dir);
        return 1;
    }

    kv_err = init_kvdb(&state.kvdb, state.kv_dir);
    ts_err = init_tsdb(&state.tsdb, state.ts_dir);
    if (kv_err != FDB_NO_ERR || ts_err != FDB_NO_ERR) {
        fprintf(stderr, "failed to initialize FlashDB: kv=%s ts=%s\n", err_name(kv_err), err_name(ts_err));
        return 1;
    }
    state.kv_open = true;
    state.ts_open = true;

    fputs("{\"command\":\"replay\",", stdout);
    fputs("\"schema_version\":1,", stdout);
    fputs("\"fixture\":", stdout);
    json_string(fixture->path);
    fputs(",\"fixture_name\":", stdout);
    json_string(fixture->name);
    fputs(",\"fixture_hash\":", stdout);
    json_string(fixture->hash);
    fputs(",\"backend\":\"flashdb-c\",", stdout);
    fputs("\"toolchain_status\":\"C_ORACLE_GENERATED\",", stdout);
    fputs("\"result\":\"completed\",", stdout);
    fputs("\"source\":{\"clone_url\":", stdout);
    json_string(ORACLE_FLASHDB_URL);
    fputs(",\"commit\":", stdout);
    json_string(ORACLE_FLASHDB_COMMIT);
    printf(",\"sec_size\":%d,\"write_gran\":1,\"file_mode\":\"posix\"},", ORACLE_SEC_SIZE);
    fputs("\"accepted_differences\":", stdout);
    print_accepted_differences(fixture);
    fputs(",\"steps\":[", stdout);

    for (i = 0; i < fixture->op_count; i++) {
        execute_operation(&state, &fixture->ops[i], &first_step);
    }

    fputs("]}\n", stdout);
    fflush(stdout);

    if (state.kv_open) {
        fdb_kvdb_deinit(&state.kvdb);
    }
    if (state.ts_open) {
        fdb_tsdb_deinit(&state.tsdb);
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *fixture_path = NULL;
    const char *work_dir = NULL;
    struct fixture fixture;
    int i;

    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--fixture") == 0 && i + 1 < argc) {
            fixture_path = argv[++i];
        } else if (strcmp(argv[i], "--work-dir") == 0 && i + 1 < argc) {
            work_dir = argv[++i];
        } else {
            fprintf(stderr, "usage: %s --fixture PATH --work-dir DIR\n", argv[0]);
            return 2;
        }
    }

    if (fixture_path == NULL || work_dir == NULL) {
        fprintf(stderr, "usage: %s --fixture PATH --work-dir DIR\n", argv[0]);
        return 2;
    }
    if (load_fixture(fixture_path, &fixture) != 0) {
        return 1;
    }
    return run_fixture(&fixture, work_dir);
}
