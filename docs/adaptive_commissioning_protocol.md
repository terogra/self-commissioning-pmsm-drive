# Adaptive commissioning protocol

This protocol defines the retry decisions and finite evaluation design for milestone 15. The existing electrical `QualityPolicy` and mechanical `MechanicalQualityPolicy` are unchanged. Retry bounds are simulation design settings, not hardware safety ratings. The supervisor sees sampled measurements, quality checks, prior controller assumptions, excitation metadata, and an optional operating request. Plant truth and closed-loop outcomes remain in the evaluation layer.

## State and decision order

Standstill Rs/Ld/Lq must pass its existing standstill quality checks before the rotating flux test. Full electrical quality must pass before the known-zero-load mechanical test. Both gates must pass before any controller parameter update. A requested operating point is assessed only after full acceptance. Its infeasibility ends the process as `operating_infeasible` without changing identification quality or retrying a test. The operating calculation is steady state; dynamic control outcome is recorded only by evaluation code.

Each stage records its configuration, measured-data quality decision, estimate if available, diagnostic snapshot, and any chosen retry action. A retryable failure on the last allowed attempt becomes `retry_budget_exhausted`; unsupported or model-residual failures become `terminal_rejected`. No stage has an unbounded loop.

## Fixed retry mapping

| Measured-data reason | Action, if within design limit |
| --- | --- |
| Standstill `insufficient_windows`, `inconsistent_halves` | Double record duration and change deterministic noise/excitation seed. |
| Standstill `conditioning` | Shorten the two voltage hold periods to enrich switching geometry. |
| Standstill `rank_deficiency`, `noise_information`, `relative_uncertainty` | Double d/q voltage magnitude, preserving their ratio; cap the vector magnitude. At the cap, double duration if possible. |
| Standstill zero-voltage input and rank or nonpositive-estimate failure | Introduce a small bipolar d/q voltage program. The configured zero input is the explicit justification. |
| Rotating `insufficient_windows`, `inconsistent_halves` | Double record duration. |
| Rotating `weak_back_emf`, `insufficient_speed`, `noise_information`, `relative_uncertainty`, `rank_deficiency`, `conditioning` | Double imposed speed; at its cap, double duration if possible. |
| Mechanical `insufficient_excitation`, `relative_uncertainty`, `noise_information`, `rank_deficiency` with weaker J component | Double plateau current amplitude, respecting the reference bound; then extend plateau time if amplitude is capped. |
| Mechanical reasons above with weaker B component, or `conditioning`, `insufficient_windows`, `inconsistent_halves` | Double plateau duration first, then increase current if duration is capped. The relative local sensitivity and component SNR determine which component is weaker. |
| Any stage `excessive_residual` | Terminal model-residual rejection. More excitation is not used to explain a poor model fit. |
| Other estimator failures and invalid measurements | Terminal unsupported-diagnostic rejection. |

The new seed yields a fresh noise/excitation realization on each retry. This may help or hurt an individual result and is not itself evidence of improved observability. The action requires a named measured-data reason or the explicit zero-input configuration. Accepted/rejected checks keep the same limits on every attempt. Where several reasons occur, an excessive residual has priority over retryable reasons.

## Retry bounds

`RetryPolicy` allows at most **four attempts per stage**: four standstill, four rotating, and four mechanical. The standstill voltage-vector magnitude is capped at **3 V** and duration at **0.8 s**. The imposed rotating speed is capped at **1200 rpm** and its record duration at **0.6 s**. Mechanical plateau reference magnitude is capped at **1 A** and each plateau at **0.5 s**. Voltage/current/ speed/ duration increments are at most **2×** and stop at the caps. The separate generator's SVPWM bus limit still applies. Initial configurations above supervisor bounds are invalid.

These caps make the simulation experiment finite and interpretable. They are not claims of permissible current, voltage, speed, or duration on a real motor or inverter.

## Paired development and held-out populations

Development seed: **20261031**. Held-out seed: **20261101**. Both populations use nine predefined scenario cells: normal low noise, weak standstill excitation, weak rotating information, weak mechanical excitation, combined weak excitation, medium noise, high noise, zero standstill input, and a voltage-infeasible operating request. A new plant is independently drawn for each cell and population from Rs 0.35–0.65 Ω, Ld 0.8–1.4 mH, Lq 0.7–1.3 mH, psi_f 0.015–0.028 Wb, J 0.0003–0.0008 kg m², and B 0.00008–0.00025 N m s/rad. All use the same prior controller assumptions. The scenario settings are specified in `experiments/adaptive_commissioning.py`.

For each plant, the one-shot and adaptive paths share cached initial sampled measurement records, including their random noise. Only the adaptive path may request further records. Every scenario remains in the CSV even if an estimator or simulation fails. Exceptions are explicit `evaluation_error` rows and are excluded from neither total nor coverage counts.

The six-parameter accuracy label means every **available** absolute percentage error for Rs, Ld, Lq, psi_f, J, and B is at most 10%, with all six required for a complete label. An accepted case with any error above 10% is a post-hoc false acceptance. A rejected case with all six available and accurate is a post-hoc false rejection. Rejections with missing estimates are reported as **unscorable** for this conditional false-rejection rate, never counted as accurate or silently removed from totals. Electrical and mechanical acceptance are reported separately. Finite sample zero false acceptances is not a reliability guarantee.

Only accepted cases predicted operating-feasible receive a separate 0.6 s closed-loop simulation. Control success requires post-load speed RMSE ≤10 rpm, iq tracking RMSE ≤0.05 A, and disturbance recovery ≤0.1 s, using the existing performance metric function. That outcome never enters quality, retry, or operating feasibility decisions. Voltage-infeasible accepted cases are retained with control outcome unavailable under this protocol. Results are not pooled with PR #9's terminal-window dynamic criterion.

The policy and this protocol are committed before running the held-out seed. The evaluation seed, scenario cells, accuracy rule, and control rule are frozen here. Any later policy changes require another separate evaluation population.
