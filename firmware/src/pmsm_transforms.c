#include "pmsm_transforms.h"

#include <math.h>
#include <stddef.h>

PmsmStatus pmsm_clarke(float a, float b, float c, PmsmAlphaBeta *out)
{
    PmsmAlphaBeta value;
    if (out == NULL || !isfinite(a) || !isfinite(b) || !isfinite(c))
        return PMSM_INVALID_ARGUMENT;
    value.alpha = (2.0f / 3.0f) * (a - 0.5f * b - 0.5f * c);
    value.beta = (2.0f / 3.0f) * ((sqrtf(3.0f) / 2.0f) * (b - c));
    if (!isfinite(value.alpha) || !isfinite(value.beta)) return PMSM_NUMERIC_RANGE;
    *out = value;
    return PMSM_OK;
}

PmsmStatus pmsm_inverse_clarke(float alpha, float beta, PmsmAbc *out)
{
    PmsmAbc value;
    if (out == NULL || !isfinite(alpha) || !isfinite(beta)) return PMSM_INVALID_ARGUMENT;
    value.a = alpha;
    value.b = -0.5f * alpha + (sqrtf(3.0f) / 2.0f) * beta;
    value.c = -0.5f * alpha - (sqrtf(3.0f) / 2.0f) * beta;
    if (!isfinite(value.b) || !isfinite(value.c)) return PMSM_NUMERIC_RANGE;
    *out = value;
    return PMSM_OK;
}

PmsmStatus pmsm_park(float alpha, float beta, float theta_e, PmsmDq *out)
{
    float ct, st;
    PmsmDq value;
    if (out == NULL || !isfinite(alpha) || !isfinite(beta) || !isfinite(theta_e))
        return PMSM_INVALID_ARGUMENT;
    ct = cosf(theta_e);
    st = sinf(theta_e);
    value.d = alpha * ct + beta * st;
    value.q = -alpha * st + beta * ct;
    if (!isfinite(value.d) || !isfinite(value.q)) return PMSM_NUMERIC_RANGE;
    *out = value;
    return PMSM_OK;
}

PmsmStatus pmsm_inverse_park(float d, float q, float theta_e, PmsmAlphaBeta *out)
{
    float ct, st;
    PmsmAlphaBeta value;
    if (out == NULL || !isfinite(d) || !isfinite(q) || !isfinite(theta_e))
        return PMSM_INVALID_ARGUMENT;
    ct = cosf(theta_e);
    st = sinf(theta_e);
    value.alpha = d * ct - q * st;
    value.beta = d * st + q * ct;
    if (!isfinite(value.alpha) || !isfinite(value.beta)) return PMSM_NUMERIC_RANGE;
    *out = value;
    return PMSM_OK;
}
