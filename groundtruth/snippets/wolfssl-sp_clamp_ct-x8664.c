#include <stdint.h>

/* Simplified types based on wolfSSL's sp_int.h */
typedef uint16_t sp_size_t;
typedef uint64_t sp_int_digit;

#ifndef SP_INT_DIGITS
#define SP_INT_DIGITS 64
#endif

typedef struct sp_int {
    sp_size_t    used;
    sp_size_t    size;
    sp_int_digit dp[SP_INT_DIGITS];
} sp_int;

/**
 * Constant time clamping
 * 
 * Scans the digits from the top to find the actual number of used digits.
 *
 * @param [in, out] a  SP integer to clamp.
 */
void sp_clamp_ct(sp_int* a)
{
    int i;
    sp_size_t used = a->used;
    /* mask is initially all ones (0xffff for uint16_t) */
    sp_size_t mask = (sp_size_t)-1;

    for (i = (int)a->used - 1; i >= 0; i--) {
        /* (a->dp[i] == 0) results in 1 if digit is zero, 0 otherwise.
         * If the mask is still active (-1), we subtract the zero flag (1 or 0) from used.
         */
        used = (sp_size_t)(used - ((a->dp[i] == 0) & mask));

        /* If we hit a non-zero digit:
         * (a->dp[i] == 0) becomes 0.
         * (0 - 0) is 0.
         * mask &= 0 zeros out the mask.
         *
         * If digit is still zero:
         * (a->dp[i] == 0) is 1.
         * (0 - 1) is -1 (all 1s in two's complement).
         * mask &= -1 leaves the mask unchanged.
         */
        mask &= (sp_size_t)(0 - (a->dp[i] == 0));
    }
    a->used = used;
}
