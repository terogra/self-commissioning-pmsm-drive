# Drive nonideality evaluation

This protocol is committed with the models, scenarios, metrics, tests and
development artifacts **before** held-out evaluation. The freeze commit is
recorded in the final README and engineering log. Baseline main is
`047d6511b86c34ce571005f8377387eb3674602b` (merged M16).

## Fixed scope and information boundary

Characterize the existing algorithms. Do not change estimators, quality policies,
retry actions/bounds, controller gains/formulas, or M16 calculations/semantics.
Simulation providers own true parameters. Existing decisions receive sampled
records and known Gaussian noise metadata only. Six-parameter error labels and
closed-loop outcomes are computed **after** commissioning, never supplied to
gates or retries. Terminal failure and missing estimates are retained explicitly.

## Models and interpretation

`src/drive_nonidealities.py` provides immutable nested configurations.

* Current: true dq -> inverse Park at true angle -> inverse Clarke -> phase
  gain/offset/nearest-quantum rounding -> Clarke -> Park at measured angle.
  Gains multiply phase current; offsets/quantum are in amperes. Common-mode
  offsets vanish under Clarke. No ADC range/clipping or specific sensor is modeled.
* Voltage: excitation/FOC command, actual terminal voltage and estimator
  reconstruction are distinct. The matrix uses reconstruction from the **command**
  in its own measured frame, followed by dq gain/offset/rounding in volts. Optional
  `source="terminal"` represents separately sensed terminals rotated into the
  measured frame; it is not used to give perfect voltage to the matrix estimators.
* Angle: fixed bias in **electrical radians**. Measurements rotate by minus bias;
  commands rotate back by measured-command-angle minus current true angle. With
  feedback delay, that command angle is delayed too. The rig still knows imposed
  mechanical speed; fixed alignment bias does not change that scalar speed.
* Timing: one control-step delay of `(id, iq, speed, measured angle)` in mechanical
  and speed control; hold the first tuple initially. Separately, commissioning
  recorded dq currents are one **record sample** late relative to unchanged
  speed/time/voltage intervals, also holding the first sample. Gaussian record
  noise is added afterward, rather than delayed a second time. Control step is
  40 us; electrical record sample is 100 us; mechanical record sample is 1 ms.
* Inverter: add `-drop * sign(i_phase)` to commanded phase voltages, with sign(0)=0;
  remove zero sequence via Clarke and map back to true dq. Evaluate sign at the
  beginning of each integration/control step and hold the true dq vector for RK4.
  This is an averaged voltage-error surrogate, **not** switching PWM or a complete
  dead-time/device model. Electrical sampled terminal voltage is the mean over
  integration substeps for optional terminal sensing.
* Bus: actual bus = nominal bus * (1 - sag), constant. After phase-error addition,
  clip the terminal vector to actual bus/sqrt(3). FOC knows only the nominal bus;
  its existing anti-windup sees nominal FOC clipping, not this extra terminal
  clipping. No switching ripple or load-dependent supply dynamics.
* Drift: clone the simulation plant for operation with `Rs *= factor`; do not
  mutate the commissioned/controller objects. Commissioning ignores this drift.
  No thermal network, temperature measurement, or online correction is modeled.

Structured errors are not placed in `MeasurementNoise`. Existing zero-mean
Gaussian sample noise is added after the deterministic measurement chain.
Mechanical/speed feedback has deterministic errors but no additional Gaussian
feedback noise; commissioning records retain their existing Gaussian noise.
These assumptions describe a simulation chain, not a specific sensor package.

## Fixed matrix and levels

`scenario_definitions.json` records the exact nested configs. There are 16 cells:
ideal; mild/strong current, voltage, angle, inverter, bus sag, Rs drift; one-sample
timing; combined mild/strong. Combined includes all modeled families. No levels
are customized to a plant.

| Quantity | Mild | Strong |
| --- | --- | --- |
| Phase-current gains (a,b,c) | 1.01, 0.99, 1.00 | 1.16, 1.14, 1.15 |
| Phase offsets [A] | .002, -.001, -.001 | .010, -.015, .005 |
| Current quantum [A] | .002 | .010 |
| dq voltage gains | 1.02, 1.02 | 1.12, 1.12 |
| dq offsets [V] | .005, -.005 | .020, -.020 |
| Voltage quantum [V] | .005 | .020 |
| Electrical angle bias | 2 degrees | 6 degrees |
| Averaged phase drop [V] | .030 | .150 |
| Bus sag | 5% | 10% |
| Operating Rs multiplier | 1.2 | 1.5 |
| Feedback / record-current delay | 1 step / 1 sample | 1 step / 1 sample |

The strong current case intentionally contains a substantial common calibration
fault (15% mean gain) plus phase mismatch. Strong voltage reconstruction has 12%
gain error. These are bounded stress/fault illustrations, **not** universal device
specifications or assertions about typical industrial sensors.

## Population, pairing and exposure

Development seed **20261004**, **two motors**; held-out seed **20261005**, **three
new motors**. Independent uniform draws use the existing M15 ranges:
Rs .35-.65 ohm; Ld .8-1.4 mH; Lq .7-1.3 mH; psi_f .015-.028 Wb;
J 3-8e-4 kg m²; B .8-2.5e-4 N m s/rad; four pole pairs.
Each motor's seed and true values are retained in separate truth-audit JSON.

Use existing locked-rotor/default voltage sequences, 600 rpm imposed-rotor flux
test with q base 5 V, and repeated known-zero-load mechanical current/coast
plateaus. Electrical record noise: .01 A, .01 V, .02 rad/s; mechanical:
.01 A, .05 rad/s. Commissioning and regular operation nominal bus is 24 V.

One-shot and unchanged M15 adaptive paths share initial sampled records and
Gaussian draws. Retries use the existing configured record seeds and bounded
actions. Cache mechanical records by excitation **and identified electrical
controller parameters**. Every scenario has both methods and all three exposures:

1. Commissioning-only: corrupted records/excitation, ideal subsequent operation.
2. Operation-only: ideal low-noise commissioning, corrupted subsequent operation.
3. Combined: corrupted commissioning and subsequent operation.

Rs drift applies only to subsequent operation, even in combined cells. Open-loop
electrical rigs have no feedback delay; bus sag matters only if their voltage
commands reach the actual bus circle. Voltage reconstruction errors do not alter
FOC feedback; during operation they change the logged reconstructed voltage only.
Cases where an effect is inactive remain in the dataset.

Expected rows: **192 development**, **288 held-out** = motors * 16 scenarios *
2 methods * 3 exposures. These are correlated scenario/exposure rows, **not**
192/288 independent motor draws. Summaries count commissioning on combined rows
only, avoiding triple counting. No inferential coverage or hardware reliability
claim is made from this small sample.

## Frozen evaluation metrics

Parameter accuracy: all six estimates available and each absolute relative error
<=10%, unchanged M15 evaluation convention. This is **post-hoc**, not a gate.
Retain accepted-accurate, accepted-inaccurate (silent acceptance), rejected-accurate,
and rejected-inaccurate/unavailable. Retain stage accepts, estimates, all error
columns, attempt counts, terminal state/reason and complete adaptive histories.

Only full-accepted results run normal commissioned control. Rejection remains
explicit `commissioning_unavailable`, with no assigned zero error or control
success. Operation exceptions/nonfinite signals are explicit failures. No hidden
voltage-feasibility filter removes a commissioned case.

Regular control: existing 1000 rpm, .05 N m load at .30 s, .60 s duration, 5 A
current-reference limit, 300 Hz current/10 Hz speed tuning, 40 us RK4/control.
Reuse existing post-load metrics and M15 success: speed RMSE <=10 rpm, iq RMSE
<=.05 A, finite recovery <=.1 s. For angle/delay cases, compare true iq with the
controller current reference rotated into the **true frame**; also report
controller-frame feedback tracking separately. Preserve legacy `(k+1)` post-step
samples tagged `k*dt` in existing metric functions; response CSVs label actual
post-step observation times explicitly. Log true id RMS, true/measured current
peaks, max speed deviation, nominal-command and actual-bus clipping fractions,
voltage utilization, actual bus and true-frame terminal-minus-command RMS/max.
Reference limiting is not an instantaneous current-protection guarantee.

Small M16 interaction: first motor's clean accepted adaptive model, 1000 rpm,
constant .05 N m load from t=0, deadline .60 s, unchanged hold/current criterion.
Choose nominal bus **before operation** as 1.04 times identified steady required
voltage converted to bus units. Compare a single unchanged M16 prediction against
ideal, mild/strong sag, mild/strong combined operation, and strong Rs drift.
This recipe deliberately probes small nominal headroom using estimates, not
hidden truth or a search for disagreements. Preserve quasi-steady estimate
terminology: it is not a universal physical lower bound.

## Freeze and artifact checks

Run development, inspect correctness/scaling and add regression tests for
intended negative findings. Commit method/scenarios/metrics/protocol before
running held-out. No gates or algorithms change for either population. Preserve
failed cells and all original evidence. Final review compares protected algorithm
source against baseline, validates row counts/JSON/CSV, inspects generated plots,
runs full pytest and `git diff --check`, then opens a feature PR without merging.

## Development review before freeze

Both original and final-schema development runs used the same seed, models,
scenarios and metrics; the latter adds explicit estimator-failure/attempt-estimate
fields and consistent plot colors. Outcomes and numeric metrics reproduced:
26/32 accepted for each method, six silent inaccurate acceptances, six terminal
residual rejections, zero retries/recoveries and no accurate full rejections.
Commissioning-only control succeeded 26/26 evaluated, operation-only 28/32,
combined 24/26 (six unavailable). M16 agreed 2/6 with four optimistic predictions.
No severity, model calculation, gate or controller was fitted to these outcomes.

The complete suite passed **180 tests** before freeze; focused tests subsequently
passed 29/29 after making the algorithm-contract fingerprint portable across
Python 3.11/3.12 and explicitly checking rejected supervisor controller state.
The final full suite will be rerun after held-out artifacts and documentation.
The baseline algorithm contract compares 12 module ASTs, excluding only the two
electrical simulation-provider functions, and preserves future deliberate review
of any algorithm changes. No held-out motor/outcome has been inspected at freeze.
