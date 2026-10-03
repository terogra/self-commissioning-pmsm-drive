# v1.1.0

## Scope

Turkish-first landing page, full English equivalent, centralized bilingual
presentation in a native PySide6/Qt desktop and Windows x64 onedir distribution.
Source execution is `python -m app`, opening the same native Qt application.
Unknown motor parameters are hidden from the default input workflow: the
simulation model is in a collapsed advanced section, and editable prior values
require an explicit Custom selection. All numerical defaults remain unchanged.
The old Streamlit UI (`python -m app.legacy`) is an optional
development-only interface. This is productization, **not M20**.

## Distribution

Release assets:

- `PMSM-Commissioning-Workbench-v1.1.0-Windows-x64.zip`
- `SHA256SUMS.txt`
- GitHub's source ZIP/tar.gz

The portable EXE opens a native Qt window with no browser, HTTP server or persistent console.
CI initializes the actual built and extracted Qt executable in offscreen mode.
Qt plugins, Matplotlib resources and committed M18 parity data are bundled.
The EXE is unsigned; SHA-256 and Actions provenance are not code signing.

## Engineering preservation

No model, transform, estimator, controller, acceptance threshold, retry budget,
feasibility semantics, M17 definitions, C equations or parity tolerance changes.
Historical results/docs remain intact. Current export version provenance may
differ from historical v1.0 headers; numeric content remains exact.
Original technical README is archived verbatim as `README.v1.0.md`.

## Validation and limits

See [productization evidence](docs/v1_1_productization.md) and PR CI for exact
Python/compiler/localization/EXE smoke results. Compilation alone does not
satisfy acceptance. No MCU deployment, target timing, hardware validation,
MISRA or physical safety claim. Existing bias/identifiability/model limits remain.
