# Self-Commissioning PMSM Drive

Python model of a permanent-magnet synchronous motor (PMSM) drive. The current
stage includes a dq-axis plant, Clarke/Park transforms, cascaded speed and dq
current PI control, a DC-bus voltage constraint, parameter mismatch studies,
and a two-stage electrical commissioning workflow. Locked-rotor excitation
estimates `Rs`, `Ld`, and `Lq`; driven-rotor excitation estimates `psi_f`.
Measured-data quality checks decide whether those parameters may retune the
controllers. A third, free-rotor stage now reconstructs torque from measured
currents and electrical estimates to identify inertia `J` and viscous friction
`B`. Accepted full commissioning uses all six identified parameters; rejected
full commissioning preserves the original controller assumptions. Independent
development and evaluation populations measure coverage, accuracy, and outcomes.
An independent operating-point layer now checks accepted estimates against the
requested steady-state current and voltage envelope, without changing either
identification-quality decision.
A bounded commissioning supervisor can now retry a diagnosed weak test within
configured simulation limits. It records every attempt, updates controllers
only after full acceptance, and reports operating feasibility separately.
A separate dynamic analysis now estimates a quasi-steady acceleration time and
predicts deadline/hold success with the existing controller on the identified model.

## Current simulation

`src.motor.PMSMParameters` stores motor constants. `PMSMModel` uses the **plant**
parameters for electrical and mechanical dynamics. `CurrentFOCController` and
`SpeedController` use separate **controller-assumed** parameters for PI gains,
decoupling, and the torque constant. The reusable
`run_speed_foc_simulation(plant_params=..., controller_params=...)` function in
`src.speed_foc_simulation` constructs fresh controllers for each run.

Defaults reproduce the working nominal case: a 1000 rpm speed command, a
0.05 N·m load step at 0.30 s, a 20 µs integration/control step, and a 0.6 s
run. The plant is integrated with RK4. The current controller defaults to a
48 V DC bus. Its commanded dq voltage vector is limited to a magnitude of
`Vdc / sqrt(3)`, the phase-neutral fundamental peak available inside the
linear space-vector PWM circle. The whole vector is scaled, preserving its
direction. Both current PI integrators use back-calculation from the applied
voltage when saturation occurs. The back-calculation gain defaults to the
current-loop bandwidth in rad/s.

Pass `dc_bus_voltage=...` to `run_speed_foc_simulation` to select the supply,
or `dc_bus_voltage=None` for an unconstrained reference run. The 48 V nominal
case does not saturate and retains the previous trajectory. Simulation output
includes applied `voltage_d`, `voltage_q`, their magnitude, the requested
magnitude, and a per-step `voltage_saturated` flag.

The voltage circle approximates an ideal linear SVPWM inverter. The closed-loop
model does not include switching, bus sag, overmodulation, dead time,
measurement noise, or sampling delays; rotor position and currents are
measured exactly. The commissioning experiment below can add sampled
measurement noise independently.

## Run

From the repository root, install dependencies and run:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.speed_foc_simulation
python -m experiments.parameter_sensitivity
python -m experiments.voltage_saturation_mismatch
python -m experiments.standstill_identification
python -m experiments.rotating_flux_identification
python -m experiments.commissioning_recovery
python -m experiments.commissioning_monte_carlo
python -m experiments.commissioning_quality_validation --population development
python -m experiments.commissioning_quality_validation --population evaluation
python -m experiments.full_commissioning_recovery
python -m experiments.mechanical_population --population development
python -m experiments.mechanical_population --population evaluation
python -m experiments.operating_feasibility
python -m experiments.adaptive_commissioning --population development
python -m experiments.adaptive_commissioning --population evaluation
```

The experiment commands write CSV tables and comparison plots to `results/`.
GitHub Actions runs pytest on pushes and pull requests using Python 3.11 and
3.12.
Other existing examples include `src.simulation`, `src.foc_simulation`,
`experiments.load_sweep`, and `experiments.foc_load_sweep`.

## Parameter sensitivity

The sweep keeps controller assumptions at the nominal values and changes
exactly one **plant** parameter per run: `Rs`, `Ld`, `Lq`, or `psi_f`. Each is
tested at −40%, −20%, +20%, and +40%, plus one fully nominal run. Thus a
−40% `Rs` case means the physical resistance is 0.6 times the resistance
assumed by the controller. Mechanical parameters and controller bandwidths
remain fixed.

The CSV records:

- **Speed RMSE [rpm]:** root-mean-square speed error relative to 1000 rpm
  across the full run, including startup.
- **iq tracking RMSE [A]:** root-mean-square difference between actual `iq`
  and its time-varying reference across the full run.
- **Maximum post-step speed deviation [rpm]:** largest absolute difference
  from the speed reference from the load step through the end of the run.
- **Disturbance recovery time [s]:** elapsed time after the load step until
  speed enters and remains within ±1% of the speed reference. A value of
  `NaN` means it did not settle within the simulated interval.

The sensitivity sweep uses the default 48 V bus. The speed plot zooms in on
the load-step response. The metric plot compares
all four measures across mismatch levels. Speed RMSE includes the large
startup transient, so the post-step measures are better for isolating load
rejection.

The voltage experiment compares −40%, nominal, and +40% physical `psi_f` at
a 24 V bus against unconstrained runs. Controller parameters remain nominal.
For +40% `psi_f`, the higher back-EMF consumes the voltage headroom: the
limited case settles near 936 rpm, while the unconstrained case reaches
1000 rpm. The limited case cannot recover to within 1% after the load step
within the 0.6 s run. The experiment is intended to expose this voltage
feasibility effect, not to represent inverter switching behavior.

## Standstill electrical commissioning

`src.identification` provides reusable excitation, sampled measurement,
estimation, and fitted-current prediction functions. The rotor is held by a
mechanical fixture at zero speed. Independent bipolar voltage holds are
applied to the d and q axes with different switching intervals. The requested
vector remains inside the 24 V bus linear SVPWM circle. The data generator
uses the existing PMSM electrical plant; its output contains only sampled
time, applied voltage, current, and measured speed. Optional Gaussian noise
can be configured separately for current, voltage, and speed measurements.

At standstill, the electrical equations reduce to:

```text
v_d = Rs i_d + Ld (di_d/dt)
v_q = Rs i_q + Lq (di_q/dt)
```

For each non-overlapping window from sample `a` to `b`, the estimator
integrates these equations:

```text
Σ v_d[k] Δt = Rs Σ ((i_d[k] + i_d[k+1])/2) Δt + Ld (i_d[b] − i_d[a])
Σ v_q[k] Δt = Rs Σ ((i_q[k] + i_q[k+1])/2) Δt + Lq (i_q[b] − i_q[a])
```

Each window contributes two rows to a linear regression with unknown vector
`[Rs, Ld, Lq]`. The estimator scales the regression columns and solves least
squares. It checks sampled speed and rejects rank-deficient excitation. Using
window integrals avoids pointwise differentiation of noisy current samples.
The independent voltage changes create transient current changes for `Ld`
and `Lq`, while sustained currents provide information for `Rs`.

The default experiment uses a hidden plant with `Rs = 0.48 Ω`,
`Ld = 0.8 mH`, and `Lq = 1.25 mH`, plus sampled noise. The estimator receives
only measurements. The experiment then compares its estimates against the
plant values and saves `results/standstill_identification.csv` and a plot of
excitation, measured and fitted currents, speed, residuals, and parameter
convergence. With the default seed, absolute errors are below 0.2%.

This stage assumes a locked rotor, known dq alignment, known applied
phase-neutral voltage, constant linear `Rs/Ld/Lq`, and adequate sampling.
Measurement errors in both sides of this ordinary least-squares regression
can bias estimates, especially at higher noise levels. `psi_f` does not
appear in the standstill equations and cannot be inferred from this test.
Ordinary closed-loop speed operation also does not guarantee identification:
feedback may correlate voltages and currents or fail to excite independent
electrical dynamics.

## Rotating flux-linkage commissioning

`src.rotating_identification` runs a **separate** driven-rotor experiment.
An external drive holds the rotor at 600 rpm while a fixed q-axis voltage bias
and independent d/q bipolar perturbations excite the existing PMSM electrical
plant. The requested dq voltage remains inside the 24 V linear SVPWM circle.
The measurement record contains only sampled applied voltage, current, and
mechanical speed; optional Gaussian noise is configured independently for all
three. The estimator receives the previous standstill estimates, the sampled
record, and a known pole-pair count. It never receives the true `psi_f`.

For electrical speed `omega_e = pole_pairs * omega_m`, the rotating q-axis
voltage balance is:

```text
v_q = Rs i_q + Lq (di_q/dt) + omega_e (Ld i_d + psi_f)
```

Integrating from sample `a` to `b` gives one regression row per window:

```text
y = Σ v_q[k] Δt − Rs ∫i_q dt − Lq(i_q[b] − i_q[a]) − Ld ∫omega_e i_d dt
x = ∫omega_e dt
y = x psi_f
```

The integrals of sampled current and speed use trapezoids; applied voltage is
held over each sample interval. Least squares through the origin estimates
`psi_f = Σ(x y) / Σ(x²)`. Windows avoid differentiating noisy current.
The estimator requires sustained, same-sign speed above a configurable
threshold and rejects zero-speed data. At zero speed the flux term vanishes,
so `psi_f` is unidentifiable from these equations. The estimate also depends
on correct dq alignment, known pole-pair count, accurate applied fundamental
voltage and speed, constant linear motor parameters, and adequately identified
`Rs/Ld/Lq`. Biased sensor readings or incorrect electrical parameters can bias
the flux fit. A driven rotor and programmed excitation are deliberate; normal
closed-loop operation need not supply enough independent information.

Run `python -m experiments.rotating_flux_identification` for a standalone
sampled-signal plot, fitted back-EMF voltage integral, parameter convergence,
and a CSV comparing the estimate with the hidden plant value.

## Automatic retuning and recovery

`src.commissioning.commission_from_measurements` combines both data sets into
one `CommissioningResult`. Its `retuned_controller_parameters(prior)` replaces
only `Rs`, `Ld`, `Lq`, and `psi_f` in a new controller parameter object. Known
pole pairs and the prior mechanical `J` and `B` remain the controller inputs.
Passing an accepted `commissioning_result=...` to `run_speed_foc_simulation`
constructs fresh current and speed controllers from that object. Rejected
results use the original controller parameters and report the rejection.
Current PI gains are
`Kp,d = Ld omega_c`, `Kp,q = Lq omega_c`, and `Ki,d = Ki,q = Rs omega_c`.
The speed PI uses `Kt = 1.5 pole_pairs psi_f`,
`Kp = (2 zeta omega_n J − B) / Kt`, and `Ki = omega_n² J / Kt`.
The controller also uses the new constants for dq decoupling and back-EMF
feedforward. PI state is reset at retuning; online bumpless transfer has not
been modeled.

`python -m experiments.commissioning_recovery` compares a true-parameter
reference, an incorrect controller, and the self-commissioned controller with
the **same plant and a 12 V DC bus**. The incorrect controller starts with
`Rs = 0.24 Ω`, `Ld = 0.6 mH`, `Lq = 1.4 mH`, and `psi_f = 35 mWb` against a
plant with `0.56 Ω`, `1.4 mH`, `0.8 mH`, and `15 mWb`. Sampled commissioning
data include noise. The deterministic seed gives parameter errors below
0.12%. In the 0.05 N·m load-step interval, speed RMSE falls from 10.46 to
4.41 rpm and iq tracking RMSE from 0.0137 to 0.0046 A after retuning;
the true-parameter reference is 4.41 rpm and 0.0046 A. Maximum speed dip
falls from 29.45 to 14.31 rpm. Voltage saturation occurs in all three runs.
The experiment saves parameter and performance CSV files plus identification
and recovery plots in `results/`. Full-run RMSE includes startup and should be
read alongside post-load metrics; different startup saturation can reverse
the apparent ranking of full-run iq RMSE.

This is a simulation of offline commissioning under imposed speed, not an
online estimator or hardware commissioning procedure. Mechanics, sensor
offsets, inverter nonidealities, thermal drift, magnetic saturation, and
uncertainty in rotor angle remain outside the model.

## Monte Carlo robustness validation

`src.monte_carlo` preserves the standstill estimator, rotating flux estimator,
and automatic retuning path. Run
`python -m experiments.commissioning_monte_carlo` to run the seeded design
with the current acceptance gate. The committed `commissioning_monte_carlo_*`
results and quantitative results in this section are the historical ungated
milestone; they are preserved, and rerunning now changes acceptance and retuning.
The separate `results/quality_gate/` artifacts below describe the gated workflow.
The design crosses three measurement-noise levels, four driven
commissioning speeds (0, 150, 600, and 1200 rpm), and three DC-bus voltages
(12, 24, and 48 V), with two independently drawn plants per cell: 72 cases.
One additional zero-voltage standstill case tests rank-deficient excitation.
The zero-speed cases are deliberate negative controls. The seed is `20260929`.

Each synthetic plant independently draws `Rs` uniformly from 0.25–0.75 Ω,
`Ld` from 0.65–1.55 mH, `Lq` from 0.60–1.50 mH, and `psi_f` from 12–36 mWb.
These are a chosen test envelope, not a statistical model of manufactured
motors. Mechanical parameters and pole pairs stay at their baseline values.
Low, medium, and high Gaussian measurement-noise standard deviations are,
respectively, `(0.01 A, 0.01 V, 0.02 rad/s)`,
`(0.08 A, 0.05 V, 0.05 rad/s)`, and
`(0.4 A, 0.2 V, 0.1 rad/s)` for sampled current, voltage, and speed.
Both commissioning tests use the case's bus voltage; rotating q-axis bias is
`min(6 V, 0.25 Vdc)`. The control comparison uses the same true plant for a
fixed incorrect controller and a freshly commissioned controller, with the
configured voltage limit. The 0.6 s speed/load test uses a 40 µs control
step for this population run. True plant constants are used only to simulate
measurements/control and to score errors; neither estimator receives them.

The per-case CSV retains **every** case with its inputs, true and estimated
parameters, signed percentage errors, before/after post-load speed RMSE,
post-load iq tracking RMSE, recovery time, saturation fraction, status, and
failure reason. An unavailable estimate or retuned run is blank. `NaN`
recovery time means speed did not enter and remain within ±1% of 1000 rpm
before the run ended. The JSON summary reports medians, 95th percentiles,
worst finite values, and available/missing counts. Paired statistics use only
cases with both controllers measured; the overall before and after summaries
have different denominators when estimation fails. Plots show parameter-error
distributions, paired control performance, and pairwise failure rates versus
noise, commissioning speed, and bus voltage. The intentionally unexcited
case remains in the CSV and totals but is excluded from the factorial
heatmaps.

This validation defines a **workflow success** as: all four parameter errors
within 10%; post-load speed RMSE at most 10 rpm; post-load iq RMSE at most
0.05 A; recovery within 0.10 s; and neither post-load RMSE more than 5% worse
than the mismatched controller. These are study thresholds, not guarantees
for hardware. Approximate steady-state voltage feasibility is also reported
for diagnosis: at 1000 rpm after the load step, set `id = 0`, calculate the
required `iq` from torque, then compare
`sqrt((-omega_e Lq iq)^2 + (Rs iq + omega_e psi_f)^2)` with `Vdc/sqrt(3)`.
This uses the hidden plant only in analysis, ignores transients, and is not
fed to the estimator or controller.

In the historical ungated 73-case run, **25 cases succeed (34.2%)**, 54 complete both
control runs, and 19 report estimator failure. Eighteen failures are the
zero-speed flux tests; the other is the deliberately unexcited standstill
test. Among completed estimations, 36 meet the 10% parameter criterion.
The median absolute errors for `Rs`, `Ld`, `Lq`, and `psi_f` are 0.068%,
2.04%, 1.42%, and 0.275%; their 95th percentiles are 1.19%, 46.2%,
41.7%, and 6.55%. On the 54 paired control cases, median post-load speed
RMSE falls from 8.30 to 4.42 rpm and median iq RMSE from 0.0102 to 0.00354 A.
The high-noise group has 0 successes in 24 cases, while low and medium noise
have 12/24 and 13/24. The 12 V group has 2/24 successes; 23/73 cases are
approximately voltage infeasible and 15 completed retuned cases never recover
within the simulated interval. The worst speed RMSE exceeds 500 rpm under
severe voltage shortage; retuning cannot create voltage headroom.
Among the 26 cases with nonzero speed, low or medium noise, and diagnostic
steady-state voltage feasibility, 25 meet all thresholds. The remaining case
tracks well in absolute terms but misses the strict 5% relative improvement
criterion. The overall 34.2% rate includes all deliberate boundary cases.

Failure mechanisms are visible separately: zero or insufficient driven speed
removes the flux regressor; absent standstill voltage changes make the
`Rs/Ld/Lq` regression rank deficient; excessive noise can yield positive but
inaccurate inductance estimates without an exception; and insufficient bus
voltage can prevent closed-loop tracking even with good identification.
The finite-sample failure maps pool one factor per panel and have few draws
per cell, so their percentages are diagnostic for this seeded population,
not population-wide confidence estimates. Sensor bias, correlated noise,
temperature dependence, inverter errors, and unsafe physical excitation are
still outside this simulation. The driven-rotor test holds speed with an ideal
external rig and does not enforce a commissioning current limit.

## Measured-data commissioning quality gate

`src.identification_quality` adds diagnostics to both existing regressions;
the point-estimation equations and excitation sequences are preserved.
`src.commissioning_quality.assess_commissioning` accepts only fitted estimates,
their measurement diagnostics, the known pole-pair count, and `QualityPolicy`.
It has no true motor parameters, parameter-error labels, voltage-feasibility
labels, or control outcomes. Sensor noise standard deviations are supplied as
`MeasurementNoise` metadata: known simulation settings here, independently
calibrated sensor specifications in a physical implementation. Missing metadata
is not treated as zero noise and causes rejection.

### Diagnostic equations and interpretation

For the standstill regression `y = X theta`, `theta = [Rs, Ld, Lq]`, each
window contributes rows `[integral(id), delta(id), 0]` and
`[integral(iq), 0, delta(iq)]`; `y` contains applied-voltage integrals.
Let `D = diag(norm(X[:, j]))`, `Z = X D^-1`, `G = D^-1 Z+`, and
`r = y - X theta_hat`. SVD and rank are calculated on `Z`, avoiding units
dominating the reported condition number. Physical regressor energies are
`D[j,j]^2`; normalization alone cannot reveal weak physical excitation.

At full rank, differentiating the actual least-squares estimate gives

```text
d(theta_hat) = (G G^T) (dX)^T r + G (dy - dX theta_hat)
C_theta = sum_channels sigma_channel^2 J_channel J_channel^T
SE_j = sqrt(C_theta[j,j])
```

`J` differentiates with respect to sampled current and voltage measurements,
including their occurrence in `X`. Contributions at shared integration-window
endpoints are accumulated before forming covariance. The `D^-1` map is included,
so the covariance and standard errors have physical parameter units. This is
first-order sensor-noise propagation, consistent with the sensitivity approach
in [NIST Technical Note 1297](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty).
It is **not** a calibrated confidence interval and does not include estimator
bias. Ordinary fixed-design least-squares covariance is inadequate when current
measurements also form the regressors; see [NIST's predictor-error assumption](https://www.itl.nist.gov/div898/handbook/pmd/section2/pmd216.htm).

For `m` windows of `w` intervals with sampling period `dt` and independent
current noise `sigma_i`, the expected standstill design-noise normal matrix is

```text
N = m sigma_i^2 diag(2 dt^2 (w - 1/2), 2, 2)
rho = max_a (a^T N a) / (a^T X^T X a)
```

`rho` is computed in scaled coordinates using the largest eigenvalue. It is
invariant to parameter units and warns when sensor noise accounts for much of
the observed regression information. It is not an upper bound on parameter
error or on errors-in-variables bias. The local SE can be small around a biased
estimate, which is why both diagnostics are needed.

For rotation, `x = integral(omega_e)` and
`y = integral(vq) - Rs integral(iq) - Lq delta(iq) - Ld integral(omega_e id)`.
The preserved scalar fit is `psi_hat = x^T y / E`, `E = x^T x`, hence

```text
d(psi_hat) = (x/E)^T dy + ((y - 2 x psi_hat)/E)^T dx
C_psi = C_rotating_sensor + g C_theta g^T
g = -[x^T integral(iq), x^T integral(omega_e id), x^T delta(iq)] / E
```

Standstill and rotating records are assumed independent; the second term
propagates the full electrical-parameter covariance in `Rs, Ld, Lq` order.
Speed noise enters both the speed integral and the cross-coupling integral.
The flux design-noise fraction is
`m (pole_pairs sigma_speed dt)^2 (w - 1/2) / E`.

Residual RMS is compared with propagated sensor residual RMS. For each
standstill axis the latter has variance
`sigma_i^2 ||Rs a + L b||^2 + sigma_v^2 w dt^2`, where `a` contains trapezoid
weights and `b = [-1, 0, ..., 1]`. Rotation additionally propagates current
cross-coupling and speed noise. This residual screen is conditional on the
fitted electrical constants; it does not include their prior uncertainty or
the reduction from fitting residuals. It is therefore an engineering check,
not a statistical goodness-of-fit test. Each stage also compares first-half
and second-half fits, normalized by the full-record estimate. Both halves
must be identifiable. Constant nonzero-speed open-circuit data can identify
the scalar flux parameter; voltage variation is not falsely required there.

### Frozen ACCEPT / REJECT policy

Every check must pass. Estimator exceptions, nonpositive fitted parameters,
missing diagnostics, or missing noise information produce explicit rejection.
The policy and development artifacts were committed at **`b33b227` before the
independent evaluation**. The [freeze record](docs/quality_policy_freeze.md)
records the protocol and rationale; no threshold was changed using final
evaluation data or optimized against hidden true parameters.

| Check | Budget | Engineering justification |
| --- | --- | --- |
| Rank | Full column rank | Necessary uniqueness of each fit. |
| Windows | At least 10 per stage | At least 5 windows in each temporal half, exceeding the unknown count; not a statistical sample-size guarantee. |
| Scaled condition number | ≤100 | At most two orders of directional amplification in the normalized design; separate information check still required. |
| Design-noise fraction `rho` | ≤0.05 | A 5% contamination budget below the 10% precision target; not a rigorous bias bound. |
| Largest `SE / abs(estimate)` | ≤0.10/3 | Three local sensitivity units fit inside a 10% precision budget; no 99.7% coverage claim. |
| Half-fit relative difference | ≤0.10 | Temporal consistency within the parameter precision budget; common bias can pass. |
| Residual RMS | ≤3 predicted noise RMS + 0.01 target RMS | Threefold noise margin plus explicit 1% model/integration tolerance; neither term is statistically calibrated. |
| Rotating noise RMS / fitted back-EMF RMS | ≤0.10 | Integrated back-EMF signal-to-noise ratio at least 10. |
| Minimum absolute mechanical speed | ≥10 rad/s | Existing estimator operating floor, supplemented by back-EMF SNR; zero speed cannot identify flux. |

These are reviewable engineering design tolerances, not universal optimum
thresholds or a confidence score. The development population supported retaining
the candidate policy unchanged despite conservative false rejections.

`commission_from_measurements` returns a `CommissioningResult` with
`quality.accepted`, named rejection reasons, per-check values/limits, and a
separate estimator-failure reason. Calling `retuned_controller_parameters`
on a rejected result raises `CommissioningRejectedError`. The speed simulation
instead explicitly falls back to the original parameter object, logs
`commissioning_accepted=False` and rejection reasons, and performs no
commissioning update. Accepted results continue through the existing PI and
feedforward retuning path. Manually constructed unassessed results default to
rejection. This guards normal API use, not deliberate fabrication of an accepted
Python result object.

### Development and independent evaluation

Development seed **20261001** crosses the three noise levels, 150/600 rpm,
24 V, and standstill voltage multipliers 0.08/1.0, plus an unexcited sentinel:
13 cases. Final seed **20261002** crosses the same noise/excitation levels,
0/150/600/1200 rpm, and 12/24/48 V, plus the sentinel: 73 cases. Each factorial
cell has one independently drawn plant. The common deterministic sentinel is a
structural negative control, not an independent random draw. Random plant and
sensor draws are separate across populations; a test verifies disjoint seeds.
Development did not cover the entire final operating envelope.

Accuracy is scored **after** the gate: all four absolute parameter errors must
be ≤10%. False acceptance is reported both as inaccurate/accepted and as
accepted/inaccurate complete estimates; false rejection is rejected/accurate
complete estimates. Estimator failures without all four estimates are counted
separately, not assigned an invented error. Partial estimates remain in the CSV
and overall parameter summaries. Closed-loop success uses the composite
criterion in the Monte Carlo section above, including its relative-degradation
limit. Speed and iq RMSE use the post-load interval; saturation uses the full run.

| Outcome | Development | Independent final evaluation |
| --- | ---: | ---: |
| Total cases | 13 | 73 |
| Estimator failures | 1 | 19 |
| Quality-gate rejections (complete estimates) | 8 | 33 |
| Accepted commissioning | 4 | 21 |
| Acceptance coverage | 4/13 = 30.77% | 21/73 = 28.77% |
| Inaccurate among accepted (false acceptance) | 0/4 = 0% | 0/21 = 0% |
| Accepted among inaccurate complete estimates | 0/6 = 0% | 0/27 = 0% |
| Rejected among accurate complete estimates (false rejection) | 2/6 = 33.33% | 6/27 = 22.22% |
| Accurate among accepted | 4/4 = 100% | 21/21 = 100% |
| Accurate before gating, complete estimates | 6/12 = 50% | 27/54 = 50% |
| Closed-loop success among accepted | 2/4 = 50% | 17/21 = 80.95% |
| Closed-loop success / all cases | 2/13 = 15.38% | 17/73 = 23.29% |

No observed false acceptance in 21 accepted final cases does **not** establish
a zero population risk. The gate improves observed accepted-estimate accuracy
at the cost of coverage; this is not evidence that it improves overall workflow
success compared with a separate ungated population having different plants.

Final absolute parameter errors, in percent (complete estimates only):

| Parameter | Accepted median / p95 / worst (n=21) | Rejected median / p95 / worst (n=33) |
| --- | ---: | ---: |
| Rs | 0.0644 / 0.2004 / 0.3310 | 2.0779 / 52.1388 / 58.7316 |
| Ld | 1.2541 / 4.5592 / 4.6201 | 77.8349 / 99.3161 / 99.5814 |
| Lq | 1.0657 / 3.7185 / 5.0665 | 62.6344 / 98.9996 / 99.4959 |
| psi_f | 0.0752 / 1.2176 / 1.6621 | 8.9286 / 62.0450 / 138.3361 |

Development accepted median errors for `Rs/Ld/Lq/psi_f` were
0.0436% / 0.2281% / 0.7293% / 0.0503%; rejected medians were
2.1525% / 60.8446% / 53.9022% / 5.4033%. Both JSON summaries retain
unrounded medians, p95, worst values, and available/missing counts.

Final accepted-controller comparisons retain all 21 accepted cases:

| Metric | Mismatched median / p95 / worst | Commissioned median / p95 / worst |
| --- | ---: | ---: |
| Post-load speed RMSE [rpm] | 7.5141 / 459.2700 / 469.1878 | 4.4143 / 459.2759 / 469.1840 |
| Post-load iq RMSE [A] | 0.007944 / 4.694120 / 4.701372 | 0.003147 / 4.694122 / 4.701372 |
| Recovery time [s], 17 finite pairs | 0.04932 / 0.069768 / 0.07204 | 0.03228 / 0.03244 / 0.03244 |
| Saturation fraction, full run | 0 / 0.98240 / 0.98467 | 0 / 0.98247 / 0.98600 |

Four accepted cases never recover; they remain in counts and CSV, with `nan`
recovery times. All four have a 12 V bus and are voltage infeasible under the
post-hoc steady-state check. The entire final population contains 22
voltage-infeasible cases. The gate correctly accepts their electrical estimates
because measurement quality cannot certify operating-point voltage feasibility.
Seventeen accepted cases improve each of speed and iq RMSE; four worsen each
metric slightly or substantially (these need not be the same cases for both
metrics). Development medians were 6.0502 → 5.5746 rpm and 0.408805 → 0.400441 A,
with one accepted unrecovered case and only three finite recovery pairs.

The 19 final estimator failures comprise 18 deliberately unsupported zero-speed
excitation requests and one unexcited standstill rank failure. High-noise cases
are all rejected or fail. Six accurate final rejections have low noise and 8%
standstill excitation, failing only the information-contamination budget.
The rejected inductance errors approaching 100% illustrate the earlier
positive-but-biased-estimate failure mode. Raw residual alone does not separate
these cases, and small flux local SE does not account for bias transferred
from the electrical fit. The combined gate retains the conservative rejection;
final labels were not used to relax it.

Artifacts (every case retained, including rejected and voltage-infeasible cases):

- [Development cases](results/quality_gate/development/cases.csv) and [summary](results/quality_gate/development/summary.json).
- [Independent evaluation cases](results/quality_gate/evaluation/cases.csv) and [summary](results/quality_gate/evaluation/summary.json).
- [Diagnostics versus post-hoc error](results/quality_gate/evaluation/diagnostics_vs_error.png).
- [Accepted/rejected error distributions](results/quality_gate/evaluation/accepted_rejected_errors.png).
- [Acceptance regions versus noise, speed, and excitation](results/quality_gate/evaluation/acceptance_regions.png).
- [Accepted control performance, including failures](results/quality_gate/evaluation/accepted_control_recovery.png).

### Review, tests, and limitations

Tests cover good-data acceptance and retuning; zero/low speed, rank failure,
missing noise metadata, weak excitation, and excessive noise; rejection
preserving the original controller object and trajectory; scalar open-circuit
flux identifiability; unit-invariant information ratios; and independent
finite-difference checks of standstill and flux covariance, including shared
samples and propagated prior covariance. A deterministic population test
preserves all outcome categories and verifies post-hoc scoring cannot change
recorded decisions. The gate operates with estimate/diagnostic-only objects.
At the electrical-quality milestone the full local suite passed **53 tests**;
the mechanical milestone below adds to that baseline.

Critical review found no true-parameter input to the gate or retuning decision:
true constants are used by physical simulation and post-hoc error/feasibility
analysis only. The final run used the frozen source policy. Sensor metadata
contains noise levels, not hidden electrical constants. Existing baseline,
saturation, identification, and recovery tests remain part of the full suite.

Uncertainty assumes independent zero-mean sensor channels/samples with known
standard deviations. It is a local linearization, omitting errors-in-variables
bias, second-order noise products, offsets, rotor-angle errors, thermal drift,
inverter errors, and noise-calibration uncertainty. The two commissioning
records are assumed independent. A common voltage bias can mimic flux and
pass residual/half-fit checks. Local SE must not be interpreted as a confidence
probability. The small stratified population, one draw per cell, and pooled
heatmaps do not establish population-wide rates. The gate does not enforce
commissioning current safety, select excitation adaptively, or guarantee
voltage feasibility. Rejected cases use the prior controller; their hypothetical
retuned performance is deliberately unavailable. Future policy revisions need
fresh held-out evaluation, and hardware deployment needs a separate operating
feasibility and excitation-safety stage.

## Mechanical J/B identification and full commissioning

The electrical-only API remains available and preserves prior `J/B`. The new
normal full-commissioning path identifies both mechanical constants before
retuning the outer speed loop. Known pole-pair count is still required; no true
electrical or mechanical motor constants are needed by the estimator or full
retuning path. An oracle controller exists only in evaluation experiments.

### Integrated model, reconstructed torque, and known load

The existing plant obeys `J d(omega_m)/dt = Te - Tload - B omega_m`.
Integrating between sampled endpoints `ta` and `tb` gives

```text
integral(Te - Tload) dt = J [omega_m(tb) - omega_m(ta)] + B integral(omega_m) dt
y_k = X_k theta,  X_k = [delta(omega_m), integral(omega_m)], theta = [J, B]
Te_hat = 1.5 p [psi_f_hat iq_measured + (Ld_hat - Lq_hat) id_measured iq_measured]
```

`src.mechanical_identification` receives `MechanicalMeasurements`, electrical
estimates, flux estimate, and known pole count. It imports no plant model and
has no input for hidden torque, `J`, or `B`. It integrates sampled reconstructed
torque and speed using trapezoids, then fits column-scaled least squares. Speed
differences occur only at window endpoints; there is no pointwise numerical
speed differentiation. `y` has units N m s; the two columns have units rad/s
and rad, respectively, yielding J in kg m² and B in N m s/rad (radian treated
as dimensionless).

**The experiment explicitly has zero external load.** The measurement record
must declare `known_load_torque_nm=0.0`; unknown (`None`) load is rejected. The
estimator can subtract an explicitly known constant load, but its measurement
uncertainty is not modeled. This does not estimate an arbitrary unknown load.
Unknown load can be absorbed into the inferred friction, especially over a
narrow operating region, and can yield a biased estimate with small residual.

### Mechanical excitation

`src.mechanical_excitation` simulates the existing freely rotating PMSM plant
with the existing current FOC, using accepted electrical estimates for its
controller. It does not impose speed or use a speed PI during identification.
The q-current reference is `[0.8, 0, 0.4, -0.4, 0] A`, repeated twice, each
plateau lasting 0.25 s. The d-current reference is zero. Acceleration,
deceleration, and zero-current coast intervals separate inertia and viscous
torque; the repeated pattern supplies both temporal halves with useful motion.
Default runtime is 2.5 s, control/RK4 step 40 µs, and sampled record period 1 ms.
Fifty nonoverlapping 50 ms windows form the default regression. Shared endpoints
are retained when propagating noise.

The simulation enforces a configured 1 A reference limit and the existing
`Vdc/sqrt(3)` voltage circle with anti-windup (48 V default commissioning rig).
These are simulation constraints, **not physical hardware safety guarantees**.
Current and speed feedback to the excitation FOC are ideal; independent
zero-mean noise is added to the recorded measurements. Default measurement
standard deviations are 0.01 A and 0.05 rad/s; seed 701. The main comparison
reaches approximately 52 rad/s during commissioning. The electrical test stages
keep their previous locked-rotor and externally driven-rotor assumptions.

### Mechanical diagnostics and uncertainty

The estimator records rank, singular values and condition number of the
column-normalized design, physical column norms/energies, residual RMS,
first/second-half fit consistency, and local sensitivity. A column's conditional
norm is the norm remaining after projecting out the other column: this captures
information unique to J or B. Normalizing columns cannot manufacture physical
information from weak acceleration or tiny speed signals.

Using the earlier notation `G = X+` in physical parameter units,

```text
d(theta_hat) = G (dy - dX theta_hat) + (G G^T) dX^T r
C_sensor = sigma_speed² Js Js^T + sigma_current² (Jd Jd^T + Jq Jq^T)
N = m sigma_speed² diag(2, dt² (w - 1/2))
rho = max_a (a^T N a)/(a^T X^T X a)
```

The speed-noise Jacobian includes both endpoint differences and integrals;
current Jacobians differentiate the reconstructed torque. Sample contributions
shared by adjacent windows are summed before covariance is formed. The
expected conditional sensor residual variance in a window is

```text
sigma_speed² ||J b + B a||²
  + sigma_current² (||a * dTe/did||² + ||a * dTe/diq||²)
```

Here `a` is the trapezoid-weight vector, `b=[-1,0,...,1]`, and `*` means
elementwise multiplication. This is a local noise diagnostic, not a residual
chi-square statistic. It excludes model bias and electrical-parameter error
from the residual budget.

Torque also inherits electrical error. For `q=[Ld,Lq,psi_f]`, let
`A = G d(y)/d(q)`, with window derivatives
`1.5p [integral(id iq), -integral(id iq), integral(iq)]`. The mechanical
diagnostics expose `A` and use each supplied marginal electrical standard error
`s_q` to form

```text
electrical_SD_bound_j = sum_l abs(A[j,l]) s_q[l]
total_local_SD_bound_j = sqrt(C_sensor[j,j]) + electrical_SD_bound_j
```

This triangle-inequality bound does not assume that flux and inductance errors
are independent: the flux estimate already depends on the electrical fit.
It is conservative for first-order random perturbations under the supplied
marginal noise model. It does not bound systematic error, errors-in-variables
bias, current-product higher-order terms, or noise-model uncertainty. No
probabilistic confidence interval or coverage is claimed. Missing upstream
uncertainty information prevents acceptance.

### Mechanical quality and full retuning

All checks below must pass; each failure has a named `mechanical.*` reason.
The existing electrical gate is unchanged. Full rank alone never implies
acceptance.

| Mechanical check | Budget and rationale |
| --- | --- |
| Rank and windows | Rank 2, at least 10 windows: identifiable full fit and redundant temporal halves. |
| Scaled condition | ≤100, preserving the electrical gate's numerical amplification budget. |
| Design-noise fraction `rho` | ≤5%, preserving the electrical information-contamination budget; not a bias bound. |
| Relative local SD bound | ≤0.10/3 for each parameter; three sensitivity units within a 10% precision budget. |
| Conditional component SNR | ≥3 for both `abs(theta_j) norm(X_j projected away from other column)/sqrt(m) / sensor_residual_RMS`; each physical contribution must exceed three sensor-noise units. |
| Temporal half-fit difference | ≤10% of the full estimate, requiring consistency within the precision budget. |
| Residual RMS | ≤3 predicted sensor RMS + 1% target RMS, matching the explicit engineering noise/model allowance. |

Unknown load, rank-deficient records, nonpositive estimates, and malformed
measurements are explicit estimator failures. Weak acceleration harms J
information; too little speed makes friction torque hard to resolve. Constant
nonzero speed can inform B if torque/load are known, but gives no J information;
speed range alone is not a universal identifiability test. The analytical
fixtures test these distinct limitations.

`src.full_commissioning.FullCommissioningResult` nests the existing electrical
`CommissioningResult` and a `MechanicalCommissioningResult` containing its
estimate and quality decision. `complete_commissioning(electrical_result, data)`
requires accepted electrical commissioning before attempting mechanics.
The full result's `.quality` combines both decisions. Its
`retuned_controller_parameters(prior)` returns new assumptions for all six
parameters only when both stages accept. An explicit exception prevents direct
retuning on rejection; passing a rejected full result to the speed simulation
preserves the entire prior controller, logs rejection, and changes no J/B.
The accepted electrical-only result remains separately usable by explicit choice.

Current PI remains `Kp_d=Ld omega_c`, `Kp_q=Lq omega_c`, `Ki=Rs omega_c`, with
identified electrical decoupling/feedforward. Speed PI uses **identified**
`Kt=1.5 p psi_f`, `Kp=(2 zeta omega_n J - B)/Kt`, and `Ki=omega_n² J/Kt`.
Existing controller constructors do this calculation without modification.
Offline retuning resets controller state; online bumpless transfer remains absent.

### Four-controller comparison

`python -m experiments.full_commissioning_recovery` uses the earlier electrical
mismatch and a modest attached-inertia/friction scenario: true J=5e-4 kg m²,
B=3e-4 N m s/rad, versus prior J=2e-4 and B=1e-4. True electrical parameters
are `0.56 ohm, 1.4 mH, 0.8 mH, 15 mWb`; prior values are
`0.24 ohm, 0.6 mH, 1.4 mH, 35 mWb`. These values were specified before the
first mechanical run and were not selected by searching outcomes. All four
controllers use the same plant, 24 V bus, 1000 rpm command, 0.05 N m load at
0.30 s, 20 µs step, and 0.6 s duration. The voltage limit is active in the
model but does not saturate this comparison; voltage shortage is explored in
the population study. The commissioning tests themselves have zero load.

| Mechanical parameter | Estimate | Absolute error |
| --- | ---: | ---: |
| J [kg m²] | 4.992267860e-4 | 0.154643% |
| B [N m s/rad] | 2.996960067e-4 | 0.101331% |

Both gates accept. Mechanical scaled condition is 1.04690, information-noise
fraction 0.000354884, largest relative local SD bound 0.21659%, minimum
conditional component SNR 14.0876, half-fit discrepancy 0.92313%, and residual
RMS 3.30048e-5 N m s (predicted sensor RMS 3.58645e-5).

| Metric | Mismatched | Electrical-only | Full commissioned | Oracle |
| --- | ---: | ---: | ---: | ---: |
| Post-load speed RMSE [rpm] | 18.46145 | 4.42862 | 1.76792 | 1.76507 |
| Maximum post-load speed deviation [rpm] | 41.38503 | 11.87565 | 5.73125 | 5.72361 |
| Recovery within ±10 rpm [s] | 0.08928 | 0.04340 | 0 | 0 |
| Post-load iq RMSE [A] | 0.0125682 | 0.00322238 | 0.00460608 | 0.00460877 |
| Startup overshoot [rpm] | 125.07555 | 35.79090 | 6.56738 | 6.53785 |
| Full-run speed RMSE [rpm] | 260.35132 | 258.44776 | 258.18496 | 258.18466 |
| Full-run iq RMSE [A] | 0.123706 | 0.102715 | 0.104162 | 0.104195 |
| Voltage saturation fraction | 0 | 0 | 0 | 0 |

Full commissioning lowers speed RMSE by about **60.1% relative to electrical-only**
commissioning, approaching the oracle. Zero recovery time means the response
never leaves the ±10 rpm band, not instantaneous settling. The mismatched
controller still has a startup transient at the load time; its metric is
honestly reported as post-load tracking error, not isolated disturbance rejection.
Full commissioning has **higher iq RMSE than electrical-only tuning**, both
post-load and full-run. The faster speed loop demands a different current
trajectory; this tradeoff is retained. Early cumulative B error exceeds 10%
before enough motion is collected; acceptance uses the complete record and
its temporal checks, not the most favorable prefix.

Artifacts: [parameter estimates](results/mechanical_commissioning/parameters.csv),
[all performance metrics](results/mechanical_commissioning/performance.csv),
[diagnostics and check values](results/mechanical_commissioning/diagnostics.json),
[sampled measurements](results/mechanical_commissioning/measurements.csv),
[mechanical identification plot](results/mechanical_commissioning/mechanical_identification.png),
and [four-controller recovery plot](results/mechanical_commissioning/full_commissioning_recovery.png).

### Small J/B population study

The core implementation was completed before this optional extension. The
existing electrical plant generator is reused unchanged; a separate seeded
stream draws J uniformly over [1.5e-4, 9e-4] kg m² and B over
[0.5e-4, 5e-4] N m s/rad. These are chosen test envelopes, not a manufacturing
distribution. Mechanical current/speed noise levels are low (0.01 A, 0.05 rad/s),
medium (0.04 A, 0.2 rad/s), and high (0.2 A, 1 rad/s). Plateau references are
scaled to 8% or 100%. Electrical commissioning remains at low noise
(0.01 A, 0.01 V, 0.02 rad/s) on its existing 48 V rig; mechanical excitation and
control use the per-case bus. Every case compares all four controllers.

Development seed **20261011** has five cases (low/high noise, two excitation
scales, 24 V, plus an unexcited sentinel). Evaluation seed **20261012** has
13 cases (three noise levels, two scales, 12/24 V, plus sentinel). Each cell
has one independently drawn plant; seeds for all three measurement stages are
disjoint across populations. The gate and protocol were frozen in **`30f9c7c`**
before final evaluation, with no threshold changes afterward. The
[freeze record](docs/mechanical_policy_freeze.md) documents the budgets and the
initial shared-electrical-noise pilot, which is retained separately and excluded
from the corrected development/evaluation comparison.

| Outcome | Corrected development | Held-out evaluation |
| --- | ---: | ---: |
| Total cases | 5 | 13 |
| Electrical gate accepted | 5 | 13 |
| Mechanical estimator failures | 1 | 1 |
| Mechanical quality rejections | 1 | 7 |
| Full accepted / coverage | 3 / 60% | 5 / 38.46% |
| Inaccurate J/B among accepted | 0/3 | 0/5 |
| Accepted among inaccurate complete J/B estimates | 0/1 | 0/5 |
| Rejected among accurate complete J/B estimates | 0/3 | 2/7 (28.57%) |
| Accepted control successes | 3/3 | 1/5 (20%) |

Post-hoc mechanical accuracy means both errors ≤10%. Accepted control success
also requires post-load speed RMSE ≤10 rpm, iq RMSE ≤0.05 A, and recovery
within 0.10 s. This study's criterion does not require every metric to improve
over electrical-only control. The truth labels, oracle response, and any
voltage-feasibility analysis are absent from gate inputs. Rejected full results
run the prior-controller fallback; those metrics are labeled by acceptance and
never counted as full-commissioning successes.

| Final absolute error [%] | Accepted median / p95 / worst (n=5) | Rejected with estimates median / p95 / worst (n=7) |
| --- | ---: | ---: |
| J | 0.1565 / 0.2759 / 0.2968 | 12.9797 / 92.6496 / 96.8905 |
| B | 0.5374 / 0.9847 / 0.9995 | 11.2040 / 28.1876 / 31.5074 |

The final accepted median speed RMSE is **85.1385 rpm** for electrical-only,
full, and oracle control (rounded). Their corresponding median iq RMSE is
**4.53575 A**. This poor aggregate is retained: **four accepted plants are
voltage infeasible** at the target speed/load, and even the oracle fails. A
post-hoc steady-state check gives required magnitudes **11.9191, 7.0892,
12.7736 V** for three 12 V-bus cases (limit 6.9282 V), and **15.1284 V** for
one 24 V-bus case (limit 13.8564 V). These are case IDs 0, 1, 5, and 7.
Worst full speed RMSE is **463.7074 rpm**, and all four have unavailable
recovery times. Among accepted cases full saturation fraction has median
**91.2733%**, p95 **98.264%**, and worst **98.29%**.

The one voltage-feasible accepted case improves speed RMSE
**4.4151 → 3.2769 rpm**, versus oracle **3.2718 rpm**. Its recovery time improves
**0.03598 → 0.02130 s**, versus oracle **0.02120 s**. This is only one held-out
feasible success, not evidence of broad control reliability. Development also
contains an accepted case where electrical-only speed RMSE is **4.3876 rpm**,
full is **4.9548 rpm**, and oracle **4.8824 rpm**: recovering the intended tuning
does not guarantee lower disturbance RMSE than every mismatched tuning.

The two final false rejections are a low-noise weak-excitation case and a
high-noise full-excitation case. The latter has J/B errors 6.31%/2.39% in this
realization but fails information/sensitivity checks. High-noise weak excitation
produces positive J estimates with up to **96.89%** error; the gate rejects them.
Both populations retain the rank-deficient unexcited case. No failed/rejected
case is discarded, and no thresholds were relaxed using final error labels.

Data and plots: [development cases](results/mechanical_population/development/cases.csv),
[development summary](results/mechanical_population/development/summary.json),
[evaluation cases](results/mechanical_population/evaluation/cases.csv),
[evaluation summary](results/mechanical_population/evaluation/summary.json), and
[evaluation plot](results/mechanical_population/evaluation/population.png).
Summaries include finite-value medians, p95, worst, and missing counts. The
population is deliberately small and stratified: zero observed false acceptances
in five accepted final cases does not establish a low population failure risk.

### Mechanical limitations and review

- Unknown external load can be confounded with viscous friction; load metadata
  must describe an actually known condition. The estimator cannot verify it.
- Coulomb/static friction and stiction are absent from `B omega`. A real attached
  load changes effective J; these estimates describe the assembled simulated
  system, not an invariant unloaded rotor inertia.
- Weak acceleration, small speed signals, correlated regressors, or a temporal
  half lacking excitation can prevent useful J/B estimation. Zero or nearly
  zero viscous friction may be unresolvable and rejected by this positive-B fit.
- Torque reconstruction inherits electrical error. A multiplicative torque
  error can scale both J and B with a good residual; uncertainty propagation
  cannot detect unmodeled common bias.
- Sensor bias is not zero-mean noise. Correlation, calibration drift, inverter
  torque errors, angle error, and load-model errors can produce precise-looking
  biased fits. First-order sensitivity bounds do not cover these effects.
- Sampled trapezoid integration has discretization/aliasing error, especially
  around fast current transitions. This study does not identify mechanics from
  ordinary arbitrary closed-loop records or implement online adaptation.
- No claim of hardware commissioning safety follows from current references
  and voltage limits in this ideal simulation. Additional feasibility and
  excitation-safety design is still needed.

Review verified that estimator/gate modules have no plant dependency, hidden
torque input, true J/B, outcome labels, or pointwise speed differentiation.
Tests disable the plant torque method after data generation and still estimate
mechanics successfully; scaling commissioned electrical torque scales the fit,
demonstrating inherited electrical error. Finite-difference tests verify sensor
covariance and electrical sensitivity in physical units. Other tests cover
multiple J/B plants, noisy/weak/rank-deficient records, unknown load, both gate
outcomes, unchanged rejected-controller trajectories, accepted speed PI gains,
electrical-only compatibility, deterministic populations, and oracle recovery.
At the mechanical milestone the full local suite passed **74 tests**, versus
its **53-test baseline**. The operating-feasibility milestone below adds to it.

## Operating-point feasibility from accepted commissioning

Identification quality and operating feasibility are separate decisions.
Accepted electrical and mechanical estimates can describe a motor whose
requested speed/load cannot be sustained on the available bus or current limit.
`src.operating_feasibility` adds an analytical **steady-state** check. It neither
retunes the controller nor changes the existing quality gates.

### Equations and strategy

The baseline strategy is `id_ref = 0`; no field weakening or MTPA is assumed.
For a nonnegative speed request and known nonnegative resisting load:

```text
omega_m = rpm_ref * 2*pi/60
omega_e = pole_pairs * omega_m
Te_required = T_load + B_hat * omega_m
Kt = 1.5 * pole_pairs * psi_f_hat
id_required = 0
iq_required = Te_required / Kt
I_required = abs(iq_required)

vd_required = -omega_e * Lq_hat * iq_required
vq_required = Rs_hat * iq_required + omega_e * psi_f_hat
V_required = hypot(vd_required, vq_required)
V_limit = Vdc / sqrt(3)
```

These are the existing PMSM equations with electrical derivatives set to zero.
The voltage convention is unchanged: phase-neutral fundamental peak in the
amplitude-invariant dq frame and the ideal linear SVPWM inscribed circle.
The saliency term vanishes at id=0; Ld is not needed in this restricted check.
**J affects acceleration, not steady mechanical torque balance**, so the
feasibility equations and parameter extraction do not read J.

Current and voltage feasibility require `I_required <= I_max` and
`V_required <= V_limit`. Margins are limit minus requirement; utilization is
requirement divided by limit. Negative margin identifies the violated constraint;
positive margin is steady headroom. Equality is included with zero reserve.
No uncertainty or transient safety margin is silently added. A point just inside
the boundary can become infeasible under parameter error or bus variation.

### API and separation of decisions

```python
from src.operating_feasibility import OperatingPointRequest, assess_operating_point

request = OperatingPointRequest(
    speed_rpm=1000, load_torque_nm=0.05,
    dc_bus_voltage_v=24, current_limit_a=5,
)
operating = assess_operating_point(accepted_full_result, request)
```

`OperatingPointRequest` rejects negative speed/load, nonpositive bus/current
limits, and nonfinite values with `operating.invalid_request`. This first API
covers forward motoring only; zero speed/load are valid. It does not interpret
negative inputs as a regenerative/reverse operating mode.

`assess_operating_point` accepts the full commissioning result and reads only
its accepted Rs/Lq/psi_f/B estimates and known pole count. No plant object,
prior-controller defaults, hidden torque, true parameters, or simulation outcome
are inputs. Unaccepted commissioning raises `operating.commissioning_not_accepted`:
the analysis is unavailable, not a declaration that the operating point is
infeasible. Original electrical and mechanical quality decisions remain intact.
An explicit evaluation-only oracle adapter uses true parameters separately.

The immutable `OperatingFeasibility` result exposes:

- `steady_state_feasible` (`feasible` alias), `current_feasible`, `voltage_feasible`;
- requested speed/load, required torque, id/iq/current magnitude, current limit,
  current margin and utilization;
- required vd/vq/voltage magnitude, voltage limit, voltage margin and utilization,
  and electrical speed;
- `reasons` (`operating.current_limit`, `operating.voltage_limit`) and assumptions;
- classification: `feasible`, `current_limited`, `voltage_limited`, or `both_limited`.

Thus `electrical=ACCEPT`, `mechanical=ACCEPT`, `operating=INFEASIBLE` is a valid
and tested outcome. The legacy true-plant voltage diagnostic remains confined
to historical evaluation; the new normal API uses accepted estimates only.

The speed simulation now accepts `current_limit_a`, default **5 A**, and passes
it to the existing speed PI's iq-reference clamp. Default trajectories are
unchanged. This is a simulation/design limit, not an assumed hardware rating.
It limits the reference, **not instantaneous measured dq current**; current can
exceed it during saturation or transients. The analytical magnitude constraint
applies to the desired steady point. Simulated current is logged and checked
separately in dynamic validation.

### Independent simulation validation

Run `python -m experiments.operating_feasibility`. The
[protocol](docs/operating_feasibility_protocol.md) and implementation were
committed as **`e55b851` before the new held-out run**. No feasibility threshold
is learned: the classifier compares physical requirements with requested limits.
The identification gates are unchanged.

For the new study, dynamic success is defined independently from simulation:
all speed samples in the final 0.1 s must be within `max(1 rpm, 1% command)`,
and maximum measured dq current in that window must be ≤1.01 times the design
current limit. Each run starts from rest, lasts 0.6 s, applies the requested
load at 0.3 s, and uses a 40 µs step. The current tolerance allows small tracking
error; it is not an instantaneous protection specification. Full-run/post-load
speed RMSE, achieved speed, current, applied voltage, and saturation fractions
are retained even when the outcome fails.

The representative motor uses the accepted PR #8 comparison estimates. Selected
rows from all seven retained scenarios:

| Request (rpm / load N m / bus V / limit A) | Prediction | Required I / V | Current / voltage margin | Dynamic outcome |
| --- | --- | --- | --- | --- |
| 250 / 0.02 / 24 / 3 | Feasible | 0.30938 A / 1.74431 V | +2.69062 A / +12.11209 V | Success; 249.99994 rpm |
| 250 / 0.50 / 48 / 1 | Current limited | 5.64237 A / 4.75369 V | -4.64237 A / +22.95912 V | Failure |
| 2000 / 0.05 / 12 / 5 | Voltage limited | 1.25290 A / 13.29527 V | +3.74710 A / -6.36707 V | Failure; 1009.386 rpm |
| 2500 / 0.50 / 12 / 1 | Both limited | 6.42692 A / 20.04533 V | -5.42692 A / -13.11713 V | Failure |
| 1000 / 0.005 / 48 / 0.444666 | Feasible | 0.40424 A / 6.51134 V | +0.04042 A / +21.20147 V | Failure at 0.6 s; 335.499 rpm |

The voltage-limited example has full-run saturation **87.16%**, terminal
saturation **100%**, and terminal applied voltage **6.92820 V**, its SVPWM
limit. The acceleration-limited representative has **zero voltage saturation**
and succeeds when the unchanged request is run for 4 s. Steady feasibility
alone does not say how quickly the drive can reach the target.

### PR #8 held-out re-analysis

All **13 original rows** are retained. The **five accepted** cases have their
electrical/mechanical measurement stages replayed with original seeds and
settings, verifying identical J/B fits and acceptance. Replay is necessary
because the historical CSV did not save electrical estimates. True electrical
columns are never substituted into the normal feasibility API. The other eight
rows remain explicitly unavailable for accepted-parameter feasibility analysis.
Historical control metrics are reused without rerunning the four controllers.

| Original case | Required current [A] | Required voltage [V] | Voltage limit [V] | Margin [V] | Prediction |
| --- | ---: | ---: | ---: | ---: | --- |
| 0 | 0.600511 | 11.921700 | 6.928203 | -4.993497 | Voltage infeasible |
| 1 | 1.011184 | 7.088917 | 6.928203 | -0.160714 | Voltage infeasible |
| 3 | 0.420079 | 10.013569 | 13.856406 | +3.842837 | Feasible |
| 5 | 0.398940 | 12.772827 | 6.928203 | -5.844623 | Voltage infeasible |
| 7 | 0.439037 | 15.125725 | 13.856406 | -1.269319 | Voltage infeasible |

The result is **1 predicted feasible, 4 predicted infeasible**, **5/5 agreement
with oracle steady predictions**, and **5/5 agreement with historical control
success/failure**, for both commissioned and oracle controllers. All five remain
accepted identification results. The historical simulation-only success criterion
uses post-load speed RMSE ≤10 rpm, iq RMSE ≤0.05 A, and recovery ≤0.1 s; its old
parameter-error label is excluded. This differs from the new terminal-window
criterion and is not combined into a single classification rate.

### Fresh held-out population and disagreements

Seed **20261021** draws three new plants across the protocol's electrical and
mechanical ranges, each with independent commissioning noise. Each plant
receives the same seven predeclared scenarios, producing **21 cases**: low
speed/load, current limited, both limited, voltage limited, just inside/outside
the voltage boundary, and limited acceleration. Boundary bus values are
1.005/0.995 times the commissioned required voltage times sqrt(3). The
acceleration case has 10% current reserve above its predicted steady requirement.
Requests are constructed before control simulation; outcomes are not used to
select favorable cases. All three commissioning results are accepted.

| Finite-dataset result | Representative (7) | PR #8 accepted replay (5) | New held-out (21) |
| --- | ---: | ---: | ---: |
| Predicted feasible + simulation succeeds | 2 | 1 | 6 |
| Predicted infeasible + simulation fails | 4 | 4 | 9 |
| False feasible: predicted feasible + simulation fails | 1 | 0 | **3** |
| False infeasible: predicted infeasible + simulation succeeds | 0 | 0 | **3** |
| Oracle steady-prediction agreement | 7/7 | 5/5 | 21/21 |

The three held-out false-feasible cases are all acceleration limited. Terminal
currents are effectively at their limits (0.20284, 0.16700, 0.14604 A), with
zero voltage saturation. Terminal speeds are **258.761, 126.329, 240.578 rpm**
for 1000 rpm commands. Even ideal id=0 acceleration without friction/load would
reach at most approximately **357.3, 165.6, 324.5 rpm** in 0.6 s, using
`Kt_hat I_max t / J_hat` as a post-hoc transient diagnostic. This does not enter
the steady classifier. The predeclared 4 s reruns improve speeds to
**906.821, 585.513, 883.061 rpm** but **all three still fail** the same terminal
tolerance. Their original failures remain in the confusion counts; no eventual
success is claimed without simulation evidence.

The three false-infeasible cases are just outside the exact voltage boundary
(margins **-0.03625, -0.04079, -0.05640 V**). They settle around
**992.613, 991.860, 993.981 rpm**, within the allowed ±10 rpm band although
the exact 1000 rpm point is outside the id=0 envelope. All have **100% terminal
voltage saturation**. This reflects the difference between an exact operating
point and tolerance-based finite-run success, not a reason to change the
equations or hide disagreements. Overall dynamic agreement is **15/21** on
this small design. The cases share three plants and are not 21 independent
motor samples; no universal classification accuracy is claimed.

### Operating envelope and artifacts

The deterministic speed/load grid for the representative commissioned motor
uses **24 V and 2 A**, 0–3000 rpm in 50 rpm steps, and 0–0.50 N m in
0.01 N m steps. All **3,111** nodes are retained: **643 feasible**, **1,291
current limited**, **198 voltage limited**, and **979 both limited**. The plot
colors grid nodes; its pixel boundaries are resolution-limited, not a more
precise continuous boundary or a validated transient operating map.

- [Representative report](results/operating_feasibility/representative.csv) and [identified model/assumptions](results/operating_feasibility/representative_model.json).
- [Speed/load envelope plot](results/operating_feasibility/envelope.png) and [every grid node](results/operating_feasibility/envelope.csv).
- [Representative dynamics plot](results/operating_feasibility/representative_dynamics.png).
- [PR #8 re-analysis](results/operating_feasibility/pr8_reanalysis.csv), including unavailable rows.
- [Held-out predicted-versus-simulated table](results/operating_feasibility/held_out.csv), [plant/estimate audit](results/operating_feasibility/held_out_plants.json), and [aggregate results](results/operating_feasibility/summary.json).

### Limitations and verification

This is an id=0, ideal-inverter steady-state assessment using point estimates,
known requested load, and constant B. Bus sag, thermal/current ratings,
parameter uncertainty margins, Coulomb friction, sensor/inverter errors, and
dynamic voltage/current reserve are not certified. Reverse/regenerative requests
are unsupported. Field weakening could enlarge some operating regions but is
future work; it is not silently added to classify a point as feasible.

The simulated constant load torque retains its sign if a failed overloaded
trajectory reverses. Such negative achieved speeds are kept in the CSV, not
reinterpreted as valid forward motoring. The both-limited representative also
exceeds its current-reference limit in measured current under saturation;
this is evidence that reference limiting is not physical current protection.
No hardware operating instructions or safety guarantee follow from this map.

Review verified: no true-parameter or outcome input to the normal API; identical
Vdc/dq convention; no J term in steady equations; unchanged electrical and
mechanical gates; and independent dynamic labels. Tests exercise all constraint
categories, zero speed/load, invalid requests, monotonic limits, J independence,
estimate-only inputs, oracle agreement, PR #8 replay, default trajectory
preservation, configurable current references, and deterministic envelopes.
The full local suite passes **99 tests**, versus the **74-test baseline**.

## Bounded adaptive commissioning supervisor

The fixed one-shot sequence could reject informative estimates because its
initial test was too weak. The supervisor in
[`src/adaptive_commissioning.py`](src/adaptive_commissioning.py) runs the
standstill, rotating flux, and known-zero-load mechanical stages in order. It
uses their **existing, unchanged quality policies**. A failed stage may request
another sampled experiment only when its measured diagnostics and configured
test explain a specific bounded action. It does not change an estimator equation
or acceptance threshold. The simulation plant is held only by measurement
provider callbacks; the supervisor receives their sampled records, prior
controller assumptions, and optional operating request.

`SupervisorResult` reports the final state, full commissioning result if
available, operating result if requested, all `AttemptRecord`s, per-stage
attempt counts, terminal reason, and whether controller parameters were
updated. Each attempt preserves its excitation configuration, estimate if
available, quality checks/reasons, diagnostic snapshot, and retry decision.
Accepted full commissioning updates all six controller assumptions. A rejected
stage returns the original controller parameters. An accepted but
operating-infeasible case keeps accepted identification and reports
`operating_infeasible` without retrying identification.

### Frozen retry rules and bounds

The [policy and validation protocol](docs/adaptive_commissioning_protocol.md)
were committed before the independent held-out run. The policy permits at most
**four attempts per stage**. Its simulation design caps are **3 V** for the
standstill dq voltage vector (also limited by `Vdc/sqrt(3)`), **0.8 s**
standstill duration, **1200 rpm** imposed rotating speed, **0.6 s** rotating
duration, **1 A** mechanical current-reference/plateau magnitude, and **0.5 s**
per mechanical plateau. Supported increments are at most 2×, except the
explicit small excitation introduced after a known zero-input failure.

Standstill information/precision failures increase bounded voltage and then
duration; poor conditioning changes the bipolar switching pattern. Weak
rotating back-EMF or speed information increases imposed speed, then duration.
Mechanical component SNR and relative local sensitivity distinguish weak J
information, which calls for stronger acceleration plateaus, from weak B
information, which calls first for longer speed/coast plateaus. Temporal
inconsistency calls for a longer record. An excessive residual stops as a
model-fit concern. Unsupported estimator failures, including an invalid
locked-rotor speed record, stop explicitly. A retryable failure on the last
allowed attempt reports `retry_budget_exhausted`; reaching an excitation cap
with no useful action reports a terminal design limit. New deterministic
seeds provide new measurement realizations; a lucky noise draw is not treated
as proof that excitation improved observability.

The three decisions remain separate: **identification quality**, **steady
operating feasibility**, and **finite-run control success**. The supervisor
never reads true parameter errors, hidden torque, oracle performance, or
closed-loop outcome to accept, retry, or stop. Operating feasibility uses
accepted estimates only. A steady-feasible result makes no claim about
acceleration time or transient tracking.

### Paired development and independent evaluation

The [experiment](experiments/adaptive_commissioning.py) uses the same plant and
cached initial noisy records for one-shot and adaptive methods in each case.
Nine predefined cells cover normal excitation, weak standstill, weak flux,
weak mechanical, combined weak, medium/high noise, zero standstill input, and
an accepted but voltage-infeasible operating request. Different deterministic
seeds draw independent plants for development (**20261031**) and held-out
evaluation (**20261101**). Truth is stored separately and used only afterward
to score absolute parameter errors. All nine cases are retained in each
population, including failed and unscorable cases.

| Result | Development one-shot | Development adaptive | Held-out one-shot | Held-out adaptive |
| --- | ---: | ---: | ---: | ---: |
| Full acceptance | 4/9 | 8/9 | 3/9 | 7/9 |
| Accurate accepted (all six errors ≤10%) | 4 | 8 | 3 | 7 |
| False acceptance among accepted | 0/4 | 0/8 | 0/3 | 0/7 |
| False rejection among accurate complete estimates | 1/5 | 0/8 | 2/5 | 1/8 |
| Rejections without six estimates | 4 | 1 | 4 | 1 |
| Operating-infeasible accepted cases | 1 | 1 | 1 | 1 |
| Control successes among accepted feasible simulated cases | 3/3 | 7/7 | 2/2 | 6/6 |

Adaptive commissioning recovered **four** one-shot rejections in each
population. Successful adaptive cases required development retry counts
`[0,1,0,3,4,0,1,0]` and held-out counts `[0,0,1,3,5,1,0]` across all stages.
**No case exhausted the configured attempt count**; one development case and
two held-out cases stopped as non-retryable or at a design limit. The held-out
combined-weak case needed one standstill, one rotating, and three mechanical
retries before all measured-data checks passed. The initially weak mechanical
cases gained enough information through longer and stronger plateaus without
lowering the gate standards.

The held-out **medium-noise** case remained rejected after two mechanical
retries: component excitation stayed below the frozen threshold after the
duration and current caps were reached. Post-hoc errors in its final J and B
estimates were **0.7924%** and **0.0034%**, so it is the one adaptive false
rejection among eight complete accurate estimates. The high-noise case failed
the existing locked-rotor measured-speed validity check and was not retried.
The accepted voltage-infeasible case had an estimated voltage margin of
**−12.7698 V** at the requested 2000 rpm; identification stayed accepted and
no control success was imputed. No closed-loop run was used to choose a retry.

Among held-out adaptive cases with six estimates, median absolute errors were
**0.0583% Rs, 0.1478% Ld, 0.3364% Lq, 0.0571% psi_f, 0.1327% J, and
0.1636% B**. All seven accepted cases met the post-hoc 10% per-parameter rule.
Their six operating-feasible control runs met the predeclared post-load speed,
iq, and recovery criteria. On those held-out feasible accepted subsets,
one-shot median post-load speed/iq RMSE was **2.1822 rpm / 0.00303 A**
(`n=2`); adaptive median was **1.7468 rpm / 0.00359 A** (`n=6`). These
subsets differ because adaptation accepted more cases, so the medians are not
a paired performance-improvement estimate. These are finite results on nine independently
drawn scenario plants, not calibrated reliability or safety guarantees.

- [Development case table](results/adaptive_commissioning/development/cases.csv), [attempt history](results/adaptive_commissioning/development/attempts.json), and [summary](results/adaptive_commissioning/development/summary.json).
- [Held-out case table](results/adaptive_commissioning/evaluation/cases.csv), [attempt history](results/adaptive_commissioning/evaluation/attempts.json), and [summary](results/adaptive_commissioning/evaluation/summary.json).
- [Held-out example attempt trace](results/adaptive_commissioning/evaluation/example_trace.json), [attempt plot](results/adaptive_commissioning/evaluation/attempts_to_acceptance.png), [retry-reason plot](results/adaptive_commissioning/evaluation/retry_reasons.png), and [accepted/rejected error plot](results/adaptive_commissioning/evaluation/parameter_error_by_decision.png). The [truth audit](results/adaptive_commissioning/evaluation/truth_posthoc.json) is separate from supervisor history.

### Limits of adaptation

Stronger simulated excitation cannot create information beyond the configured
limits and cannot guarantee gate acceptance. Sensor bias and model mismatch may
survive noise-based diagnostics; unknown mechanical load remains confounded
with friction in the current model. Accepted commissioning does not imply an
achievable requested operating point. Steady-state feasibility does not
guarantee finite-time tracking. No field weakening, online operation-stage
adaptation, inverter nonideality, physical protection design, or hardware
commissioning procedure is included. The excitation caps are simulation
choices, not hardware-safety prescriptions.

The full local regression suite passes **115 tests**, including the existing
electrical, mechanical, and operating-feasibility tests.

## Milestone 16 — Dynamic operating feasibility

Steady-state current/voltage feasibility does not answer whether startup can
finish before a deadline. [`src/dynamic_feasibility.py`](src/dynamic_feasibility.py)
keeps identification quality, steady feasibility, and dynamic capability separate.
`assess_dynamic_operating_point(accepted_full_result, request, config)` takes
accepted estimates and design settings only, with no hidden plant or outcome
input. Its immutable result retains both an quasi-steady model estimate and
an existing-controller prediction, plus limiting factors and reasons. It never
changes gates, controller assumptions, or adaptive retry decisions.

### Quasi-steady and controller models

For forward id=0 motoring, with `omega_e = p*omega_m` and `Vlim = Vdc/sqrt(3)`:

```text
a = (omega_e*Lq)^2 + Rs^2
b = 2*Rs*omega_e*psi_f
c = (omega_e*psi_f)^2 - Vlim^2
a*iq^2 + b*iq + c <= 0
```

When `c <= 0`, the nonnegative voltage-limited root is calculated as
`iq_v = 2*(-c)/(b + sqrt(b^2 - 4*a*c))`, avoiding subtractive cancellation
(the zero-reserve root is zero). When `c > 0`, even zero motoring current is
outside the quasi-steady voltage domain. Apply:

```text
iq_available = min(Imax, iq_v)
Te_available = 1.5*p*psi_f*iq_available
alpha_max = (Te_available - Tload - B*omega_m)/J
T_quasi_steady_estimate = integral[d(omega_m)/alpha_max(omega_m)]
```

Integrate to the **lower tolerance-band boundary**, not silently to a different
exact target. Nonpositive acceleration blocks entry in this model; otherwise
refine the trapezoid grid until consecutive times change by at most 0.1%.
Unresolved integration returns an indeterminate quasi-steady deadline result.
`quasi_steady_deadline_met` compares entry time **plus required hold**
with the deadline. Current, voltage, coincident limits, acceleration margin,
and the limiting/bottleneck speed are retained along the trajectory.

This is a **quasi-steady model-specific time estimate**, not a physical minimum
or universal lower bound. It assumes instantaneous torque and omits `Lq*diq/dt`.
The full dq transient simulation can enter the band earlier, **even using the
same commissioned parameters**. A False quasi-steady deadline result does not
physically rule out a transition; True does not guarantee controller success.

The second calculation constructs a complete motor model from identified
`Rs/Ld/Lq/psi_f/J/B/p` and runs the existing 300 Hz current / 10 Hz speed PI,
SVPWM vector saturation, anti-windup, and iq-reference limiter. Both its plant
model and controller use estimates. Independent hidden-plant simulations
exist only in the experiment, **after prediction**. The only historical
simulator extension is `initial_speed_rpm=0.0`; old defaults are preserved.

### Deadline and interpretation

`DynamicOperatingRequest` requires a nonnegative initial speed and resisting
load, target greater than initial speed, positive finite bus/current/deadline,
and a positive hold. The default band is ±`max(1 rpm, 1% target)` and hold
**0.1 s**. Load is constant from t=0; initial dq currents and PI states are zero.
Success requires a contiguous sampled hold completed before the deadline,
finite signals, and `abs(iq_ref) <= Imax`. First entry, qualified entry, hold
completion, final-band state, measured-current peak and saturation are separate
outputs. A brief crossing is insufficient; a qualified hold is not permanent
settling. Historical post-step states are interpreted at `(k+1)*dt` here,
without changing old log timestamps. Downsampling plots does not affect scoring.

Exact-target steady feasibility and lower-band steady feasibility remain
separate. Near a voltage boundary a drive can hold within ±10 rpm while being
unable to reach exactly 1000 rpm. Reference current limiting does not prevent
all transient measured-current overshoot. The unconstrained mechanical plant
can briefly reverse under a constant load before current builds up; minimum
speed and `dynamic.reverse_speed_excursion` expose that scope caveat. No
reverse/regenerative request analysis is supported.

### Reproduce validation

```bash
python -m experiments.dynamic_operating_feasibility --population development
# Freeze method/protocol before inspecting independently seeded evaluation.
python -m experiments.dynamic_operating_feasibility --population evaluation
python -m pytest -q
```

The [fixed protocol](docs/dynamic_feasibility_protocol.md) and development
artifacts were committed in **717ef32** before held-out execution. Seeds
**20261002 / 20261003** draw three development / five evaluation motors with
eight scenarios per motor. Boundaries and randomized request settings use
estimates only. Rejected commissioning and evaluation errors keep their rows.
This is a small scenario sample with shared motors, not a reliability estimate.

### Post-evaluation semantics correction

PR #11 review corrected the API and artifact naming **after** the original
held-out negative finding. `DynamicFeasibilityResult.quasi_steady` contains
`quasi_steady_transition_time_estimate_s`, `quasi_steady_completion_time_estimate_s`,
`quasi_steady_deadline_met`, and `quasi_steady_band_reachable`. Reachability and
deadline flags describe only the reduced model, not physical impossibility.
Nonpositive acceleration, missed deadline and unresolved integration reasons
are also explicitly scoped to that model. No numerical method, controller,
population/seed, gate or success criterion changed. Original saved evaluation
values are preserved; plot labels were rebuilt from those CSVs with
`python -m experiments.dynamic_operating_feasibility --replot-saved`. No
replacement held-out population was run.

### Quantitative results

Eight representative requests retain **8/8** controller/outcome agreement,
**4** successes, and **5** quasi-steady completion estimates within deadline.
Times below are seconds; controller columns are **qualified band-entry times**, requiring an
additional 0.1 s hold. A dash means no qualified hold before the deadline.

| Scenario (deadline) | Quasi-steady entry estimate | Predicted qualified entry | Actual qualified entry | Outcome |
| --- | ---: | ---: | ---: | --- |
| Easy 250 rpm (0.6 s) | 0.05257 | 0.09344 | 0.09356 | Success |
| Slow 1000 rpm (0.6 s) | 3.63427 | — | — | Failure; 336.73 rpm final |
| Same slow point (4 s) | 3.63427 | 3.63484 | 3.65108 | Success |
| Stronger current (0.6 s) | 0.89031 | — | — | Failure; 721.58 rpm final |
| Voltage-limited 2000 rpm (0.6 s) | 0.35287 | 0.45824 | 0.45864 | Success; 61.45% saturation |
| Outside exact voltage boundary (0.6 s) | 0.30847 | — | — | Failure; 983.75 rpm final |
| Unreachable 2000 rpm / 12 V (0.6 s) | — | — | — | Failure; 1008.79 rpm final |
| Moving start 250→1000 rpm (0.6 s) | 0.27587 | 0.27972 | 0.28020 | Success |

Development: **24/24** agreement, 11 successes, zero false predicted successes
or failures. Held-out: **40/40** agreement on five motors, **19** successes,
**21** failures, zero unavailable/error rows, zero false predicted successes
or failures. Quasi-steady completion estimates meet **20/40** deadlines.
The 19 jointly qualified holds have median signed entry-time error **−0.00020 s**, maximum
absolute error **0.00492 s**. Limiting factors: **25 current-only**, **15
current+voltage**. Four of five held-out slightly outside exact voltage
boundaries succeed within the band; the fifth remains at **988.61 rpm**.

Negative findings are retained. Actual first entry precedes the quasi-steady
estimate in **3/40** held-out rows. Motor 3's slow case enters **4.307 ms**
earlier, consistent with point-estimate error; motor 4's high-speed and boundary
cases enter **1.251 / 4.301 ms** earlier. For those latter two, even the
commissioned-model controller enters before its own quasi-steady estimate,
showing the effect of omitted dq transients. Inspection of the saved records
also finds motor 3's same-model high-speed entry **151.25 µs** before its estimate
(comparable to the 0.1% integration-refinement tolerance): three same-model
early entries in total, two overlapping the three hidden-plant cases. These do not cause a binary
deadline disagreement here. Brief reverse excursions occur in **35/40**
held-out traces; the minimum across that population is **−0.01885 rpm**.
The representative longer run's entry prediction error is **−16.24 ms**,
larger than the held-out maximum; it is not omitted from the report.

Replayed M14 acceleration cases have quasi-steady entry estimates **5.18108 /
11.40166 / 5.55408 s**. Predictions and independent outcomes fail at both
0.6 s and 4 s: **6/6 agreement**. The t=0 load and hold criterion differ from
M14; saved historical outcomes remain separate. No algorithm was tuned to
force these outcomes. The original implementation passed **147 tests** (115 baseline + 32 new).
The semantics follow-up passes **151 tests**, including preserved-evidence,
same-model deadline-counterexample and API/documentation regression checks.

Artifacts: [representative rows](results/dynamic_operating_feasibility/representative.csv),
[held-out rows](results/dynamic_operating_feasibility/held_out.csv),
[summary](results/dynamic_operating_feasibility/summary.json),
[M14 retrospective](results/dynamic_operating_feasibility/m14_retrospective.csv),
[response comparisons](results/dynamic_operating_feasibility/representative_dynamics.png),
and [transition-time map](results/dynamic_operating_feasibility/transition_time_map.png).
The folder also retains development rows, separate plant/estimate audits,
downsampled representative traces and the complete capability-map grid.

### Assumptions and remaining work

Simulation/design analysis only: accepted identified **point estimates**,
known constant external load, constant viscous friction, ideal bus and linear
SVPWM circle, id=0 command, no field weakening or MTPA. Finite controller
transients can produce nonzero id. There are no uncertainty reserves or
hardware guarantees. Inverter switching, sensor/inverter nonidealities, thermal
drift and realistic delays are not modeled; realistic nonidealities belong to
**Milestone 17**, which is not implemented here.
