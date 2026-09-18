#include <stdint.h>
#include <stdbool.h>

uint32_t ct_select_u32_v4(uint32_t x, uint32_t y, bool bit) {
  signed b = 0-bit;
  return (x&b) | (y&~b);
}