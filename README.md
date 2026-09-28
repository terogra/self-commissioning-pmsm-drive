# Self-Commissioning PMSM Drive

Python model of a permanent-magnet synchronous motor (PMSM) drive. The current
stage includes a dq-axis plant, Clarke/Park transforms, cascaded speed and dq
current PI control, a DC-bus voltage constraint, parameter mismatch studies,
and a two-stage electrical commissioning workflow. Locked-rotor excitation
estimates `Rs`, `Ld`, and `Lq`; driven-rotor excitation estimates `psi_f`.
Measured-data quality checks now decide whether those parameters may retune
the current and speed PI loops. Rejected commissioning preserves the original
controller assumptions. Independent development and evaluation populations
measure this gate's coverage, estimation accuracy, and control outcomes.

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
The full local suite passes: **53 tests** (`python -m pytest -q -p no:cacheprovider`).

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
