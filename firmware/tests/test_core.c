/* Host-only assertions, including the GENERATED configuration header. */
#include "pmsm_control.h"
#include "pmsm_transforms.h"
#include "generated_motor_config.h"

#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition) do { ++checks; if (!(condition)) { \
    fprintf(stderr, "C check failed at line %d: %s\n", __LINE__, #condition); return 1; } } while (0)

int main(void)
{
    unsigned checks = 0u;
    PmsmMotorParams motor = commissioned_motor;
    PmsmCurrentConfig current = commissioned_current;
    PmsmSpeedConfig speed = commissioned_speed;
    PmsmPiConfig pi = {1.0f, 2.0f, -1.0f, 1.0f, 1, 1};
    PmsmPiState state = {9.0f};
    PmsmCurrentState cs, before;
    PmsmSpeedState ss;
    PmsmCurrentInput input = {0.1f, 0.4f, 0.0f, 0.0f, 20.0f, 0.00002f};
    PmsmCurrentOutput first, repeated, out;
    PmsmVoltageOutput voltage;
    PmsmAlphaBeta ab = {99.0f, 88.0f};
    float value = 123.0f;

    CHECK(pmsm_pi_init(&pi, &state) == PMSM_OK && state.integral == 0.0f);
    CHECK(pmsm_pi_update(&pi, &state, 4.0f, 0.1f, &value) == PMSM_OK);
    CHECK(value == 1.0f && state.integral == 0.0f);
    CHECK(pmsm_pi_update(&pi, &state, -4.0f, 0.1f, &value) == PMSM_OK);
    CHECK(value == -1.0f && state.integral == 0.0f);
    CHECK(pmsm_pi_update(&pi, &state, 0.2f, 0.1f, &value) == PMSM_OK);
    CHECK(fabsf(value - 0.24f) < 1e-6f && fabsf(state.integral - 0.04f) < 1e-6f);
    CHECK(pmsm_pi_track(&state, 0.0f, 1.0f, 0.1f, 2.0f) == PMSM_OK);
    CHECK(fabsf(state.integral + 0.16f) < 1e-6f);
    pmsm_pi_reset(&state);
    CHECK(state.integral == 0.0f);
    value = 123.0f;
    CHECK(pmsm_pi_update(&pi, &state, 1.0f, 0.0f, &value) == PMSM_INVALID_ARGUMENT);
    CHECK(value == 123.0f && state.integral == 0.0f);
    CHECK(pmsm_pi_track(&state, NAN, 0.0f, 0.1f, 1.0f) == PMSM_INVALID_ARGUMENT);
    pi.output_min = 2.0f;
    CHECK(pmsm_pi_init(&pi, &state) == PMSM_INVALID_ARGUMENT);
    pi.output_min = -1.0f;
    pi.ki = FLT_MAX;
    CHECK(pmsm_pi_update(&pi, &state, FLT_MAX, 1.0f, &value) == PMSM_NUMERIC_RANGE);
    CHECK(state.integral == 0.0f && value == 123.0f);

    CHECK(pmsm_limit_voltage(3.0f, 4.0f, 1, 2.5f, &voltage) == PMSM_OK);
    CHECK(voltage.saturated && fabsf(voltage.vd - 1.5f) < 1e-6f && fabsf(voltage.vq - 2.0f) < 1e-6f);
    CHECK(fabsf(voltage.vd * 4.0f - voltage.vq * 3.0f) < 1e-6f);
    CHECK(pmsm_limit_voltage(3.0f, 4.0f, 1, -1.0f, &voltage) == PMSM_INVALID_ARGUMENT);
    CHECK(pmsm_limit_voltage(3.0f, 4.0f, 0, 0.0f, &voltage) == PMSM_OK && !voltage.saturated);
    CHECK(pmsm_clarke(NAN, 0.0f, 0.0f, &ab) == PMSM_INVALID_ARGUMENT);
    CHECK(ab.alpha == 99.0f && ab.beta == 88.0f);
    CHECK(pmsm_park(1.0f, 0.0f, INFINITY, NULL) == PMSM_INVALID_ARGUMENT);

    CHECK(pmsm_current_init(&motor, &current, &cs) == PMSM_OK);
    CHECK(pmsm_current_update(&motor, &current, &cs, &input, &first) == PMSM_OK);
    pmsm_current_reset(&cs);
    CHECK(pmsm_current_update(&motor, &current, &cs, &input, &repeated) == PMSM_OK);
    CHECK(first.vd == repeated.vd && first.vq == repeated.vq && first.saturated == repeated.saturated);
    before = cs;
    out = first;
    input.dt = -0.1f;
    CHECK(pmsm_current_update(&motor, &current, &cs, &input, &out) == PMSM_INVALID_ARGUMENT);
    CHECK(cs.d_pi.integral == before.d_pi.integral && cs.q_pi.integral == before.q_pi.integral);
    CHECK(out.vd == first.vd && out.vq == first.vq);
    input.dt = 0.00002f;
    current.dc_bus_voltage = -1.0f;
    CHECK(pmsm_current_init(&motor, &current, &cs) == PMSM_INVALID_ARGUMENT);
    current = commissioned_current;
    cs.q_pi.integral = NAN;
    before = cs;
    CHECK(pmsm_current_update(&motor, &current, &cs, &input, &out) == PMSM_INVALID_ARGUMENT);
    CHECK(cs.d_pi.integral == before.d_pi.integral && isnan(cs.q_pi.integral));

    CHECK(pmsm_speed_init(&speed, &ss) == PMSM_OK);
    CHECK(pmsm_speed_update(&speed, &ss, 1000.0f, 0.0f, 0.001f, &value) == PMSM_OK);
    CHECK(value == speed.iq_limit && ss.pi.integral == 0.0f);
    CHECK(pmsm_speed_update(&speed, &ss, -1000.0f, 0.0f, 0.001f, &value) == PMSM_OK);
    CHECK(value == -speed.iq_limit && ss.pi.integral == 0.0f);
    CHECK(pmsm_speed_update(&speed, &ss, 0.5f, 0.0f, 0.001f, &value) == PMSM_OK);
    CHECK(ss.pi.integral != 0.0f);
    pmsm_speed_reset(&ss);
    CHECK(ss.pi.integral == 0.0f);
    speed.iq_limit = 0.0f;
    CHECK(pmsm_speed_init(&speed, &ss) == PMSM_INVALID_ARGUMENT);
    pmsm_current_reset(NULL);
    pmsm_speed_reset(NULL);
    pmsm_pi_reset(NULL);
    printf("%u C core checks passed\n", checks);
    return 0;
}
