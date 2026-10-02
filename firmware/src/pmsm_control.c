#include "pmsm_control.h"

#include <float.h>
#include <math.h>
#include <stddef.h>

static int flag_valid(int flag) { return flag == 0 || flag == 1; }

static int pi_valid(const PmsmPiConfig *c)
{
    return c != NULL && isfinite(c->kp) && isfinite(c->ki)
        && flag_valid(c->lower_limit_enabled) && flag_valid(c->upper_limit_enabled)
        && isfinite(c->output_min) && isfinite(c->output_max)
        && (!(c->lower_limit_enabled && c->upper_limit_enabled) || c->output_min <= c->output_max);
}

PmsmStatus pmsm_pi_init(const PmsmPiConfig *config, PmsmPiState *state)
{
    if (state == NULL || !pi_valid(config)) return PMSM_INVALID_ARGUMENT;
    pmsm_pi_reset(state);
    return PMSM_OK;
}

void pmsm_pi_reset(PmsmPiState *state) { if (state != NULL) state->integral = 0.0f; }

PmsmStatus pmsm_pi_update(const PmsmPiConfig *config, PmsmPiState *state,
                          float error, float dt, float *output)
{
    float previous, integral, value;
    if (state == NULL || output == NULL || !pi_valid(config) || !isfinite(state->integral)
        || !isfinite(error) || !isfinite(dt) || dt <= 0.0f) return PMSM_INVALID_ARGUMENT;
    previous = state->integral;
    integral = previous + config->ki * error * dt;
    value = config->kp * error + integral;
    if (!isfinite(integral) || !isfinite(value)) return PMSM_NUMERIC_RANGE;
    /* Same ordered comparisons and conditional rollback as Python PIController. */
    if (config->upper_limit_enabled && value > config->output_max) {
        if (error > 0.0f) integral = previous;
        value = config->output_max;
    }
    if (config->lower_limit_enabled && value < config->output_min) {
        if (error < 0.0f) integral = previous;
        value = config->output_min;
    }
    state->integral = integral;
    *output = value;
    return PMSM_OK;
}

PmsmStatus pmsm_pi_track(PmsmPiState *state, float applied, float requested, float dt, float gain)
{
    float integral;
    if (state == NULL || !isfinite(state->integral) || !isfinite(applied) || !isfinite(requested)
        || !isfinite(dt) || dt <= 0.0f || !isfinite(gain)) return PMSM_INVALID_ARGUMENT;
    integral = state->integral + gain * dt * (applied - requested);
    if (!isfinite(integral)) return PMSM_NUMERIC_RANGE;
    state->integral = integral;
    return PMSM_OK;
}

PmsmStatus pmsm_limit_voltage(float vd, float vq, int enabled, float limit, PmsmVoltageOutput *out)
{
    PmsmVoltageOutput value;
    if (out == NULL || !isfinite(vd) || !isfinite(vq) || !isfinite(limit) || !flag_valid(enabled)
        || (enabled && limit <= 0.0f)) return PMSM_INVALID_ARGUMENT;
    value.requested_magnitude = hypotf(vd, vq);
    if (!isfinite(value.requested_magnitude)) return PMSM_NUMERIC_RANGE;
    value.saturated = enabled && value.requested_magnitude > limit;
    if (value.saturated) {
        float scale = limit / value.requested_magnitude;
        vd *= scale;
        vq *= scale;
    }
    value.vd = vd;
    value.vq = vq;
    value.magnitude = hypotf(vd, vq);
    if (!isfinite(value.magnitude)) return PMSM_NUMERIC_RANGE;
    *out = value;
    return PMSM_OK;
}

static int current_valid(const PmsmMotorParams *m, const PmsmCurrentConfig *c)
{
    if (m == NULL || c == NULL) return 0;
    if (!isfinite(m->Rs) || m->Rs <= 0.0f || !isfinite(m->Ld) || m->Ld <= 0.0f
        || !isfinite(m->Lq) || m->Lq <= 0.0f || !isfinite(m->psi_f) || m->psi_f <= 0.0f
        || !isfinite(m->J) || m->J <= 0.0f || !isfinite(m->B) || m->B < 0.0f
        || m->pole_pairs == 0u || m->pole_pairs > 16777216u)
        return 0;
    if (!isfinite(c->kp_d) || !isfinite(c->ki_d) || !isfinite(c->kp_q) || !isfinite(c->ki_q)
        || !isfinite(c->anti_windup_gain) || c->anti_windup_gain < 0.0f
        || !flag_valid(c->voltage_limit_enabled)) return 0;
    if (c->voltage_limit_enabled) {
        float expected;
        if (!isfinite(c->dc_bus_voltage) || c->dc_bus_voltage <= 0.0f
            || !isfinite(c->voltage_limit) || c->voltage_limit <= 0.0f) return 0;
        expected = c->dc_bus_voltage / sqrtf(3.0f);
        /* Independently rounded exported bus/limit may differ by a few ulps. */
        if (fabsf(expected - c->voltage_limit) > 4.0f * FLT_EPSILON * expected) return 0;
    } else if (c->dc_bus_voltage != 0.0f || c->voltage_limit != 0.0f) return 0;
    return 1;
}

PmsmStatus pmsm_current_init(const PmsmMotorParams *motor, const PmsmCurrentConfig *config, PmsmCurrentState *state)
{
    if (state == NULL || !current_valid(motor, config)) return PMSM_INVALID_ARGUMENT;
    pmsm_current_reset(state);
    return PMSM_OK;
}

void pmsm_current_reset(PmsmCurrentState *state)
{
    if (state != NULL) { pmsm_pi_reset(&state->d_pi); pmsm_pi_reset(&state->q_pi); }
}

PmsmStatus pmsm_current_update(const PmsmMotorParams *motor, const PmsmCurrentConfig *config,
                              PmsmCurrentState *state, const PmsmCurrentInput *input, PmsmCurrentOutput *output)
{
    PmsmCurrentState next;
    PmsmCurrentOutput value;
    PmsmVoltageOutput voltage;
    PmsmPiConfig d, q;
    float vd_pi, vq_pi, omega_e, error_d, error_q;
    PmsmStatus status;
    if (state == NULL || input == NULL || output == NULL || !current_valid(motor, config)
        || !isfinite(input->id_ref) || !isfinite(input->iq_ref) || !isfinite(input->id)
        || !isfinite(input->iq) || !isfinite(input->omega_m) || !isfinite(input->dt)
        || input->dt <= 0.0f || !isfinite(state->d_pi.integral) || !isfinite(state->q_pi.integral))
        return PMSM_INVALID_ARGUMENT;
    next = *state;
    d = (PmsmPiConfig){config->kp_d, config->ki_d, 0.0f, 0.0f, 0, 0};
    q = (PmsmPiConfig){config->kp_q, config->ki_q, 0.0f, 0.0f, 0, 0};
    error_d = input->id_ref - input->id;
    error_q = input->iq_ref - input->iq;
    if (!isfinite(error_d) || !isfinite(error_q)) return PMSM_NUMERIC_RANGE;
    status = pmsm_pi_update(&d, &next.d_pi, error_d, input->dt, &vd_pi);
    if (status != PMSM_OK) return status;
    status = pmsm_pi_update(&q, &next.q_pi, error_q, input->dt, &vq_pi);
    if (status != PMSM_OK) return status;
    omega_e = (float)motor->pole_pairs * input->omega_m;
    value.vd_requested = vd_pi - omega_e * motor->Lq * input->iq;
    value.vq_requested = vq_pi + omega_e * (motor->Ld * input->id + motor->psi_f);
    if (!isfinite(omega_e) || !isfinite(value.vd_requested) || !isfinite(value.vq_requested))
        return PMSM_NUMERIC_RANGE;
    status = pmsm_limit_voltage(value.vd_requested, value.vq_requested,
                              config->voltage_limit_enabled, config->voltage_limit, &voltage);
    if (status != PMSM_OK) return status;
    if (voltage.saturated) {
        status = pmsm_pi_track(&next.d_pi, voltage.vd, value.vd_requested, input->dt, config->anti_windup_gain);
        if (status != PMSM_OK) return status;
        status = pmsm_pi_track(&next.q_pi, voltage.vq, value.vq_requested, input->dt, config->anti_windup_gain);
        if (status != PMSM_OK) return status;
    }
    value.vd = voltage.vd;
    value.vq = voltage.vq;
    value.requested_magnitude = voltage.requested_magnitude;
    value.magnitude = voltage.magnitude;
    value.saturated = voltage.saturated;
    *state = next;
    *output = value;
    return PMSM_OK;
}

static int speed_valid(const PmsmSpeedConfig *c)
{
    return c != NULL && isfinite(c->kp) && isfinite(c->ki) && isfinite(c->iq_limit)
        && c->iq_limit > 0.0f && isfinite(c->torque_constant) && c->torque_constant > 0.0f;
}

PmsmStatus pmsm_speed_init(const PmsmSpeedConfig *config, PmsmSpeedState *state)
{
    if (state == NULL || !speed_valid(config)) return PMSM_INVALID_ARGUMENT;
    pmsm_speed_reset(state);
    return PMSM_OK;
}

void pmsm_speed_reset(PmsmSpeedState *state) { if (state != NULL) pmsm_pi_reset(&state->pi); }

PmsmStatus pmsm_speed_update(const PmsmSpeedConfig *config, PmsmSpeedState *state,
                            float omega_ref, float omega_measured, float dt, float *iq_ref)
{
    PmsmPiConfig pi;
    float error;
    if (state == NULL || iq_ref == NULL || !speed_valid(config)
        || !isfinite(omega_ref) || !isfinite(omega_measured) || !isfinite(dt) || dt <= 0.0f)
        return PMSM_INVALID_ARGUMENT;
    error = omega_ref - omega_measured;
    if (!isfinite(error)) return PMSM_NUMERIC_RANGE;
    pi = (PmsmPiConfig){config->kp, config->ki, -config->iq_limit, config->iq_limit, 1, 1};
    return pmsm_pi_update(&pi, &state->pi, error, dt, iq_ref);
}
