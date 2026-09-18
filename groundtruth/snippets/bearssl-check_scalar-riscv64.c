#include <stdint.h>
#include <stddef.h>
#include <string.h>


/*
 * Returns 1 if x == 0, 0 otherwise. Take care that the operand is signed.
 */
static inline uint32_t
EQ0(int32_t x)
{
	uint32_t q;

	q = (uint32_t)x;
	return ~(q | -q) >> 31;
}

/*
 * Comparison: returns 1 if x > y, 0 otherwise.
 */
static inline uint32_t
GT(uint32_t x, uint32_t y)
{
	/*
	 * If both x < 2^31 and x < 2^31, then y-x will have its high
	 * bit set if x > y, cleared otherwise.
	 *
	 * If either x >= 2^31 or y >= 2^31 (but not both), then the
	 * result is the high bit of x.
	 *
	 * If both x >= 2^31 and y >= 2^31, then we can virtually
	 * subtract 2^31 from both, and we are back to the first case.
	 * Since (y-2^31)-(x-2^31) = y-x, the subtraction is already
	 * fine.
	 */
	uint32_t z;

	z = y - x;
	return (z ^ ((x ^ y) & (x ^ z))) >> 31;
}

/*
 * General comparison: returned value is -1, 0 or 1, depending on
 * whether x is lower than, equal to, or greater than y.
 */
static inline int32_t
CMP(uint32_t x, uint32_t y)
{
	return (int32_t)GT(x, y) | -(int32_t)GT(y, x);
}

static const unsigned char P256_N[] = {
	0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF,
	0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xBC, 0xE6, 0xFA, 0xAD,
	0xA7, 0x17, 0x9E, 0x84, 0xF3, 0xB9, 0xCA, 0xC2, 0xFC, 0x63,
	0x25, 0x51
};

uint32_t
check_scalar(const unsigned char *k)
{
	int32_t c;
	size_t u;

    c = 0;
    for (u = 0; u < 32; u ++) {
        c |= -(int32_t)EQ0(c) & CMP(k[u], P256_N[u]);
    }
	
	return c;
}