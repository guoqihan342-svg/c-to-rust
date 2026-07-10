/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-traversed-len */
/* function: fdb_kv_iterate_traversed_len_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-traversed-len.json */
/* fixture cases: 3 */
/* observable outputs: return_value, itr_traversed_len */
/* fixture case: first-sector input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-traversed-len.json expected_outputs={"itr_traversed_len": 4096, "return_value": true} */
/* fixture case: accumulated-sectors input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-traversed-len.json expected_outputs={"itr_traversed_len": 12288, "return_value": true} */
/* fixture case: u32-wrap input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-traversed-len.json expected_outputs={"itr_traversed_len": 3, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#define db_sec_size(db) ((db)->sec_size)
struct Database { uint32_t sec_size; };
struct FdbKvIterator { uint32_t traversed_len; };
static bool fdb_kv_iterate_traversed_len_probe(struct Database *db, struct FdbKvIterator *itr)
{
        itr->traversed_len += db_sec_size(db);
    return true;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_traversed_len_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-traversed-len.json");
  struct Database actual_first_sector_db = { .sec_size = (uint32_t)4096u };
  struct FdbKvIterator actual_first_sector_itr = { .traversed_len = (uint32_t)0u };
  uint32_t expected_first_sector_wrapping_state = (uint32_t)(actual_first_sector_itr.traversed_len + actual_first_sector_db.sec_size);
  if (expected_first_sector_wrapping_state != (uint32_t)4096u) {
    fprintf(stderr, "first-sector declared wrapping state mismatch\\n");
    return 1;
  }
  bool actual_first_sector_return = fdb_kv_iterate_traversed_len_probe(&actual_first_sector_db, &actual_first_sector_itr);
  if (actual_first_sector_return != true) {
    fprintf(stderr, "first-sector return mismatch\\n");
    return 1;
  }
  puts("fixture case first-sector return_value matched");
  if (actual_first_sector_itr.traversed_len != expected_first_sector_wrapping_state) {
    fprintf(stderr, "first-sector wrapping state mismatch\\n");
    return 1;
  }
  puts("fixture case first-sector itr_traversed_len matched");
  struct Database actual_accumulated_sectors_db = { .sec_size = (uint32_t)4096u };
  struct FdbKvIterator actual_accumulated_sectors_itr = { .traversed_len = (uint32_t)8192u };
  uint32_t expected_accumulated_sectors_wrapping_state = (uint32_t)(actual_accumulated_sectors_itr.traversed_len + actual_accumulated_sectors_db.sec_size);
  if (expected_accumulated_sectors_wrapping_state != (uint32_t)12288u) {
    fprintf(stderr, "accumulated-sectors declared wrapping state mismatch\\n");
    return 1;
  }
  bool actual_accumulated_sectors_return = fdb_kv_iterate_traversed_len_probe(&actual_accumulated_sectors_db, &actual_accumulated_sectors_itr);
  if (actual_accumulated_sectors_return != true) {
    fprintf(stderr, "accumulated-sectors return mismatch\\n");
    return 1;
  }
  puts("fixture case accumulated-sectors return_value matched");
  if (actual_accumulated_sectors_itr.traversed_len != expected_accumulated_sectors_wrapping_state) {
    fprintf(stderr, "accumulated-sectors wrapping state mismatch\\n");
    return 1;
  }
  puts("fixture case accumulated-sectors itr_traversed_len matched");
  struct Database actual_u32_wrap_db = { .sec_size = (uint32_t)5u };
  struct FdbKvIterator actual_u32_wrap_itr = { .traversed_len = (uint32_t)4294967294u };
  uint32_t expected_u32_wrap_wrapping_state = (uint32_t)(actual_u32_wrap_itr.traversed_len + actual_u32_wrap_db.sec_size);
  if (expected_u32_wrap_wrapping_state != (uint32_t)3u) {
    fprintf(stderr, "u32-wrap declared wrapping state mismatch\\n");
    return 1;
  }
  bool actual_u32_wrap_return = fdb_kv_iterate_traversed_len_probe(&actual_u32_wrap_db, &actual_u32_wrap_itr);
  if (actual_u32_wrap_return != true) {
    fprintf(stderr, "u32-wrap return mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap return_value matched");
  if (actual_u32_wrap_itr.traversed_len != expected_u32_wrap_wrapping_state) {
    fprintf(stderr, "u32-wrap wrapping state mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap itr_traversed_len matched");
  return 0;
}
