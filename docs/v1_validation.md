# v1 release-candidate validation

This document separates newly computed M19 application results from retained
M1-M18 engineering evidence. It is not a hardware-validation report.

## Starting state and scope

Fetched/verified main **fe0173120fbc64a5accb05ca474a86892ec569e1** before creating
`codex/end-to-end-engineering-app-v1`. Baseline: **232 passed in 117.87 s**.
M19 adds orchestration/presentation/tests/docs; no pre-existing functional
engineering source, threshold, equation, held-out seed or historical result is
changed. No new population is used to tune the dashboard demonstration.

## Local test evidence

Full suite: **265 passed in 168.01 s**, no skips or xfails. The 33 new tests
exercise real headless orchestration, not stored result substitution:

- Accepted and rejected end-to-end paths, partial estimates and retained priors.
- Six identified parameters, original constructor gains and M18 header equivalence.
- Direct M14/M16 invocation equivalence and actual simulation trace equivalence.
- Adaptive retry history and terminal model-residual rejection.
- Exact M17 presets, operation-only bus sag and accepted measurement bias.
- Accepted-but-voltage-infeasible operation, with unchanged identification status.
- Measurement failure retention and distinct export-unavailability behavior.
- Reproducible seed, resolved provider metadata and read-only traces.
- Bundle truth separation, stale-header removal and historical-result protection.
- Real one-command demo reproduction, allowing provenance metadata differences.
- Read-only presentation helpers, launch smoke check and headless Streamlit AppTest.
- Native HTML numeric-grid defaults checked so the real browser can submit small
  SI parameters, rather than relying only on AppTest's non-browser input path.

Actual local-browser inspection also verified accepted controller update,
terminal rejection, inspectable partial fits and absence of the export button
after rejection. Screenshots are actual computed runs:

- [Accepted controller update](images/v1_dashboard_accepted.png)
- [Rejected timing-delay case](images/v1_dashboard_rejected.png)

## Native C and parity

GCC **16.2.0**, strict `-std=c99 -Wall -Wextra -Werror -pedantic -O2
-ffp-contract=off`: **43 native assertions**, **31,484 samples**, unchanged M18
numerical results. M19 regenerated this evidence into a temporary output only;
the committed historical M18 artifact was not overwritten.

| Evidence | Result |
| --- | --- |
| Worst absolute discrepancy | 0.0001535715773 V, requested voltage magnitude |
| Worst relative discrepancy | 0.00585030427, small q integral |
| Saturation flag agreement | 30,592 / 30,608 |
| Away from declared boundary envelope | 30,512 / 30,512 |
| Boundary discrepancies | 16 / 96 probes, all retained |

Local Clang is unavailable. Existing GCC and Clang CI jobs remain authoritative
for both compiler configurations; CI runs strict C tests and the parity
experiment. Full-suite jobs retain Python 3.11/3.12. A new Python 3.12 job runs
the application/backend tests and demo headlessly without launching a browser.
CI status is reported with the PR, rather than inferred from a local compiler.

The app reads `results/firmware_parity/parity_summary.json` as **COMMITTED M18
VALIDATION EVIDENCE**, including artifact SHA256, compiler, sample counts,
maxima and boundary caveat. It does not claim a C replay was performed for its
newly computed case.

## Predeclared demonstration

Run `python -m experiments.v1_demo`. Configuration is fixed in that module
before execution: seed 1901, truth Rs=0.5 ohm, Ld=0.0012 H, Lq=0.0009 H,
psi_f=0.022 Wb, J=0.00055 kg m², B=0.0002 N m s/rad, known p=4. Priors are the
existing nominal parameter defaults. Bus=24 V, iq limit=5 A, target=1000 rpm,
load step=0.05 N m at 0.3 s, duration/deadline=0.6 s, hold=0.1 s, dt=40 us.
Electrical noise is 0.01 A / 0.01 V / 0.02 rad/s; the existing mechanical
configuration uses 0.01 A / 0.05 rad/s. Stage seeds are 1901/1902/1903.
Mechanical commissioning assumes known zero external load.

### Nominal accepted case

Three accepted one-shot stages, full retuning, M14 `feasible`, firmware available.

| Parameter | Estimate | Absolute error % |
| --- | --- | --- |
| Rs (ohm) | 0.4999714668704501 | 0.005706625910 |
| Ld (H) | 0.0011998665089995645 | 0.011124250036 |
| Lq (H) | 0.0008998205646831202 | 0.019937257431 |
| psi_f (Wb) | 0.02199917603768355 | 0.003745283257 |
| J (kg m²) | 0.0005491416419952162 | 0.156065091779 |
| B (N m s/rad) | 0.00019975742406827315 | 0.121287965863 |

| Actual hidden-plant validation metric | Value |
| --- | --- |
| Post-load speed RMSE | 1.6072373103997428 rpm |
| True-frame iq tracking RMSE | 0.0030203618653856356 A |
| Maximum post-load speed deviation | 5.210293678960511 rpm |
| Disturbance recovery time | 0.0 s |
| Peak true current | 4.999996729356155 A |
| Command / terminal voltage utilization | 0.7944419176947385 / 0.7944419176947385 |
| Command / actual-bus saturation fraction | 0 / 0 |
| Final speed | 999.9999963226587 rpm |

The zero recovery time follows the existing +/-10 rpm band: the load excursion
never leaves it. It does **not** indicate instantaneous disturbance dynamics.

M16 quasi-steady transition/completion estimates: **0.09495434060449318 /
0.19495434060449318 s**. Controller-aware entry/hold completion: **0.10172 /
0.20172000000000004 s**, predicted success true. Also retained:
`dynamic.reverse_speed_excursion` with minimum speed **-0.017217995998478113 rpm**.
That diagnostic and success coexist in the unchanged M16 output; neither is
suppressed or used to retune a threshold. Constant-load M16 prediction and
load-step actual validation are distinct experiments.

### Explicit rejected case

Exact M17 `timing_one_sample` preset, adaptive mode, same plant/seed/request.
One standstill estimator succeeds numerically but quality rejects with
`standstill.excessive_residual`. Supervisor terminates with
`standstill.model_residual_terminal`; action `model_residual_terminal`, no next
retry configuration. This is a model-residual rejection, not a fabricated
estimator failure.

Partial estimates: Rs **0.4728342026011756 ohm**, Ld **0.0012425407380017705 H**,
Lq **0.0009394228188310561 H**. Rank=3, scaled condition=**1.0026856200502245**,
residual RMSE=**0.0001018341996930411 V s**, normalized excess residual
**1.6977787767548365** against existing threshold **1.0**. All 4,001 sampled
standstill measurements remain in the workflow record. No later stages are
invented. All prior controller parameters remain unchanged. No steady/dynamic
analysis, commissioned control trace or firmware header is created.

## Reproduction and artifact inspection

Accepted bundle: summary/attempts JSON, sampled trace CSV, generated C header,
summary PNG. Rejected bundle: summary/attempts JSON and rejection PNG only.
Every attempt remains in JSON. Full sampled acquisition records remain in the
in-memory typed result; the compact export records their counts, failure/noise
metadata and configurations, not every commissioning waveform.

The automated reproduction test invokes the real demo command into a temporary
directory and compares computed JSON fields, headers and parsed CSV values
against committed artifacts. It excludes UTC time, revision and dirty state;
numeric comparisons allow 1e-8 relative / 1e-10 absolute cross-platform rounding.
Booleans/header content remain exact. PNG bytes are not treated as numerical
evidence; plots are inspected visually. Trace CSV keeps every 25th row, final
sample and saturation-state transitions, while metrics use all samples.
The generation/export APIs protect historical result directories.

## Integration issues found and corrected

1. Initial result metadata retained default stage seed/bus values even though
   providers used the selected values. Store resolved provider configuration and
   test it directly. Numerical results did not change.
2. Real browser number-input validation rejected small SI defaults because
   generic steps were too coarse; the hold-time default was also off its input
   grid. Use compatible small steps, verify browser validity and add a grid
   regression. AppTest alone had not exposed native HTML validity behavior.
3. Distinguish accepted-but-unavailable firmware configuration from quality
   rejection at the new export wrapper. Both block export explicitly; no gate
   or original exporter changes.
4. Correct the new summary figure's accepted-but-unavailable control label:
   report the accepted controller update rather than incorrectly claiming the
   prior was retained. A regression covers this status and warning. Saturation
   transitions are also retained when sampling plots for display.

These fixes are confined to new integration code. No M1-M18 correctness issue
required changing the engineering backend.

## Remaining limits and release boundary

- This is simulation-based validation of an averaged dq plant, not hardware.
- Known pole pairs, locked/driven commissioning conditions and zero external
  mechanical load are explicit. Unknown load can confound friction; Coulomb/
  static friction and attached-inertia changes remain outside the model.
- Torque reconstruction inherits electrical error. Sensor bias is not
  zero-mean noise; gates can accept precise but biased estimates. Good speed
  tracking does not establish parameter accuracy.
- Quality acceptance, steady feasibility, quasi-steady timing, controller
  prediction and actual validation have different meanings. The quasi-steady
  estimate is not a universal lower bound; M16's negative finding is preserved.
- M17 error models are not hardware specifications or safety guarantees. The
  nominal-bus controller does not secretly observe terminal voltage correction.
- Header generation is an accepted motor/controller configuration, not a
  certificate that every requested operating condition is feasible.
- No MCU deployment, target deadlines/WCET, peripherals, hardware validation or
  MISRA claim. Host C parity includes genuine float32 boundary differences.
- The local dashboard runs synchronously; large cases can take time. There is
  no background real-time service or packaged standalone installer.
- The repository has no declared software license; M19 does not invent one.
  A license decision and PR/CI review remain release decisions.

Version is prepared as 1.0.0 RC. **Do not tag, publish a GitHub Release or merge
as part of this milestone.** Review the open PR and CI before release decisions.
