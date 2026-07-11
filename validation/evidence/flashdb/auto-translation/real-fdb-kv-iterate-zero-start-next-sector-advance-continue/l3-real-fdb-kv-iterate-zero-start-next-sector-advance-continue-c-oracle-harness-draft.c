/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-zero-start-next-sector-advance-continue */
/* function: fdb_kv_iterate_zero_start_next_sector_advance_continue_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json */
/* fixture cases: 5 */
/* observable outputs: return_value, call_count, call_db_observed, call_sector_seed, call_alias_start, alias_start_after, owner_traversed_after */
/* fixture case: zero-start-ordinary input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json expected_outputs={"alias_start_after": 124, "call_alias_start": 0, "call_count": 0, "call_db_observed": 0, "call_sector_seed": 0, "owner_traversed_after": 19, "return_value": false} */
/* fixture case: zero-start-u32-wrap input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json expected_outputs={"alias_start_after": 8, "call_alias_start": 0, "call_count": 0, "call_db_observed": 0, "call_sector_seed": 0, "owner_traversed_after": 29, "return_value": false} */
/* fixture case: sentinel-hit input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json expected_outputs={"alias_start_after": 0, "call_alias_start": 36, "call_count": 1, "call_db_observed": 31, "call_sector_seed": 33, "owner_traversed_after": 5, "return_value": true} */
/* fixture case: zero-miss input_ref=cases[3] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json expected_outputs={"alias_start_after": 0, "call_alias_start": 46, "call_count": 1, "call_db_observed": 41, "call_sector_seed": 43, "owner_traversed_after": 47, "return_value": false} */
/* fixture case: ordinary-miss input_ref=cases[4] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json expected_outputs={"alias_start_after": 7, "call_alias_start": 56, "call_count": 1, "call_db_observed": 51, "call_sector_seed": 53, "owner_traversed_after": 57, "return_value": false} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#define FAILED_ADDR ((uint32_t)-1)
#define db_sec_size(db) ((db)->sec_size)
struct Database { uint32_t observed; uint32_t sec_size; };
struct Sector { uint32_t seed; uint32_t addr; };
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
typedef struct Kv *fdb_kv_t;
struct Owner { struct Kv curr; uint32_t traversed_len; };
uint32_t get_next_kv_addr(struct Database *db, struct Sector *sector, struct Kv *kv);
static bool fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(struct Database *db, struct Sector sector_seed, uint32_t SECTOR_HDR_DATA_SIZE, struct Owner *itr)
{
    fdb_kv_t kv = &(itr->curr);
    struct Sector sector = sector_seed;
    bool run_once = true;
    while (run_once) {
        run_once = false;
                if (kv->addr.start == 0) {
                    kv->addr.start = sector.addr + SECTOR_HDR_DATA_SIZE;
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
  puts("oracle harness draft for fdb_kv_iterate_zero_start_next_sector_advance_continue_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json");
  c2r_call_return = 4294967295u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_zero_start_ordinary_db = { .observed = (uint32_t)11u, .sec_size = (uint32_t)7u };
  struct Sector actual_zero_start_ordinary_sector_seed = { .seed = (uint32_t)13u, .addr = (uint32_t)100u };
  uint32_t actual_zero_start_ordinary_SECTOR_HDR_DATA_SIZE = (uint32_t)24u;
  struct Owner actual_zero_start_ordinary_itr = { .curr = { .addr = { .start = (uint32_t)0u } }, .traversed_len = (uint32_t)19u };
  bool actual_zero_start_ordinary_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&actual_zero_start_ordinary_db, actual_zero_start_ordinary_sector_seed, actual_zero_start_ordinary_SECTOR_HDR_DATA_SIZE, &actual_zero_start_ordinary_itr);
  if (actual_zero_start_ordinary_return != false) {
    fprintf(stderr, "zero-start-ordinary return_value mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-ordinary return_value matched");
  if (c2r_call_count != 0u) {
    fprintf(stderr, "zero-start-ordinary call_count mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-ordinary call_count matched");
  if (c2r_call_snapshot_0 != 0u) {
    fprintf(stderr, "zero-start-ordinary call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-ordinary call_db_observed matched");
  if (c2r_call_snapshot_1 != 0u) {
    fprintf(stderr, "zero-start-ordinary call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-ordinary call_sector_seed matched");
  if (c2r_call_snapshot_2 != 0u) {
    fprintf(stderr, "zero-start-ordinary call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-ordinary call_alias_start matched");
  if (actual_zero_start_ordinary_itr.curr.addr.start != 124u) {
    fprintf(stderr, "zero-start-ordinary alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-ordinary alias_start_after matched");
  if (actual_zero_start_ordinary_itr.traversed_len != 19u) {
    fprintf(stderr, "zero-start-ordinary owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-ordinary owner_traversed_after matched");
  c2r_call_return = 0u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_zero_start_u32_wrap_db = { .observed = (uint32_t)21u, .sec_size = (uint32_t)9u };
  struct Sector actual_zero_start_u32_wrap_sector_seed = { .seed = (uint32_t)23u, .addr = (uint32_t)4294967288u };
  uint32_t actual_zero_start_u32_wrap_SECTOR_HDR_DATA_SIZE = (uint32_t)16u;
  struct Owner actual_zero_start_u32_wrap_itr = { .curr = { .addr = { .start = (uint32_t)0u } }, .traversed_len = (uint32_t)29u };
  bool actual_zero_start_u32_wrap_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&actual_zero_start_u32_wrap_db, actual_zero_start_u32_wrap_sector_seed, actual_zero_start_u32_wrap_SECTOR_HDR_DATA_SIZE, &actual_zero_start_u32_wrap_itr);
  if (actual_zero_start_u32_wrap_return != false) {
    fprintf(stderr, "zero-start-u32-wrap return_value mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-u32-wrap return_value matched");
  if (c2r_call_count != 0u) {
    fprintf(stderr, "zero-start-u32-wrap call_count mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-u32-wrap call_count matched");
  if (c2r_call_snapshot_0 != 0u) {
    fprintf(stderr, "zero-start-u32-wrap call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-u32-wrap call_db_observed matched");
  if (c2r_call_snapshot_1 != 0u) {
    fprintf(stderr, "zero-start-u32-wrap call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-u32-wrap call_sector_seed matched");
  if (c2r_call_snapshot_2 != 0u) {
    fprintf(stderr, "zero-start-u32-wrap call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-u32-wrap call_alias_start matched");
  if (actual_zero_start_u32_wrap_itr.curr.addr.start != 8u) {
    fprintf(stderr, "zero-start-u32-wrap alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-u32-wrap alias_start_after matched");
  if (actual_zero_start_u32_wrap_itr.traversed_len != 29u) {
    fprintf(stderr, "zero-start-u32-wrap owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-start-u32-wrap owner_traversed_after matched");
  c2r_call_return = 4294967295u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_sentinel_hit_db = { .observed = (uint32_t)31u, .sec_size = (uint32_t)9u };
  struct Sector actual_sentinel_hit_sector_seed = { .seed = (uint32_t)33u, .addr = (uint32_t)34u };
  uint32_t actual_sentinel_hit_SECTOR_HDR_DATA_SIZE = (uint32_t)35u;
  struct Owner actual_sentinel_hit_itr = { .curr = { .addr = { .start = (uint32_t)36u } }, .traversed_len = (uint32_t)4294967292u };
  bool actual_sentinel_hit_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&actual_sentinel_hit_db, actual_sentinel_hit_sector_seed, actual_sentinel_hit_SECTOR_HDR_DATA_SIZE, &actual_sentinel_hit_itr);
  if (actual_sentinel_hit_return != true) {
    fprintf(stderr, "sentinel-hit return_value mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit return_value matched");
  if (c2r_call_count != 1u) {
    fprintf(stderr, "sentinel-hit call_count mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit call_count matched");
  if (c2r_call_snapshot_0 != 31u) {
    fprintf(stderr, "sentinel-hit call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit call_db_observed matched");
  if (c2r_call_snapshot_1 != 33u) {
    fprintf(stderr, "sentinel-hit call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit call_sector_seed matched");
  if (c2r_call_snapshot_2 != 36u) {
    fprintf(stderr, "sentinel-hit call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit call_alias_start matched");
  if (actual_sentinel_hit_itr.curr.addr.start != 0u) {
    fprintf(stderr, "sentinel-hit alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit alias_start_after matched");
  if (actual_sentinel_hit_itr.traversed_len != 5u) {
    fprintf(stderr, "sentinel-hit owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case sentinel-hit owner_traversed_after matched");
  c2r_call_return = 0u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_zero_miss_db = { .observed = (uint32_t)41u, .sec_size = (uint32_t)42u };
  struct Sector actual_zero_miss_sector_seed = { .seed = (uint32_t)43u, .addr = (uint32_t)44u };
  uint32_t actual_zero_miss_SECTOR_HDR_DATA_SIZE = (uint32_t)45u;
  struct Owner actual_zero_miss_itr = { .curr = { .addr = { .start = (uint32_t)46u } }, .traversed_len = (uint32_t)47u };
  bool actual_zero_miss_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&actual_zero_miss_db, actual_zero_miss_sector_seed, actual_zero_miss_SECTOR_HDR_DATA_SIZE, &actual_zero_miss_itr);
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
  if (c2r_call_snapshot_0 != 41u) {
    fprintf(stderr, "zero-miss call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss call_db_observed matched");
  if (c2r_call_snapshot_1 != 43u) {
    fprintf(stderr, "zero-miss call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss call_sector_seed matched");
  if (c2r_call_snapshot_2 != 46u) {
    fprintf(stderr, "zero-miss call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss call_alias_start matched");
  if (actual_zero_miss_itr.curr.addr.start != 0u) {
    fprintf(stderr, "zero-miss alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss alias_start_after matched");
  if (actual_zero_miss_itr.traversed_len != 47u) {
    fprintf(stderr, "zero-miss owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case zero-miss owner_traversed_after matched");
  c2r_call_return = 7u;
  c2r_call_count = 0u;
  c2r_call_snapshot_0 = 0u;
  c2r_call_snapshot_1 = 0u;
  c2r_call_snapshot_2 = 0u;
  struct Database actual_ordinary_miss_db = { .observed = (uint32_t)51u, .sec_size = (uint32_t)52u };
  struct Sector actual_ordinary_miss_sector_seed = { .seed = (uint32_t)53u, .addr = (uint32_t)54u };
  uint32_t actual_ordinary_miss_SECTOR_HDR_DATA_SIZE = (uint32_t)55u;
  struct Owner actual_ordinary_miss_itr = { .curr = { .addr = { .start = (uint32_t)56u } }, .traversed_len = (uint32_t)57u };
  bool actual_ordinary_miss_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&actual_ordinary_miss_db, actual_ordinary_miss_sector_seed, actual_ordinary_miss_SECTOR_HDR_DATA_SIZE, &actual_ordinary_miss_itr);
  if (actual_ordinary_miss_return != false) {
    fprintf(stderr, "ordinary-miss return_value mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-miss return_value matched");
  if (c2r_call_count != 1u) {
    fprintf(stderr, "ordinary-miss call_count mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-miss call_count matched");
  if (c2r_call_snapshot_0 != 51u) {
    fprintf(stderr, "ordinary-miss call_db_observed mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-miss call_db_observed matched");
  if (c2r_call_snapshot_1 != 53u) {
    fprintf(stderr, "ordinary-miss call_sector_seed mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-miss call_sector_seed matched");
  if (c2r_call_snapshot_2 != 56u) {
    fprintf(stderr, "ordinary-miss call_alias_start mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-miss call_alias_start matched");
  if (actual_ordinary_miss_itr.curr.addr.start != 7u) {
    fprintf(stderr, "ordinary-miss alias_start_after mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-miss alias_start_after matched");
  if (actual_ordinary_miss_itr.traversed_len != 57u) {
    fprintf(stderr, "ordinary-miss owner_traversed_after mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-miss owner_traversed_after matched");
  return 0;
}
