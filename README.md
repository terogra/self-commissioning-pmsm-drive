# Self-Commissioning PMSM Drive

Python model of a permanent-magnet synchronous motor (PMSM) drive. The current
stage includes a dq-axis plant, Clarke/Park transforms, cascaded speed and dq
current PI control, a DC-bus voltage constraint, and one-at-a-time motor
parameter mismatch experiments.
Motor parameter identification and automatic PI retuning are future work.

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

The voltage circle approximates an ideal linear SVPWM inverter. The model
does not include switching, bus sag, overmodulation, dead time, measurement
noise, or sampling delays; rotor position and currents are measured exactly.

## Run

From the repository root, install dependencies and run:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.speed_foc_simulation
python -m experiments.parameter_sensitivity
python -m experiments.voltage_saturation_mismatch
```

The experiment commands write CSV tables and comparison plots to `results/`.
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

## Next steps

Use the separate parameter sets as an interface for online motor parameter
identification, then update the controller assumptions and retune the PI loops.
