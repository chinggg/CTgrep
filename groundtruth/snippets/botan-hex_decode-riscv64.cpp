#include <type_traits>
#include <cstdint>
#include <vector>

inline constexpr uint8_t choose(uint8_t mask, uint8_t a, uint8_t b)
{
//    return (mask & a) | (~mask & b);
    return (b ^ (mask & (a ^ b)));
}

template<typename uint8_t>
inline constexpr uint8_t expand_top_bit(uint8_t a)
   requires (std::is_integral<uint8_t>::value)
   {
   return static_cast<uint8_t>(0) - (a >> (sizeof(uint8_t)*8-1));
   }

static uint8_t is_within_range(uint8_t v, uint8_t l, uint8_t u)
    {
    //return Mask<uint8_t>::is_gte(v, l) & Mask<uint8_t>::is_lte(v, u);

    const uint8_t v_lt_l = v^((v^l) | ((v-l)^v));
    const uint8_t v_gt_u = u^((u^v) | ((u-v)^u));
    const uint8_t either = v_lt_l | v_gt_u;
    return ~uint8_t(expand_top_bit(either));
    }


static uint8_t is_any_of(uint8_t v, std::vector<uint8_t> accepted)
{
    uint8_t accept = 0;

    for(auto a: accepted)
    {
        const uint8_t diff = a ^ v;
        const uint8_t eq_zero = ~diff & (diff - 1);
        accept |= eq_zero;
    }

    return expand_top_bit(accept);
}

uint8_t is_whitespace(uint8_t c) 
{
    const uint8_t whitespace = is_any_of(c, {
         uint8_t(' '), uint8_t('\t'), uint8_t('\n'), uint8_t('\r')
      });
    const auto is_alpha_upper = is_within_range(c, uint8_t('A'), uint8_t('F'));
    const auto is_alpha_lower = is_within_range(c, uint8_t('a'), uint8_t('f'));
    const auto is_decimal     = is_within_range(c, uint8_t('0'), uint8_t('9'));
    
    const uint8_t c_upper = c - uint8_t('A') + 10;
    const uint8_t c_lower = c - uint8_t('a') + 10;
    const uint8_t c_decim = c - uint8_t('0');

    uint8_t ret = 0xff;
    // return choose(whitespace, 0x80, ret);
    ret = choose(is_alpha_upper, c_upper, ret);
    ret = choose(is_alpha_lower, c_lower, ret);
    ret = choose(is_decimal, c_decim, ret);
    ret = choose(whitespace, 0x80, ret);
    return ret;
}