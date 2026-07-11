/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-sector-advance-continue */
/* function: fdb_kv_iterate_sector_advance_continue_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-advance-continue.json */
/* fixture cases: 3 */
/* observable outputs: return_value, kv_addr_start, itr_traversed_len */
/* fixture case: ordinary-sector-advance input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-advance-continue.json expected_outputs={"itr_traversed_len": 8192, "kv_addr_start": 0, "return_value": true} */
/* fixture case: zero-sector-size input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-advance-continue.json expected_outputs={"itr_traversed_len": 17, "kv_addr_start": 0, "return_value": true} */
/* fixture case: u32-wrap-and-maximum-address input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-advance-continue.json expected_outputs={"itr_traversed_len": 3, "kv_addr_start": 0, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#define db_sec_size(db) ((db)->sec_size)
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
typedef struct Kv *fdb_kv_t;
struct Database { uint32_t sec_size; };
struct FdbKvIterator { struct Kv curr_kv; uint32_t traversed_len; };
static bool fdb_kv_iterate_sector_advance_continue_probe(const struct Database *db, struct FdbKvIterator *itr)
{
    fdb_kv_t kv = &(itr->curr_kv);
    bool run_once = true;
    while (run_once) {
        run_once = false;
                    kv->addr.start = 0;
                    itr->traversed_len += db_sec_size(db);
                    continue;
        return false;
    }
    return true;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_sector_advance_continue_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-advance-continue.json");
  struct Database actual_ordinary_sector_advance_db = { .sec_size = (uint32_t)4096u };
  struct FdbKvIterator actual_ordinary_sector_advance_itr = { .curr_kv = { .addr = { .start = (uint32_t)8192u } }, .traversed_len = (uint32_t)4096u };
  bool actual_ordinary_sector_advance_return = fdb_kv_iterate_sector_advance_continue_probe(&actual_ordinary_sector_advance_db, &actual_ordinary_sector_advance_itr);
  if (actual_ordinary_sector_advance_return != true) {
    fprintf(stderr, "ordinary-sector-advance return mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-sector-advance return_value matched");
  if (actual_ordinary_sector_advance_itr.curr_kv.addr.start != (uint32_t)0u) {
    fprintf(stderr, "ordinary-sector-advance reset state mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-sector-advance kv_addr_start matched");
  if (actual_ordinary_sector_advance_itr.traversed_len != (uint32_t)8192u) {
    fprintf(stderr, "ordinary-sector-advance add state mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-sector-advance itr_traversed_len matched");
  struct Database actual_zero_sector_size_db = { .sec_size = (uint32_t)0u };
  struct FdbKvIterator actual_zero_sector_size_itr = { .curr_kv = { .addr = { .start = (uint32_t)1u } }, .traversed_len = (uint32_t)17u };
  bool actual_zero_sector_size_return = fdb_kv_iterate_sector_advance_continue_probe(&actual_zero_sector_size_db, &actual_zero_sector_size_itr);
  if (actual_zero_sector_size_return != true) {
    fprintf(stderr, "zero-sector-size return mismatch\\n");
    return 1;
  }
  puts("fixture case zero-sector-size return_value matched");
  if (actual_zero_sector_size_itr.curr_kv.addr.start != (uint32_t)0u) {
    fprintf(stderr, "zero-sector-size reset state mismatch\\n");
    return 1;
  }
  puts("fixture case zero-sector-size kv_addr_start matched");
  if (actual_zero_sector_size_itr.traversed_len != (uint32_t)17u) {
    fprintf(stderr, "zero-sector-size add state mismatch\\n");
    return 1;
  }
  puts("fixture case zero-sector-size itr_traversed_len matched");
  struct Database actual_u32_wrap_and_maximum_address_db = { .sec_size = (uint32_t)5u };
  struct FdbKvIterator actual_u32_wrap_and_maximum_address_itr = { .curr_kv = { .addr = { .start = (uint32_t)4294967295u } }, .traversed_len = (uint32_t)4294967294u };
  bool actual_u32_wrap_and_maximum_address_return = fdb_kv_iterate_sector_advance_continue_probe(&actual_u32_wrap_and_maximum_address_db, &actual_u32_wrap_and_maximum_address_itr);
  if (actual_u32_wrap_and_maximum_address_return != true) {
    fprintf(stderr, "u32-wrap-and-maximum-address return mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap-and-maximum-address return_value matched");
  if (actual_u32_wrap_and_maximum_address_itr.curr_kv.addr.start != (uint32_t)0u) {
    fprintf(stderr, "u32-wrap-and-maximum-address reset state mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap-and-maximum-address kv_addr_start matched");
  if (actual_u32_wrap_and_maximum_address_itr.traversed_len != (uint32_t)3u) {
    fprintf(stderr, "u32-wrap-and-maximum-address add state mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap-and-maximum-address itr_traversed_len matched");
  return 0;
}
