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
    uint32_t t2[len];
    // uint32_t *t2 = t1;
    size_t mwlen = 16;
    size_t k = 16/len;
    // file: i32_modpow2.c
    // Line: 135
    uint32_t * base = t1 + mwlen;
    for (size_t u = 1; u < ((uint32_t)1 << k); u ++) {
        uint32_t mask;

        mask = -EQ(u, bits);
        for (size_t v = 1; v < mwlen; v ++) {
            t2[v] |= mask & base[v];
        }
        base += mwlen;
    }

	return t2[1];
}