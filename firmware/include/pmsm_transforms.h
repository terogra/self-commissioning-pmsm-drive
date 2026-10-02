#ifndef PMSM_TRANSFORMS_H
#define PMSM_TRANSFORMS_H

#include "pmsm_config.h"

typedef struct { float a, b, c; } PmsmAbc;
typedef struct { float alpha, beta; } PmsmAlphaBeta;
typedef struct { float d, q; } PmsmDq;

/* Amplitude-invariant, theta in electrical radians. Invalid input leaves out intact. */
PmsmStatus pmsm_clarke(float a, float b, float c, PmsmAlphaBeta *out);
PmsmStatus pmsm_inverse_clarke(float alpha, float beta, PmsmAbc *out);
PmsmStatus pmsm_park(float alpha, float beta, float theta_e, PmsmDq *out);
PmsmStatus pmsm_inverse_park(float d, float q, float theta_e, PmsmAlphaBeta *out);

#endif
