# Dynamic feasibility evaluation

## Method fixed before evaluation

The development population uses seed **20261002**, three independently drawn
motors and eight requests per accepted motor. The held-out population uses
seed **20261003**, five new motors and the same request recipe. The recipe draws
Rs 0.35–0.65 ohm, Ld 0.8–1.4 mH, Lq 0.7–1.3 mH, flux 0.015–0.028 Wb,
J 3–8 × 10^-4 kg m² and B 0.8–2.5 × 10^-4 N m s/rad. These are deliberately
bounded simulation examples, not a distribution representative of all PMSMs.

No identification gate or adaptive retry rule changes. Commissioning uses
the existing noisy M14 measurement generators and estimators. Every unavailable
commissioning retains all eight scenario rows. Model/simulation errors retain
their rows and reasons. Prediction runs before independent hidden-plant control.
The truth audit is separate from the estimator-only normal API.

The eight fixed scenarios are easy, short deadline, identical longer deadline,
stronger current, high-speed near voltage boundary, slightly outside exact
voltage boundary, unreachable low-voltage target, and moving start. Boundaries
and current requirements are calculated from estimates only. The slow current
multiplier is 1.03–1.30 (representative: 1.10); moving start is 150–400 rpm
(representative: 250). Deadlines are 0.6 s and 4 s. All loads start at t=0.

## Numerical settings and criterion

The quasi-steady integral starts with 257 path nodes and doubles interval count
up to 4097 nodes, stopping when consecutive trapezoid integrals differ by
at most **0.1%** of time. This is a numerical resolution criterion, not a
confidence threshold. Lack of convergence returns an indeterminate quasi-steady
deadline classification. It does not alter identification quality. A focused
test compares the default integral with **0.001%** refinement.

The existing FOC runs at **40 microseconds**, matching M14's validation step.
No controller tuning change is made. Reported traces are downsampled to 1 ms;
success uses every simulation sample, with post-step observation timestamps.
Defaults are ±max(1 rpm, 1% command) and a **0.1 s contiguous hold completed
before the deadline**, matching the earlier tolerance and observation duration.
This is a qualified band hold, not permanent settling. Final-band state is
also reported. Current **references** must remain within Imax and signals must
be finite. Measured current overshoot and voltage saturation are reported;
reference limiting does not constitute physical current protection.

Root coincidence tolerance (relative 10^-9, absolute 10^-12 A) only labels
numerically equal voltage/current limits. It creates no feasibility reserve.
Band and exact-target steady feasibility retain the existing exact inequalities.
No parameter-error label or hidden closed-loop outcome enters these decisions.

The quasi-steady id=0 voltage envelope omits Lq*d(iq)/dt and assumes instant
use of available torque. Its integrated time is a model-specific estimate,
not a physical minimum or universal lower bound. The full dq transient simulation
can enter the band earlier even on the same commissioned parameter model.
Identify disagreements instead of tuning them away. Predictions use accepted
point estimates without probabilistic uncertainty or robustness reserves.

## Development observations and freeze

All **24/24** requests were evaluated with **24/24** controller/outcome agreement,
**11** predicted and actual successes, **zero** false predicted successes or
failures, and **12** quasi-steady completion estimates within deadline. For 11 jointly qualified
holds, median signed entry-time error was **-40 microseconds** and maximum
absolute error **280 microseconds**. Factors: **15 current**, **9 current+voltage**.
No actual entry preceded its quasi-steady estimate in this small sample.

The constant resisting load with initially zero dq currents produced brief
negative speed in **21/24** development trajectories. Retain minimum speed
and an explicit `dynamic.reverse_speed_excursion` reason; do not interpret
these as reverse/regenerative commissioning support. The requested domain is
forward only; the existing unconstrained plant can temporarily violate it.
This scope caveat does not replace the specified band-hold success criterion.

No empirical decision threshold was fitted. The equations, numerical settings,
request design and success scoring above are frozen with the development
artifacts before held-out execution. Later evaluation must report all
disagreements, time errors, unavailable cases and limiting factors. Small
scenario counts sharing motors cannot establish reliability or hardware safety.

## M14 retrospective

Replay the three saved M14 held-out motors and measurement seeds; use their
original acceleration-limited current limits at 0.6 s and 4 s. Preserve old
outcomes separately. M16's t=0 constant load and sampled hold differ from
M14's t=0.3 s load step and terminal-window measured-current criterion, so
this is a sanity check, not an exact rescore or pooled agreement statistic.

## Post-evaluation semantics correction (PR #11 review)

The original numerical method and evaluation remain frozen in **717ef32**
and the original result commit **c7bcc3e**. After the held-out negative finding,
API names and saved artifact schemas were corrected to quasi-steady estimates:
`quasi_steady_transition_time_estimate_s`,
`quasi_steady_completion_time_estimate_s`, `quasi_steady_deadline_met`, and
`quasi_steady_band_reachable`. The deadline flag is True only when the reduced
model estimates entry plus hold within the deadline, False for a model-blocked
entry or estimated deadline miss, and None for unresolved integration.
Neither True nor False certifies the full dq response. Rejection reasons
are now `dynamic.quasi_steady_nonpositive_acceleration`,
`dynamic.quasi_steady_deadline_exceeded` and
`dynamic.quasi_steady_integration_resolution`.

The original held-out records retain **3/40** hidden-plant early entries and
**3/40** same-model controller early entries relative to the quasi-steady
estimate, including **two** of the three hidden-plant early-entry cases.
Those overlapping cases invalidate a universal-bound interpretation independently
of parameter-estimation error. The third same-model gap is 151.25 µs, comparable
to the numerical integration-refinement tolerance. No numerical value, seed, population, controller,
quality gate, supervisor or success criterion changed. Plot labels are rendered
from original CSV values using `--replot-saved`; no replacement evaluation is run.

The trajectory acceleration is now `quasi_steady_acceleration_rad_s2`, and the
minimum path margin is `quasi_steady_minimum_acceleration_margin_rad_s2`.
Aggregate keys are `quasi_steady_deadline_met` (count in summaries),
`quasi_steady_deadline_missed_but_actual_success`, and
`actual_entry_before_quasi_steady_estimate`. These are model/record diagnostics.
The result container is `DynamicFeasibilityResult.quasi_steady`, its type is
`QuasiSteadyCapability`, and its helper is `assess_quasi_steady_capability`.
The original ambiguous API names are removed rather than retained as aliases.
