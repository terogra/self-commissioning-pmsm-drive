#ifndef PMSM_CONFIG_H
#define PMSM_CONFIG_H

#include <stdint.h>
#include <float.h>
#include <limits.h>

#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128
#error "The M18 control core requires IEEE binary32 float"
#endif
typedef char PmsmBinary32StorageCheck[(sizeof(float) * CHAR_BIT == 32) ? 1 : -1];

/* SI units; float must be IEEE binary32 (checked at compile time in the core). */
typedef struct {
    float Rs;                 /* ohm */
    float Ld, Lq;             /* H */
    float psi_f;              /* Wb */
    float J;                  /* kg m^2 */
    float B;                  /* N m s/rad */
    uint32_t pole_pairs;
} PmsmMotorParams;

typedef struct {
    float kp, ki;
    float output_min, output_max;
    int lower_limit_enabled, upper_limit_enabled;
} PmsmPiConfig;

typedef struct {
    float kp_d, ki_d, kp_q, ki_q;
    float anti_windup_gain;    /* 1/s */
    float dc_bus_voltage;     /* nominal V; 0 when voltage limiting disabled */
    float voltage_limit;      /* phase-neutral peak V; nominal Vdc/sqrt(3) */
    int voltage_limit_enabled;
} PmsmCurrentConfig;

typedef struct {
    float kp, ki;
    float iq_limit;           /* A, positive symmetric reference limit */
    float torque_constant;    /* N m/A; provenance constant, not recomputed in C */
} PmsmSpeedConfig;

typedef enum {
    PMSM_OK = 0,
    PMSM_INVALID_ARGUMENT = 1,
    PMSM_NUMERIC_RANGE = 2
} PmsmStatus;

#endif
