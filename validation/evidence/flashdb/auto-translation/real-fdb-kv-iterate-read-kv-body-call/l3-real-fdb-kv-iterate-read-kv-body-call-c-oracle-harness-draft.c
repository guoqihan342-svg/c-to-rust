/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-read-kv-body-call */
/* function: fdb_kv_iterate_read_kv_body_call_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-read-kv-body-call.json */
/* fixture cases: 3 */
/* observable outputs: return_value, itr_kv_addr_start, body_call_count, body_call_args, external_call_count, external_call_args, call_order */
/* fixture case: failed-address-first input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-read-kv-body-call.json expected_outputs={"body_call_args": [[17, 0]], "body_call_count": 1, "call_order": [1, 2], "external_call_args": [[17, 29, 0]], "external_call_count": 1, "itr_kv_addr_start": 4294967295, "return_value": false} */
/* fixture case: one-kv-then-failed input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-read-kv-body-call.json expected_outputs={"body_call_args": [[3, 99], [3, 4096]], "body_call_count": 2, "call_order": [1, 2, 1, 2], "external_call_args": [[3, 5, 99], [3, 5, 4096]], "external_call_count": 2, "itr_kv_addr_start": 4294967295, "return_value": false} */
/* fixture case: two-kvs-then-failed input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-read-kv-body-call.json expected_outputs={"body_call_args": [[305419896, 17], [305419896, 12288], [305419896, 16384]], "body_call_count": 3, "call_order": [1, 2, 1, 2, 1, 2], "external_call_args": [[305419896, 2271560481, 17], [305419896, 2271560481, 12288], [305419896, 2271560481, 16384]], "external_call_count": 3, "itr_kv_addr_start": 4294967295, "return_value": false} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>
#define FAILED_ADDR ((uint32_t)-1)
struct Database { uint32_t generation; };
struct Sector { uint32_t offset; };
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
typedef struct Kv *fdb_kv_t;
struct Owner { struct Kv current; };
int read_kv(struct Database *db, struct Kv *kv);
uint32_t get_next_kv_addr(struct Database *db, struct Sector *sector, struct Kv *kv);
static bool fdb_kv_iterate_read_kv_body_call_probe(struct Database *db, struct Sector sector_seed, struct Owner *itr)
{
    fdb_kv_t kv = &itr->current;
    struct Sector sector = sector_seed;
    bool run_once = true;
    while (run_once) {
        run_once = false;
        do {
                    read_kv(db, kv);
                } while ((kv->addr.start = get_next_kv_addr(db, &sector, kv)) != FAILED_ADDR);
        return false;
    }
    return true;
}

/* Fixture-only body/tail observers; real external callee semantics are not verified. */
static const uint32_t *c2r_scripted_external_sequence = NULL;
static size_t c2r_scripted_external_sequence_len = 0u;
static size_t c2r_scripted_external_sequence_index = 0u;
static size_t c2r_scripted_external_call_count = 0u;
static uint32_t c2r_scripted_external_call_args[8][3];
static size_t c2r_scripted_body_call_count = 0u;
static uint32_t c2r_scripted_body_call_args[8][2];
static size_t c2r_scripted_call_order_count = 0u;
static uint32_t c2r_scripted_call_order[16];

int read_kv(
    struct Database *db,
    struct Kv *kv)
{
    if (c2r_scripted_body_call_count >= 8u ||
        c2r_scripted_call_order_count >= 16u) {
        fputs("scripted body observer call limit exceeded\n", stderr);
        exit(86);
    }
    c2r_scripted_body_call_args[c2r_scripted_body_call_count][0] = db->generation;
    c2r_scripted_body_call_args[c2r_scripted_body_call_count][1] = kv->addr.start;
    c2r_scripted_body_call_count += 1u;
    c2r_scripted_call_order[c2r_scripted_call_order_count++] = (uint32_t)1u;
    return (int)0u;
}

uint32_t get_next_kv_addr(
    struct Database *db,
    struct Sector *sector,
    struct Kv *kv)
{
    if (c2r_scripted_external_sequence_index >= c2r_scripted_external_sequence_len ||
        c2r_scripted_external_call_count >= 8u ||
        c2r_scripted_call_order_count >= 16u) {
        fputs("scripted external return sequence exhausted\n", stderr);
        exit(86);
    }
    c2r_scripted_external_call_args[c2r_scripted_external_call_count][0] = db->generation;
    c2r_scripted_external_call_args[c2r_scripted_external_call_count][1] = sector->offset;
    c2r_scripted_external_call_args[c2r_scripted_external_call_count][2] = kv->addr.start;
    c2r_scripted_external_call_count += 1u;
    c2r_scripted_call_order[c2r_scripted_call_order_count++] = (uint32_t)2u;
    return c2r_scripted_external_sequence[c2r_scripted_external_sequence_index++];
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_read_kv_body_call_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-read-kv-body-call.json");
  const uint32_t scripted_failed_address_first_sequence[] = { (uint32_t)4294967295u };
  c2r_scripted_external_sequence = scripted_failed_address_first_sequence;
  c2r_scripted_external_sequence_len = sizeof(scripted_failed_address_first_sequence) / sizeof(scripted_failed_address_first_sequence[0]);
  c2r_scripted_external_sequence_index = 0u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_body_call_count = 0u;
  c2r_scripted_call_order_count = 0u;
  struct Database actual_failed_address_first_db = { .generation = (uint32_t)17u };
  struct Sector actual_failed_address_first_sector_seed = { .offset = (uint32_t)29u };
  struct Owner actual_failed_address_first_itr = { .current = { .addr = { .start = (uint32_t)0u } } };
  bool actual_failed_address_first_return = fdb_kv_iterate_read_kv_body_call_probe(&actual_failed_address_first_db, actual_failed_address_first_sector_seed, &actual_failed_address_first_itr);
  if (actual_failed_address_first_return != false) {
    fprintf(stderr, "failed-address-first return mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first return_value matched");
  if (actual_failed_address_first_itr.current.addr.start != (uint32_t)4294967295u) {
    fprintf(stderr, "failed-address-first state mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first itr_kv_addr_start matched");
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
  if (c2r_scripted_external_call_args[0][2] != (uint32_t)0u) {
    fprintf(stderr, "failed-address-first external call args mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first external_call_args matched");
  if (c2r_scripted_body_call_count != (size_t)1u) {
    fprintf(stderr, "failed-address-first body call count mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first body_call_count matched");
  if (c2r_scripted_body_call_args[0][0] != (uint32_t)17u) {
    fprintf(stderr, "failed-address-first body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[0][1] != (uint32_t)0u) {
    fprintf(stderr, "failed-address-first body call args mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first body_call_args matched");
  if (c2r_scripted_call_order_count != (size_t)2u) {
    fprintf(stderr, "failed-address-first call order count mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[0] != (uint32_t)1u) {
    fprintf(stderr, "failed-address-first call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[1] != (uint32_t)2u) {
    fprintf(stderr, "failed-address-first call order mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address-first call_order matched");
  const uint32_t scripted_one_kv_then_failed_sequence[] = { (uint32_t)4096u, (uint32_t)4294967295u };
  c2r_scripted_external_sequence = scripted_one_kv_then_failed_sequence;
  c2r_scripted_external_sequence_len = sizeof(scripted_one_kv_then_failed_sequence) / sizeof(scripted_one_kv_then_failed_sequence[0]);
  c2r_scripted_external_sequence_index = 0u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_body_call_count = 0u;
  c2r_scripted_call_order_count = 0u;
  struct Database actual_one_kv_then_failed_db = { .generation = (uint32_t)3u };
  struct Sector actual_one_kv_then_failed_sector_seed = { .offset = (uint32_t)5u };
  struct Owner actual_one_kv_then_failed_itr = { .current = { .addr = { .start = (uint32_t)99u } } };
  bool actual_one_kv_then_failed_return = fdb_kv_iterate_read_kv_body_call_probe(&actual_one_kv_then_failed_db, actual_one_kv_then_failed_sector_seed, &actual_one_kv_then_failed_itr);
  if (actual_one_kv_then_failed_return != false) {
    fprintf(stderr, "one-kv-then-failed return mismatch\\n");
    return 1;
  }
  puts("fixture case one-kv-then-failed return_value matched");
  if (actual_one_kv_then_failed_itr.current.addr.start != (uint32_t)4294967295u) {
    fprintf(stderr, "one-kv-then-failed state mismatch\\n");
    return 1;
  }
  puts("fixture case one-kv-then-failed itr_kv_addr_start matched");
  if (c2r_scripted_external_call_count != (size_t)2u) {
    fprintf(stderr, "one-kv-then-failed external call count mismatch\\n");
    return 1;
  }
  puts("fixture case one-kv-then-failed external_call_count matched");
  if (c2r_scripted_external_call_args[0][0] != (uint32_t)3u) {
    fprintf(stderr, "one-kv-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][1] != (uint32_t)5u) {
    fprintf(stderr, "one-kv-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][2] != (uint32_t)99u) {
    fprintf(stderr, "one-kv-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][0] != (uint32_t)3u) {
    fprintf(stderr, "one-kv-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][1] != (uint32_t)5u) {
    fprintf(stderr, "one-kv-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][2] != (uint32_t)4096u) {
    fprintf(stderr, "one-kv-then-failed external call args mismatch\\n");
    return 1;
  }
  puts("fixture case one-kv-then-failed external_call_args matched");
  if (c2r_scripted_body_call_count != (size_t)2u) {
    fprintf(stderr, "one-kv-then-failed body call count mismatch\\n");
    return 1;
  }
  puts("fixture case one-kv-then-failed body_call_count matched");
  if (c2r_scripted_body_call_args[0][0] != (uint32_t)3u) {
    fprintf(stderr, "one-kv-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[0][1] != (uint32_t)99u) {
    fprintf(stderr, "one-kv-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[1][0] != (uint32_t)3u) {
    fprintf(stderr, "one-kv-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[1][1] != (uint32_t)4096u) {
    fprintf(stderr, "one-kv-then-failed body call args mismatch\\n");
    return 1;
  }
  puts("fixture case one-kv-then-failed body_call_args matched");
  if (c2r_scripted_call_order_count != (size_t)4u) {
    fprintf(stderr, "one-kv-then-failed call order count mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[0] != (uint32_t)1u) {
    fprintf(stderr, "one-kv-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[1] != (uint32_t)2u) {
    fprintf(stderr, "one-kv-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[2] != (uint32_t)1u) {
    fprintf(stderr, "one-kv-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[3] != (uint32_t)2u) {
    fprintf(stderr, "one-kv-then-failed call order mismatch\\n");
    return 1;
  }
  puts("fixture case one-kv-then-failed call_order matched");
  const uint32_t scripted_two_kvs_then_failed_sequence[] = { (uint32_t)12288u, (uint32_t)16384u, (uint32_t)4294967295u };
  c2r_scripted_external_sequence = scripted_two_kvs_then_failed_sequence;
  c2r_scripted_external_sequence_len = sizeof(scripted_two_kvs_then_failed_sequence) / sizeof(scripted_two_kvs_then_failed_sequence[0]);
  c2r_scripted_external_sequence_index = 0u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_body_call_count = 0u;
  c2r_scripted_call_order_count = 0u;
  struct Database actual_two_kvs_then_failed_db = { .generation = (uint32_t)305419896u };
  struct Sector actual_two_kvs_then_failed_sector_seed = { .offset = (uint32_t)2271560481u };
  struct Owner actual_two_kvs_then_failed_itr = { .current = { .addr = { .start = (uint32_t)17u } } };
  bool actual_two_kvs_then_failed_return = fdb_kv_iterate_read_kv_body_call_probe(&actual_two_kvs_then_failed_db, actual_two_kvs_then_failed_sector_seed, &actual_two_kvs_then_failed_itr);
  if (actual_two_kvs_then_failed_return != false) {
    fprintf(stderr, "two-kvs-then-failed return mismatch\\n");
    return 1;
  }
  puts("fixture case two-kvs-then-failed return_value matched");
  if (actual_two_kvs_then_failed_itr.current.addr.start != (uint32_t)4294967295u) {
    fprintf(stderr, "two-kvs-then-failed state mismatch\\n");
    return 1;
  }
  puts("fixture case two-kvs-then-failed itr_kv_addr_start matched");
  if (c2r_scripted_external_call_count != (size_t)3u) {
    fprintf(stderr, "two-kvs-then-failed external call count mismatch\\n");
    return 1;
  }
  puts("fixture case two-kvs-then-failed external_call_count matched");
  if (c2r_scripted_external_call_args[0][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][1] != (uint32_t)2271560481u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[0][2] != (uint32_t)17u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][1] != (uint32_t)2271560481u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[1][2] != (uint32_t)12288u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[2][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[2][1] != (uint32_t)2271560481u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_external_call_args[2][2] != (uint32_t)16384u) {
    fprintf(stderr, "two-kvs-then-failed external call args mismatch\\n");
    return 1;
  }
  puts("fixture case two-kvs-then-failed external_call_args matched");
  if (c2r_scripted_body_call_count != (size_t)3u) {
    fprintf(stderr, "two-kvs-then-failed body call count mismatch\\n");
    return 1;
  }
  puts("fixture case two-kvs-then-failed body_call_count matched");
  if (c2r_scripted_body_call_args[0][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-kvs-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[0][1] != (uint32_t)17u) {
    fprintf(stderr, "two-kvs-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[1][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-kvs-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[1][1] != (uint32_t)12288u) {
    fprintf(stderr, "two-kvs-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[2][0] != (uint32_t)305419896u) {
    fprintf(stderr, "two-kvs-then-failed body call args mismatch\\n");
    return 1;
  }
  if (c2r_scripted_body_call_args[2][1] != (uint32_t)16384u) {
    fprintf(stderr, "two-kvs-then-failed body call args mismatch\\n");
    return 1;
  }
  puts("fixture case two-kvs-then-failed body_call_args matched");
  if (c2r_scripted_call_order_count != (size_t)6u) {
    fprintf(stderr, "two-kvs-then-failed call order count mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[0] != (uint32_t)1u) {
    fprintf(stderr, "two-kvs-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[1] != (uint32_t)2u) {
    fprintf(stderr, "two-kvs-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[2] != (uint32_t)1u) {
    fprintf(stderr, "two-kvs-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[3] != (uint32_t)2u) {
    fprintf(stderr, "two-kvs-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[4] != (uint32_t)1u) {
    fprintf(stderr, "two-kvs-then-failed call order mismatch\\n");
    return 1;
  }
  if (c2r_scripted_call_order[5] != (uint32_t)2u) {
    fprintf(stderr, "two-kvs-then-failed call order mismatch\\n");
    return 1;
  }
  puts("fixture case two-kvs-then-failed call_order matched");
  return 0;
}
