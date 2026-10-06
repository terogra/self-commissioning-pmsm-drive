# C control core and Python/C comparison

Reference main: `3eb116ef6d22550668c507c23c9847cdde01c04b`.
Python controllers, transforms, commissioning and M16/M17 results stay unchanged.

## C API

ISO C99, IEEE binary32 `float`, explicit caller-owned structs, no heap or mutable
global state. Headers separate motor/controller configuration, transform vectors
and mutable PI/current/speed states. Initialization validates configuration and
zeros state. Reset restores integrators to zero. Update/track functions return
`PMSM_OK`, `PMSM_INVALID_ARGUMENT` or `PMSM_NUMERIC_RANGE`; invalid/null/nonfinite
inputs, nonpositive dt, invalid bus/limit and arithmetic overflow leave state and
output untouched. This validation is an explicit C integration contract, not a
redesign of the Python equations for valid inputs or a physical fault handler.

Transforms return amplitude-invariant abc/alpha-beta/dq vectors through output
pointers. Current update takes motor parameters, current config, state and
`(id_ref, iq_ref, id, iq, omega_m, dt)`; returns requested/applied vd/vq, their
magnitudes and saturation flag. Speed update takes config/state and
`(omega_ref, omega_measured, dt)`, returning iq reference. Generic PI exposes
optional lower/upper bounds and explicit back-calculation tracking. No C gain
tuning or commissioning logic: Python constructs and exports the constants.

Preserved order: PI integrates `Ki*error*dt`, computes `Kp*error+integral`, then
rolls back the integral only when a clamped error drives further into that limit.
FOC updates both PIs, computes electrical speed `p*omega_m`, applies decoupling,
limits the entire vector at nominal bus/sqrt(3), and tracks both integrators with
`gain*dt*(applied-requested)` after limiting. No integrator clipping or redesigned
anti-windup is introduced. Negative speed inputs are supported by these equations.

The exporter requires an accepted **FullCommissioningResult**, extracts all six
identified values and known pole pairs, invokes existing Python constructors,
then rounds motor/gain constants to binary32 once. C99 hexadecimal literals with
`f` suffix preserve those exact constants. Rejection cannot export a configuration.
Unconstrained voltage is an explicit disabled-limit setting for reference tests.

## Comparison method and predefined tolerances

Both implementations receive the same binary32-representable input values; Python
receives them as Python floats and retains its original float64 arithmetic.
Configuration float32 rounding is included in reported reference differences.
Do not compare independently evolving plants. A deterministic Python plant run
generates the combined replay stream; both speed controllers receive its same
reference/feedback, and both FOC controllers receive the same recorded iq reference
and measured currents/speed. Thus upstream output differences do not change the
primary current-controller inputs. This is controller replay, not C closed loop.

Deterministic vectors cover signed/zero transforms and angles; PI accumulation,
positive/negative limiting/recovery/tracking; FOC nominal, nonzero d/q, positive
and negative speed, decoupling/back-EMF and saturation; speed positive/negative
limits and recovery. Compare **every output and integral state at every step**.
Keep separate boundary probes rather than silently removing threshold ties.

Acceptance budgets `abs_error <= atol + rtol*abs(reference)`:

| Stream | Absolute budget | Relative budget |
| --- | ---: | ---: |
| Transform components (magnitudes up to 20) | 8e-6 | 2e-6 |
| Standalone PI / speed sequences (<=512 steps) | 2e-4 | 2e-5 |
| Synthetic FOC voltages / integral states (<=512 steps) | 5e-3 V | 2e-5 |
| Combined 30,000-step replay current voltage/state | 5e-3 V | 2e-5 |
| Combined speed output / integral state | 5e-3 A | 2e-5 |

Binary32 unit roundoff is `u=2^-24`; its accumulation bound
`gamma_n=n*u/(1-n*u)` is about .00179 at 30,000 additions. The 5 mV/5 mA long
replay budgets allow accumulation in order-one integral states plus coefficient
rounding/cancellation. Synthetic saturated FOC can have much larger opposing
back-EMF/integral terms; its 5 mV budget allows cancellation of those terms.
The transform budget covers a few rounded operations and single-precision libm
calls on the bounded test magnitudes/angles. These are engineering regression
budgets for the declared streams, not a universal error theorem or a target-MCU
timing/accuracy guarantee. Record actual errors even when far below budget.
Do not loosen these budgets after a failing parity test.
A tolerance change requires a separate comparison study.

Report maximum absolute error and its stream/sample/signal, plus maximum relative
error only where `abs(reference)>=1e-6`; relative error at cancellation/zero is
undefined or misleading, so also retain signed/absolute errors. Exact saturation
flag agreement is required away from a boundary. Boundary probes within
`16*u*(abs(requested_magnitude)+abs(limit))` report both flags, distance and any
disagreement separately. Precision can change a strict comparison at equality;
compiler flags and probe records remain fixed. An explicit binary32 Python
FOC/PI calculation provides a secondary rounding diagnostic, without replacing
the unmodified float64 reference.

## Build, evidence and boundary

Compile with GCC/Clang: `-std=c99 -Wall -Wextra -Werror -pedantic -O2
-ffp-contract=off`; no fast-math. Host harness may use standard I/O; the core does
not. Binaries build in temporary directories and are never committed. Python
tests skip native compile/parity explicitly when no compiler exists locally;
Linux CI requires a compiler and runs the full compile/parity/C-test path.

Save a header from real simulated accepted full commissioning, vector/trace CSV,
quantitative compiler/tolerance/metric JSON and one parity plot under
`results/firmware_parity/`. No M17 population replay or altered historical results.
This is firmware-ready, not deployed firmware; no peripheral, PWM/ADC/encoder,
HAL, RTOS, fixed-point or motor-plant C implementation. No hard real-time deadline
has been measured on target silicon and no hardware validation/MISRA claim follows.
