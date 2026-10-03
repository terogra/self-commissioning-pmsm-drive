# v1.1.0 — sürüm adayı / release candidate

Henüz etiketlenmedi veya yayımlanmadı. Not tagged or released.

## Scope

Turkish-first landing page, full English equivalent, centralized bilingual
presentation and optional Windows x64 onedir distribution. Source execution
with `python -m app` remains supported. This is productization, **not M20**.

## Distribution

Expected assets after independent review and publication:

- `PMSM-Engineering-App-v1.1.0-Windows-x64.zip`
- `SHA256SUMS.txt`
- GitHub's source ZIP/tar.gz

During review use verified Actions artifacts or run from source. The portable
EXE starts Streamlit in-process, binds only to loopback and opens a browser in
normal mode. CI sets `PMSM_HEADLESS=1` and tests the built and extracted EXE.
Required runtime/static resources and committed M18 parity data are bundled.
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

No merge, v1.1 tag or release publication is performed by this change.
