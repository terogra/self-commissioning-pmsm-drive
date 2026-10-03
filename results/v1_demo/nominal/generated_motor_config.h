/* Generated binary32 constants. SIMULATED accepted full commissioning; project 1.0.0 RC; seed 1901; scenario ideal.
 * Demonstration/configuration only; no hardware validation or safety guarantee. */
#ifndef COMMISSIONED_PMSM_CONFIG_H
#define COMMISSIONED_PMSM_CONFIG_H

#include "pmsm_config.h"

static const PmsmMotorParams commissioned_motor = {
    0x1.fff8860000000p-2f,
    0x1.3a89ae0000000p-10f,
    0x1.d7c3e00000000p-11f,
    0x1.686f3c0000000p-6f,
    0x1.1fe88c0000000p-11f,
    0x1.a2ebf40000000p-13f,
    4u
};

static const PmsmCurrentConfig commissioned_current = {
    0x1.217f3a0000000p+1f,
    0x1.d736460000000p+9f,
    0x1.b2350a0000000p+0f,
    0x1.d736460000000p+9f,
    0x1.d73d280000000p+10f,
    0x1.8000000000000p+4f,
    0x1.bb67ae0000000p+3f,
    1
};

static const PmsmSpeedConfig commissioned_speed = {
    0x1.0ae63e0000000p-1f,
    0x1.06c9de0000000p+4f,
    0x1.4000000000000p+2f,
    0x1.0e536c0000000p-3f
};

#endif /* COMMISSIONED_PMSM_CONFIG_H */
