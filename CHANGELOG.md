# Changelog

## 1.0.0 — 2026-10-03

### Added in Milestone 19

- One-command local Streamlit engineering application: `python -m app`.
- Typed headless orchestration of real sampled commissioning, quality gates,
  bounded adaptive supervision, retuning, M14/M16 analysis, M17 simulation and
  M18 configuration export.
- Per-stage fit/diagnostic inspection, retained failed attempts and partial fits,
  explicit truth/evaluation boundary and export blocking on rejection.
- Current-run JSON/CSV/PNG/header bundles and deterministic accepted/rejected
  demonstration: `python -m experiments.v1_demo`.
- Version source, architecture/validation/release documentation and
  headless application/demo CI alongside existing Python and C checks.
- 33 application/backend tests; complete local suite now has 265 passing tests.
- MIT License for source-code use, modification and redistribution.

### Preserved

M1-M18 algorithms, estimator/gate thresholds, adaptive logic, M14/M16 semantics,
M17 scenario/evaluation evidence and M18 C/parity equations/budgets. The earlier
M16 observation that dq transients can beat the quasi-steady estimate remains
explicit. No MCU deployment, hardware-validation claim, or change to historical engineering evidence.

### Corrected during integration

Resolved seed/bus provenance, browser numeric-input default validity, and
distinct accepted-but-unavailable export/plot reporting. These corrections affect
new integration paths only; existing engineering numerical results are unchanged.

## Earlier engineering milestones

See [the chronological engineering journal](docs/engineering_log.md) and
historical experiment evidence for M1-M18. Their history is not reconstructed
as fabricated package releases.
