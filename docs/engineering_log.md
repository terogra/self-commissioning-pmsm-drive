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

## Milestone 14 — Operating-point feasibility assessment

### Problem / Motivation

PR #8 accepted accurate electrical and mechanical estimates for five held-out plants, yet four requested operating points failed even with oracle tuning. Identification quality did not establish whether the bus/current envelope could sustain the requested speed and load. These decisions needed separate representations.

### Engineering Decision

Assess the existing id=0 control strategy analytically from accepted commissioned parameters. Use `Te_required=Tload+B_hat*omega`, `iq_required=Te_required/(1.5*p*psi_f_hat)`, `vd=-omega_e*Lq_hat*iq`, and `vq=Rs_hat*iq+omega_e*psi_f_hat`. Compare current magnitude with a configured design limit and voltage magnitude with the unchanged `Vdc/sqrt(3)` convention. Include equality with zero reserve; report margins and utilization. J is excluded because it affects acceleration, not steady-state mechanical balance. Keep both identification gates unchanged and evaluate finite-run tracking independently.

### Implementation

[`operating_feasibility.py`](../src/operating_feasibility.py) adds an immutable request/result API, explicit invalid-request/unavailable-commissioning errors, separate current/voltage decisions, named operating-limit reasons, and a deterministic envelope grid. The normal API reads only accepted Rs/Lq/psi_f/B and known pole count. It does not require a plant object or prior defaults. The speed simulation gains a configurable `current_limit_a`, defaulting to the previous 5 A iq-reference limit; existing default trajectories are unchanged. The [experiment](../experiments/operating_feasibility.py) compares predictions against actual signals, generates an envelope, replays accepted PR #8 measurement stages, and evaluates three fresh plants over seven predefined scenarios each. The [protocol](operating_feasibility_protocol.md) and source were committed in **`e55b851` before the new held-out run**; no thresholds were fitted to outcomes.

### Problems / Unexpected Results

Analytical steady feasibility did not imply success within 0.6 s: the representative low-current case reached only **335.499 rpm** for a feasible 1000 rpm request. Three held-out points were also false feasible under the finite-run criterion despite zero voltage saturation. Conversely, three slightly voltage-infeasible held-out points met the allowed ±1% speed tolerance while remaining saturated. Exact operating-point feasibility and tolerance-based tracking success therefore disagree near boundaries. Overloaded simulated trajectories can reverse under the existing constant-sign load torque, and measured current can exceed its reference limit under voltage saturation; neither behavior was filtered out.

### Resolution

Keep `steady_state_feasible` separate from `closed_loop_dynamic_success` and preserve all disagreements. Assess dynamic success from final-window speed/current samples, never from the prediction. Rerun every false-feasible case for a predeclared 4 s with the same controller/request, without replacing its original outcome. The representative then succeeds; the three held-out acceleration cases still fail at 4 s. Retain current/voltage utilization and measured applied-voltage behavior. Reject unsupported negative requests explicitly. Document reference limiting as a simulation constraint rather than physical protection. No field weakening, MTPA, quality-gate adjustment, or automatic supervisor was added.

### Validation / Results

The latest-main baseline passed **74 tests**. The completed full suite passed **99 tests**. New coverage includes low-speed feasibility, voltage/current/both limits, zero speed/load, invalid values, monotonic limits, J independence, estimate-only API inputs, unchanged identification acceptance, default trajectory preservation, configurable iq limits, deterministic envelopes, a dynamic counterexample, and historical accepted-case replay. `git diff --check` passes; original electrical/mechanical estimator and gate sources remain unchanged.

Representative feasible request: **250 rpm, 0.02 N m, 24 V, 3 A**. Required current **0.309380 A**, voltage **1.744314 V**, current margin **+2.690620 A**, voltage margin **+12.112092 V**; achieved terminal mean speed **249.999936 rpm**. Representative voltage-infeasible request: **2000 rpm, 0.05 N m, 12 V, 5 A**. Required voltage **13.295272 V** versus **6.928203 V** available, margin **-6.367069 V**; achieved speed **1009.386 rpm**, full-run saturation **87.16%**, terminal saturation **100%**. [All representative rows](../results/operating_feasibility/representative.csv) retain near-boundary, current-limited, both-limited, and slow-acceleration cases; [dynamics plot](../results/operating_feasibility/representative_dynamics.png).

PR #8 re-analysis retains **13 rows**, evaluates the **five accepted** commissioning results, and marks the other eight unavailable. Because the old CSV omitted electrical estimates, original measurement stages are replayed and J/B fits checked against saved values; hidden electrical columns never supply the normal API. Case **3** is predicted feasible; cases **0, 1, 5, 7** are voltage infeasible with margins **-4.993497, -0.160714, -5.844623, -1.269319 V**, respectively. Predictions agree **5/5** with oracle steady predictions and **5/5** with historical commissioned/oracle control outcomes. All five identification decisions stay accepted. [Re-analysis table](../results/operating_feasibility/pr8_reanalysis.csv).

Fresh held-out seed **20261021**: **21 points on three independently drawn/commissioned plants**, all retained. Under the final-0.1-s speed tolerance `max(1 rpm, 1% command)` and measured-current tolerance `1.01 Imax`, results are **6 true positives, 9 true negatives, 3 false feasible, 3 false infeasible**. Oracle steady predictions agree **21/21**. The false-feasible acceleration cases reach **258.761 / 126.329 / 240.578 rpm** at 0.6 s with current essentially clamped at its reference limit and zero voltage saturation. Their 4 s reruns reach **906.821 / 585.513 / 883.061 rpm**, still below tolerance. A post-hoc ideal id=0 no-friction/no-load acceleration bound using identified J predicts only **357.3 / 165.6 / 324.5 rpm** attainable in 0.6 s, supporting the transient-demand explanation without putting J into the steady classifier.

The three false-infeasible points have voltage margins **-0.03625 / -0.04079 / -0.05640 V** and terminal speeds **992.613 / 991.860 / 993.981 rpm**, all within ±10 rpm of the 1000 rpm target while saturated throughout the terminal window. They satisfy the finite tolerance without reaching the exact requested point. [Held-out table](../results/operating_feasibility/held_out.csv), [plant/estimate audit](../results/operating_feasibility/held_out_plants.json), and [summary](../results/operating_feasibility/summary.json) preserve all counts and investigation runs.

The **24 V, 2 A** commissioned envelope contains **3,111 grid nodes**: **643 feasible, 1,291 current limited, 198 voltage limited, 979 both limited** over 0–3000 rpm and 0–0.50 N m. [Envelope plot](../results/operating_feasibility/envelope.png) and [complete grid](../results/operating_feasibility/envelope.csv). This is an id=0 steady-state map, not a validated dynamic/hardware operating region.

### What We Learned

Trustworthy motor estimates and a feasible requested point are distinct prerequisites. A physically meaningful margin explains previous voltage failures without relabeling good identification as bad. Current headroom sufficient for steady torque may be insufficient for startup on a finite timescale. Classification agreement depends on whether success means the exact target or a tolerance band; both definitions and all disagreements must remain visible.

### Remaining Limitations

Point estimates, constant known load and viscous friction, ideal linear SVPWM, fixed bus, and forward id=0 motoring only. No uncertainty reserve, field weakening, MTPA, bus-sag/thermal limits, regenerative/reverse analysis, or hardware-safety certification. Reference current limiting is not instantaneous physical current protection. The constant-sign external load can reverse failed trajectories. The 21 scenarios share only three motors, so the observed **15/21 dynamic agreement** is a finite-dataset outcome, not universal classification accuracy. Historical PR #8 outcomes use their original simulation-metric criterion and are not pooled with the new terminal-window criterion.

### Next Decision

Evaluate transient acceleration/reserve requirements and uncertainty-aware operating margins with a fresh validation design. A later supervisor could use identification quality and operating feasibility as separate inputs; adaptive excitation and field weakening remain future work. No such supervisor or hardware procedure is part of this milestone.

## Milestone 15 — Bounded adaptive commissioning supervisor

### Problem / Motivation

The electrical and mechanical identification stages were previously run as fixed one-shot tests. Earlier validation retained weak-excitation cases with accurate or nearly accurate estimates rejected because their measured information was insufficient. PR #9 separately showed that accurate, accepted identification can coexist with voltage-infeasible requests and that steady feasibility need not imply rapid acceleration. A process controller was needed to distinguish a repairable weak test from a model/data failure and from an infeasible operating request.

### Engineering Decision

Use a stage-ordered supervisor around the existing estimators and **unchanged** quality policies. Retry only for specific named measured-data reasons or an explicitly zero test input, with configured upper bounds and a finite attempt budget. Measurement providers generate sampled data at the simulation boundary; the supervisor receives no plant truth, hidden torque, parameter error, oracle result, or closed-loop success label. Assess operating feasibility only after full quality acceptance. Use the same initial noisy records for paired one-shot/adaptive comparisons and a separate held-out seed after freezing the retry policy.

### Implementation

[`adaptive_commissioning.py`](../src/adaptive_commissioning.py) adds `RetryPolicy`, stage and terminal-state enums, immutable structured attempt/result records, and `run_adaptive_commissioning`. Standstill quality is selected from the existing electrical gate's standstill checks; full electrical quality is checked again after flux identification. Mechanical identification uses the existing full commissioning composition. Full controller parameters change only after both gates accept. Attempts retain configs, estimated values if available, quality checks, diagnostic snapshots, reasons, retry actions, and the next config. Terminal outcomes distinguish non-retryable rejection, attempt-budget exhaustion, full acceptance, and operating-feasible/infeasible acceptance.

Standstill retries adjust voltage, record duration, or switching geometry according to the failed check. A known zero-input failure receives a small nonzero bipolar program. Weak rotating back-EMF/speed information requests higher imposed speed, then longer duration. Mechanical component SNR and relative local sensitivity select longer speed/coast plateaus for weak B information or stronger acceleration plateaus for weak J information. Excessive residual and unsupported measurement/estimator failures stop. Policy limits are four attempts per stage, 3 V standstill vector and 0.8 s duration, 1200 rpm rotating speed and 0.6 s duration, 1 A mechanical reference/plateau magnitude and 0.5 s plateau duration. The [freeze protocol](adaptive_commissioning_protocol.md) describes the reason map, design limits, and scoring before held-out seed **20261101** was run. The policy and development results were committed in **`467a11a`**, followed by a pre-evaluation bound-validation fix in **`b26f2a2`**. No retry rule or gate threshold changed after held-out evaluation.

The [paired experiment](../experiments/adaptive_commissioning.py) draws nine plants for each population and covers normal, weak electrical/flux/mechanical, combined weak, medium/high noise, zero input, and voltage-infeasible cells. It caches the initial sampled records so one-shot and adaptive paths see the same initial noise realization. True parameters are stored in separate post-hoc audit files. Case CSV, attempt JSON, retry reason distribution, example trace, attempt count plot, and parameter-error comparison are retained for both populations.

### Problems / Unexpected Results

In development, zero commanded standstill voltage with noisy current produced a **nonpositive estimator result**, rather than a clean rank-deficiency diagnostic. The configured zero input and failure together justified one bounded input retry; the revised attempt passed. A high-noise standstill case violated the existing near-zero **measured** speed check and remained a terminal rejection, since more electrical voltage would not repair that measurement problem. A dedicated weak-flux cell passed on its first development draw but needed a rotating-speed retry on the independent held-out draw; the combined-weak cell exercised that retry in both populations.

The held-out medium-noise mechanical case still failed `mechanical.insufficient_excitation` after duration and current reached their design caps. Its final J/B estimates were accurate post-hoc (**0.7924% / 0.0034%** absolute error), illustrating a conservative measured-data rejection. The accepted 12 V operating case was voltage-infeasible despite accepted estimates. No estimator retry was triggered by its feasibility result. The new plot review also exposed clipped long reason labels; plot layout was adjusted without changing policy or evaluation outcomes.

### Resolution

Map the zero-input/nonpositive-result pair to a small explicitly bounded standstill excitation; retain other nonpositive/invalid failures as terminal. Preserve every failed attempt and the held-out accurate rejection. Stop mechanical strengthening at the predeclared cap rather than relaxing the gate or adding an unplanned experiment. Keep operating infeasibility as a distinct accepted-identification terminal state. No dynamic control outcome is used by the supervisor; the evaluation executes control only after its commissioning and feasibility decisions.

### Validation / Results

The updated-main baseline passed **99 tests**. The completed full suite passed **115 tests** locally. Focused supervisor tests cover nominal acceptance, standstill/flux/mechanical recovery, weak J/B action selection, unchanged quality thresholds, zero input, bounded attempt count, explicit budget exhaustion, residual termination, design-limit validation, unchanged rejected controller assumptions, accepted retuning, operating infeasibility without retry, a steady-feasible but slow dynamic case, deterministic histories, one-shot API compatibility, and separation of truth labels.

Development seed **20261031**, nine cases: one-shot accepted **4/9**, adaptive **8/9**, recovering **4** one-shot rejections. Adaptive electrical/mechanical acceptance was **8/9** each. One-shot false acceptance **0/4**, false rejection **1/5** complete accurate estimates; adaptive false acceptance **0/8**, false rejection **0/8**. Four one-shot and one adaptive cases lacked all six estimates and remained explicitly unscorable for the conditional false-rejection denominator. One accepted case per method was operating-infeasible. All **3/3** one-shot and **7/7** adaptive accepted feasible cases subjected to the predeclared control test succeeded. No attempt-budget exhaustion; one adaptive terminal rejection from invalid noisy locked-rotor speed.

Independent held-out seed **20261101**, nine new plants: one-shot accepted **3/9**, adaptive **7/9**, again recovering **4**. Adaptive electrical acceptance **8/9**, mechanical/full acceptance **7/9**. One-shot false acceptance **0/3**, false rejection **2/5** complete accurate estimates; adaptive false acceptance **0/7**, false rejection **1/8**. Four one-shot and one adaptive rows lacked six estimates; all nine remain in the aggregate denominator. The accepted voltage-infeasible case has estimated voltage margin **−12.7698 V** at 2000 rpm. Accepted feasible control successes were **2/2** one-shot and **6/6** adaptive. Adaptive retries per accepted case were **[0, 0, 1, 3, 5, 1, 0]**. There were **0 attempt-budget-exhausted** cases and **2 terminal rejections**: the high-noise standstill speed failure and the medium-noise mechanical design-limit case. The latter is the one adaptive false rejection.

Held-out adaptive median absolute Rs/Ld/Lq/psi_f/J/B errors among available estimates were **0.0583% / 0.1478% / 0.3364% / 0.0571% / 0.1327% / 0.1636%**. All seven accepted cases met the post-hoc 10%-per-parameter accuracy label. On the different accepted-feasible subsets, one-shot median post-load speed/iq RMSE was **2.1822 rpm / 0.00303 A** (`n=2`), versus adaptive **1.7468 rpm / 0.00359 A** (`n=6`); these are not paired performance-improvement estimates. The finite rates are neither probabilistic coverage nor a guarantee on other plants. [Development summary](../results/adaptive_commissioning/development/summary.json), [held-out summary](../results/adaptive_commissioning/evaluation/summary.json), [held-out attempt history](../results/adaptive_commissioning/evaluation/attempts.json), [combined-weak trace](../results/adaptive_commissioning/evaluation/example_trace.json), [attempt plot](../results/adaptive_commissioning/evaluation/attempts_to_acceptance.png), and [error plot](../results/adaptive_commissioning/evaluation/parameter_error_by_decision.png) preserve the detailed evidence.

### What We Learned

Retrying an experiment can improve measured information without changing the estimator or gate. Stage-specific diagnostics matter: weak flux information and weak J/B information call for different data. A correct rejection can persist at the design limit even when the hidden error happens to be small; that is a limitation of available evidence, not a reason to override the gate. Operating feasibility remains a separate question after trustworthy identification.

### Remaining Limitations

The nine-case held-out set is deliberately small and stratified; zero observed false acceptances is not a general reliability claim. Noise is modeled as configured zero-mean samples. Sensor bias, correlated noise, thermal drift, unmodeled friction/load, and inverter nonidealities can produce confident-looking bias. Unknown external mechanical load remains problematic. Accepted commissioning does not guarantee operating feasibility, and steady-state feasibility does not guarantee finite-time dynamic success. A retry may receive a more favorable noise realization, so one case's improvement is not proof of physical information gain. Simulated voltage/current/speed/duration bounds are not hardware-safety prescriptions. No field weakening, online adaptation during normal running, hardware procedure, or physical protection design is included.

### Next Decision

Study transient operating reserve and uncertainty-aware feasibility using an independent design, and evaluate sensor bias/model mismatch before claiming broader autonomous robustness. Hardware commissioning and online operation-stage adaptation remain separate future work.

## Milestone 16 — Dynamic operating feasibility

### Problem / Motivation

M14 found accepted, steady-feasible motors that could not accelerate to the command within a finite run. Its three held-out acceleration cases remained below tolerance even at 4 s. Slightly outside voltage boundaries, other cases held within ±10 rpm despite exact-target infeasibility. The engineering question was whether identified parameters and configured limits could explain finite-time capability without using hidden truth or changing commissioning acceptance.

### Engineering Decision

Keep three independent concepts: identification quality, steady operating feasibility, and dynamic capability. Add two dynamic predictions: an interpretable quasi-steady id=0 torque model and the existing cascaded controller simulated on a model built entirely from accepted estimates. Require a complete contiguous sampled hold before the deadline, while retaining first entry and final-band state separately. Report exact-target and lower-band steady feasibility independently. Use a development population, commit the fixed method, then run a different deterministic held-out seed; no gate or empirical decision threshold is fitted.

### Implementation

[`src/dynamic_feasibility.py`](../src/dynamic_feasibility.py) introduces immutable request/config, quasi-steady trajectory, controller-prediction and combined result records. For `omega_e=p*omega_m`, the quasi-steady voltage inequality is `a*iq²+b*iq+c<=0`, with `a=(omega_e*Lq)²+Rs²`, `b=2*Rs*omega_e*psi_f`, and `c=(omega_e*psi_f)²-(Vdc/sqrt(3))²`. The physically valid nonnegative root is rationalized as `2*(-c)/(b+sqrt(b²-4*a*c))`; a negative voltage reserve makes even zero motoring current infeasible. Apply `iq_available=min(Imax,iq_v)`, `Te=1.5*p*psi_f*iq_available`, and `alpha=(Te-Tload-B*omega_m)/J`. Nonpositive acceleration prevents lower-band entry in the quasi-steady model; otherwise integrate `domega/alpha` on a refined grid. Identified J now explicitly controls acceleration time.

The controller-aware path builds all six motor parameters and known p from accepted full commissioning. It uses the existing FOC, speed PI, voltage circle, anti-windup and current-reference limit. The only old simulator change adds a default-zero initial speed, finite validation and logging. Load starts at t=0, currents and integrators start at zero. The normal API receives no hidden plant, truth-error label, oracle or actual control outcome. Estimator, quality-policy and adaptive-supervisor source files remain unchanged.

[`experiments/dynamic_operating_feasibility.py`](../experiments/dynamic_operating_feasibility.py) reuses M14 commissioning and then predicts before executing an independent hidden-plant simulation. It retains easy, short/long deadline, stronger-current, high-speed voltage, exact/band boundary, unreachable and moving-start requests. CSV rows keep all evaluated, unavailable or failed cases. Plant truth is stored in separate audit JSON. Plots compare predicted/actual responses and map quasi-steady entry estimates against target speed and current limit; traces and map grid are also saved. [`docs/dynamic_feasibility_protocol.md`](dynamic_feasibility_protocol.md) fixes numerical settings and outcome definitions.

### Problems / Unexpected Results

The quasi-steady envelope omits `Lq*diq/dt` and assumes instantaneous available torque. Three held-out hidden-plant responses entered before the quasi-steady estimate; in two of those cases the same-model controller also entered earlier. Inspection of the original saved records during the semantics follow-up found three same-model early entries in total, including motor 3's high-speed case (151.25 µs earlier, comparable to the 0.1% integration-refinement tolerance). Thus the integrated time cannot be advertised as a certified lower bound for arbitrary full-dq transients. Point-estimate error also shifts timing: the representative slow case's prediction was 16.24 ms early, larger than the held-out maximum. None of these observations was tuned away.

Known constant resisting load with zero initial dq current caused small reverse excursions before current built up: 21/24 development, 35/40 held-out, and 7/8 representative traces. The worst held-out minimum was −0.01885 rpm. This is a scope caveat of the unconstrained simulated plant, not support for reverse or regenerative commissioning. The representative slightly outside exact voltage boundary was band-steady-feasible but had not completed a hold at 0.6 s (983.75 rpm final); four of five analogous held-out requests succeeded and one reached only 988.61 rpm.

### Resolution

PR #11 review found that the original timing/deadline API names still implied a physical bound despite the documented negative result. Correct the names after that held-out finding to explicitly represent a quasi-steady model estimate, preserve controller-aware prediction as a separate output, and report every earlier-than-envelope entry. Add minimum speed and explicit `dynamic.reverse_speed_excursion` reasons without replacing the specified band-hold criterion. Do not clamp the plant speed or rewrite historical simulations. The quasi-steady deadline comparison includes estimated entry plus hold; False cannot physically rule out a full dq transition; integration nonconvergence is indeterminate rather than a confident classification. Retain measured-current peaks because current-reference limiting is not instantaneous physical current protection. Interpret historical post-step logs at `(k+1)*dt` only for this new criterion.

The semantics follow-up renamed `DynamicFeasibilityResult.physical` to `quasi_steady`, `PhysicalCapability` to `QuasiSteadyCapability` and `assess_physical_capability` to `assess_quasi_steady_capability`. Timing, deadline, reachability and acceleration fields and model-specific reasons were renamed across source, saved CSV/JSON, plots and documentation. The full dq transient simulation can enter the band earlier; this estimate is not a physical minimum or universal lower bound. Original numbers and evidence were preserved, plots were rendered from saved data, and no replacement population or altered success criterion was used. New regression tests retain the three hidden-plant early entries, the two overlapping same-model cases and the third same-model early entry and exercise a same-model deadline counterexample.

### Validation / Results

Current-main baseline **363b70d** passed **115 tests**. The completed full suite passed **147 tests in 153.64 s**, including 32 new tests for request/config validation, rejected/missing estimates, explicit estimate-only model construction, J dependence, current/voltage monotonicity, analytic constant-acceleration integration, root domain/coincidence, convergence diagnostics, brief crossings, finite/reference checks, short/long deadline behavior, exact-vs-band distinction, unchanged adaptive histories/quality, deterministic request recipes and historical default samples. `git diff --check` passes. Both generated plots were visually inspected.

The PR #11 semantics follow-up passed the full suite with **151 tests in 177.86 s**. Four added test instances preserve the saved counterexamples, replay the two overlapping same-model cases and test deadlines between their original completion estimates, and enforce explicit model-scoped API/documentation terminology. All numerical/Boolean/null JSON leaves and all CSV cells in the 12 saved data artifacts were compared with **c7bcc3e** and remain unchanged modulo schema/reason renames. Production AST comparison confirms unchanged calculations and decision rules after normalizing renamed identifiers/reasons and removing docstrings. Plots were relabeled from original saved data and inspected; no replacement held-out population was run.

The development method and protocol were frozen in **717ef32** before independent evaluation. Development seed **20261002**, three motors/eight requests each: **24/24 agreement**, **11 successes**, no false predicted success/failure and no unavailable cases. Quasi-steady completion estimates met **12** deadlines. Median signed qualified-entry error **−40 µs**, maximum absolute error **280 µs** on the 11 jointly qualified holds. Limits: **15 current**, **9 current+voltage**. No actual first entry preceded its quasi-steady estimate.

Held-out seed **20261003**, five new motors/eight requests each: **40/40 agreement**, **19 successes / 21 failures**, zero false predicted successes/failures, zero unavailable/error cases. Quasi-steady completion estimates met **20** deadlines; no quasi-steady deadline miss coincided with actual success in the original evaluation. On 19 jointly qualified holds, median signed entry error **−0.00020 s**, maximum absolute error **0.00492 s**. Factors: **25 current-only / 15 current+voltage**. Earlier-than-envelope hidden entries were motor 3's longer deadline (**4.307 ms**) and motor 4's high-speed/boundary cases (**1.251 / 4.301 ms**); the latter two also violate a universal-envelope-bound interpretation on the commissioned model itself. These remain in [held-out.csv](../results/dynamic_operating_feasibility/held_out.csv).

The eight representative requests agree **8/8**, with **4 successes** versus **5** quasi-steady completion estimates within deadline. Easy 250 rpm entry estimate **0.0525735 s**, actual qualified entry **0.09356 s**. Slow 1000 rpm entry estimate **3.634268 s**: at 0.6 s it fails and reaches **336.734 rpm**; unchanged request at 4 s succeeds with predicted/actual qualified entries **3.63484 / 3.65108 s**. Raising current shortens the estimate to **0.890312 s**, still too slow for 0.6 s (**721.585 rpm** final). Voltage-limited 2000 rpm succeeds with predicted/actual entries **0.45824 / 0.45864 s** and **61.45%** saturation. The unreachable 2000 rpm / 12 V case ends at **1008.792 rpm**. The moving-start case succeeds at **0.28020 s** actual qualified entry. [Representative table](../results/dynamic_operating_feasibility/representative.csv), [response plot](../results/dynamic_operating_feasibility/representative_dynamics.png), [capability map](../results/dynamic_operating_feasibility/transition_time_map.png) and [summary](../results/dynamic_operating_feasibility/summary.json) retain all eight outcomes.

Replayed M14 held-out acceleration cases have quasi-steady entry estimates **5.181076 / 11.401662 / 5.554084 s**. All fail both 0.6 s and 4 s, with **6/6** controller/outcome agreement. Their 4 s final speeds are **901.680 / 579.202 / 879.377 rpm**. This replay uses M16's constant t=0 load and sampled hold, whereas M14 used a 0.3 s load step and terminal-window measured-current criterion. Saved old outcomes are retained separately; the two sets are not pooled. [Retrospective table](../results/dynamic_operating_feasibility/m14_retrospective.csv).

### What We Learned

Accepted estimates describe a model; steady feasibility describes a point; finite-time capability also requires J, torque reserve, current buildup and controller behavior. A point inside the steady envelope can be unusable at a short deadline. A slightly unattainable exact target can still satisfy an explicit band, while band feasibility alone does not guarantee a finite hold. The torque envelope is useful for interpretation, but full dq dynamics prevent treating its time as a universal physical certificate.

### Remaining Limitations

Simulation/design analysis with identified point estimates, known constant load, viscous friction, ideal constant bus and linear SVPWM. No field weakening, MTPA, uncertainty reserve, inverter switching, sensor/inverter nonidealities, or hardware guarantee. Controller id transients and measured-current overshoot are retained. Unsupported negative/decelerating requests fail; brief reverse responses expose the plant's startup assumption. Qualified sampled hold is not permanent settling. The 40 requests share only five motors; zero observed binary disagreements is not calibrated reliability. Commissioning acceptance remains independent of every dynamic outcome.

### Next Decision

Milestone 17 should study realistic nonidealities, sensor/model bias and timing effects before broader claims about commissioning and operating predictions. It is not implemented in this PR. A later orchestration layer can combine the three separate decisions without conflating them.

## Milestone 17 — Realistic drive nonidealities and robustness characterization

### Problem / Motivation

The complete commissioning path had been validated primarily with ideal signal
chains plus zero-mean Gaussian record noise. M16's successful ideal-model dynamic
predictions did not establish robustness to sensor calibration, coordinate-frame
misalignment, delayed records, unknown terminal voltage or a stale resistance.
These effects can violate an estimator's model while leaving its numerical fit
apparently precise. Characterization was needed before changing the algorithms.

### Engineering Decision

Start from merged M16 main **047d6511b86c34ce571005f8377387eb3674602b**.
Keep estimators, gates, adaptive retry
policy/actions, FOC tuning and M16 calculations unchanged. Put deterministic
nonidealities at the simulation measurement/actuation boundary. Pair one-shot
and adaptive methods, separate commissioning-only/operation-only/combined
exposure, and use truth only for post-decision evaluation. Commit the method,
levels, metrics, protocol and development results before a separate held-out seed.
Freeze SHA: **4723230167786d8760c8dc801ec32c05b11d330b**.

### Implementation

[`drive_nonidealities.py`](../src/drive_nonidealities.py) adds immutable nested
current, voltage, frame, timing, actuation and operating-drift configurations.
Current sensing passes through existing inverse Park/Clarke transforms into abc,
per-phase gain/offset/nearest-quantum rounding, and measured-angle Clarke/Park.
Fixed electrical-angle bias rotates both measurement and commanded-voltage frames
consistently. One-step feedback delays include measured angle; one-sample record
alignment delays current relative to unchanged voltage, speed and timestamps.

The averaged phase error is `-drop*sign(i_phase)` with sign(0)=0; Clarke removes
zero sequence. Actual terminal dq voltage is clipped at the sagged bus circle,
while FOC retains its nominal bus and unchanged anti-windup. Estimator voltage
is command reconstruction in this matrix, with gain/offset/quantization; optional
explicit terminal sensing is a separate setting. Post-commissioning Rs drift
clones only the operating plant, preserving commissioned/controller objects.
Gaussian record noise is added after this chain; systematic errors are not
declared as Gaussian `MeasurementNoise` to the existing diagnostics.

Hooks extend four simulation providers; estimator bodies are preserved.
The [experiment](../experiments/nonideality_robustness.py) draws two development
and three held-out motors from existing M15 ranges, covers 16 fixed cells and
retains both methods/all three exposures. Mechanical-record caches include the
identified electrical controller as well as excitation config. Speed logs
distinguish command, true-frame command, terminal and reconstructed voltage,
true/measured/feedback current, rotated true-frame references and actual bus
clipping. [Protocol](nonideality_robustness_protocol.md) records placements,
applicability, units, levels, seeds, unchanged success conventions and freeze.

### Problems / Unexpected Results

**Structured bias passes the unchanged gates.** Every strong current, voltage
and inverter cell is accepted but exceeds the existing post-hoc six-parameter
<=10% accuracy convention. Held-out current gain yields Rs/Ld/Lq errors
**12.61–13.46%**, J **14.44–14.70%**, B **15.21–15.61%**, with flux error <.02%.
Voltage reconstruction scales all six estimates into **11.25–12.23%** error.
Inverter error mainly biases Rs **15.76–16.12%**, with other estimates <.74%.
Rank/residual/noise-sensitivity checks do not necessarily expose a coherent
calibration error absorbed into the fitted model.

Timing and both combined commissioning cases are rejected for
`standstill.excessive_residual`, even when partial standstill estimates have
modest percentage errors. Adaptive terminal action `model_residual_terminal`
prevents later stages; no retry is triggered. One-shot's existing electrical
path can still fit/assess flux after a valid but quality-rejected standstill fit;
held-out rotating-only acceptance is **47/48 one-shot versus 39/48 adaptive**.
Neither path commissions mechanical parameters from rejected electrical data.

Good speed control conceals some inaccurate parameters. All accepted
commissioning-only cases pass the operating test; strong voltage/inverter bias
also passes combined control. Strong current bias instead violates the .05 A
physical iq tracking criterion despite speed RMSE remaining small. Angle error
creates persistent physical id, rather than merely zero-mean ripple. M16's
nominal 4% voltage-headroom recipe becomes optimistic after 5/10% actual bus sag.

### Resolution

Preserve these findings rather than tuning gates, severities, excitation or
controllers. Retain all partial estimates, error labels, rejection reasons and
attempt histories. Mark rejected control unavailable; never substitute zeros or
count it as a successful simulation. Compare actual currents/references in the
same true frame and separately report controller-frame error. Keep true torque
and post-hoc accuracy labels outside every normal decision interface.

Add regression tests demonstrating accepted uniform-current-gain bias and safe
terminal rejection. The latter explicitly verifies the supervisor leaves prior
controller parameters unchanged. A baseline AST contract verifies 12 protected
modules, excluding only the two edited electrical simulation providers; empty
Python 3.12 type-parameter AST fields are normalized for Python 3.11/3.12 CI.
Final development output was rerun with the same method/seed after adding
failure/attempt-estimate fields and consistent plot colors, reproducing all
numbers. No model/metric/scenario/test change followed held-out execution.

### Validation / Results

Baseline **151 tests in 153.73 s**. M17 adds **29** tests for immutable/invalid
configs, phase transforms and physical units/signs, coherent frame rotation,
voltage source separation, inverter error/actual bus clipping, exact delay
alignment, deterministic records, zero-error equivalence across all providers,
isolated operating drift, unchanged stochastic metadata, unchanged algorithm
contract, decision API boundaries and intended negative results. Full suite
passed **180 tests in 143.08 s** before freeze. Final full-suite verification
passed **180 tests in 130.47 s** after held-out artifacts/documentation; no tests
were skipped or xfailed. `git diff --check` also passed.

Development seed **20261004**, two motors, **192 rows**: each method accepts
**26/32 (81.25%)**, with **20 accepted accurate**, **6 silent inaccurate** and
**6 rejected/unavailable** full fits; no accurate full rejection or numerical
estimator failure. Held-out seed **20261005**, three new motors, **288 rows**:
each method accepts **39/48 (81.25%)**, with **30 accepted accurate**, **9 silent
inaccurate**, **9 rejected/unavailable**, no accurate full rejection and no
numerical estimator failure. Silent cases are **23.08% of accepted commissioning**
in both populations. Both methods have identical full acceptance/operating
outcomes. Adaptive performs **zero retries**, **zero recoveries**, **6/9 residual
terminal rejections** and no budget/design-bound terminations. This is not
evidence of retry recovery, or retry making structured bias worse.

Control success/evaluated counts per method, development -> held-out:

| Exposure | Development | Held-out | Held-out unavailable |
| --- | ---: | ---: | ---: |
| Commissioning-only | 26/26 | 39/39 | 9 |
| Operation-only | 28/32 | 42/48 | 0 |
| Combined | 24/26 | 36/39 | 9 |

Held-out post-load speed RMSE median/worst: commissioning-only **1.44142 /
2.73349 rpm**, operation-only **1.44171 / 3.17383 rpm**, combined **1.44166 /
2.74765 rpm**. Current-strong combined iq RMSE **.06977–.11524 A** fails all
three motors. Combined mild/strong commissioning is unavailable on all three;
after clean commissioning, operation-only mild passes **3/3**, strong fails
**3/3**, with worst iq RMSE **.116755 A**, speed deviation **10.0264 rpm** and
recovery **.01664 s**. Most recovery values are zero because the disturbance
remains within the existing ±10 rpm band, not because dynamics are instantaneous.
Strong angle combined true id RMS is **.04825–.07991 A**, versus clean baseline
**8.18–18.12 microampere**. Strong Rs drift still passes all three motors with
speed RMSE **1.19786–2.74765 rpm**, iq RMSE **.00432–.00643 A** at this operating point.

Small independent M16 interaction: first clean commissioned motor, fixed
nominal-bus recipe from identified steady voltage, six operating cells per
population. **2/6 agreement, four optimistic predictions** in each: sag-only
and combined mild/strong all fail the unchanged hold, while ideal and Rs drift
succeed. Held-out nominal bus **16.18591 V**, actual **15.37661/14.56732 V**;
sag-only final speeds **984.01665/931.24935 rpm**, combined
**982.07732/929.74449 rpm**, with **85.75–86.77%** terminal clipping in failures.
M16 and its quasi-steady estimate semantics remain unchanged.

[Development](../results/nonideality_robustness/development.csv),
[held-out](../results/nonideality_robustness/held_out.csv),
[summary](../results/nonideality_robustness/held_out_summary.json),
[attempts](../results/nonideality_robustness/held_out_attempts.json),
[impact plot](../results/nonideality_robustness/held_out_nonideality_impact_matrix.png),
[response plot](../results/nonideality_robustness/held_out_combined_case_response.png)
and [M16 rows](../results/nonideality_robustness/held_out_m16_comparison.csv)
retain original results, with separate truth audits and sampled response traces.
Plots were visually inspected. Exposure rows share only five motors, so they do
not establish independent-sample population reliability.

### What We Learned

A measured-data gate can detect an inconsistent model without detecting a
coherently biased model. Common current gain approximately scales electrical
Rs/L down and reconstructed torque/J/B up; common voltage gain scales electrical
and mechanical parameters together. Small residual and local noise sensitivity
do not certify sensor calibration. Integral control and correlated tuning errors
can preserve speed response despite inaccurate estimates. Sensing bias,
historically valid-but-stale parameters and actuator headroom failures need
separate interpretation. Adaptive logic cannot request a retry for an error its
diagnostics accept; no retry effectiveness claim follows from this matrix.

### Remaining Limitations

Averaged simulation, not switching PWM/dead-time/device modeling or hardware
validation. Fixed bounded stress/fault severities, low Gaussian noise and five
motors do not represent universal device specifications. Gaussian noise is
added after the deterministic sample chain; no full ADC or feedback-noise chain
is modeled. Fixed bus sag, sign-based averaged voltage drop, fixed alignment bias
and a one-step/sample delay do not capture frequency-dependent sensor dynamics,
switching ripple or jitter. Rs drift is not a thermal network/online estimator.
Unknown load/friction/model mismatch limitations of prior commissioning remain.
Current-reference and excitation limits are simulation constraints, not physical
hardware-safety guarantees. The compact M16 comparison probes one motor per
population and a deliberately small nominal-headroom recipe, not universal
prediction reliability. No calibrated probabilistic coverage for structured
bias is claimed.
The actual-bus clipping flag uses a strict vector comparison and can include
last-bit boundary clips even without sag; it is separate from nominal FOC
saturation and must be interpreted with terminal-command discrepancy.

### Next Decision

Use retained silent-bias and nominal/actual-bus failures to inform a separately
designed future study of calibration/model validity and operating reserves.
Any redesign requires its own development/held-out protocol. This milestone
only characterizes the frozen workflow; firmware, GUI, online adaptation and
release/orchestration work remain outside this PR.

## Milestone 18 — firmware-ready portable C control core with Python parity

### Problem / Motivation

Commissioning and robustness studies through M17 used Python. A future MCU needs
an explicit controller state/configuration interface and evidence that translation
preserves the validated equations, especially integral rollback and saturation
back-calculation. Copying source without checking state trajectories would not
demonstrate that equivalence.

### Engineering Decision

Verified/fetched main `3eb116ef6d22550668c507c23c9847cdde01c04b`.
Port only transforms, generic PI, dq FOC, vector
limiting and speed PI. Keep Python commissioning, tuning formulas, plant and
M16/M17 evidence unchanged. Define the [C API/parity protocol](firmware_core_protocol.md)
before implementation; use real IEEE binary32 `float`, caller-owned configuration
and mutable state, and no heap/global controller state. Primary proof replays
identical inputs against the unchanged Python float64 reference rather than
comparing independently evolving plants. Do not require bitwise equality.

### Implementation

Three headers define motor/current/speed/PI configurations, vector types, PI
states, requested/applied-voltage outputs and status codes. Two C99 translation
units implement amplitude-invariant transforms, ordered PI integration/clamping,
`p*omega_m` decoupling/feedforward, direction-preserving nominal-bus vector limiting,
back-calculation after saturation and speed iq limiting. Failed calls leave
state/output untouched; reset deterministically zeros integrators.

`src.firmware_config` requires accepted full electrical+mechanical commissioning,
extracts identified Rs/Ld/Lq/psi/J/B, invokes existing current/speed constructors
and emits exact binary32 hexadecimal C constants. There is no C commissioning or
second gain formula. Tests reject either failed gate and invalid/unrepresentable
configuration. The [example header](../results/firmware_parity/generated_motor_config.h)
comes from real simulated sampled commissioning with seeds 1801/1802/1803 and a
24 V nominal bus, explicitly labeled as simulation-derived demonstration values.

`firmware.parity` compiles a host library, binds the public API and compares all
outputs/integrators over deterministic transform, PI, FOC, speed and combined
streams. The existing Python simulation only generates combined inputs; both
FOC implementations use the same recorded iq reference and feedback. The speed
output is compared separately, preventing upstream differences from contaminating
the current-controller parity proof. All 30,000 replay steps are checked; artifact
sampling retains every signal's maximum absolute/relative sample and all flag
disagreements. Native C assertions also include/compile the generated header.
CI adds visible GCC/Clang compile/parity jobs alongside the existing full suite.

### Problems / Unexpected Results

No GCC/Clang was initially on local PATH. A temporary official w64devkit toolchain
was downloaded, checksum-verified and extracted outside the repository; GCC 16.2.0
provided actual local C verification. No toolchain or binaries are committed.
An initial focused pytest run had an existing Windows cache-directory permission
warning; final verification disables that optional cache provider.

**16/96 strict saturation-boundary probes have different Python/C flags**, although
their numerical vector differences satisfy the predeclared budget. Float32 norm
rounding can change a strict `>` comparison; forcing the flag would change the
reference algorithm. The largest relative difference is in the small q integral,
not the voltage magnitude: **.585%** despite only **.1494 mV** absolute discrepancy
at that relative-worst step. Long accumulated rounding and cancellation must be
reported even when output error is small.

### Resolution

Kept float precision, controller comparisons and tolerances unchanged. Retain
every boundary probe and report exact flag agreement separately away from the
predeclared `16*u*(abs(norm)+abs(limit))` envelope. Add tests that prohibit silent
filtering; do not fix a platform-dependent count as a universal requirement.
Use explicit float32 arithmetic only as a secondary diagnostic, keeping original
Python arithmetic as the acceptance reference. Tests verify invalid dt/bus/gains,
overflow without partial commits, independent instances and deterministic reset.
Source hash tests normalize line endings and protect all four Python references.

### Validation / Results

Baseline: **180 tests passed in 124.46 s**. Local C builds cleanly with GCC
**16.2.0**, `-std=c99 -Wall -Wextra -Werror -pedantic -O2 -ffp-contract=off`.
**43 native C assertions pass**, including the generated configuration. No compiler
warning was suppressed. Final full suite: **232 passed in 119.35 s**, including
**52 new M18 tests**, with no skips or xfails. `git diff --check` passed. The
generated plot was visually inspected, including separate error axes.

**31,484 compared samples**: 108 transforms, 256 standalone PI, 768 synthetic
FOC, 256 speed, 96 boundary vectors, 30,000 combined trace steps. Transform
maximum absolute/relative error is **1.864605e-6 / 3.896980e-7**. Standalone PI
output/integral maximum absolute error is **1.354661e-6 / 9.292793e-7**;
speed reference/integral **6.804361e-7 / 6.649375e-7 A**. Synthetic FOC requested
vd/vq errors are **6.066528e-7 / 7.545959e-6 V**; applied vd/vq
**1.398782e-6 / 5.710366e-6 V**; d/q integral
**4.332207e-7 / 5.309827e-6 V**.

Combined applied vd/vq: **2.053589e-7 / 1.531645e-4 V**; current d/q integral
**4.963309e-9 / 1.527868e-4 V**; speed output/integral both
**1.751090e-5 A**. Overall absolute maximum: requested voltage magnitude,
**.0001535715773 V**, sample **24545** (Python 9.48622325084 V, C 9.48606967926 V).
Overall relative maximum: q integral **.00585030427**, sample **6397**
(Python .02553443619 V, C .02538505197 V). This is 0.585%, not the voltage
magnitude's much smaller relative discrepancy. All numerical differences meet
the budgets declared before C results; none were loosened.

Flags: **30,592/30,608 agreement**, **30,512/30,512 away from boundary**, with
**16 disagreements among 96 boundary probes**, all retained. Explicit secondary
float32 FOC agrees exactly for six compared outputs/states on this compiler;
no universal bitwise-libm claim follows. Artifacts retain full maxima and locations:
[summary](../results/firmware_parity/parity_summary.json),
[vectors](../results/firmware_parity/parity_vectors.csv),
[sampled replay](../results/firmware_parity/parity_trace.csv),
[plot](../results/firmware_parity/parity_plot.png). No M16/M17 population was rerun
or modified; no pre-existing functional Python code changed.

### What We Learned

Controller output parity alone can hide state discrepancies or update-order
errors. Replaying identical sampled inputs makes that distinction auditable.
Real binary32 introduces both accumulated integral rounding and Boolean boundary
differences; preserving and quantifying them is stronger evidence than hiding
double precision inside C. Offline accepted commissioning can supply a portable
configuration without moving research estimators onto an MCU.

### Remaining Limitations

Firmware-ready, not deployed firmware. Host compiler tests do not measure target
silicon deadlines, WCET, interrupt behavior or hardware validation. No peripheral,
PWM/ADC/encoder, HAL/RTOS, fixed point or MISRA certification is provided. No C
motor simulation is used; this study proves controller replay under declared
streams, not a complete hardware drive. Float32/libm/FPU/ABI settings and last-bit
flags require target verification. Existing commissioning bias/model/load limits
still apply; the exporter does not re-certify accepted estimates.

### Next Decision

Use these APIs, generated constants and replay vectors for a separately scoped
future hardware integration, including target timing and peripheral validation.
M18 ends with this portable-kernel PR; no M19 implementation is started.

## Milestone 19 — End-to-end engineering application and v1 release candidate

### Problem / Motivation

M1-M18 supplied the complete simulation/commissioning/analysis/C backend, but
a reviewer had to assemble many experiment commands to follow one case.
Accepted/rejected estimates, retry history, retuned controllers, operating
predictions, nonidealities and firmware configuration lacked one inspectable
application path. Productizing that path must not introduce a second estimator,
change quality gates, hide failures or mistake historical evidence for a new run.

### Engineering Decision

Verified/fetched current main `fe0173120fbc64a5accb05ca474a86892ec569e1`.
Implement the headless orchestration
first, then a thin local Streamlit dashboard. Keep existing algorithms, gates,
adaptive actions, M14/M16 semantics, M17 registry/results and M18 C budgets
unchanged. Use typed frozen result envelopes, an explicit simulation-truth
boundary, original controller constructors and accepted-only export. Prepare
version 1.0.0 as a release candidate, without a tag, GitHub Release or merge.

### Implementation

`src.engineering_workflow` resolves configuration/seeds/bus and calls existing
sampled standstill, driven-rotor and free-rotor acquisition. One-shot or original
adaptive commissioning returns actual estimates/gates/attempts. Full acceptance
feeds original retuning, M14 steady and M16 dynamic assessment, original speed
FOC simulation with exact M17 errors, and M18 configuration construction.
Rejection keeps all prior controller parameters, partial fits and failures,
with no fabricated downstream commissioned operation.

`app` launches with `python -m app`; read-only presentation shows estimates,
units, diagnostics, fit plots, attempt actions/next settings, active parameters
and gains. Truth/errors/true-frame control validation are separately labeled.
Current-run downloads use `src.engineering_bundle`; engineering figures use
`src.engineering_reporting`. Firmware export rechecks acceptance. M18 evidence
is displayed as committed, hashed validation evidence, never current-run replay.

`python -m experiments.v1_demo` computes two predeclared cases into a new
`results/v1_demo` directory: nominal one-shot and adaptive one-sample timing
error. Historical directories are protected. New headless tests and CI exercise
real backend/AppTest/demo paths. README now leads with v1 usage; architecture,
validation, changelog and release-candidate notes document the boundaries.

### Problems / Unexpected Results

The initial result configuration reported obsolete default stage seeds/bus
although providers used the selected values. This was a provenance integration
error, not an estimator error. Native browser number validation also blocked
submission of small SI defaults and the hold-time default because their generic
input steps did not fit the HTML grid. Headless AppTest alone did not expose
that browser behavior. An accepted-but-unavailable export originally used an
exception name implying quality rejection; those states need distinct reporting.
Final review also found a new figure label claiming retained priors when accepted
control validation was unavailable; that label needed the same separation.

The nominal M16 controller prediction returns success while also reporting
`dynamic.reverse_speed_excursion`: minimum **-0.017217995998478113 rpm**.
This is existing backend semantics, not a new integration defect. The actual
load-step recovery metric is **0 s** because the entire deviation is within the
existing +/-10 rpm band; it is not evidence of instantaneous dynamics.
The exact timing-delay preset terminates at standstill despite a rank-3 numerical
fit. Neither observation was tuned away to improve the demonstration.

### Resolution

Store resolved provider inputs and assert them against measurement records.
Stop feature expansion to correct numeric widget steps, verify real browser
validity and add a grid regression. Distinguish export/plot unavailability from
gate rejection and cover the accepted-but-unavailable plot in a regression.
Inspect the accepted/rejected application in a real local browser;
save screenshots, including blocked export. Preserve original reason strings,
success criteria and all partial/rejected records. No M1-M18 algorithm correction
was needed.

### Validation / Results

Baseline **232 passed in 117.87 s**; final **265 passed in 168.01 s**, including
33 new tests and no skips/xfails. Direct equivalence tests cover M14, M16,
constructor gains, actual control trace and M18 header. Additional tests preserve
adaptive retries, rejected priors, biased acceptances, operation-only sag,
accepted-but-infeasible operation and failed providers. The demo is reproduced
by one command and its computed JSON/CSV/header compared against the new artifacts.

Local strict GCC **16.2.0** recheck: **43 C assertions**, **31,484 samples**,
unchanged maximum absolute error **0.0001535715773 V**, relative maximum
**0.00585030427** in q integral. Flags **30,592/30,608**, away from boundary
**30,512/30,512**; all 16 boundary discrepancies retained. Clang is checked by
the existing CI job; it was not available locally. No M18 artifact was overwritten.

Nominal seed 1901, 24 V, 1000 rpm, 5 A limit, load step 0.05 N m at 0.3 s:
three accepted stages, M14 `feasible`, firmware available. Estimates/errors:

| Parameter | Estimate | Absolute error % |
| --- | --- | --- |
| Rs (ohm) | 0.4999714668704501 | 0.005706625910 |
| Ld (H) | 0.0011998665089995645 | 0.011124250036 |
| Lq (H) | 0.0008998205646831202 | 0.019937257431 |
| psi_f (Wb) | 0.02199917603768355 | 0.003745283257 |
| J (kg m²) | 0.0005491416419952162 | 0.156065091779 |
| B (N m s/rad) | 0.00019975742406827315 | 0.121287965863 |

Post-load speed RMSE **1.6072373103997428 rpm**, true-frame iq RMSE
**0.0030203618653856356 A**, maximum speed deviation **5.210293678960511 rpm**,
recovery **0 s**, current peak **4.999996729356155 A**, command/terminal voltage
utilization **0.7944419176947385**, both saturation fractions **0**.
M16 quasi-steady transition **0.09495434060449318 s**; controller entry
**0.10172 s**, hold completion **0.20172000000000004 s**, predicted success true,
with the reverse-excursion diagnostic retained.

Adaptive timing case: one rejected standstill attempt, reason
`standstill.excessive_residual`, terminal reason
`standstill.model_residual_terminal`, no retry. Partial Rs/Ld/Lq remain visible;
residual **0.0001018341996930411 V s**, scaled condition **1.0026856200502245**,
normalized excess residual **1.6977787767548365 > 1.0**. No later commissioned
stages or header are fabricated. See [v1 validation](v1_validation.md) and the
[new demo bundles](../results/v1_demo) for complete records.

### What We Learned

A coherent application needs explicit state and information boundaries as much
as numerical algorithms. Quality acceptance, operating feasibility, model
prediction and hidden-plant evaluation must remain separately interpretable.
Browser-native validation can reveal a real input failure that a headless UI
test misses. Provenance must describe actual resolved inputs. Rejected cases
and small adverse diagnostics are part of the engineering demonstration.

### Remaining Limitations

Simulation only; no MCU deployment, hardware validation, target timing, MISRA
claim or physical safety guarantee. Known zero external mechanical load,
attached-inertia changes, friction mismatch and sensor bias remain existing
limits. Gates can accept biased data; good tracking does not imply accurate
commissioning. M16 quasi-steady timing is not a universal lower bound; its earlier
negative held-out finding remains intact. M16 constant-load prediction and
actual load-step/M17 validation have distinct assumptions. The dashboard is
synchronous, not a real-time drive service. Compact bundles retain all attempts
but do not export every acquisition waveform. The repository has no declared
software license; no license was invented for v1 preparation.

### Next Decision

Review the M19 PR and Python/GCC/Clang/headless-app CI, decide licensing and
release readiness, then separately authorize merge/tag/release if appropriate.
This milestone ends with an open PR and release-candidate files; it starts no
new engineering algorithm, hardware integration or subsequent milestone.


## v1.0.0 release finalization — 2026-10-03

After M19 review and passing Python 3.11/3.12, GCC, Clang, and headless
application/demo CI, the repository was prepared for the v1.0.0 release.
The project release status changed from release candidate to released and an
MIT License was added. Firmware-header provenance was made version-stable by
recording project version, seed, and scenario without embedding the transient
RC label.

This finalization changes no PMSM equation, estimator, quality threshold,
adaptive action, M14/M16 semantics, M17 scenario/evidence, or M18 numerical
parity budget. Hardware deployment, MCU timing, and hardware validation remain
future work.
