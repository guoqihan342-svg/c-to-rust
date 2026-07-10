/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-sector-tail */
/* function: fdb_kv_iterate_sector_tail_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-tail.json */
/* fixture cases: 3 */
/* observable outputs: return_value, itr_sector_addr, external_call_count, external_call_args */
/* fixture case: failed-address-first input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-tail.json expected_outputs={"external_call_args": [[17, 29, 41]], "external_call_count": 1, "itr_sector_addr": 4294967295, "return_value": true} */
/* fixture case: one-sector-then-failed input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-tail.json expected_outputs={"external_call_args": [[3, 5, 7], [3, 5, 7]], "external_call_count": 2, "itr_sector_addr": 4294967295, "return_value": true} */
/* fixture case: two-sectors-then-failed input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-tail.json expected_outputs={"external_call_args": [[305419896, 2271560481, 8192], [305419896, 2271560481, 8192], [305419896, 2271560481, 8192]], "external_call_count": 3, "itr_sector_addr": 4294967295, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#include <stdlib.h>
#define FAILED_ADDR ((uint32_t)-1)
struct Database { uint32_t generation; };
struct Sector { uint32_t offset; };
struct FdbKvIterator { uint32_t sector_addr; uint32_t traversed_len; };
uint32_t get_next_sector_addr(struct Database *db, struct Sector *sector, uint32_t traversed_len);
static bool fdb_kv_iterate_sector_tail_probe(struct Database *db, struct Sector sector_seed, struct FdbKvIterator *itr)
{
    struct Sector sector = sector_seed;
    do {
    } while ((itr->sector_addr = get_next_sector_addr(db, &sector, itr->traversed_len)) != FAILED_ADDR);
    return true;
}

/* Fixture-only finite scripted sequence; real external callee semantics are not verified. */
static const uint32_t *c2r_scripted_external_sequence = NULL;
static size_t c2r_scripted_external_sequence_len = 0u;
static size_t c2r_scripted_external_sequence_index = 0u;
static size_t c2r_scripted_external_call_count = 0u;
static uint32_t c2r_scripted_external_call_args[8][3];

uint32_t get_next_sector_addr(
    struct Database *db,
    struct Sector *sector,
    uint32_t traversed_len)
{
    if (c2r_scripted_external_sequence_index >= c2r_scripted_external_sequence_len ||
        c2r_scripted_external_call_count >= 8u) {
        fputs("scripted external return sequence exhausted\n", stderr);
        exit(86);
    }
    c2r_scripted_external_call_args[c2r_scripted_external_call_count][0] = db->generation;
    c2r_scripted_external_call_args[c2r_scripted_external_call_count][1] = sector->offset;
    c2r_scripted_external_call_args[c2r_scripted_external_call_count][2] = traversed_len;
    c2r_scripted_external_call_count += 1u;
    return c2r_scripted_external_sequence[c2r_scripted_external_sequence_index++];
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_sector_tail_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-tail.json");
  const uint32_t scripted_failed_address_first_sequence[] = { (uint32_t)4294967295u };
  c2r_scripted_external_sequence = scripted_failed_address_first_sequence;
  c2r_scripted_external_sequence_len = sizeof(scripted_failed_address_first_sequence) / sizeof(scripted_failed_address_first_sequence[0]);
  c2r_scripted_external_sequence_index = 0u;
  c2r_scripted_external_call_count = 0u;
  struct Database actual_failed_address_first_db = { .generation = (uint32_t)17u };
  struct Sector actual_failed_address_first_sector_seed = { .offset = (uint32_t)29u };
  struct FdbKvIterator actual_failed_address_first_itr = { .sector_addr = (uint32_t)0u, .traversed_len = (uint32_t)41u };
  bool actual_failed_address_first_return = fdb_kv_iterate_sector_tail_probe(&actual_failed_address_first_db, actual_failed_address_first_sector_seed, &actual_failed_address_first_itr);
  if (actual_failed_address_first_return != true) {
    fprintf(stderr, "failed-address-first return mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first return_value matched");
  if (actual_failed_address_first_itr.sector_addr != (uint32_t)4294967295u) {
    fprintf(stderr, "failed-address-first state mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first itr_sector_addr matched");
  if (c2r_scripted_external_call_count != (size_t)1u) {
    fprintf(stderr, "failed-address-first external call count mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first external_call_count matched");
  if (c2r_scripted_external_call_args[0][0] != (uint32_t)17u) {
    fprintf(stderr, "failed-address-first external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][1] != (uint32_t)29u) {
    fprintf(stderr, "failed-address-first external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][2] != (uint32_t)41u) {
    fprintf(stderr, "failed-address-first external call args mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first external_call_args matched");
  const uint32_t scripted_one_sector_then_failed_sequence[] = { (uint32_t)4096u, (uint32_t)4294967295u };
  c2r_scripted_external_sequence = scripted_one_sector_then_failed_sequence;
  c2r_scripted_external_sequence_len = sizeof(scripted_one_sector_then_failed_sequence) / sizeof(scripted_one_sector_then_failed_sequence[0]);
  c2r_scripted_external_sequence_index = 0u;
  c2r_scripted_external_call_count = 0u;
  struct Database actual_one_sector_then_failed_db = { .generation = (uint32_t)3u };
  struct Sector actual_one_sector_then_failed_sector_seed = { .offset = (uint32_t)5u };
  struct FdbKvIterator actual_one_sector_then_failed_itr = { .sector_addr = (uint32_t)99u, .traversed_len = (uint32_t)7u };
  bool actual_one_sector_then_failed_return = fdb_kv_iterate_sector_tail_probe(&actual_one_sector_then_failed_db, actual_one_sector_then_failed_sector_seed, &actual_one_sector_then_failed_itr);
  if (actual_one_sector_then_failed_return != true) {
    fprintf(stderr, "one-sector-then-failed return mismatch\\n");
    return 1;
  }
  puts("fixture case one-sector-then-failed return_value matched");
  if (actual_one_sector_then_failed_itr.sector_addr != (uint32_t)4294967295u) {
    fprintf(stderr, "one-sector-then-failed state mismatch\\n");
    return 1;
  }
  puts("fixture case one-sector-then-failed itr_sector_addr matched");
  if (c2r_scripted_external_call_count != (size_t)2u) {
    fprintf(stderr, "one-sector-then-failed external call count mismatch\\n");
    return 1;
  }
  puts("fixture case one-sector-then-failed external_call_count matched");
  if (c2r_scripted_external_call_args[0][0] != (uint32_t)3u) {
    fprintf(stderr, "one-sector-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][1] != (uint32_t)5u) {
    fprintf(stderr, "one-sector-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][2] != (uint32_t)7u) {
    fprintf(stderr, "one-sector-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][0] != (uint32_t)3u) {
    fprintf(stderr, "one-sector-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][1] != (uint32_t)5u) {
    fprintf(stderr, "one-sector-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][2] != (uint32_t)7u) {
    fprintf(stderr, "one-sector-then-failed external call args mismatch\\n");
    return 1;
  }
  puts("fixture case one-sector-then-failed external_call_args matched");
  const uint32_t scripted_two_sectors_then_failed_sequence[] = { (uint32_t)12288u, (uint32_t)16384u, (uint32_t)4294967295u };
  c2r_scripted_external_sequence = scripted_two_sectors_then_failed_sequence;
  c2r_scripted_external_sequence_len = sizeof(scripted_two_sectors_then_failed_sequence) / sizeof(scripted_two_sectors_then_failed_sequence[0]);
  c2r_scripted_external_sequence_index = 0u;
  c2r_scripted_external_call_count = 0u;
  struct Database actual_two_sectors_then_failed_db = { .generation = (uint32_t)305419896u };
  struct Sector actual_two_sectors_then_failed_sector_seed = { .offset = (uint32_t)2271560481u };
  struct FdbKvIterator actual_two_sectors_then_failed_itr = { .sector_addr = (uint32_t)17u, .traversed_len = (uint32_t)8192u };
  bool actual_two_sectors_then_failed_return = fdb_kv_iterate_sector_tail_probe(&actual_two_sectors_then_failed_db, actual_two_sectors_then_failed_sector_seed, &actual_two_sectors_then_failed_itr);
  if (actual_two_sectors_then_failed_return != true) {
    fprintf(stderr, "two-sectors-then-failed return mismatch\\n");
    return 1;
  }
  puts("fixture case two-sectors-then-failed return_value matched");
  if (actual_two_sectors_then_failed_itr.sector_addr != (uint32_t)4294967295u) {
    fprintf(stderr, "two-sectors-then-failed state mismatch\\n");
    return 1;
  }
  puts("fixture case two-sectors-then-failed itr_sector_addr matched");
  if (c2r_scripted_external_call_count != (size_t)3u) {
    fprintf(stderr, "two-sectors-then-failed external call count mismatch\\n");
    return 1;
  }
  puts("fixture case two-sectors-then-failed external_call_count matched");
  if (c2r_scripted_external_call_args[0][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][1] != (uint32_t)2271560481u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][2] != (uint32_t)8192u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][1] != (uint32_t)2271560481u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][2] != (uint32_t)8192u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[2][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[2][1] != (uint32_t)2271560481u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[2][2] != (uint32_t)8192u) {
    fprintf(stderr, "two-sectors-then-failed external call args mismatch\\n");
    return 1;
  }
  puts("fixture case two-sectors-then-failed external_call_args matched");
  return 0;
}
