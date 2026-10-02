#ifndef PMSM_CONTROL_H
#define PMSM_CONTROL_H

#include "pmsm_config.h"

typedef struct { float integral; } PmsmPiState;
typedef struct { PmsmPiState d_pi, q_pi; } PmsmCurrentState;
typedef struct { PmsmPiState pi; } PmsmSpeedState;

typedef struct {
    float id_ref, iq_ref, id, iq, omega_m, dt;
} PmsmCurrentInput;           /* A, mechanical rad/s, s */

typedef struct {
    float vd_requested, vq_requested;
    float vd, vq;
    float requested_magnitude, magnitude;
    int saturated;
} PmsmCurrentOutput;

typedef struct {
    float vd, vq, requested_magnitude, magnitude;
    int saturated;
} PmsmVoltageOutput;

/* Valid configs/state and distinct output objects are caller-owned. No allocation.
 * All failed calls leave state/output unchanged. Reset(NULL) is a no-op. */
PmsmStatus pmsm_pi_init(const PmsmPiConfig *config, PmsmPiState *state);
void pmsm_pi_reset(PmsmPiState *state);
PmsmStatus pmsm_pi_update(const PmsmPiConfig *config, PmsmPiState *state,
                          float error, float dt, float *output);
PmsmStatus pmsm_pi_track(PmsmPiState *state, float applied, float requested,
                         float dt, float gain);
PmsmStatus pmsm_limit_voltage(float vd, float vq, int enabled, float limit,
                              PmsmVoltageOutput *out);
PmsmStatus pmsm_current_init(const PmsmMotorParams *motor,
                            const PmsmCurrentConfig *config, PmsmCurrentState *state);
void pmsm_current_reset(PmsmCurrentState *state);
PmsmStatus pmsm_current_update(const PmsmMotorParams *motor,
                              const PmsmCurrentConfig *config, PmsmCurrentState *state,
                              const PmsmCurrentInput *input, PmsmCurrentOutput *output);
PmsmStatus pmsm_speed_init(const PmsmSpeedConfig *config, PmsmSpeedState *state);
void pmsm_speed_reset(PmsmSpeedState *state);
PmsmStatus pmsm_speed_update(const PmsmSpeedConfig *config, PmsmSpeedState *state,
                            float omega_ref, float omega_measured, float dt, float *iq_ref);

#endif
