# Engineering development log

This is a living engineering-development journal for the Self-Commissioning PMSM Drive. Update it after every future milestone with the decision made, evidence from code/tests/results, unexpected observations, and remaining limits. Entries below reconstruct completed work from the repository's commit order, merged pull requests, README, and committed experiment outputs. A result described as “later validation” was measured after the milestone's initial commit; no unrecorded debugging history is implied.

## Milestone 1 — PMSM dq-axis mathematical model

### Problem / Motivation

The project needed electrical and mechanical dynamics before a current or speed controller could be evaluated.

### Engineering Decision

Represent the motor in the rotor-aligned dq frame with state `[id, iq, mechanical speed, electrical angle]`. Include stator resistance, separate d/q inductances, permanent-magnet flux linkage, pole pairs, inertia, viscous friction, and load torque. Use fourth-order Runge–Kutta (RK4) integration for the first simulation.

### Implementation

Commit `248fb1b` added [`PMSMParameters` and `PMSMModel`](../src/motor.py) and the [open-loop simulation/RK4 step](../src/simulation.py). The model computes dq current derivatives, electromagnetic torque including the reluctance term when `Ld != Lq`, rotor acceleration, and electrical-angle rate. The initial example applies a constant q-axis voltage.

### Problems / Unexpected Results

No model defect or failed run is recorded in this commit. A fixed open-loop voltage cannot regulate speed against load changes; this became measurable in the later load sweep.

### Resolution

The plant was retained as the common simulation model. A later [open-loop load sweep](../results/open_loop_load_sweep.csv), added in commit `6104b25`, checked torque balance rather than treating a single no-load trace as validation.

### Validation / Results

The later sweep at 0, 0.05, and 0.10 N·m load recorded steady-state speeds of **760.63, 740.40, and 720.95 rpm**, respectively. Its torque-balance errors were about `6 × 10^-14` N·m. [Motor equation tests](../tests/test_motor.py), also added later, check surface-PMSM torque, the initial standstill q-current derivative, and load-induced deceleration. These checks support the implemented equations; they are not hardware validation.

### What We Learned

The model reproduces the expected direction of load-speed change and mechanical torque balance, while showing why voltage-only operation is insufficient for speed regulation.

### Remaining Limitations

Parameters are constant and lumped. The model omits iron loss, saturation, temperature change, spatial harmonics, and inverter switching.

### Next Decision

Add frame transforms and tests so three-phase quantities and rotor-aligned control calculations have a consistent convention.

## Milestone 2 — Clarke/Park transforms and initial validation

### Problem / Motivation

The dq plant alone did not establish how balanced three-phase signals map into the stationary and rotating reference frames used by FOC.

### Engineering Decision

Use an amplitude-invariant Clarke transform and a rotor-angle Park rotation, each with an inverse. Validate round trips before relying on the frame convention in the controller.

### Implementation

Commit `6104b25` added [Clarke, inverse Clarke, Park, and inverse Park functions](../src/transforms.py) and [round-trip tests](../tests/test_transforms.py). This work was committed together with the first current FOC implementation; the two milestones are separated here by engineering purpose, not by a separate Git commit.

### Problems / Unexpected Results

No transform failure is recorded. The inverse Clarke implementation assumes the balanced, zero-sequence-free three-phase subspace; the tests do not cover unbalanced zero-sequence signals.

### Resolution

The tests reconstruct the chosen balanced abc example and the chosen alpha-beta example at a nonzero electrical angle. The amplitude convention is documented in the transform functions.

### Validation / Results

[`test_clarke_round_trip`](../tests/test_transforms.py) reconstructs `(2, -1, -1)` within `np.isclose` tolerance. `test_park_round_trip` reconstructs `(alpha, beta) = (1.4, -0.8)` at `theta_e = 1.2 rad`. No separate waveform- or hardware-based transform validation is committed.

### What We Learned

Round-trip tests catch sign, angle, and scaling mistakes in the implemented convention before those mistakes are embedded in closed-loop results.

### Remaining Limitations

The tests cover selected balanced cases, not sensor offsets, angle-estimation errors, or all possible three-phase waveforms.

### Next Decision

Use the established dq convention to close the current loops and compensate dq coupling and back-EMF.

## Milestone 3 — dq current FOC

### Problem / Motivation

Fixed voltage produces load-dependent speed and does not directly hold the torque-producing q current or flux-axis d current at requested values.

### Engineering Decision

Use separate d/q PI current loops with voltage feedforward for cross-coupling and permanent-magnet back-EMF. The nominal test commands `id = 0 A` and `iq = 1 A`.

### Implementation

Commit `6104b25` added the [PI controller](../src/controllers.py), [current FOC controller](../src/foc.py), and [current-control simulation](../src/foc_simulation.py). The [FOC load sweep](../experiments/foc_load_sweep.py) was added in the next commit, `cccd97f`, as further validation. The current-loop gains use `Kp,d = Ld omega_c`, `Kp,q = Lq omega_c`, and `Ki,d = Ki,q = Rs omega_c`; the voltage commands compensate `-omega_e Lq iq` on d and `omega_e(Ld id + psi_f)` on q.

### Problems / Unexpected Results

The load sweep demonstrates a remaining structural limit: current tracking alone does not hold rotor speed constant as load rises. No current-loop implementation failure is documented.

### Resolution

The FOC load sweep checks current tracking separately from speed behavior. Speed regulation was deferred to an outer loop rather than changing the current-loop objective.

### Validation / Results

The [load-sweep assertions](../experiments/foc_load_sweep.py) cover 0, 0.05, and 0.10 N·m, require final `|id| < 0.001 A` and `|iq - 1 A| < 0.001 A` in each run, and require speed to decrease monotonically as load increases. The repository does not retain a numerical FOC load-sweep table, so no exact speeds are asserted here.

### What We Learned

Good dq current regulation is distinct from good speed regulation; the latter needs its own feedback objective.

### Remaining Limitations

The first current controller had no physical voltage magnitude limit, inverter model, measurement noise, or sampling delay.

### Next Decision

Add an outer speed controller that requests q current while preserving the faster current loop.

## Milestone 4 — Cascaded speed control

### Problem / Motivation

The fixed `iq = 1 A` FOC experiment could not reject load-induced speed droop or follow a specified speed reference.

### Engineering Decision

Place a slower speed PI loop outside the dq current loops. The speed loop converts speed error into a bounded iq reference; the current loops continue to command dq voltage.

### Implementation

Commit `cccd97f` added [`SpeedController`](../src/speed_control.py), the [speed FOC simulation](../src/speed_foc_simulation.py), bounded PI output handling, and the [FOC load-sweep validation script](../experiments/foc_load_sweep.py). Nominal settings use a 10 Hz speed-loop natural frequency, damping ratio 1, an `iq` reference limit of ±5 A, a 1000 rpm command, and a 0.05 N·m load step at 0.30 s in a 0.6 s run.

### Problems / Unexpected Results

No recorded failure accompanied this commit. The architecture still assumed exact motor constants and, at this stage, allowed voltage commands without a physical bus constraint.

### Resolution

The cascaded structure established a repeatable nominal benchmark. Parameter assumptions and voltage feasibility were made explicit in subsequent milestones.

### Validation / Results

The later nominal sensitivity [result row](../results/parameter_mismatch_metrics.csv) reports **14.315 rpm** maximum post-load speed deviation and **0.0323 s** recovery to within ±1% of 1000 rpm. The [parameter-mismatch PR](https://github.com/terogra/self-commissioning-pmsm-drive/pull/1) reports the nominal example finishing at **1000.00 rpm**. Those are later benchmark results for the cascaded implementation, not measurements recorded in the original speed-control commit.

### What We Learned

Separating slow speed regulation from fast current regulation provides a useful baseline for comparing model uncertainty and physical constraints.

### Remaining Limitations

The speed PI uses assumed torque constant, inertia, and damping. At this point there was no independent plant/controller parameter configuration or voltage saturation.

### Next Decision

Separate true plant constants from controller assumptions and quantify sensitivity before attempting parameter identification.

## Milestone 5 — Plant/controller parameter mismatch framework

### Problem / Motivation

Using one parameter object for plant and controller made it impossible to study how incorrect controller assumptions affect tracking.

### Engineering Decision

Configure plant and controller parameters independently. Hold controller assumptions fixed while changing one physical parameter at a time, and measure both startup-inclusive tracking and post-load recovery.

### Implementation

[PR #1](https://github.com/terogra/self-commissioning-pmsm-drive/pull/1), merged as commit `7482eb1`, made the [speed simulation](../src/speed_foc_simulation.py) reusable with separate parameter inputs. The [sensitivity experiment](../experiments/parameter_sensitivity.py) sweeps `Rs`, `Ld`, `Lq`, and `psi_f` at −40%, −20%, +20%, and +40% relative to nominal. It saves a [CSV](../results/parameter_mismatch_metrics.csv) and [speed](../results/parameter_mismatch_speed.png)/[metric](../results/parameter_mismatch_metrics.png) plots. [Tests](../tests/test_parameter_sensitivity.py) check architecture and metrics.

### Problems / Unexpected Results

The [results](../results/parameter_mismatch_metrics.csv) show very little effect from `Ld` changes under this `id_ref = 0` test, whereas flux-linkage mismatch changes speed recovery noticeably. Full-run speed RMSE includes the large startup transient and can obscure the load-step behavior. These are properties of the chosen operating point and metric window, not evidence that `Ld` is generally unimportant.

### Resolution

The experiment records speed and iq RMSE along with maximum post-step speed deviation and time to return within ±1% of the reference. The same nominal control case is retained for direct comparison.

### Validation / Results

Nominal full-run speed RMSE is **128.70 rpm** and load-step recovery is **0.0323 s**. With physical `psi_f` at −40%, these become **163.17 rpm** and **0.0531 s**; at +40%, they are **111.65 rpm** and **0.01786 s** in the then-unconstrained model. The full local suite passed **12 tests** at [PR #1](https://github.com/terogra/self-commissioning-pmsm-drive/pull/1).

### What We Learned

Parameter sensitivity depends on excitation, operating point, and the measurement window. An apparently favorable unconstrained high-flux result may change once the voltage limit is included.

### Remaining Limitations

The controller parameters are deliberately wrong but still supplied manually. The experiment had no inverter voltage limit and did not estimate parameters.

### Next Decision

Constrain commanded dq voltage to a feasible DC-bus envelope and prevent current PI windup during saturation.

## Milestone 6 — DC-bus voltage saturation and anti-windup

### Problem / Motivation

The mismatch framework could command voltages beyond what a finite DC bus can produce, especially when back-EMF increases with flux linkage and speed.

### Engineering Decision

Approximate an ideal linear SVPWM inverter by limiting the dq voltage vector magnitude to `Vdc/sqrt(3)`, preserving its direction. Feed the difference between requested and applied voltage back to both current PI integrators.

### Implementation

[PR #2](https://github.com/terogra/self-commissioning-pmsm-drive/pull/2), merged as `8f75c3c`, added a configurable bus, vector scaling, back-calculation anti-windup, and voltage/saturation logging in [`CurrentFOCController`](../src/foc.py) and the [speed simulation](../src/speed_foc_simulation.py). The [voltage mismatch experiment](../experiments/voltage_saturation_mismatch.py) compares nominal and ±40% physical flux at 24 V with and without the limit. [Tests](../tests/test_voltage_constraint.py) cover vector magnitude, anti-windup recovery, logging, and nominal equivalence.

### Problems / Unexpected Results

The earlier unconstrained +40% flux case looked favorable. With a 24 V bus, that case saturates for **96.48%** of the run and finishes at **936.45 rpm**; the unconstrained counterpart reaches about **1000.00 rpm**. The constrained case has no recorded recovery within the 0.6 s window.

### Resolution

Applied voltage is explicitly limited and logged; both current PI integrators use back-calculation during saturation. The experiment reports non-recovery as `NaN` rather than assigning an artificial recovery time. This addresses PI windup and makes voltage infeasibility visible; it does not create missing voltage headroom.

### Validation / Results

The [CSV](../results/voltage_saturation_mismatch.csv) and [plot](../results/voltage_saturation_mismatch.png) show the +40% flux outcome above. The 48 V nominal simulation ends at **1000.00 rpm** without saturation and matches its unconstrained trajectory. The [PR](https://github.com/terogra/self-commissioning-pmsm-drive/pull/2) records **20 passing tests**.

### What We Learned

Controller tuning and parameter sensitivity cannot be interpreted independently of actuator voltage feasibility. Anti-windup limits integrator accumulation but cannot make an infeasible operating point track.

### Remaining Limitations

The voltage circle assumes ideal linear SVPWM. Switching, bus sag, dead time, overmodulation, and inverter measurement errors are not modeled.

### Next Decision

Begin commissioning from informative standstill measurements so controller constants need not be supplied as known truth.

## Milestone 7 — Locked-rotor Rs/Ld/Lq identification

### Problem / Motivation

Plant/controller mismatch was measurable, but the controller still had no procedure to estimate the electrical constants needed for tuning and decoupling.

### Engineering Decision

Hold the rotor at zero speed and apply independent bipolar d/q voltage holds. Integrate each axis's voltage equation over sample windows to estimate `[Rs, Ld, Lq]` by scaled least squares, avoiding pointwise differentiation of noisy current.

### Implementation

[PR #3](https://github.com/terogra/self-commissioning-pmsm-drive/pull/3), merged as `e381c0b`, added the reusable [excitation, sampled measurement, estimator, and fitted-current predictor](../src/identification.py), an [experiment](../experiments/standstill_identification.py), [tests](../tests/test_identification.py), [CSV](../results/standstill_identification.csv), and [diagnostic plot](../results/standstill_identification.png). At standstill the regression comes from `vd = Rs id + Ld d(id)/dt` and `vq = Rs iq + Lq d(iq)/dt`. This PR also added [GitHub Actions pytest](../.github/workflows/pytest.yml) for Python 3.11 and 3.12.

### Problems / Unexpected Results

`psi_f` disappears from the locked-rotor electrical equations, so this experiment cannot identify flux linkage. Unexcited data are rank deficient, and a rotating record violates the estimator's standstill assumption. The [tests](../tests/test_identification.py) exercise these rejection cases; no unrecorded estimator defect is inferred.

### Resolution

The estimator checks measured speed, excitation rank, positivity, and sampling consistency. The test uses different d/q hold periods to provide current transients and sustained-current information. Flux identification was assigned to a separate rotating test.

### Validation / Results

With sampled noise, true `Rs = 0.48 Ω`, `Ld = 0.8 mH`, and `Lq = 1.25 mH` were estimated as **0.47979069 Ω**, **0.80099467 mH**, and **1.2496937 mH**, or **−0.0436%, +0.1243%, and −0.0245%** error. Tests cover three distinct plant parameter sets with a 2% tolerance and fitted-current RMSE below 0.03 A. The [PR](https://github.com/terogra/self-commissioning-pmsm-drive/pull/3) records **27 passing tests**.

### What We Learned

Designed excitation makes the electrical regression identifiable at standstill, while the equations themselves define which parameters cannot be recovered there.

### Remaining Limitations

The rotor is mechanically locked, dq alignment and applied voltage are known, parameters are linear and constant, and ordinary least squares can be biased when both current and voltage are noisy.

### Next Decision

Add a driven-rotor experiment to make the back-EMF term informative for `psi_f`.

## Milestone 8 — Rotating psi_f identification

### Problem / Motivation

The standstill stage leaves permanent-magnet flux unobservable, yet flux affects torque constant, speed PI gains, and back-EMF feedforward.

### Engineering Decision

Impose a nonzero mechanical speed with an external drive and apply a programmed dq voltage sequence. Use the previously identified `Rs/Ld/Lq`, sampled voltage/current/speed, and known pole-pair count in an integrated q-axis regression for flux linkage.

### Implementation

[PR #4](https://github.com/terogra/self-commissioning-pmsm-drive/pull/4), merged as `0311a0f`, added the [rotating data generator and estimator](../src/rotating_identification.py), a [standalone experiment](../experiments/rotating_flux_identification.py), [CSV](../results/rotating_flux_identification.csv), and [plot](../results/rotating_flux_identification.png). Starting from `vq = Rs iq + Lq d(iq)/dt + omega_e(Ld id + psi_f)`, each integration window forms `y = x psi_f` with `x = integral(omega_e dt)`. Least squares fits `psi_f`; the estimator receives sampled data, not the plant's true flux.

### Problems / Unexpected Results

At zero speed, `x` vanishes and flux is unidentifiable. The estimator rejects zero or reversing measured speed. Its result also inherits errors from the earlier `Rs/Ld/Lq` estimates and requires correct rotor alignment and pole-pair count.

### Resolution

The rotating experiment uses 600 rpm, independent voltage perturbations, configurable sampled noise, and a minimum-speed check. The [tests](../tests/test_commissioning_recovery.py) cover three flux values and rejected zero/reversing-speed data.

### Validation / Results

The standalone noisy experiment estimates **0.0149997055 Wb** against **0.015 Wb** true flux, an error of **−0.00196%**, with window-regression RMSE **1.17 × 10^-5 V·s**. The tests require estimates within 2% for flux values 0.015, 0.025, and 0.035 Wb. [PR #4](https://github.com/terogra/self-commissioning-pmsm-drive/pull/4) records **33 passing tests** for the combined milestone.

### What We Learned

Flux estimation requires an operating condition where electrical speed makes back-EMF observable; it cannot be inferred from the locked-rotor data alone.

### Remaining Limitations

The experiment assumes an ideal external speed source, known applied fundamental dq voltage, known pole pairs and angle, and constant motor parameters. It is offline simulated commissioning, not an online estimator.

### Next Decision

Combine both identification outputs and use them to update the controller assumptions and gains.

## Milestone 9 — Automatic controller retuning

### Problem / Motivation

Identified parameters were useful only for reporting until the controller could consume them without reusing the hidden plant object.

### Engineering Decision

Package standstill and rotating estimates into one commissioning result. Replace only identified electrical constants in a new controller parameter object, then construct fresh current and speed PI controllers from it.

### Implementation

The same [PR #4](https://github.com/terogra/self-commissioning-pmsm-drive/pull/4) added [`CommissioningResult` and `commission_from_measurements`](../src/commissioning.py) and a `commissioning_result` input in the [speed simulation](../src/speed_foc_simulation.py). Retuning changes `Rs`, `Ld`, `Lq`, and `psi_f`; it keeps the prior `J`, `B`, and known pole-pair count. Current gains follow `Kp,d/q = Ld/q omega_c` and `Ki,d/q = Rs omega_c`. Speed gains use `Kt = 1.5 p psi_f`, `Kp = (2 zeta omega_n J - B)/Kt`, and `Ki = omega_n^2 J/Kt`. Decoupling and back-EMF feedforward also use the updated constants.

### Problems / Unexpected Results

The implementation retunes by constructing fresh controllers, which resets PI state. No online state transfer or bumpless update was implemented. Mechanical constants are still assumed, not identified.

### Resolution

The commissioning object validates pole-pair consistency and returns a new parameter object without mutating the old one. The workflow remains an offline before/after comparison; online handover remains open work.

### Validation / Results

The [test](../tests/test_commissioning_recovery.py) checks that retuned electrical parameters and resulting current/speed PI gains are within 2% of the true-parameter reference while `J` and `B` remain the prior values. The [recovery experiment's estimate table](../results/commissioning_parameter_estimates.csv) reports errors of **−0.0377% Rs**, **+0.1155% Ld**, **+0.0303% Lq**, and **−0.00196% psi_f** for its deterministic noisy data.

### What We Learned

Identification closes the controller-parameter loop only when estimated constants actually enter both PI tuning and feedforward paths.

### Remaining Limitations

No confidence gate, mechanical identification, thermal adaptation, or online bumpless transfer is present.

### Next Decision

Compare the retuned controller directly with a mismatched controller and a true-parameter reference under voltage saturation.

## Milestone 10 — Closed-loop performance recovery

### Problem / Motivation

Accurate estimates and gain calculations do not by themselves demonstrate that speed and current tracking recover in closed loop.

### Engineering Decision

Run three controllers on the same plant and 12 V bus: true-parameter reference, deliberately mismatched, and self-commissioned. Evaluate the load-step interval separately from startup.

### Implementation

The [commissioning recovery experiment](../experiments/commissioning_recovery.py), delivered in [PR #4](https://github.com/terogra/self-commissioning-pmsm-drive/pull/4), uses a plant with `Rs = 0.56 Ω`, `Ld = 1.4 mH`, `Lq = 0.8 mH`, `psi_f = 15 mWb` and an initial controller assuming `0.24 Ω`, `0.6 mH`, `1.4 mH`, and `35 mWb`. It writes [parameter](../results/commissioning_parameter_estimates.csv) and [performance](../results/commissioning_performance.csv) tables plus [flux-fit](../results/commissioning_flux_identification.png) and [recovery](../results/commissioning_performance.png) plots.

### Problems / Unexpected Results

The full-run iq RMSE is **0.248 A** for the mismatched controller versus **0.298 A** for the commissioned controller because startup trajectories and saturation differ. Taken alone, that metric would suggest the wrong conclusion about disturbance response. All three cases experience some voltage saturation.

### Resolution

The comparison reports post-load speed and iq RMSE, maximum post-step deviation, recovery time, and saturation fraction in addition to full-run RMSE. This isolates the response of interest without hiding startup behavior.

### Validation / Results

Post-load speed RMSE changes from **10.4568 rpm mismatched** to **4.4142 rpm commissioned**, matching the **4.4143 rpm** true-parameter reference. Post-load iq RMSE changes from **0.01374 A** to **0.004612 A** (reference **0.004611 A**). Maximum post-step speed deviation falls from **29.45** to **14.31 rpm**; recovery time from **0.06578** to **0.03230 s**; saturation fraction from **11.09%** to **5.82%**. The [test](../tests/test_commissioning_recovery.py) checks recovery under a finite voltage limit.

### What We Learned

The identified constants can restore this deliberately degraded closed-loop case, but evaluation needs a metric window tied to the disturbance and must retain voltage-saturation evidence.

### Remaining Limitations

This is one selected plant, one mismatch, one noise seed, one bus voltage, and fresh-controller offline retuning. It does not establish a population success rate.

### Next Decision

Test the complete workflow across plant variation, measurement conditions, excitation speed, and available bus voltage, retaining failures explicitly.

## Milestone 11 — Monte Carlo / robustness validation

### Problem / Motivation

The single recovery example showed feasibility but not when the full workflow fails, degrades, or becomes voltage infeasible.

### Engineering Decision

Use a seeded, stratified Monte Carlo design: independently draw physical `Rs`, `Ld`, `Lq`, and `psi_f` across stated ranges; cross noise, commissioning speed, and DC-bus conditions; and retain every case, including estimator exceptions and unrecovered controllers. Compare mismatched and commissioned control on each same plant.

### Implementation

[PR #5](https://github.com/terogra/self-commissioning-pmsm-drive/pull/5), merged as `3c1361e`, added the reusable [population runner and summary](../src/monte_carlo.py), [experiment/plots](../experiments/commissioning_monte_carlo.py), [deterministic tests](../tests/test_monte_carlo.py), [73-row case table](../results/commissioning_monte_carlo_cases.csv), [aggregate JSON](../results/commissioning_monte_carlo_summary.json), and [parameter-error](../results/commissioning_monte_carlo_errors.png), [paired-control](../results/commissioning_monte_carlo_recovery.png), and [failure-region](../results/commissioning_monte_carlo_failure_regions.png) plots. The factorial part has three noise levels, four speeds (0, 150, 600, 1200 rpm), three bus voltages (12, 24, 48 V), and two draws per cell; one zero-excitation case is added. Seed: `20260929`.

### Problems / Unexpected Results

The 73 cases include **18 intentional zero-speed flux-test failures** and **one rank-deficient zero-excitation failure**. High noise yielded positive but inaccurate inductance estimates without estimator exceptions: the high-noise group had **0/24** workflow successes. At 12 V, only **2/24** cases met the workflow criterion. The diagnostic steady-state check classified **23/73** cases as voltage infeasible; **15 completed commissioned runs** did not recover within the simulation. These are recorded outcomes, not cases removed from the analysis.

### Resolution

The case table records failure stage and reason, parameter errors, before/after performance, saturation, and missing values. The summary reports medians, 95th percentiles, worst finite values, and available/missing counts; paired statistics use only cases with both controllers. The deliberately unexcited case remains in totals but is omitted from the factorial heatmaps. The study did **not** modify the estimator to make difficult cases pass.

### Validation / Results

**25/73 cases (34.2%)** meet the documented composite criterion: all four parameter errors ≤10%, post-load speed RMSE ≤10 rpm, iq RMSE ≤0.05 A, recovery ≤0.10 s, and neither RMSE more than 5% worse than the mismatched controller. **54** cases complete both control runs; **36** completed estimates meet the parameter-error criterion. Among the 54 pairs, median speed RMSE improves **8.296 → 4.418 rpm** and median iq RMSE **0.01019 → 0.003536 A**. Median absolute errors for `Rs/Ld/Lq/psi_f` are **0.068% / 2.04% / 1.42% / 0.275%**; their 95th percentiles are **1.19% / 46.2% / 41.7% / 6.55%**. The worst commissioned post-load speed RMSE is **538.71 rpm**, illustrating voltage-limited failure. Among 26 cases with nonzero speed, low/medium noise, and diagnostic steady-state voltage feasibility, **25** meet the criterion; the remaining case tracks well in absolute terms but misses the 5% relative-improvement rule. [PR #5](https://github.com/terogra/self-commissioning-pmsm-drive/pull/5) records **37 passing tests**, with GitHub Actions passing on Python 3.11 and 3.12.

### What We Learned

Success depends on identifiability, noise, and actuator feasibility together. A valid numerical estimate is not necessarily accurate, and retuning cannot overcome a bus-voltage shortage. The headline success rate must be read with its intentional boundary cases and explicit criterion.

### Remaining Limitations

This is a small seeded synthetic population with fixed mechanical parameters, ideal speed forcing during flux identification, no commissioning current limit, Gaussian uncorrelated measurement noise, and an idealized inverter. Pairwise heatmap cells contain few draws and are diagnostic rather than population-confidence estimates. Sensor bias, thermal drift, magnetic saturation, angle error, and hardware safety are untested.

### Next Decision

Before hardware commissioning or online adaptation, evaluate uncertainty and excitation quality, add feasibility and confidence gates, enforce safe current/voltage limits during tests, and validate nonideal sensors and inverter behavior. These are future decisions, not completed capabilities.

## Milestone 12 — Measured-data commissioning quality and independent validation

### Problem / Motivation

Milestone 11 produced positive but inaccurate inductance estimates under noise. Numerical success alone permitted those estimates to retune the controller. A usable commissioning result needed an explicit measurement-quality decision without consulting hidden plant truth.

### Engineering Decision

Preserve both integrated least-squares estimators and add measured-data diagnostics: scaled rank/SVD/condition, physical regressor energy, residual RMS, expected design-noise contamination, local sensor-noise covariance, chronological half-fit consistency, and rotating back-EMF strength. Require every quality check to pass before updating parameters. Use separate development and final populations, with the policy committed before final evaluation. Do not call the local covariance a calibrated confidence interval.

### Implementation

[`identification_quality.py`](../src/identification_quality.py) propagates sampled-sensor sensitivities through the actual regressions, including noisy regressors, shared integration-window endpoints, physical column scaling, and electrical-estimate covariance entering flux estimation. [`commissioning_quality.py`](../src/commissioning_quality.py) uses only estimates, diagnostics, noise metadata, and known pole count. [`commissioning.py`](../src/commissioning.py) returns explicit acceptance/rejection and blocks rejected retuning; the speed simulation preserves the original controller on rejection. The Monte Carlo runner records quality outcomes, reasons, errors, and available control metrics for every case. The [validation experiment](../experiments/commissioning_quality_validation.py) saves development and final case tables, summaries, and four diagnostic/performance plots. The [policy freeze record](quality_policy_freeze.md) documents every threshold and the protocol, committed as `b33b227` before the final run.

### Problems / Unexpected Results

Development accepted 4/13 cases; all four estimates met the post-hoc 10% criterion, but only two met the full closed-loop criterion. Two accurate estimates were rejected under weak excitation. In final evaluation, six accurate low-noise estimates at 8% standstill excitation were rejected solely for excessive expected information contamination. Conversely, four accurately estimated accepted plants could not recover at 12 V. Small local standard errors and small raw residuals alone do not rule out regression bias. Rejected final inductance errors reached 99.58% (Ld) and 99.50% (Lq).

### Resolution

Retain the candidate engineering budgets unchanged after development rather than relax them for favorable individual error realizations. Freeze before seed `20261002`; use hidden true parameters solely in physical simulation and post-hoc scoring. Report measurement quality separately from control success and voltage feasibility. Preserve all failures and rejections, with missing retuned metrics explicitly unavailable. The gate's 5% noise-information budget, 10% half-fit tolerance, three-local-SE/10% precision budget, residual allowance, and other limits are engineering screens, not calibrated probabilities. Future changes require another independent evaluation.

### Validation / Results

Development seed **20261001**: **13 cases**, **1 estimator failure**, **8 quality rejections**, **4 accepted (30.77% coverage)**. False acceptance **0/4**; false rejection **2/6 accurate complete estimates (33.33%)**; accepted closed-loop success **2/4**. Accepted median absolute errors `Rs/Ld/Lq/psi_f`: **0.0436% / 0.2281% / 0.7293% / 0.0503%**.

Independent final seed **20261002**: **73 cases**, **19 estimator failures** (18 zero-speed excitation requests, one unexcited rank failure), **33 quality rejections**, **21 accepted (28.77% coverage)**. False acceptance **0/21 accepted**, also **0/27 inaccurate complete estimates**. False rejection **6/27 accurate complete estimates (22.22%)**. Accuracy among accepted is **21/21**, compared with **27/54** complete numerical estimates before gating; this is observed finite-sample accuracy, not a guaranteed reliability probability. **17/21 accepted cases (80.95%)** meet the composite closed-loop criterion, or **17/73** across all cases.

Final accepted median / p95 / worst absolute errors are **Rs 0.0644 / 0.2004 / 0.3310%**, **Ld 1.2541 / 4.5592 / 4.6201%**, **Lq 1.0657 / 3.7185 / 5.0665%**, and **psi_f 0.0752 / 1.2176 / 1.6621%**. Rejected medians are **2.0779% / 77.8349% / 62.6344% / 8.9286%**, respectively.

Across all 21 accepted controller pairs, median post-load speed RMSE changes **7.5141 → 4.4143 rpm**, iq RMSE **0.007944 → 0.003147 A**. Among 17 finite recovery pairs, median recovery changes **0.04932 → 0.03228 s**. Four accepted cases remain unrecovered and voltage infeasible; worst commissioned speed RMSE is **469.1840 rpm**, and maximum saturation fraction is **98.6%**. The final dataset retains **22 total voltage-infeasible cases**. Full precision and denominators are in the [development summary](../results/quality_gate/development/summary.json), [final summary](../results/quality_gate/evaluation/summary.json), and [final case table](../results/quality_gate/evaluation/cases.csv). See [diagnostics](../results/quality_gate/evaluation/diagnostics_vs_error.png), [error distributions](../results/quality_gate/evaluation/accepted_rejected_errors.png), [acceptance regions](../results/quality_gate/evaluation/acceptance_regions.png), and [accepted control comparison](../results/quality_gate/evaluation/accepted_control_recovery.png).

### What We Learned

Information quality must accompany numerical solvability. First-order precision does not capture errors-in-variables bias; combined diagnostics improve observed accepted-estimate accuracy while reducing coverage. Accurate identification and adequate actuator voltage are distinct requirements. Retuning cannot recover a voltage-infeasible operating point.

The full local regression suite passes **53 tests**. Tests explicitly verify accepted retuning, rejected retuning refusal and unchanged fallback trajectories, estimate-only gate inputs, disjoint development/evaluation seeds, and finite-difference uncertainty propagation for both stages. The final case table independently records **0 rejected retuning attempts** and **21 accepted retuning attempts**. Source comparison confirms no policy or estimator changes after the pre-evaluation freeze.

### Remaining Limitations

Thresholds are explicit engineering tolerances with a small development sample, not statistically optimized universal constants. There is no calibrated confidence coverage or guarantee of zero false acceptance. Sensor noise is known, independent, and zero mean; bias, correlation, noise-model error, thermal/inverter/angle effects, and nonlinear magnetic behavior remain untested. Commissioning speed is imposed externally and current safety is not enforced. Gate acceptance does not imply voltage feasibility. The sentinel is a repeated structural negative control, not an independent random plant. Hypothetical rejected-controller retuning is not run.

### Next Decision

Add an operating-point feasibility and excitation-safety stage using available measurements/accepted estimates, then validate sensor bias and model mismatch on a fresh population. These are future work; this milestone implements measured-data acceptance and offline fallback only.

## Milestone 13 — Mechanical J/B identification and full self-commissioning

### Problem / Motivation

The electrical commissioning loop still assumed controller inertia J and friction B were known. The speed PI could therefore remain incorrectly tuned even when Rs/Ld/Lq/psi_f were accurately identified. This milestone follows the requested mechanical-identification priority; the earlier proposed voltage-feasibility stage remains future work.

### Engineering Decision

Use known-zero-external-load, freely rotating current excitation, reconstruct electromagnetic torque from measured id/iq and commissioned Ld/Lq/psi_f, and fit `integral(Te - Tload) = J delta(omega) + B integral(omega)`. Avoid pointwise differentiation of noisy speed. Keep the electrical result/API intact and compose it with a separately assessed mechanical result. Full retuning requires both gates; rejection preserves the prior controller.

### Implementation

[`mechanical_excitation.py`](../src/mechanical_excitation.py) runs two repetitions of `[0.8, 0, 0.4, -0.4, 0] A` current plateaus, 0.25 s each, through the existing FOC/voltage limit with ordinary PMSM dynamics. It samples currents and speed at 1 ms with configurable measurement noise. [`mechanical_identification.py`](../src/mechanical_identification.py) performs 50 ms integrated regression, scaled rank/SVD/conditioning, physical/conditional information, residual and half-fit checks, shared-sample sensor covariance, and a conservative electrical-uncertainty sensitivity bound. It has no plant import or hidden-torque input. [`full_commissioning.py`](../src/full_commissioning.py) composes structured electrical and mechanical results and supplies all six identified constants to the unchanged controller constructors. The [comparison](../experiments/full_commissioning_recovery.py) evaluates oracle, fully mismatched, electrical-only, and full commissioning. The [small population extension](../experiments/mechanical_population.py) reuses the existing electrical plant generator and independently randomizes J/B.

### Problems / Unexpected Results

The first comparison estimated J/B accurately but had higher current tracking RMSE after full commissioning than after electrical-only tuning; the speed response was substantially better. Early cumulative B error exceeded 10% before sufficient motion was collected. A development population case also had slightly lower speed RMSE with the mismatched mechanical tuning than with full/oracle tuning. These observations show that intended pole placement does not optimize every metric for every plant.

Review caught fixed electrical-noise seeds inherited by the first population pilot from the comparison experiment. Those artifacts were retained under `pilot_shared_electrical_noise`, excluded from the reported development/final comparison, and development was rerun with independent per-case streams. No thresholds changed. The final held-out population then accepted five accurate mechanical fits, but only one achieved the control criterion; the other four were voltage infeasible even with oracle parameters. All cases remain in the data.

### Resolution

Report speed and current metrics together, including startup/full-run quantities and zero-recovery-band semantics. Use the complete excitation record and temporal quality checks, not a favorable convergence prefix. The mechanical gate retains the electrical policy's engineering budgets and adds a three-noise-unit conditional physical-contribution check. Electrical uncertainty uses a triangle-inequality bound rather than assuming flux and inductance errors independent. Policy/protocol were frozen in commit **`30f9c7c`** before held-out evaluation; [rationale](mechanical_policy_freeze.md) explicitly disclaims calibrated confidence. No oracle/error/control label influences acceptance.

### Validation / Results

The updated-main baseline was **53 passing tests**. The completed suite has **74 passing tests**. New tests cover two additional mechanical plants, noisy data, weak J and B information, unknown load, rank failure, missing uncertainty, temporal bias changes, finite diagnostics, deterministic excitation/populations, independent numerical sensitivity verification, hidden-torque denial, accepted speed PI gains, and unchanged rejected-controller parameters/trajectories. All original electrical-only, quality, saturation, and recovery tests remain passing.

For the primary plant, true J is **5e-4 kg m²**, B **3e-4 N m s/rad**; prior J/B are **2e-4 / 1e-4**. Estimated J is **4.992267860e-4 (0.154643% absolute error)** and B **2.996960067e-4 (0.101331%)**. Both gates accept. Mechanical condition number is **1.04690**, information-noise fraction **0.000354884**, largest relative local SD bound **0.21659%**, and minimum physical component SNR **14.0876**.

| Metric | Mismatched | Electrical-only | Full | Oracle |
| --- | ---: | ---: | ---: | ---: |
| Post-load speed RMSE [rpm] | 18.46145 | 4.42862 | 1.76792 | 1.76507 |
| Maximum post-load deviation [rpm] | 41.38503 | 11.87565 | 5.73125 | 5.72361 |
| Recovery to ±10 rpm [s] | 0.08928 | 0.04340 | 0 | 0 |
| Post-load iq RMSE [A] | 0.0125682 | 0.00322238 | 0.00460608 | 0.00460877 |
| Startup overshoot [rpm] | 125.07555 | 35.79090 | 6.56738 | 6.53785 |
| Voltage saturation fraction | 0 | 0 | 0 | 0 |

The same 24 V plant/test is used for all controllers. Full commissioning improves speed RMSE about **60.1% beyond electrical-only**, while iq RMSE increases. Zero recovery means speed stays inside the band throughout the load response. The mismatched startup transient has not fully settled at load application. [Full metrics](../results/mechanical_commissioning/performance.csv), [parameter estimates](../results/mechanical_commissioning/parameters.csv), [diagnostics](../results/mechanical_commissioning/diagnostics.json), [sampled record](../results/mechanical_commissioning/measurements.csv), [identification](../results/mechanical_commissioning/mechanical_identification.png), and [comparison plot](../results/mechanical_commissioning/full_commissioning_recovery.png) preserve these details.

Corrected development seed **20261011**: **5 cases**, **3 accepted**, **1 quality rejection**, **1 rank failure**, zero observed false acceptances/rejections, **3/3 accepted control successes**. Held-out seed **20261012**: **13 cases**, **5 accepted (38.46%)**, **7 quality rejections**, **1 rank failure**. False acceptance **0/5 accepted**, also **0/5 inaccurate complete estimates**; false rejection **2/7 accurate complete estimates (28.57%)**. Accepted J median/p95/worst error is **0.1565/0.2759/0.2968%**; B is **0.5374/0.9847/0.9995%**. Rejected complete estimates reach **96.8905% J** and **31.5074% B** error.

Only **1/5 accepted final cases (20%)** meets the control criterion. Four accepted cases are voltage infeasible and unrecovered even with the oracle; median full speed RMSE is **85.1385 rpm**, worst **463.7074 rpm**. The one feasible accepted case improves speed RMSE **4.4151 → 3.2769 rpm**, oracle **3.2718 rpm**, and recovery **0.03598 → 0.02130 s**, oracle **0.02120 s**. Development also retains a case with electrical-only speed RMSE **4.3876 rpm**, full **4.9548 rpm**, and oracle **4.8824 rpm**. [Development](../results/mechanical_population/development/summary.json), [final summary](../results/mechanical_population/evaluation/summary.json), [all final cases](../results/mechanical_population/evaluation/cases.csv), and [population plot](../results/mechanical_population/evaluation/population.png) include failures and missing metrics explicitly.

### What We Learned

Sampled current/speed data and a trustworthy electrical model can close the remaining J/B tuning gap under a known load condition. Motion must separate acceleration torque from friction torque; column normalization is not physical excitation. Torque reconstruction error propagates into both mechanical estimates. Accurate mechanics restore the designed speed loop but do not guarantee every metric improves or create voltage headroom.

### Remaining Limitations

Known zero external load is essential to the experiment; unknown load can be confounded with B. Coulomb/static friction, stiction, sensor bias/correlation, angle and inverter errors, temperature dependence, and changing attached loads are not modeled. J is effective assembly inertia, not necessarily bare-rotor inertia. Very small B and weak speed signals may be unresolvable. First-order sensitivity bounds are not confidence intervals or systematic-bias bounds. The small stratified population is exploratory, with only one feasible accepted held-out control case. Current references and voltage limiting in an ideal simulation are not physical safety guarantees; no hardware procedure is provided.

### Next Decision

Add a measured/estimated operating-feasibility assessment and excitation-safety design, then evaluate unknown-load/model bias and sensor nonidealities on a fresh independent population. Do not retune the frozen mechanical gate to the current held-out labels. These are future tasks, not completed parts of this milestone.
