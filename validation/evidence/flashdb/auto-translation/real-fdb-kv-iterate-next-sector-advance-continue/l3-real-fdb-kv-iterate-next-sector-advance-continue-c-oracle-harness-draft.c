/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-next-sector-advance-continue */
/* function: fdb_kv_iterate_next_sector_advance_continue_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-next-sector-advance-continue.json */
/* fixture cases: 4 */
/* observable outputs: return_value, call_count, call_db_observed, call_sector_seed, call_alias_start, alias_start_after, owner_traversed_after */
/* fixture case: sentinel-hit-ordinary input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-next-sector-advance-continue.json expected_outputs={"alias_start_after": 0, "call_alias_start": 99, "call_count": 1, "call_db_observed": 41, "call_sector_seed": 23, "owner_traversed_after": 17, "return_value": true} */
/* fixture case: sentinel-hit-u32-wrap input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-next-sector-advance-continue.json expected_outputs={"alias_start_after": 0, "call_alias_start": 1, "call_count": 1, "call_db_observed": 4294967295, "call_sector_seed": 0, "owner_traversed_after": 3, "return_value": true} */
/* fixture case: zero-miss input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-next-sector-advance-continue.json expected_outputs={"alias_start_after": 0, "call_alias_start": 77, "call_count": 1, "call_db_observed": 17, "call_sector_seed": 31, "owner_traversed_after": 100, "return_value": false} */
/* fixture case: ordinary-nonzero-miss input_ref=cases[3] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-next-sector-advance-continue.json expected_outputs={"alias_start_after": 7, "call_alias_start": 88, "call_count": 1, "call_db_observed": 3, "call_sector_seed": 44, "owner_traversed_after": 200, "return_value": false} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#define FAILED_ADDR ((uint32_t)-1)
#define db_sec_size(db) ((db)->sec_size)
struct Database { uint32_t observed; uint32_t sec_size; };
struct Sector { uint32_t seed; };
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
typedef struct Kv *fdb_kv_t;
struct Owner { struct Kv curr; uint32_t traversed_len; };
uint32_t get_next_kv_addr(struct Database *db, struct Sector *sector, struct Kv *kv);
static bool fdb_kv_iterate_next_sector_advance_continue_probe(struct Database *db, struct Sector sector_seed, struct Owner *itr)
{
    fdb_kv_t kv = &(itr->curr);
    struct Sector sector = sector_seed;
    bool run_once = true;
    while (run_once) {
        run_once = false;
        if (0) {
                } else if ((kv->addr.start = get_next_kv_addr(db, &sector, kv)) == FAILED_ADDR) {
                    kv->addr.start = 0;
                    itr->traversed_len += db_sec_size(db);
                    continue;
        }
        return false;
    }
    return true;
}

/* Fixture-only scripted external; real callee semantics are not verified. */
static uint32_t c2r_call_return = 0u;
static size_t c2r_call_count = 0u;
static uint32_t c2r_call_snapshot_0 = 0u;
static uint32_t c2r_call_snapshot_1 = 0u;
static uint32_t c2r_call_snapshot_2 = 0u;

uint32_t get_next_kv_addr(
    struct Database *db,
    struct Sector *sector,
    struct Kv *kv)
{
    c2r_call_count += 1u;
    c2r_call_snapshot_0 = db->observed;
    c2r_call_snapshot_1 = sector->seed;
    c2r_call_snapshot_2 = kv->addr.start;
    return c2r_call_return;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_next_sector_advance_continue_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-next-sector-advance-continue.json");
  c2r_call_return = 4294967295u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_sentinel_hit_ordinary_db = { .observed = (uint32_t)41u, .sec_size = (uint32_t)7u };
  struct Sector actual_sentinel_hit_ordinary_sector_seed = { .seed = (uint32_t)23u };
  struct Owner actual_sentinel_hit_ordinary_itr = { .curr = { .addr = { .start = (uint32_t)99u } }, .traversed_len = (uint32_t)10u };
  bool actual_sentinel_hit_ordinary_return = fdb_kv_iterate_next_sector_advance_continue_probe(&actual_sentinel_hit_ordinary_db, actual_sentinel_hit_ordinary_sector_seed, &actual_sentinel_hit_ordinary_itr);
  if (actual_sentinel_hit_ordinary_return != true) {
    fprintf(stderr, "sentinel-hit-ordinary return_value mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-ordinary return_value matched");
  if (c2r_call_count != 1u) {
    fprintf(stderr, "sentinel-hit-ordinary call_count mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-ordinary call_count matched");
  if (c2r_call_snapshot_0 != 41u) {
    fprintf(stderr, "sentinel-hit-ordinary call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-ordinary call_db_observed matched");
  if (c2r_call_snapshot_1 != 23u) {
    fprintf(stderr, "sentinel-hit-ordinary call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-ordinary call_sector_seed matched");
  if (c2r_call_snapshot_2 != 99u) {
    fprintf(stderr, "sentinel-hit-ordinary call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-ordinary call_alias_start matched");
  if (actual_sentinel_hit_ordinary_itr.curr.addr.start != 0u) {
    fprintf(stderr, "sentinel-hit-ordinary alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-ordinary alias_start_after matched");
  if (actual_sentinel_hit_ordinary_itr.traversed_len != 17u) {
    fprintf(stderr, "sentinel-hit-ordinary owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-ordinary owner_traversed_after matched");
  c2r_call_return = 4294967295u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_sentinel_hit_u32_wrap_db = { .observed = (uint32_t)4294967295u, .sec_size = (uint32_t)5u };
  struct Sector actual_sentinel_hit_u32_wrap_sector_seed = { .seed = (uint32_t)0u };
  struct Owner actual_sentinel_hit_u32_wrap_itr = { .curr = { .addr = { .start = (uint32_t)1u } }, .traversed_len = (uint32_t)4294967294u };
  bool actual_sentinel_hit_u32_wrap_return = fdb_kv_iterate_next_sector_advance_continue_probe(&actual_sentinel_hit_u32_wrap_db, actual_sentinel_hit_u32_wrap_sector_seed, &actual_sentinel_hit_u32_wrap_itr);
  if (actual_sentinel_hit_u32_wrap_return != true) {
    fprintf(stderr, "sentinel-hit-u32-wrap return_value mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-u32-wrap return_value matched");
  if (c2r_call_count != 1u) {
    fprintf(stderr, "sentinel-hit-u32-wrap call_count mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-u32-wrap call_count matched");
  if (c2r_call_snapshot_0 != 4294967295u) {
    fprintf(stderr, "sentinel-hit-u32-wrap call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-u32-wrap call_db_observed matched");
  if (c2r_call_snapshot_1 != 0u) {
    fprintf(stderr, "sentinel-hit-u32-wrap call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-u32-wrap call_sector_seed matched");
  if (c2r_call_snapshot_2 != 1u) {
    fprintf(stderr, "sentinel-hit-u32-wrap call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-u32-wrap call_alias_start matched");
  if (actual_sentinel_hit_u32_wrap_itr.curr.addr.start != 0u) {
    fprintf(stderr, "sentinel-hit-u32-wrap alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-u32-wrap alias_start_after matched");
  if (actual_sentinel_hit_u32_wrap_itr.traversed_len != 3u) {
    fprintf(stderr, "sentinel-hit-u32-wrap owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit-u32-wrap owner_traversed_after matched");
  c2r_call_return = 0u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_zero_miss_db = { .observed = (uint32_t)17u, .sec_size = (uint32_t)9u };
  struct Sector actual_zero_miss_sector_seed = { .seed = (uint32_t)31u };
  struct Owner actual_zero_miss_itr = { .curr = { .addr = { .start = (uint32_t)77u } }, .traversed_len = (uint32_t)100u };
  bool actual_zero_miss_return = fdb_kv_iterate_next_sector_advance_continue_probe(&actual_zero_miss_db, actual_zero_miss_sector_seed, &actual_zero_miss_itr);
  if (actual_zero_miss_return != false) {
    fprintf(stderr, "zero-miss return_value mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss return_value matched");
  if (c2r_call_count != 1u) {
    fprintf(stderr, "zero-miss call_count mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss call_count matched");
  if (c2r_call_snapshot_0 != 17u) {
    fprintf(stderr, "zero-miss call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss call_db_observed matched");
  if (c2r_call_snapshot_1 != 31u) {
    fprintf(stderr, "zero-miss call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss call_sector_seed matched");
  if (c2r_call_snapshot_2 != 77u) {
    fprintf(stderr, "zero-miss call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss call_alias_start matched");
  if (actual_zero_miss_itr.curr.addr.start != 0u) {
    fprintf(stderr, "zero-miss alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss alias_start_after matched");
  if (actual_zero_miss_itr.traversed_len != 100u) {
    fprintf(stderr, "zero-miss owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss owner_traversed_after matched");
  c2r_call_return = 7u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_ordinary_nonzero_miss_db = { .observed = (uint32_t)3u, .sec_size = (uint32_t)11u };
  struct Sector actual_ordinary_nonzero_miss_sector_seed = { .seed = (uint32_t)44u };
  struct Owner actual_ordinary_nonzero_miss_itr = { .curr = { .addr = { .start = (uint32_t)88u } }, .traversed_len = (uint32_t)200u };
  bool actual_ordinary_nonzero_miss_return = fdb_kv_iterate_next_sector_advance_continue_probe(&actual_ordinary_nonzero_miss_db, actual_ordinary_nonzero_miss_sector_seed, &actual_ordinary_nonzero_miss_itr);
  if (actual_ordinary_nonzero_miss_return != false) {
    fprintf(stderr, "ordinary-nonzero-miss return_value mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-nonzero-miss return_value matched");
  if (c2r_call_count != 1u) {
    fprintf(stderr, "ordinary-nonzero-miss call_count mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-nonzero-miss call_count matched");
  if (c2r_call_snapshot_0 != 3u) {
    fprintf(stderr, "ordinary-nonzero-miss call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-nonzero-miss call_db_observed matched");
  if (c2r_call_snapshot_1 != 44u) {
    fprintf(stderr, "ordinary-nonzero-miss call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-nonzero-miss call_sector_seed matched");
  if (c2r_call_snapshot_2 != 88u) {
    fprintf(stderr, "ordinary-nonzero-miss call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-nonzero-miss call_alias_start matched");
  if (actual_ordinary_nonzero_miss_itr.curr.addr.start != 7u) {
    fprintf(stderr, "ordinary-nonzero-miss alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-nonzero-miss alias_start_after matched");
  if (actual_ordinary_nonzero_miss_itr.traversed_len != 200u) {
    fprintf(stderr, "ordinary-nonzero-miss owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-nonzero-miss owner_traversed_after matched");
  return 0;
}
