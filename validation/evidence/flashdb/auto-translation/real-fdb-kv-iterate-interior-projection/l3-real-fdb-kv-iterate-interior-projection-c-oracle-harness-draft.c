/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-interior-projection */
/* function: fdb_kv_iterate_projection_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-interior-projection.json */
/* fixture cases: 3 */
/* observable outputs: return_value, kv_addr_start */
/* fixture case: already-zero input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-interior-projection.json expected_outputs={"kv_addr_start": 0, "return_value": true} */
/* fixture case: ordinary-address input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-interior-projection.json expected_outputs={"kv_addr_start": 0, "return_value": true} */
/* fixture case: maximum-address input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-interior-projection.json expected_outputs={"kv_addr_start": 0, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
typedef struct Kv *fdb_kv_t;
struct FdbKvIterator { struct Kv curr_kv; };
static bool fdb_kv_iterate_projection_probe(struct FdbKvIterator *itr)
{
    fdb_kv_t kv = &(itr->curr_kv);
    kv->addr.start = 0;
    return true;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_projection_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-interior-projection.json");
  struct FdbKvIterator actual_already_zero_itr = { .curr_kv = { .addr = { .start = (uint32_t)0u } } };
  bool actual_already_zero_return = fdb_kv_iterate_projection_probe(&actual_already_zero_itr);
  if (actual_already_zero_return != true) {
    fprintf(stderr, "already-zero return mismatch\\n");
    return 1;
  }
  puts("fixture case already-zero return_value matched");
  if (actual_already_zero_itr.curr_kv.addr.start != (uint32_t)0u) {
    fprintf(stderr, "already-zero projected state mismatch\\n");
    return 1;
  }
  puts("fixture case already-zero kv_addr_start matched");
  struct FdbKvIterator actual_ordinary_address_itr = { .curr_kv = { .addr = { .start = (uint32_t)8192u } } };
  bool actual_ordinary_address_return = fdb_kv_iterate_projection_probe(&actual_ordinary_address_itr);
  if (actual_ordinary_address_return != true) {
    fprintf(stderr, "ordinary-address return mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-address return_value matched");
  if (actual_ordinary_address_itr.curr_kv.addr.start != (uint32_t)0u) {
    fprintf(stderr, "ordinary-address projected state mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-address kv_addr_start matched");
  struct FdbKvIterator actual_maximum_address_itr = { .curr_kv = { .addr = { .start = (uint32_t)4294967295u } } };
  bool actual_maximum_address_return = fdb_kv_iterate_projection_probe(&actual_maximum_address_itr);
  if (actual_maximum_address_return != true) {
    fprintf(stderr, "maximum-address return mismatch\\n");
    return 1;
  }
  puts("fixture case maximum-address return_value matched");
  if (actual_maximum_address_itr.curr_kv.addr.start != (uint32_t)0u) {
    fprintf(stderr, "maximum-address projected state mismatch\\n");
    return 1;
  }
  puts("fixture case maximum-address kv_addr_start matched");
  return 0;
}
