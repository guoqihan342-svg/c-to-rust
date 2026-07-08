/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <flashdb.h>

/* slice: flashdb/real-fdb-kv-to-blob */
/* function: fdb_kv_to_blob */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-to-blob.json */
/* fixture cases: 3 */
/* observable outputs: return_same_blob, blob.saved.meta_addr, blob.saved.addr, blob.saved.len */
/* fixture case: zero-addresses-empty-value input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-to-blob.json expected_outputs={"blob.saved.addr": 0, "blob.saved.len": 0, "blob.saved.meta_addr": 0, "return_same_blob": true} */
/* fixture case: nominal-kv-value input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-to-blob.json expected_outputs={"blob.saved.addr": 4352, "blob.saved.len": 128, "blob.saved.meta_addr": 4096, "return_same_blob": true} */
/* fixture case: max-u32-addresses input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-to-blob.json expected_outputs={"blob.saved.addr": 4294967295, "blob.saved.len": 65535, "blob.saved.meta_addr": 4294967280, "return_same_blob": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
fdb_blob_t fdb_kv_to_blob(fdb_kv_t kv, fdb_blob_t blob)
{
    blob->saved.meta_addr = kv->addr.start;
    blob->saved.addr = kv->addr.value;
    blob->saved.len = kv->value_len;

    return blob;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_to_blob");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-to-blob.json");
  struct fdb_kv zero_addresses_empty_value_kv = {0};
  zero_addresses_empty_value_kv.addr.start = (uint32_t)0u;
  zero_addresses_empty_value_kv.addr.value = (uint32_t)0u;
  zero_addresses_empty_value_kv.value_len = (size_t)0u;
  struct fdb_blob zero_addresses_empty_value_blob = {0};
  zero_addresses_empty_value_blob.saved.addr = (uint32_t)88u;
  zero_addresses_empty_value_blob.saved.len = (size_t)77u;
  zero_addresses_empty_value_blob.saved.meta_addr = (uint32_t)99u;
  fdb_blob_t actual_zero_addresses_empty_value_blob = fdb_kv_to_blob(&zero_addresses_empty_value_kv, &zero_addresses_empty_value_blob);
  if (actual_zero_addresses_empty_value_blob != &zero_addresses_empty_value_blob) {
    fprintf(stderr, "zero-addresses-empty-value return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case zero-addresses-empty-value return_same_blob matched");
  if (zero_addresses_empty_value_blob.saved.addr != (uint32_t)0u) {
    fprintf(stderr, "zero-addresses-empty-value blob.saved.addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)0u, (unsigned long long)zero_addresses_empty_value_blob.saved.addr);
    return 1;
  }
  puts("fixture case zero-addresses-empty-value blob.saved.addr matched");
  if (zero_addresses_empty_value_blob.saved.len != (size_t)0u) {
    fprintf(stderr, "zero-addresses-empty-value blob.saved.len mismatch: expected %llu got %llu\n", (unsigned long long)(size_t)0u, (unsigned long long)zero_addresses_empty_value_blob.saved.len);
    return 1;
  }
  puts("fixture case zero-addresses-empty-value blob.saved.len matched");
  if (zero_addresses_empty_value_blob.saved.meta_addr != (uint32_t)0u) {
    fprintf(stderr, "zero-addresses-empty-value blob.saved.meta_addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)0u, (unsigned long long)zero_addresses_empty_value_blob.saved.meta_addr);
    return 1;
  }
  puts("fixture case zero-addresses-empty-value blob.saved.meta_addr matched");
  struct fdb_kv nominal_kv_value_kv = {0};
  nominal_kv_value_kv.addr.start = (uint32_t)4096u;
  nominal_kv_value_kv.addr.value = (uint32_t)4352u;
  nominal_kv_value_kv.value_len = (size_t)128u;
  struct fdb_blob nominal_kv_value_blob = {0};
  nominal_kv_value_blob.saved.addr = (uint32_t)2u;
  nominal_kv_value_blob.saved.len = (size_t)3u;
  nominal_kv_value_blob.saved.meta_addr = (uint32_t)1u;
  fdb_blob_t actual_nominal_kv_value_blob = fdb_kv_to_blob(&nominal_kv_value_kv, &nominal_kv_value_blob);
  if (actual_nominal_kv_value_blob != &nominal_kv_value_blob) {
    fprintf(stderr, "nominal-kv-value return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case nominal-kv-value return_same_blob matched");
  if (nominal_kv_value_blob.saved.addr != (uint32_t)4352u) {
    fprintf(stderr, "nominal-kv-value blob.saved.addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4352u, (unsigned long long)nominal_kv_value_blob.saved.addr);
    return 1;
  }
  puts("fixture case nominal-kv-value blob.saved.addr matched");
  if (nominal_kv_value_blob.saved.len != (size_t)128u) {
    fprintf(stderr, "nominal-kv-value blob.saved.len mismatch: expected %llu got %llu\n", (unsigned long long)(size_t)128u, (unsigned long long)nominal_kv_value_blob.saved.len);
    return 1;
  }
  puts("fixture case nominal-kv-value blob.saved.len matched");
  if (nominal_kv_value_blob.saved.meta_addr != (uint32_t)4096u) {
    fprintf(stderr, "nominal-kv-value blob.saved.meta_addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4096u, (unsigned long long)nominal_kv_value_blob.saved.meta_addr);
    return 1;
  }
  puts("fixture case nominal-kv-value blob.saved.meta_addr matched");
  struct fdb_kv max_u32_addresses_kv = {0};
  max_u32_addresses_kv.addr.start = (uint32_t)4294967280u;
  max_u32_addresses_kv.addr.value = (uint32_t)4294967295u;
  max_u32_addresses_kv.value_len = (size_t)65535u;
  struct fdb_blob max_u32_addresses_blob = {0};
  max_u32_addresses_blob.saved.addr = (uint32_t)20u;
  max_u32_addresses_blob.saved.len = (size_t)30u;
  max_u32_addresses_blob.saved.meta_addr = (uint32_t)10u;
  fdb_blob_t actual_max_u32_addresses_blob = fdb_kv_to_blob(&max_u32_addresses_kv, &max_u32_addresses_blob);
  if (actual_max_u32_addresses_blob != &max_u32_addresses_blob) {
    fprintf(stderr, "max-u32-addresses return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case max-u32-addresses return_same_blob matched");
  if (max_u32_addresses_blob.saved.addr != (uint32_t)4294967295u) {
    fprintf(stderr, "max-u32-addresses blob.saved.addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4294967295u, (unsigned long long)max_u32_addresses_blob.saved.addr);
    return 1;
  }
  puts("fixture case max-u32-addresses blob.saved.addr matched");
  if (max_u32_addresses_blob.saved.len != (size_t)65535u) {
    fprintf(stderr, "max-u32-addresses blob.saved.len mismatch: expected %llu got %llu\n", (unsigned long long)(size_t)65535u, (unsigned long long)max_u32_addresses_blob.saved.len);
    return 1;
  }
  puts("fixture case max-u32-addresses blob.saved.len matched");
  if (max_u32_addresses_blob.saved.meta_addr != (uint32_t)4294967280u) {
    fprintf(stderr, "max-u32-addresses blob.saved.meta_addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4294967280u, (unsigned long long)max_u32_addresses_blob.saved.meta_addr);
    return 1;
  }
  puts("fixture case max-u32-addresses blob.saved.meta_addr matched");
  return 0;
}
