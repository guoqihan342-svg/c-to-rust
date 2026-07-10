/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-next */
/* function: fdb_kv_iterate_next_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-next.json */
/* fixture cases: 3 */
/* observable outputs: return_value, kv_addr_start, external_call_count, external_call_args */
/* fixture case: failed-address input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-next.json expected_outputs={"external_call_args": [17, 29, 41], "external_call_count": 1, "kv_addr_start": 4294967295, "return_value": true} */
/* fixture case: zero-address input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-next.json expected_outputs={"external_call_args": [3, 5, 7], "external_call_count": 1, "kv_addr_start": 0, "return_value": false} */
/* fixture case: next-address input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-next.json expected_outputs={"external_call_args": [305419896, 2271560481, 4096], "external_call_count": 1, "kv_addr_start": 8192, "return_value": false} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#define FAILED_ADDR ((uint32_t)-1)
struct Database { uint32_t generation; };
struct Sector { uint32_t offset; };
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
uint32_t get_next_kv_addr(struct Database *db, struct Sector *sector, struct Kv *kv);
static bool fdb_kv_iterate_next_probe(struct Database *db, struct Sector sector_seed, struct Kv *kv)
{
    struct Sector sector = sector_seed;
    bool failed = false;
    if (0) {
                } else if ((kv->addr.start = get_next_kv_addr(db, &sector, kv)) == FAILED_ADDR) {
        failed = true;
    }
    return failed;
}

/* Fixture-only scripted record external; real external callee semantics are not verified. */
static uint32_t c2r_scripted_external_return = 0u;
static size_t c2r_scripted_external_call_count = 0u;
static uint32_t c2r_scripted_external_arg0 = 0u;
static uint32_t c2r_scripted_external_arg1 = 0u;
static uint32_t c2r_scripted_external_arg2 = 0u;

uint32_t get_next_kv_addr(
    struct Database *db,
    struct Sector *sector,
    struct Kv *kv)
{
    c2r_scripted_external_call_count += 1u;
    c2r_scripted_external_arg0 = db->generation;
    c2r_scripted_external_arg1 = sector->offset;
    c2r_scripted_external_arg2 = kv->addr.start;
    return c2r_scripted_external_return;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_next_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-next.json");
  c2r_scripted_external_return = (uint32_t)4294967295u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_external_arg0 = 0u;
  c2r_scripted_external_arg1 = 0u;
  c2r_scripted_external_arg2 = 0u;
  struct Database actual_failed_address_db = { .generation = (uint32_t)17u };
  struct Sector actual_failed_address_sector_seed = { .offset = (uint32_t)29u };
  struct Kv actual_failed_address_kv = { .addr = { .start = (uint32_t)41u } };
  bool actual_failed_address_return = fdb_kv_iterate_next_probe(&actual_failed_address_db, actual_failed_address_sector_seed, &actual_failed_address_kv);
  if (actual_failed_address_return != true) {
    fprintf(stderr, "failed-address return mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address return_value matched");
  if (actual_failed_address_kv.addr.start != (uint32_t)4294967295u) {
    fprintf(stderr, "failed-address state mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address kv_addr_start matched");
  if (c2r_scripted_external_call_count != (size_t)1u) {
    fprintf(stderr, "failed-address external call count mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address external_call_count matched");
  if (      c2r_scripted_external_arg0 != (uint32_t)17u ||
      c2r_scripted_external_arg1 != (uint32_t)29u ||
      c2r_scripted_external_arg2 != (uint32_t)41u) {
    fprintf(stderr, "failed-address external call args mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address external_call_args matched");
  c2r_scripted_external_return = (uint32_t)0u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_external_arg0 = 0u;
  c2r_scripted_external_arg1 = 0u;
  c2r_scripted_external_arg2 = 0u;
  struct Database actual_zero_address_db = { .generation = (uint32_t)3u };
  struct Sector actual_zero_address_sector_seed = { .offset = (uint32_t)5u };
  struct Kv actual_zero_address_kv = { .addr = { .start = (uint32_t)7u } };
  bool actual_zero_address_return = fdb_kv_iterate_next_probe(&actual_zero_address_db, actual_zero_address_sector_seed, &actual_zero_address_kv);
  if (actual_zero_address_return != false) {
    fprintf(stderr, "zero-address return mismatch\\n");
    return 1;
  }
  puts("fixture case zero-address return_value matched");
  if (actual_zero_address_kv.addr.start != (uint32_t)0u) {
    fprintf(stderr, "zero-address state mismatch\\n");
    return 1;
  }
  puts("fixture case zero-address kv_addr_start matched");
  if (c2r_scripted_external_call_count != (size_t)1u) {
    fprintf(stderr, "zero-address external call count mismatch\\n");
    return 1;
  }
  puts("fixture case zero-address external_call_count matched");
  if (      c2r_scripted_external_arg0 != (uint32_t)3u ||
      c2r_scripted_external_arg1 != (uint32_t)5u ||
      c2r_scripted_external_arg2 != (uint32_t)7u) {
    fprintf(stderr, "zero-address external call args mismatch\\n");
    return 1;
  }
  puts("fixture case zero-address external_call_args matched");
  c2r_scripted_external_return = (uint32_t)8192u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_external_arg0 = 0u;
  c2r_scripted_external_arg1 = 0u;
  c2r_scripted_external_arg2 = 0u;
  struct Database actual_next_address_db = { .generation = (uint32_t)305419896u };
  struct Sector actual_next_address_sector_seed = { .offset = (uint32_t)2271560481u };
  struct Kv actual_next_address_kv = { .addr = { .start = (uint32_t)4096u } };
  bool actual_next_address_return = fdb_kv_iterate_next_probe(&actual_next_address_db, actual_next_address_sector_seed, &actual_next_address_kv);
  if (actual_next_address_return != false) {
    fprintf(stderr, "next-address return mismatch\\n");
    return 1;
  }
  puts("fixture case next-address return_value matched");
  if (actual_next_address_kv.addr.start != (uint32_t)8192u) {
    fprintf(stderr, "next-address state mismatch\\n");
    return 1;
  }
  puts("fixture case next-address kv_addr_start matched");
  if (c2r_scripted_external_call_count != (size_t)1u) {
    fprintf(stderr, "next-address external call count mismatch\\n");
    return 1;
  }
  puts("fixture case next-address external_call_count matched");
  if (      c2r_scripted_external_arg0 != (uint32_t)305419896u ||
      c2r_scripted_external_arg1 != (uint32_t)2271560481u ||
      c2r_scripted_external_arg2 != (uint32_t)4096u) {
    fprintf(stderr, "next-address external call args mismatch\\n");
    return 1;
  }
  puts("fixture case next-address external_call_args matched");
  return 0;
}
