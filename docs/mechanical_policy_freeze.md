# Mechanical quality policy and evaluation freeze

This record is committed before the held-out mechanical population is run.
The new estimator and gate use only measurements, commissioned electrical
parameters, their diagnostics, known pole count, and explicitly known load.
No true J/B, true electromagnetic torque, or closed-loop outcome enters a check.

## Fixed engineering budgets

The candidate budgets were specified before running the comparison/development
cases and retained unchanged. They are transparent engineering screens, not
probabilistic confidence or universal motor tolerances.

| Check | Budget | Reason |
| --- | --- | --- |
| Rank | 2 | Both mechanical coefficients must be uniquely determined. |
| Windows | At least 10 | Each chronological half has at least 5 equations for two unknowns. This is a redundancy minimum, not a sample-size theorem. |
| Scaled condition number | At most 100 | Same two-orders-of-magnitude normalized directional amplification budget as the electrical gate. |
| Expected design-noise / observed information | At most 0.05 | Same 5% errors-in-variables warning budget; not a bias bound. |
| Relative local SD bound | At most 0.10/3 for both J and B | Three local sensitivity units within a 10% precision budget, without a coverage claim. Electrical marginal uncertainties are combined by a triangle-inequality bound, not an unjustified independence assumption. |
| Conditional component SNR | At least 3 for both J and B | Each fitted physical contribution, projected away from the other regressor, must exceed three predicted sensor residual RMS units. This rejects weak physical information even when normalized rank looks adequate. |
| Half-fit disagreement | At most 10% | Same temporal consistency budget as electrical commissioning; shared bias can still pass. |
| Residual RMS | At most 3 sensor RMS + 1% target RMS | Same explicit noise/model tolerance as the electrical gate; no statistical goodness-of-fit claim. |

Unknown load, nonfinite data, nonpositive estimates, rank deficiency, or missing
noise/electrical uncertainty produce rejection. Both electrical and mechanical
gates must accept before the full result can retune any controller field.
The existing electrical gate is unchanged.

## Development and final protocol

Development seed **20261011**: 5 cases, comprising low/high mechanical noise,
8%/100% excitation at 24 V, plus an unexcited sentinel. The existing population
generator draws electrical plants; a separate deterministic stream draws
J uniformly in [1.5e-4, 9e-4] kg m² and B in [0.5e-4, 5e-4] N m s/rad.
Three cases accepted, one quality rejection, and one rank failure; no observed
false acceptance or false rejection. All three accepted cases met the control
criterion. This very small development set supports a held-out check, not
general reliability claims. No threshold was adjusted to those truth labels.

An initial pilot reused the comparison demo's fixed electrical-noise seeds.
Review identified this reuse; the pilot is retained under
`results/mechanical_population/pilot_shared_electrical_noise/` and is excluded
from the development/final comparison. The corrected population uses case seed
for mechanical noise, seed+1 for standstill, and seed+2 for rotation; development
was rerun with those separate streams before freezing. Policy values did not
change. The corrected development also has 3 accepted, 1 rejection, 1 failure.

Final seed **20261012**: 13 cases with low/medium/high mechanical noise,
8%/100% excitation, 12/24 V, one plant per cell, plus an unexcited sentinel.
Electrical commissioning noise remains low (0.01 A, 0.01 V, 0.02 rad/s) so this
small study focuses on mechanical identification. Commissioning electrical
experiments use their existing 48 V rig; mechanical excitation and controller
comparisons use the per-case bus. Draws and all sensor streams are disjoint
across corrected development and final populations. Retain every case.

Accuracy scoring uses both J/B absolute errors ≤10%, after the decision.
Report inaccurate/accepted and rejected/accurate complete estimates, coverage,
and estimator failures separately. Accepted control success additionally requires
post-load speed RMSE ≤10 rpm, iq RMSE ≤0.05 A, and recovery within 0.10 s.
Compare all four controller types on each same plant; rejected full results
explicitly run the unchanged-prior fallback and cannot count as full success.
Report finite-value statistics with missing counts for unrecovered cases.

Do not change the gate after observing final results. Any later revision needs
a new held-out population. The small stratified study is exploratory, not a
population confidence estimate.
