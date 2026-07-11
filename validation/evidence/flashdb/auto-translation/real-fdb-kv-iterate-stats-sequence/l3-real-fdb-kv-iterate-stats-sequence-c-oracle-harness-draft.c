/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-stats-sequence */
/* function: fdb_kv_iterate_stats_sequence_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-stats-sequence.json */
/* fixture cases: 4 */
/* observable outputs: return_value, itr_iterated_count, itr_iterated_obj_bytes, itr_iterated_value_bytes */
/* fixture case: ordinary input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-stats-sequence.json expected_outputs={"itr_iterated_count": 5, "itr_iterated_obj_bytes": 13, "itr_iterated_value_bytes": 27, "return_value": true} */
/* fixture case: zero-rhs input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-stats-sequence.json expected_outputs={"itr_iterated_count": 9, "itr_iterated_obj_bytes": 42, "itr_iterated_value_bytes": 99, "return_value": true} */
/* fixture case: all-wrap input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-stats-sequence.json expected_outputs={"itr_iterated_count": 0, "itr_iterated_obj_bytes": 1, "itr_iterated_value_bytes": 2, "return_value": true} */
/* fixture case: source-discriminator input_ref=cases[3].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-stats-sequence.json expected_outputs={"itr_iterated_count": 18, "itr_iterated_obj_bytes": 101, "itr_iterated_value_bytes": 209, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
struct FdbKv { uint32_t len; uint32_t value_len; };
typedef struct FdbKv *fdb_kv_t;
struct FdbKvIterator { struct FdbKv curr_kv; uint32_t iterated_cnt; size_t iterated_obj_bytes; size_t iterated_value_bytes; };
static bool fdb_kv_iterate_stats_sequence_probe(struct FdbKvIterator *itr)
{
    fdb_kv_t kv = &itr->curr_kv;
                        itr->iterated_cnt++;
                        itr->iterated_obj_bytes += kv->len;
                        itr->iterated_value_bytes += kv->value_len;
                        return true;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_stats_sequence_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-stats-sequence.json");
  struct FdbKvIterator actual_ordinary_itr = (struct FdbKvIterator){ .iterated_cnt = (uint32_t)4u, .curr_kv = (struct FdbKv){ .len = (uint32_t)3u, .value_len = (uint32_t)7u }, .iterated_obj_bytes = (size_t)10u, .iterated_value_bytes = (size_t)20u };
  uint32_t expected_ordinary_state_0 = actual_ordinary_itr.iterated_cnt + UINT32_C(1);
  if (expected_ordinary_state_0 != (uint32_t)5u) {
    fprintf(stderr, "ordinary declared state 0 mismatch\\n");
    return 1;
  }
  size_t expected_ordinary_state_1 = actual_ordinary_itr.iterated_obj_bytes + (size_t)actual_ordinary_itr.curr_kv.len;
  if (expected_ordinary_state_1 != (size_t)13u) {
    fprintf(stderr, "ordinary declared state 1 mismatch\\n");
    return 1;
  }
  size_t expected_ordinary_state_2 = actual_ordinary_itr.iterated_value_bytes + (size_t)actual_ordinary_itr.curr_kv.value_len;
  if (expected_ordinary_state_2 != (size_t)27u) {
    fprintf(stderr, "ordinary declared state 2 mismatch\\n");
    return 1;
  }
  bool actual_ordinary_return = fdb_kv_iterate_stats_sequence_probe(&actual_ordinary_itr);
  if (actual_ordinary_return != true) {
    fprintf(stderr, "ordinary return mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary return_value matched");
  if (actual_ordinary_itr.iterated_cnt != expected_ordinary_state_0) {
    fprintf(stderr, "ordinary state 0 mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary itr_iterated_count matched");
  if (actual_ordinary_itr.iterated_obj_bytes != expected_ordinary_state_1) {
    fprintf(stderr, "ordinary state 1 mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary itr_iterated_obj_bytes matched");
  if (actual_ordinary_itr.iterated_value_bytes != expected_ordinary_state_2) {
    fprintf(stderr, "ordinary state 2 mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary itr_iterated_value_bytes matched");
  struct FdbKvIterator actual_zero_rhs_itr = (struct FdbKvIterator){ .iterated_cnt = (uint32_t)8u, .curr_kv = (struct FdbKv){ .len = (uint32_t)0u, .value_len = (uint32_t)0u }, .iterated_obj_bytes = (size_t)42u, .iterated_value_bytes = (size_t)99u };
  uint32_t expected_zero_rhs_state_0 = actual_zero_rhs_itr.iterated_cnt + UINT32_C(1);
  if (expected_zero_rhs_state_0 != (uint32_t)9u) {
    fprintf(stderr, "zero-rhs declared state 0 mismatch\\n");
    return 1;
  }
  size_t expected_zero_rhs_state_1 = actual_zero_rhs_itr.iterated_obj_bytes + (size_t)actual_zero_rhs_itr.curr_kv.len;
  if (expected_zero_rhs_state_1 != (size_t)42u) {
    fprintf(stderr, "zero-rhs declared state 1 mismatch\\n");
    return 1;
  }
  size_t expected_zero_rhs_state_2 = actual_zero_rhs_itr.iterated_value_bytes + (size_t)actual_zero_rhs_itr.curr_kv.value_len;
  if (expected_zero_rhs_state_2 != (size_t)99u) {
    fprintf(stderr, "zero-rhs declared state 2 mismatch\\n");
    return 1;
  }
  bool actual_zero_rhs_return = fdb_kv_iterate_stats_sequence_probe(&actual_zero_rhs_itr);
  if (actual_zero_rhs_return != true) {
    fprintf(stderr, "zero-rhs return mismatch\\n");
    return 1;
  }
  puts("fixture case zero-rhs return_value matched");
  if (actual_zero_rhs_itr.iterated_cnt != expected_zero_rhs_state_0) {
    fprintf(stderr, "zero-rhs state 0 mismatch\\n");
    return 1;
  }
  puts("fixture case zero-rhs itr_iterated_count matched");
  if (actual_zero_rhs_itr.iterated_obj_bytes != expected_zero_rhs_state_1) {
    fprintf(stderr, "zero-rhs state 1 mismatch\\n");
    return 1;
  }
  puts("fixture case zero-rhs itr_iterated_obj_bytes matched");
  if (actual_zero_rhs_itr.iterated_value_bytes != expected_zero_rhs_state_2) {
    fprintf(stderr, "zero-rhs state 2 mismatch\\n");
    return 1;
  }
  puts("fixture case zero-rhs itr_iterated_value_bytes matched");
  struct FdbKvIterator actual_all_wrap_itr = (struct FdbKvIterator){ .iterated_cnt = (uint32_t)4294967295u, .curr_kv = (struct FdbKv){ .len = (uint32_t)3u, .value_len = (uint32_t)5u }, .iterated_obj_bytes = (size_t)18446744073709551614u, .iterated_value_bytes = (size_t)18446744073709551613u };
  uint32_t expected_all_wrap_state_0 = actual_all_wrap_itr.iterated_cnt + UINT32_C(1);
  if (expected_all_wrap_state_0 != (uint32_t)0u) {
    fprintf(stderr, "all-wrap declared state 0 mismatch\\n");
    return 1;
  }
  size_t expected_all_wrap_state_1 = actual_all_wrap_itr.iterated_obj_bytes + (size_t)actual_all_wrap_itr.curr_kv.len;
  if (expected_all_wrap_state_1 != (size_t)1u) {
    fprintf(stderr, "all-wrap declared state 1 mismatch\\n");
    return 1;
  }
  size_t expected_all_wrap_state_2 = actual_all_wrap_itr.iterated_value_bytes + (size_t)actual_all_wrap_itr.curr_kv.value_len;
  if (expected_all_wrap_state_2 != (size_t)2u) {
    fprintf(stderr, "all-wrap declared state 2 mismatch\\n");
    return 1;
  }
  bool actual_all_wrap_return = fdb_kv_iterate_stats_sequence_probe(&actual_all_wrap_itr);
  if (actual_all_wrap_return != true) {
    fprintf(stderr, "all-wrap return mismatch\\n");
    return 1;
  }
  puts("fixture case all-wrap return_value matched");
  if (actual_all_wrap_itr.iterated_cnt != expected_all_wrap_state_0) {
    fprintf(stderr, "all-wrap state 0 mismatch\\n");
    return 1;
  }
  puts("fixture case all-wrap itr_iterated_count matched");
  if (actual_all_wrap_itr.iterated_obj_bytes != expected_all_wrap_state_1) {
    fprintf(stderr, "all-wrap state 1 mismatch\\n");
    return 1;
  }
  puts("fixture case all-wrap itr_iterated_obj_bytes matched");
  if (actual_all_wrap_itr.iterated_value_bytes != expected_all_wrap_state_2) {
    fprintf(stderr, "all-wrap state 2 mismatch\\n");
    return 1;
  }
  puts("fixture case all-wrap itr_iterated_value_bytes matched");
  struct FdbKvIterator actual_source_discriminator_itr = (struct FdbKvIterator){ .iterated_cnt = (uint32_t)17u, .curr_kv = (struct FdbKv){ .len = (uint32_t)1u, .value_len = (uint32_t)9u }, .iterated_obj_bytes = (size_t)100u, .iterated_value_bytes = (size_t)200u };
  uint32_t expected_source_discriminator_state_0 = actual_source_discriminator_itr.iterated_cnt + UINT32_C(1);
  if (expected_source_discriminator_state_0 != (uint32_t)18u) {
    fprintf(stderr, "source-discriminator declared state 0 mismatch\\n");
    return 1;
  }
  size_t expected_source_discriminator_state_1 = actual_source_discriminator_itr.iterated_obj_bytes + (size_t)actual_source_discriminator_itr.curr_kv.len;
  if (expected_source_discriminator_state_1 != (size_t)101u) {
    fprintf(stderr, "source-discriminator declared state 1 mismatch\\n");
    return 1;
  }
  size_t expected_source_discriminator_state_2 = actual_source_discriminator_itr.iterated_value_bytes + (size_t)actual_source_discriminator_itr.curr_kv.value_len;
  if (expected_source_discriminator_state_2 != (size_t)209u) {
    fprintf(stderr, "source-discriminator declared state 2 mismatch\\n");
    return 1;
  }
  bool actual_source_discriminator_return = fdb_kv_iterate_stats_sequence_probe(&actual_source_discriminator_itr);
  if (actual_source_discriminator_return != true) {
    fprintf(stderr, "source-discriminator return mismatch\\n");
    return 1;
  }
  puts("fixture case source-discriminator return_value matched");
  if (actual_source_discriminator_itr.iterated_cnt != expected_source_discriminator_state_0) {
    fprintf(stderr, "source-discriminator state 0 mismatch\\n");
    return 1;
  }
  puts("fixture case source-discriminator itr_iterated_count matched");
  if (actual_source_discriminator_itr.iterated_obj_bytes != expected_source_discriminator_state_1) {
    fprintf(stderr, "source-discriminator state 1 mismatch\\n");
    return 1;
  }
  puts("fixture case source-discriminator itr_iterated_obj_bytes matched");
  if (actual_source_discriminator_itr.iterated_value_bytes != expected_source_discriminator_state_2) {
    fprintf(stderr, "source-discriminator state 2 mismatch\\n");
    return 1;
  }
  puts("fixture case source-discriminator itr_iterated_value_bytes matched");
  return 0;
}
