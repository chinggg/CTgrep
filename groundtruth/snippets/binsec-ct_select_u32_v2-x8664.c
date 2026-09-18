#include <stdint.h>
#include <stdbool.h>

uint32_t ct_select_u32_v2(uint32_t x, uint32_t y, bool bit) {
  uint32_t m = -(uint32_t) (((uint32_t)bit|-(uint32_t)bit)>>31);
  return (x&m) | (y&~m);
}