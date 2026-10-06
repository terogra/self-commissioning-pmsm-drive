# Steady-state feasibility evaluation

Specified before running the new held-out population. The classifier uses the
existing model equations and inclusive physical limits; it fits no thresholds
to development or evaluation labels. Identification gates stay unchanged.

## Scope

Forward motoring requests only: speed and resisting load must be nonnegative;
DC voltage and design current limit must be positive and finite. Zero speed
and zero load are supported. id=0, constant viscous B, ideal linear SVPWM,
no field weakening/MTPA. No J term belongs in steady-state balance.

## Independent dynamic outcome

For a 0.6 s simulation starting from rest with load applied at 0.3 s and a
40 microsecond step, all final 0.1 s speed samples must lie within
max(1 rpm, 1% command), and maximum final-window measured dq current magnitude
must be no more than 1.01 times the configured current limit. These are explicit
finite-run tracking/design tolerances, not a hardware guarantee or a restatement
of the predicted result. Full/post-load RMSE, voltage, achieved speed, current,
and saturation fractions are recorded separately. The simulator limits iq
reference; it does not impose a hard instantaneous measured-current clamp.

All false-feasible cases are also run for 4 s with the same controller, target,
bus, current limit, and load-step time. This investigates time-to-target without
changing the original classification or hiding a failure. No other retuning.

## Designs

Representative motor is the PR #8 comparison plant. Seven predeclared scenarios:
low speed/load; current limited; both limited; voltage limited; voltage boundary
inside/outside (bus 1.005/0.995 times the commissioned voltage requirement times
sqrt(3)); and limited acceleration (10% steady current reserve, starting at rest).
Boundary requests are constructed from accepted estimates before simulation,
never from truth or observed success.

Held-out seed **20261021** draws three independent plants with Rs in [0.35,0.65]
ohm, Ld in [0.8,1.4] mH, Lq in [0.7,1.3] mH, psi_f in [0.015,0.028] Wb,
J in [3e-4,8e-4] kg m², and B in [0.8e-4,2.5e-4] N m s/rad. Each receives
all seven scenarios: 21 requested cases. Each plant is commissioned using the
existing low-noise electrical and mechanical stages with fresh deterministic
sensor streams. Rejected commissioning leaves seven explicitly unavailable
analyses; it does not become seven infeasible operating points. Retain all rows.

Report true positive, true negative, false feasible, and false infeasible counts
against the independent dynamic criterion, plus agreement with oracle steady
predictions. Tolerance-based success may occur slightly outside the exact
analytical boundary; this must be reported as a finite-dataset disagreement.
These 21 correlated scenario/plant cases do not establish population accuracy.

## Historical PR #8 replay

Retain all 13 previous held-out rows. Replay only the five accepted measurement
stages (the old CSV omitted electrical estimates), using their original seeds,
excitation, noise, and bus. Check J/B match saved fits and gate acceptance is
unchanged. Normal prediction uses replayed estimates, never saved true electrical
columns. Oracle equations use true parameters only in the evaluation adapter.
Reuse historical control outcomes instead of rerunning the four controllers.
Historical dynamic success uses the recorded post-load speed RMSE <=10 rpm,
iq RMSE <=0.05 A, recovery <=0.1 s, without its former parameter-error label.
This historical criterion differs from the new terminal-window study.
