# Self-Commissioning PMSM Drive

Python model of a permanent-magnet synchronous motor (PMSM) drive. The current
stage includes a dq-axis plant, Clarke/Park transforms, cascaded speed and dq
current PI control, a DC-bus voltage constraint, parameter mismatch studies,
and a two-stage electrical commissioning workflow. Locked-rotor excitation
estimates `Rs`, `Ld`, and `Lq`; driven-rotor excitation estimates `psi_f`.
The resulting parameters automatically retune the current and speed PI loops.

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
Passing `commissioning_result=...` to `run_speed_foc_simulation` constructs
fresh current and speed controllers from that object. Current PI gains are
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
