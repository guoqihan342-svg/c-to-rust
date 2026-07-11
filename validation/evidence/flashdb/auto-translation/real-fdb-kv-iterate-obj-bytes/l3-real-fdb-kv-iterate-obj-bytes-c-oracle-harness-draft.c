/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-obj-bytes */
/* function: fdb_kv_iterate_obj_bytes_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-obj-bytes.json */
/* fixture cases: 3 */
/* observable outputs: return_value, itr_iterated_obj_bytes */
/* fixture case: ordinary-add input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-obj-bytes.json expected_outputs={"itr_iterated_obj_bytes": 16, "return_value": true} */
/* fixture case: zero-rhs input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-obj-bytes.json expected_outputs={"itr_iterated_obj_bytes": 42, "return_value": true} */
/* fixture case: usize-wrap input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-obj-bytes.json expected_outputs={"itr_iterated_obj_bytes": 1, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
struct FdbKv { uint32_t len; };
typedef struct FdbKv *fdb_kv_t;
struct FdbKvIterator { struct FdbKv curr_kv; size_t iterated_obj_bytes; };
static bool fdb_kv_iterate_obj_bytes_probe(struct FdbKvIterator *itr)
{
    fdb_kv_t kv = &itr->curr_kv;
                        itr->iterated_obj_bytes += kv->len;
    return true;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_obj_bytes_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-obj-bytes.json");
  struct FdbKvIterator actual_ordinary_add_itr = (struct FdbKvIterator){ .curr_kv = (struct FdbKv){ .len = (uint32_t)5u }, .iterated_obj_bytes = (size_t)11u };
  size_t expected_ordinary_add_usize_state = actual_ordinary_add_itr.iterated_obj_bytes + (size_t)actual_ordinary_add_itr.curr_kv.len;
  if (expected_ordinary_add_usize_state != (size_t)16u) {
    fprintf(stderr, "ordinary-add declared usize state mismatch\\n");
    return 1;
  }
  bool actual_ordinary_add_return = fdb_kv_iterate_obj_bytes_probe(&actual_ordinary_add_itr);
  if (actual_ordinary_add_return != true) {
    fprintf(stderr, "ordinary-add return mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-add return_value matched");
  if (actual_ordinary_add_itr.iterated_obj_bytes != expected_ordinary_add_usize_state) {
    fprintf(stderr, "ordinary-add usize state mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-add itr_iterated_obj_bytes matched");
  struct FdbKvIterator actual_zero_rhs_itr = (struct FdbKvIterator){ .curr_kv = (struct FdbKv){ .len = (uint32_t)0u }, .iterated_obj_bytes = (size_t)42u };
  size_t expected_zero_rhs_usize_state = actual_zero_rhs_itr.iterated_obj_bytes + (size_t)actual_zero_rhs_itr.curr_kv.len;
  if (expected_zero_rhs_usize_state != (size_t)42u) {
    fprintf(stderr, "zero-rhs declared usize state mismatch\\n");
    return 1;
  }
  bool actual_zero_rhs_return = fdb_kv_iterate_obj_bytes_probe(&actual_zero_rhs_itr);
  if (actual_zero_rhs_return != true) {
    fprintf(stderr, "zero-rhs return mismatch\\n");
    return 1;
  }
  puts("fixture case zero-rhs return_value matched");
  if (actual_zero_rhs_itr.iterated_obj_bytes != expected_zero_rhs_usize_state) {
    fprintf(stderr, "zero-rhs usize state mismatch\\n");
    return 1;
  }
  puts("fixture case zero-rhs itr_iterated_obj_bytes matched");
  struct FdbKvIterator actual_usize_wrap_itr = (struct FdbKvIterator){ .curr_kv = (struct FdbKv){ .len = (uint32_t)3u }, .iterated_obj_bytes = (size_t)18446744073709551614u };
  size_t expected_usize_wrap_usize_state = actual_usize_wrap_itr.iterated_obj_bytes + (size_t)actual_usize_wrap_itr.curr_kv.len;
  if (expected_usize_wrap_usize_state != (size_t)1u) {
    fprintf(stderr, "usize-wrap declared usize state mismatch\\n");
    return 1;
  }
  bool actual_usize_wrap_return = fdb_kv_iterate_obj_bytes_probe(&actual_usize_wrap_itr);
  if (actual_usize_wrap_return != true) {
    fprintf(stderr, "usize-wrap return mismatch\\n");
    return 1;
  }
  puts("fixture case usize-wrap return_value matched");
  if (actual_usize_wrap_itr.iterated_obj_bytes != expected_usize_wrap_usize_state) {
    fprintf(stderr, "usize-wrap usize state mismatch\\n");
    return 1;
  }
  puts("fixture case usize-wrap itr_iterated_obj_bytes matched");
  return 0;
}
