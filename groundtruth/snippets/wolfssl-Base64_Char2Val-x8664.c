#include <stdint.h>

typedef uint8_t byte;

/* Aligns the table to a cache line boundary (64 bytes) */
#define ALIGN64 __attribute__((aligned(64)))
#define BAD 0xFF
#define BASE64_MIN 0x2B

static ALIGN64 const byte base64Decode[] = {
    /* + starts at 0x2B */
    /* 0x28:       + , - . / */                   62, BAD, BAD, BAD,  63,
    /* 0x30: 0 1 2 3 4 5 6 7 */    52,  53,  54,  55,  56,  57,  58,  59,
    /* 0x38: 8 9 : ; < = > ? */    60,  61, BAD, BAD, BAD, BAD, BAD, BAD,
    /* 0x40: @ A B C D E F G */   BAD,   0,   1,   2,   3,   4,   5,   6,
    /* 0x48: H I J K L M N O */     7,   8,   9,  10,  11,  12,  13,  14,
    /* 0x50: P Q R S T U V W */    15,  16,  17,  18,  19,  20,  21,  22,
    /* 0x58: X Y Z [ \ ] ^ _ */    23,  24,  25, BAD, BAD, BAD, BAD, BAD,
    /* 0x60: ` a b c d e f g */   BAD,  26,  27,  28,  29,  30,  31,  32,
    /* 0x68: h i j k l m n o */    33,  34,  35,  36,  37,  38,  39,  40,
    /* 0x70: p q r s t u v w */    41,  42,  43,  44,  45,  46,  47,  48,
    /* 0x78: x y z           */    49,  50,  51
};

/**
 * Constant time Base64 char to value conversion.
 *
 * This version uses bitwise masking to perform table lookups in a way
 * that touches multiple cache lines to mitigate side-channel leaks.
 */
byte Base64_Char2Val(byte c)
{
    byte v;
    byte mask;

    /* Normalize input character relative to the start of the table */
    c = (byte)(c - BASE64_MIN);
    
    /* 
     * Generate a mask based on the range.
     * If c <= 0x3F (63), mask becomes 0xFF.
     * If c > 0x3F, mask becomes 0x00.
     */
    mask = (byte)((((byte)(0x3f - c)) >> 7) - 1);

    /* 
     * Load a value from the first cache line (indices 0-63) if mask is 0xFF.
     * Otherwise, load from the second cache line (indices 64-79).
     * This ensures the lookup logic is branchless.
     */
    v  = (byte)(base64Decode[ c & 0x3f        ] &   mask);
    v |= (byte)(base64Decode[(c & 0x0f) | 0x40] & (~mask));

    return v;
}