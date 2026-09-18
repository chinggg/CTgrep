#include <stdint.h>
#include <stddef.h>
#include <string.h>

static inline uint32_t
NOT(uint32_t ctl)
{
	return ctl ^ 1;
}

static inline uint32_t
EQ(uint32_t x, uint32_t y)
{
	uint32_t q;

	q = x ^ y;
	return NOT((q | -q) >> 31);
}


uint32_t br_i62_modpow_opt(uint64_t *x, size_t len, uint64_t *t1, uint64_t bits)
{
    uint64_t mask1 = -(uint64_t)EQ(bits, 0);
    uint64_t mask2 = ~mask1;
    for (int u = 0; u < len; u ++) {
        x[u] = (mask1 & x[u]) | (mask2 & t1[u]);
    }
	
	return 1;
}