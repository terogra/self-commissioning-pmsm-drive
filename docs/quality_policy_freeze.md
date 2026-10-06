# Electrical quality thresholds and evaluation

This record precedes the independent final evaluation. The commit introducing
this file freezes `QualityPolicy` and the measured-data decision logic.

## Development evidence and decision

Development seed **20261001** produced 13 cases: 4 accepted, 8 quality
rejections, and 1 estimator failure. All 4 accepted estimates met the post-hoc
10% parameter-error criterion; 2 of the 8 rejected estimates also met it.
Only 2 accepted cases met the composite closed-loop success criterion.
The two accurate rejections failed the noise/information budget under weak
excitation. Retain that conservative budget: a favorable noise realization
does not establish adequate information for another record.

The candidate policy was specified before this development run and is retained
without numerical tuning. Development supports testing it independently, not
claiming a calibrated probability of correctness. Hidden-error and control
scores describe the development outcome; they are never gate inputs.

## Fixed engineering budgets

| Check | Threshold | Rationale and scope |
| --- | --- | --- |
| Rank | Full column rank | Necessary uniqueness of the fitted regression. |
| Record length | At least 10 windows per stage | Gives each chronological half at least 5 windows (10 d/q equations at standstill, 5 scalar equations in rotation), exceeding its unknown count. An engineering minimum, not independent-sample statistical sufficiency. |
| Scaled condition number | At most 100 | Limits worst-direction numerical amplification in the normalized design to two orders of magnitude. Does not establish physical excitation strength. |
| Expected design-noise / observed information | At most 0.05 | Allocates a 5% information-contamination budget to errors-in-variables risk, smaller than the 10% parameter target. This is a warning metric, not a rigorous bias bound. |
| Local relative standard error | At most 0.10 / 3 | Allocates three local sensor-noise sensitivity units within a 10% parameter precision budget. The factor three is a conservative margin, not a 99.7% coverage claim. |
| First/second-half fit difference | At most 10% of full fit | Requires temporal consistency within the same parameter precision budget. Can reject useful records; cannot detect a common bias in both halves. |
| Residual RMS | At most 3 times predicted sensor-noise RMS plus 1% of target RMS | A threefold noise margin plus a small relative model/integration allowance. This is a model-consistency screen, not a chi-square test or fitted confidence interval. The 1% allowance is an explicit engineering tolerance, not statistically calibrated. |
| Rotating noise RMS / fitted back-EMF RMS | At most 0.10 | Requires integrated back-EMF signal-to-noise ratio of at least 10. |
| Minimum absolute mechanical speed | At least 10 rad/s | Retains the existing flux estimator operating floor; nonzero speed alone can still give weak back EMF, hence the separate signal-to-noise check. |

All checks must pass. Missing diagnostics or noise metadata reject; estimator
exceptions reject separately. These budgets intentionally trade coverage for
measurement quality. They are transparent design choices, not optimal or
universal motor thresholds.

## Locked final protocol

Use seed **20261002**, independent of development, with the already specified
73-case design: three noise levels, four speeds, three bus voltages, two
standstill excitation scales, one plant draw per cell, plus an unexcited
sentinel. Keep every case. Do not change thresholds in response to its results.
Any later policy revision requires a new independent evaluation population.

Post-hoc accuracy requires all four absolute parameter errors to be at most
10%. Report both inaccurate/accepted (false discoveries) and accepted/inaccurate
(false positives), plus rejected/accurate (false negatives). Missing complete
estimates have separate failure counts and cannot be assigned accuracy labels.
Report accepted-control performance even when voltage infeasibility prevents
success. True parameters remain restricted to physical simulation and post-hoc
scoring; they are absent from the gate interface.
