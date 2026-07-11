/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-iterated-count */
/* function: fdb_kv_iterate_iterated_count_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-iterated-count.json */
/* fixture cases: 3 */
/* observable outputs: return_value, itr_iterated_count */
/* fixture case: zero input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-iterated-count.json expected_outputs={"itr_iterated_count": 1, "return_value": true} */
/* fixture case: ordinary input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-iterated-count.json expected_outputs={"itr_iterated_count": 42, "return_value": true} */
/* fixture case: u32-wrap input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-iterated-count.json expected_outputs={"itr_iterated_count": 0, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#include <stdbool.h>
#include <stdint.h>
struct FdbKvIterator { uint32_t iterated_cnt; };
static bool fdb_kv_iterate_iterated_count_probe(struct FdbKvIterator *itr)
{
                        itr->iterated_cnt++;
    return true;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_iterated_count_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-iterated-count.json");
  struct FdbKvIterator actual_zero_itr = { .iterated_cnt = (uint32_t)0u };
  uint32_t expected_zero_postfix_state = (uint32_t)(actual_zero_itr.iterated_cnt + UINT32_C(1));
  if (expected_zero_postfix_state != (uint32_t)1u) {
    fprintf(stderr, "zero declared postfix state mismatch\\n");
    return 1;
  }
  bool actual_zero_return = fdb_kv_iterate_iterated_count_probe(&actual_zero_itr);
  if (actual_zero_return != true) {
    fprintf(stderr, "zero return mismatch\\n");
    return 1;
  }
  puts("fixture case zero return_value matched");
  if (actual_zero_itr.iterated_cnt != expected_zero_postfix_state) {
    fprintf(stderr, "zero postfix state mismatch\\n");
    return 1;
  }
  puts("fixture case zero itr_iterated_count matched");
  struct FdbKvIterator actual_ordinary_itr = { .iterated_cnt = (uint32_t)41u };
  uint32_t expected_ordinary_postfix_state = (uint32_t)(actual_ordinary_itr.iterated_cnt + UINT32_C(1));
  if (expected_ordinary_postfix_state != (uint32_t)42u) {
    fprintf(stderr, "ordinary declared postfix state mismatch\\n");
    return 1;
  }
  bool actual_ordinary_return = fdb_kv_iterate_iterated_count_probe(&actual_ordinary_itr);
  if (actual_ordinary_return != true) {
    fprintf(stderr, "ordinary return mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary return_value matched");
  if (actual_ordinary_itr.iterated_cnt != expected_ordinary_postfix_state) {
    fprintf(stderr, "ordinary postfix state mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary itr_iterated_count matched");
  struct FdbKvIterator actual_u32_wrap_itr = { .iterated_cnt = (uint32_t)4294967295u };
  uint32_t expected_u32_wrap_postfix_state = (uint32_t)(actual_u32_wrap_itr.iterated_cnt + UINT32_C(1));
  if (expected_u32_wrap_postfix_state != (uint32_t)0u) {
    fprintf(stderr, "u32-wrap declared postfix state mismatch\\n");
    return 1;
  }
  bool actual_u32_wrap_return = fdb_kv_iterate_iterated_count_probe(&actual_u32_wrap_itr);
  if (actual_u32_wrap_return != true) {
    fprintf(stderr, "u32-wrap return mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap return_value matched");
  if (actual_u32_wrap_itr.iterated_cnt != expected_u32_wrap_postfix_state) {
    fprintf(stderr, "u32-wrap postfix state mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap itr_iterated_count matched");
  return 0;
}
