/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-new-kv-alloc-compare */
/* function: fdb_alloc_compare_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-new-kv-alloc-compare.json */
/* fixture cases: 3 */
/* observable outputs: return_value, empty_kv, external_call_count, external_call_args */
/* fixture case: failed-address input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-new-kv-alloc-compare.json expected_outputs={"empty_kv": 4294967295, "external_call_args": [17, 29, 64], "external_call_count": 1, "return_value": true} */
/* fixture case: zero-address input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-new-kv-alloc-compare.json expected_outputs={"empty_kv": 0, "external_call_args": [3, 5, 0], "external_call_count": 1, "return_value": false} */
/* fixture case: allocated-address input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-new-kv-alloc-compare.json expected_outputs={"empty_kv": 8192, "external_call_args": [305419896, 2271560481, 4096], "external_call_count": 1, "return_value": false} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
/* Fixture-only scripted external; real external callee semantics are not verified. */
static uint32_t c2r_scripted_external_return = 0u;
static size_t c2r_scripted_external_call_count = 0u;
static uint32_t c2r_scripted_external_arg0 = 0u;
static uint32_t c2r_scripted_external_arg1 = 0u;
static size_t c2r_scripted_external_arg2 = 0u;

uint32_t alloc_kv(
    uint32_t db,
    uint32_t sector,
    size_t kv_size)
{
    c2r_scripted_external_call_count += 1u;
    c2r_scripted_external_arg0 = db;
    c2r_scripted_external_arg1 = sector;
    c2r_scripted_external_arg2 = kv_size;
    return c2r_scripted_external_return;
}

#define FAILED_ADDR ((uint32_t)-1)
uint32_t alloc_kv(uint32_t db, uint32_t sector, size_t kv_size);
static bool fdb_alloc_compare_probe(uint32_t db, uint32_t sector, size_t kv_size, uint32_t *empty_kv_out)
{
    uint32_t empty_kv = FAILED_ADDR;
    bool failed = false;

    if ((empty_kv = alloc_kv(db, sector, kv_size)) == FAILED_ADDR) {
        failed = true;
    }
    *empty_kv_out = empty_kv;
    return failed;
}

int main(void) {
  puts("oracle harness draft for fdb_alloc_compare_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-new-kv-alloc-compare.json");
  c2r_scripted_external_return = (uint32_t)4294967295u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_external_arg0 = 0u;
  c2r_scripted_external_arg1 = 0u;
  c2r_scripted_external_arg2 = 0u;
  uint32_t actual_failed_address_out = 0u;
  bool actual_failed_address_return = fdb_alloc_compare_probe((uint32_t)17u, (uint32_t)29u, (size_t)64u, &actual_failed_address_out);
  if (actual_failed_address_return != true) {
    fprintf(stderr, "failed-address return mismatch: expected %d got %d\\n", (int)true, (int)actual_failed_address_return);
    return 1;
  }
  puts("fixture case failed-address return_value matched");
  if (actual_failed_address_out != (uint32_t)4294967295u) {
    fprintf(stderr, "failed-address u32 out mismatch: expected %llu got %llu\\n", (unsigned long long)(uint32_t)4294967295u, (unsigned long long)actual_failed_address_out);
    return 1;
  }
  puts("fixture case failed-address empty_kv matched");
  if (c2r_scripted_external_call_count != (size_t)1u) {
    fprintf(stderr, "failed-address external call count mismatch: expected %llu got %llu\\n", (unsigned long long)(size_t)1u, (unsigned long long)c2r_scripted_external_call_count);
    return 1;
  }
  puts("fixture case failed-address external_call_count matched");
  if (c2r_scripted_external_arg0 != (uint32_t)17u ||
      c2r_scripted_external_arg1 != (uint32_t)29u ||
      c2r_scripted_external_arg2 != (size_t)64u) {
    fprintf(stderr, "failed-address external call args mismatch\\n");
    return 1;
  }
  puts("fixture case failed-address external_call_args matched");
  c2r_scripted_external_return = (uint32_t)0u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_external_arg0 = 0u;
  c2r_scripted_external_arg1 = 0u;
  c2r_scripted_external_arg2 = 0u;
  uint32_t actual_zero_address_out = 0u;
  bool actual_zero_address_return = fdb_alloc_compare_probe((uint32_t)3u, (uint32_t)5u, (size_t)0u, &actual_zero_address_out);
  if (actual_zero_address_return != false) {
    fprintf(stderr, "zero-address return mismatch: expected %d got %d\\n", (int)false, (int)actual_zero_address_return);
    return 1;
  }
  puts("fixture case zero-address return_value matched");
  if (actual_zero_address_out != (uint32_t)0u) {
    fprintf(stderr, "zero-address u32 out mismatch: expected %llu got %llu\\n", (unsigned long long)(uint32_t)0u, (unsigned long long)actual_zero_address_out);
    return 1;
  }
  puts("fixture case zero-address empty_kv matched");
  if (c2r_scripted_external_call_count != (size_t)1u) {
    fprintf(stderr, "zero-address external call count mismatch: expected %llu got %llu\\n", (unsigned long long)(size_t)1u, (unsigned long long)c2r_scripted_external_call_count);
    return 1;
  }
  puts("fixture case zero-address external_call_count matched");
  if (c2r_scripted_external_arg0 != (uint32_t)3u ||
      c2r_scripted_external_arg1 != (uint32_t)5u ||
      c2r_scripted_external_arg2 != (size_t)0u) {
    fprintf(stderr, "zero-address external call args mismatch\\n");
    return 1;
  }
  puts("fixture case zero-address external_call_args matched");
  c2r_scripted_external_return = (uint32_t)8192u;
  c2r_scripted_external_call_count = 0u;
  c2r_scripted_external_arg0 = 0u;
  c2r_scripted_external_arg1 = 0u;
  c2r_scripted_external_arg2 = 0u;
  uint32_t actual_allocated_address_out = 0u;
  bool actual_allocated_address_return = fdb_alloc_compare_probe((uint32_t)305419896u, (uint32_t)2271560481u, (size_t)4096u, &actual_allocated_address_out);
  if (actual_allocated_address_return != false) {
    fprintf(stderr, "allocated-address return mismatch: expected %d got %d\\n", (int)false, (int)actual_allocated_address_return);
    return 1;
  }
  puts("fixture case allocated-address return_value matched");
  if (actual_allocated_address_out != (uint32_t)8192u) {
    fprintf(stderr, "allocated-address u32 out mismatch: expected %llu got %llu\\n", (unsigned long long)(uint32_t)8192u, (unsigned long long)actual_allocated_address_out);
    return 1;
  }
  puts("fixture case allocated-address empty_kv matched");
  if (c2r_scripted_external_call_count != (size_t)1u) {
    fprintf(stderr, "allocated-address external call count mismatch: expected %llu got %llu\\n", (unsigned long long)(size_t)1u, (unsigned long long)c2r_scripted_external_call_count);
    return 1;
  }
  puts("fixture case allocated-address external_call_count matched");
  if (c2r_scripted_external_arg0 != (uint32_t)305419896u ||
      c2r_scripted_external_arg1 != (uint32_t)2271560481u ||
      c2r_scripted_external_arg2 != (size_t)4096u) {
    fprintf(stderr, "allocated-address external call args mismatch\\n");
    return 1;
  }
  puts("fixture case allocated-address external_call_args matched");
  return 0;
}
