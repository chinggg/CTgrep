#include <stdint.h>
#include <stdlib.h>

uint64_t precompute(uint64_t H0, uint64_t H1) {
    const uint64_t R = 0xE100000000000000;
    const uint64_t carry = R * (H1 & 1);
    return (H0 >> 1) ^ carry;
}