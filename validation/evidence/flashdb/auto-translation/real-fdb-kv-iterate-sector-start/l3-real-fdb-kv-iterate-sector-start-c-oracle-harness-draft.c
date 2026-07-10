/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-kv-iterate-sector-start */
/* function: fdb_kv_iterate_sector_start_probe */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-start.json */
/* fixture cases: 3 */
/* observable outputs: return_value, kv_addr_start */
/* fixture case: first-sector-data input_ref=cases[0].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-start.json expected_outputs={"kv_addr_start": 32, "return_value": true} */
/* fixture case: ordinary-sector-data input_ref=cases[1].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-start.json expected_outputs={"kv_addr_start": 4160, "return_value": true} */
/* fixture case: u32-wrap input_ref=cases[2].inputs expected_ref=validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-start.json expected_outputs={"kv_addr_start": 16, "return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
struct Sector { uint32_t addr; };
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
static bool fdb_kv_iterate_sector_start_probe(struct Sector sector, uint32_t SECTOR_HDR_DATA_SIZE, struct Kv *kv)
{
                    kv->addr.start = sector.addr + SECTOR_HDR_DATA_SIZE;
    return true;
}

int main(void) {
  puts("oracle harness draft for fdb_kv_iterate_sector_start_probe");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-start.json");
  struct Sector actual_first_sector_data_sector = { .addr = (uint32_t)0u };
  uint32_t actual_first_sector_data_SECTOR_HDR_DATA_SIZE = (uint32_t)32u;
  struct Kv actual_first_sector_data_kv = { .addr = { .start = (uint32_t)4294967295u } };
  uint32_t expected_first_sector_data_field_scalar_state = (uint32_t)(actual_first_sector_data_sector.addr + actual_first_sector_data_SECTOR_HDR_DATA_SIZE);
  if (expected_first_sector_data_field_scalar_state != (uint32_t)32u) {
    fprintf(stderr, "first-sector-data declared field-scalar state mismatch\\n");
    return 1;
  }
  bool actual_first_sector_data_return = fdb_kv_iterate_sector_start_probe(actual_first_sector_data_sector, actual_first_sector_data_SECTOR_HDR_DATA_SIZE, &actual_first_sector_data_kv);
  if (actual_first_sector_data_return != true) {
    fprintf(stderr, "first-sector-data return mismatch\\n");
    return 1;
  }
  puts("fixture case first-sector-data return_value matched");
  if (actual_first_sector_data_kv.addr.start != expected_first_sector_data_field_scalar_state) {
    fprintf(stderr, "first-sector-data field-scalar state mismatch\\n");
    return 1;
  }
  puts("fixture case first-sector-data kv_addr_start matched");
  struct Sector actual_ordinary_sector_data_sector = { .addr = (uint32_t)4096u };
  uint32_t actual_ordinary_sector_data_SECTOR_HDR_DATA_SIZE = (uint32_t)64u;
  struct Kv actual_ordinary_sector_data_kv = { .addr = { .start = (uint32_t)7u } };
  uint32_t expected_ordinary_sector_data_field_scalar_state = (uint32_t)(actual_ordinary_sector_data_sector.addr + actual_ordinary_sector_data_SECTOR_HDR_DATA_SIZE);
  if (expected_ordinary_sector_data_field_scalar_state != (uint32_t)4160u) {
    fprintf(stderr, "ordinary-sector-data declared field-scalar state mismatch\\n");
    return 1;
  }
  bool actual_ordinary_sector_data_return = fdb_kv_iterate_sector_start_probe(actual_ordinary_sector_data_sector, actual_ordinary_sector_data_SECTOR_HDR_DATA_SIZE, &actual_ordinary_sector_data_kv);
  if (actual_ordinary_sector_data_return != true) {
    fprintf(stderr, "ordinary-sector-data return mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-sector-data return_value matched");
  if (actual_ordinary_sector_data_kv.addr.start != expected_ordinary_sector_data_field_scalar_state) {
    fprintf(stderr, "ordinary-sector-data field-scalar state mismatch\\n");
    return 1;
  }
  puts("fixture case ordinary-sector-data kv_addr_start matched");
  struct Sector actual_u32_wrap_sector = { .addr = (uint32_t)4294967280u };
  uint32_t actual_u32_wrap_SECTOR_HDR_DATA_SIZE = (uint32_t)32u;
  struct Kv actual_u32_wrap_kv = { .addr = { .start = (uint32_t)123u } };
  uint32_t expected_u32_wrap_field_scalar_state = (uint32_t)(actual_u32_wrap_sector.addr + actual_u32_wrap_SECTOR_HDR_DATA_SIZE);
  if (expected_u32_wrap_field_scalar_state != (uint32_t)16u) {
    fprintf(stderr, "u32-wrap declared field-scalar state mismatch\\n");
    return 1;
  }
  bool actual_u32_wrap_return = fdb_kv_iterate_sector_start_probe(actual_u32_wrap_sector, actual_u32_wrap_SECTOR_HDR_DATA_SIZE, &actual_u32_wrap_kv);
  if (actual_u32_wrap_return != true) {
    fprintf(stderr, "u32-wrap return mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap return_value matched");
  if (actual_u32_wrap_kv.addr.start != expected_u32_wrap_field_scalar_state) {
    fprintf(stderr, "u32-wrap field-scalar state mismatch\\n");
    return 1;
  }
  puts("fixture case u32-wrap kv_addr_start matched");
  return 0;
}
