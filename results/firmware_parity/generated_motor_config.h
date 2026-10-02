/* Generated binary32 constants. SIMULATED accepted full commissioning, M18 seeds 1801/1802/1803; not universal motor constants.
 * Demonstration/configuration only; no hardware validation or safety guarantee. */
#ifndef COMMISSIONED_PMSM_CONFIG_H
#define COMMISSIONED_PMSM_CONFIG_H

#include "pmsm_config.h"

static const PmsmMotorParams commissioned_motor = {
    0x1.ffeac80000000p-2f,
    0x1.3a66420000000p-10f,
    0x1.d785a40000000p-11f,
    0x1.68703a0000000p-6f,
    0x1.1f94c60000000p-11f,
    0x1.a297e60000000p-13f,
    4u
};

static const PmsmCurrentConfig commissioned_current = {
    0x1.215ea00000000p+1f,
    0x1.d729a00000000p+9f,
    0x1.b1fbc20000000p+0f,
    0x1.d729a00000000p+9f,
    0x1.d73d280000000p+10f,
    0x1.8000000000000p+4f,
    0x1.bb67ae0000000p+3f,
    1
};

static const PmsmSpeedConfig commissioned_speed = {
    0x1.0a97c80000000p-1f,
    0x1.067cb00000000p+4f,
    0x1.4000000000000p+2f,
    0x1.0e542c0000000p-3f
};

#endif /* COMMISSIONED_PMSM_CONFIG_H */
