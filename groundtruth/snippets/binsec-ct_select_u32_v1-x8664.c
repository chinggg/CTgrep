#include <stdint.h>
#include <stdbool.h>

int ct_isnonzero_u32(uint32_t x) {
  return (x|-x)>>31;
}

uint32_t ct_mask_u32(uint32_t bit) {
  return -(uint32_t) ct_isnonzero_u32(bit);
}

uint32_t ct_select_u32_v1(uint32_t x, uint32_t y, bool bit) {
  uint32_t m = ct_mask_u32(bit);
  return (x&m) | (y&~m);
}