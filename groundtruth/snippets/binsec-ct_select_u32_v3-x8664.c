#include <stdint.h>
#include <stdbool.h>

uint32_t ct_select_u32_v3(uint32_t x, uint32_t y, bool bit) {
  signed b = 1-bit;
  return (x*bit) | (y*b);
}