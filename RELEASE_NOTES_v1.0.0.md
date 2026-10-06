# v1.0.0 release notes

Released under the MIT License.

## Scope

The application connects the existing engineering system from simulated
measurements to electrical/mechanical estimates, measured-data acceptance,
bounded retries, controller retuning, operating analysis,
simulation stress evaluation and portable C configuration. M19 adds integration
and presentation, not another control or identification algorithm.

## Run

```sh
python -m pip install -r requirements-legacy.txt
python -m app.legacy
```

On the current source tree, the v1.0 Streamlit interface runs through the legacy
launcher above. Python 3.11/3.12 is supported. Use `python -m experiments.v1_demo`
for a browser-free accepted nominal case and an explicit adaptive timing-error
rejection. The application itself does not require a C compiler; compiler-backed
validation uses GCC/Clang through the existing M18 tools and CI.

## Validation summary

- 265 local pytest tests passing, including 33 new integration/application tests.
- GCC 16.2.0: 43 strict C99 assertions, 31,484 Python/C comparison samples;
  unchanged numerical budgets and retained 16 boundary flag discrepancies.
- Nominal full acceptance: post-load speed RMSE 1.60723731 rpm, iq RMSE
  0.00302036 A, maximum speed deviation 5.21029368 rpm, zero saturation.
- Timing-delay adaptive case: `standstill.excessive_residual`, terminal
  rejection, retained prior controller and blocked firmware export.
- Local browser accepted/rejected paths inspected; CI covers headless
  Streamlit/backend/demo plus Python 3.11/3.12 and GCC/Clang.

See [validation details](docs/v1_validation.md) for exact numbers, reproducibility,
the unchanged M16 reverse-excursion diagnostic and evidence limitations. GitHub
Actions verifies Python 3.11/3.12, GCC, Clang and the headless application/demo;
the compiler-specific checks run in CI.

## Scope and limits

Portable firmware-ready configuration is not deployed MCU firmware. No target
timing, peripherals, hardware validation, physical safety guarantee or MISRA
compliance is claimed. Gates can accept biased measurements, operation can be
infeasible despite accepted identification, and quasi-steady timing is not a
universal physical bound. Historical failed/biased cases remain available.

The UI is synchronous and local. This is a simulation research/engineering tool,
not a real-time high-power control interface. Source code is distributed under
the MIT License; see `LICENSE`. The license permits use, copying, modification
and redistribution subject to its notice and disclaimer.
