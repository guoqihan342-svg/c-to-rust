/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <flashdb.h>

/* slice: flashdb/real-fdb-tsl-to-blob */
/* function: fdb_tsl_to_blob */
/* fixture input: validation/l2_slices/fixtures/real-fdb-tsl-to-blob.json */
/* fixture cases: 3 */
/* observable outputs: return_same_blob, blob.saved.addr, blob.saved.meta_addr, blob.saved.len */
/* fixture case: all-zero input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-tsl-to-blob.json expected_outputs={"blob.saved.addr": 0, "blob.saved.len": 0, "blob.saved.meta_addr": 0, "return_same_blob": true} */
/* fixture case: nominal-tsl input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-tsl-to-blob.json expected_outputs={"blob.saved.addr": 4352, "blob.saved.len": 128, "blob.saved.meta_addr": 4096, "return_same_blob": true} */
/* fixture case: u32-max input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-tsl-to-blob.json expected_outputs={"blob.saved.addr": 4294967295, "blob.saved.len": 4294967295, "blob.saved.meta_addr": 4294967295, "return_same_blob": true} */
/* source file: src/fdb_tsdb.c (sha256: 1d56d3820d627fdc468368d1c4a848231834b6dcb513a0c01ea94ac13c9d259b) */
fdb_blob_t fdb_tsl_to_blob(fdb_tsl_t tsl, fdb_blob_t blob)
{
    blob->saved.addr = tsl->addr.log;
    blob->saved.meta_addr = tsl->addr.index;
    blob->saved.len = tsl->log_len;

    return blob;
}

int main(void) {
  puts("oracle harness draft for fdb_tsl_to_blob");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-tsl-to-blob.json");
  struct fdb_tsl all_zero_tsl = {0};
  all_zero_tsl.addr.index = (uint32_t)0u;
  all_zero_tsl.addr.log = (uint32_t)0u;
  all_zero_tsl.log_len = (uint32_t)0u;
  struct fdb_blob all_zero_blob = {0};
  all_zero_blob.saved.addr = (uint32_t)88u;
  all_zero_blob.saved.len = (size_t)77u;
  all_zero_blob.saved.meta_addr = (uint32_t)99u;
  fdb_blob_t actual_all_zero_blob = fdb_tsl_to_blob(&all_zero_tsl, &all_zero_blob);
  if (actual_all_zero_blob != &all_zero_blob) {
    fprintf(stderr, "all-zero return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case all-zero return_same_blob matched");
  if (all_zero_blob.saved.addr != (uint32_t)0u) {
    fprintf(stderr, "all-zero blob.saved.addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)0u, (unsigned long long)all_zero_blob.saved.addr);
    return 1;
  }
  puts("fixture case all-zero blob.saved.addr matched");
  if (all_zero_blob.saved.len != (size_t)0u) {
    fprintf(stderr, "all-zero blob.saved.len mismatch: expected %llu got %llu\n", (unsigned long long)(size_t)0u, (unsigned long long)all_zero_blob.saved.len);
    return 1;
  }
  puts("fixture case all-zero blob.saved.len matched");
  if (all_zero_blob.saved.meta_addr != (uint32_t)0u) {
    fprintf(stderr, "all-zero blob.saved.meta_addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)0u, (unsigned long long)all_zero_blob.saved.meta_addr);
    return 1;
  }
  puts("fixture case all-zero blob.saved.meta_addr matched");
  struct fdb_tsl nominal_tsl_tsl = {0};
  nominal_tsl_tsl.addr.index = (uint32_t)4096u;
  nominal_tsl_tsl.addr.log = (uint32_t)4352u;
  nominal_tsl_tsl.log_len = (uint32_t)128u;
  struct fdb_blob nominal_tsl_blob = {0};
  nominal_tsl_blob.saved.addr = (uint32_t)2u;
  nominal_tsl_blob.saved.len = (size_t)3u;
  nominal_tsl_blob.saved.meta_addr = (uint32_t)1u;
  fdb_blob_t actual_nominal_tsl_blob = fdb_tsl_to_blob(&nominal_tsl_tsl, &nominal_tsl_blob);
  if (actual_nominal_tsl_blob != &nominal_tsl_blob) {
    fprintf(stderr, "nominal-tsl return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case nominal-tsl return_same_blob matched");
  if (nominal_tsl_blob.saved.addr != (uint32_t)4352u) {
    fprintf(stderr, "nominal-tsl blob.saved.addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4352u, (unsigned long long)nominal_tsl_blob.saved.addr);
    return 1;
  }
  puts("fixture case nominal-tsl blob.saved.addr matched");
  if (nominal_tsl_blob.saved.len != (size_t)128u) {
    fprintf(stderr, "nominal-tsl blob.saved.len mismatch: expected %llu got %llu\n", (unsigned long long)(size_t)128u, (unsigned long long)nominal_tsl_blob.saved.len);
    return 1;
  }
  puts("fixture case nominal-tsl blob.saved.len matched");
  if (nominal_tsl_blob.saved.meta_addr != (uint32_t)4096u) {
    fprintf(stderr, "nominal-tsl blob.saved.meta_addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4096u, (unsigned long long)nominal_tsl_blob.saved.meta_addr);
    return 1;
  }
  puts("fixture case nominal-tsl blob.saved.meta_addr matched");
  struct fdb_tsl u32_max_tsl = {0};
  u32_max_tsl.addr.index = (uint32_t)4294967295u;
  u32_max_tsl.addr.log = (uint32_t)4294967295u;
  u32_max_tsl.log_len = (uint32_t)4294967295u;
  struct fdb_blob u32_max_blob = {0};
  u32_max_blob.saved.addr = (uint32_t)20u;
  u32_max_blob.saved.len = (size_t)30u;
  u32_max_blob.saved.meta_addr = (uint32_t)10u;
  fdb_blob_t actual_u32_max_blob = fdb_tsl_to_blob(&u32_max_tsl, &u32_max_blob);
  if (actual_u32_max_blob != &u32_max_blob) {
    fprintf(stderr, "u32-max return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case u32-max return_same_blob matched");
  if (u32_max_blob.saved.addr != (uint32_t)4294967295u) {
    fprintf(stderr, "u32-max blob.saved.addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4294967295u, (unsigned long long)u32_max_blob.saved.addr);
    return 1;
  }
  puts("fixture case u32-max blob.saved.addr matched");
  if (u32_max_blob.saved.len != (size_t)4294967295u) {
    fprintf(stderr, "u32-max blob.saved.len mismatch: expected %llu got %llu\n", (unsigned long long)(size_t)4294967295u, (unsigned long long)u32_max_blob.saved.len);
    return 1;
  }
  puts("fixture case u32-max blob.saved.len matched");
  if (u32_max_blob.saved.meta_addr != (uint32_t)4294967295u) {
    fprintf(stderr, "u32-max blob.saved.meta_addr mismatch: expected %llu got %llu\n", (unsigned long long)(uint32_t)4294967295u, (unsigned long long)u32_max_blob.saved.meta_addr);
    return 1;
  }
  puts("fixture case u32-max blob.saved.meta_addr matched");
  return 0;
}
