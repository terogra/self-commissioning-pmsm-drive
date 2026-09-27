# Self-Commissioning PMSM Drive

Python model of a permanent-magnet synchronous motor (PMSM) drive. The current
stage includes a dq-axis plant, Clarke/Park transforms, cascaded speed and dq
current PI control, and one-at-a-time motor parameter mismatch experiments.
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
run. The plant is integrated with RK4. The model currently assumes ideal
voltage commands and exact state feedback; it does not model an inverter,
measurement noise, or sampling delays.

## Run

From the repository root, install dependencies and run:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.speed_foc_simulation
python -m experiments.parameter_sensitivity
```

The last command writes the sweep table and comparison plots to `results/`.
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

The speed plot zooms in on the load-step response. The metric plot compares
all four measures across mismatch levels. Speed RMSE includes the large
startup transient, so the post-step measures are better for isolating load
rejection.

## Next steps

Use the separate parameter sets as an interface for online motor parameter
identification, then update the controller assumptions and retune the PI loops.
