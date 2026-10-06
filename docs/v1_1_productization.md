# v1.1 native desktop productization

## Baseline and scope

Existing PR #17. The native migration starts
at `ff20c89238d4b620db8198aadaeedcd76b5ebcae`; baseline **283 passed in 197.59 s**
on local Python 3.12.5 including native GCC checks. Version 1.1.0 is the released productization baseline. This adds no
engineering milestone or algorithm.

The initial browser-hosted EXE did not meet the intended desktop requirement.
Its HTTP readiness evidence was valid for that earlier implementation, but
does not validate the current product. The normal product is now Qt, with no
browser, HTTP server, Streamlit or persistent console. The former launcher is
retired; the legacy web interface is optional development-only code.

## Basic configuration follow-up

After the accepted native migration at
`ed2eb2ceca32136ad699bbbc799002ee13634f4d`, the default view now presents
known/requested inputs and a read-only list of the six parameters to estimate.
The plant's editable validation truth and excitation/noise/timing controls
live in **Advanced Simulation Settings**, collapsed by default. Prior motor
fields appear only after selecting **Initial model: Custom**. Default uses
the exact existing prior values, even if retained hidden custom edits are invalid.
Language changes preserve selection, expansion, edits and completed results.

`python -m app` now calls the same native Qt entry as the EXE; `desktop` is an
internal compatible alias. The optional web UI has the explicit development
command `python -m app.legacy`. No engineering API, numerical default or
historical result changes. Tests compare both default accepted and timing-case
rejected Qt runs directly against backend summaries, excluding metadata only.
The README screenshot is regenerated from the real updated Qt application.

Local follow-up validation: **303 passed in 218.79 s**, including 18 native Qt
tests. Both `app` and the internal `desktop` alias initialize native windows
without web imports from an unrelated cwd. The rebuilt EXE initialized in
**1.438 s** and its ZIP extracted into a path with spaces in **1.578 s**;
both exited zero. These packaged probes required normal AppData log access
outside the development workspace sandbox. No runtime/logging change was made.
CI results and the new archive checksum are recorded on the PR.

See [desktop architecture](desktop_architecture.md) for module ownership,
threading, result semantics, localization, plots and resource paths.

## Distribution

```powershell
python -m pip install -r packaging/requirements-windows.txt
$env:PYTHONNOUSERSITE='1'
$env:PYTHONUSERBASE=Join-Path (Get-Location) 'build/isolated-user-site'
python -m PyInstaller --noconfirm --distpath dist --workpath build packaging/windows.spec
python packaging/smoke_test.py --exe dist/PMSM-Commissioning-Workbench/PMSM-Commissioning-Workbench.exe --output package-diagnostics/build
python packaging/archive.py --directory dist/PMSM-Commissioning-Workbench --output portable-artifacts --version 1.1.0 --smoke-result package-diagnostics/build/smoke_result.json
```

The ZIP is `PMSM-Commissioning-Workbench-v1.1.0-Windows-x64.zip`; executable is
`PMSM-Commissioning-Workbench.exe`. Normal double-click starts the native window
and event loop. `--smoke-report` is a diagnostic CI seam, not the normal flow.
`--capture-demo` runs the actual default workflow and captures the shown window;
the figure/table values are newly computed by the backend.

CI runs native Qt/localization/workflow and preservation tests with no Streamlit
installed, builds the real EXE, checks native initialization and clean exit,
then creates ZIP/checksum and verifies its extracted executable. The Windows
GUI subsystem is checked explicitly. Diagnostics upload even on failure.
Full Python 3.11/3.12 jobs also retain optional legacy UI tests. GCC/Clang parity
and deterministic accepted/rejected demo reproduction retain original budgets.
Head-specific counts, timing, artifact links and SHA-256 are recorded in PR #17.

Local native validation: **297 passed in 210.75 s** on Python 3.12.5;
the 14 Qt tests exercise real threaded accepted/rejected runs, localization,
tables, plots, save-dialog boundaries and error recovery. The final frozen
EXE initialized in **1.828 s**, and the extracted ZIP in a path with spaces
initialized in **1.719 s**. Both exited zero, reported a visible Qt window,
Windows GUI subsystem 2, and no imported web runtime. Timings are observations,
not a startup deadline guarantee.

The screenshot at `docs/images/v1_1_dashboard_tr.png` is a `QWidget.grab()`
capture from the visible frozen application after a newly computed default
commissioning run. That normal Windows process remained responsive and had
no TCP connections. The external Windows capture helper returned black frames
and could not activate the window, so it was not used to claim a completed
mouse-driven acceptance walkthrough. Native widget interactions are covered
by Qt tests; broader manual display/DPI testing remains a limitation.

## Integration problems and resolutions

The first frozen Qt build failed importing QtCore even though source Qt worked.
Analysis found an unrelated Poppler `icuuc.dll` on the build PATH. It exports
versioned ICU names, while Qt imports Windows' unversioned ICU API. The spec
leaves this OS component to Windows rather than shipping the ambient DLL.
Unused pandas/pyarrow dependencies are excluded. The actual executable is
retested after this fix; increasing a timeout does not resolve a DLL mismatch.

The initial failed frozen run opened a bootloader error dialog and timed out;
those diagnostics remain local evidence. Smoke error printing now uses UTF-8
so Turkish bootloader text cannot hide the original failure behind a console
encoding exception. Startup smoke failures return nonzero without an app
error dialog; normal end-user startup errors remain visible and logged.

An initial source startup probe could not create its normal AppData log path
under workspace sandbox restrictions. Logging falls back to the temporary
directory when the normal directory cannot be created. Native startup no
longer depends on a console being available.

The first Linux GUI CI run failed at test collection because the runner lacked
`libEGL.so.1`. Offscreen Qt still needs its linked system libraries. Linux GUI
jobs now install `libegl1` and `libopengl0`; no tests are skipped to address
that environment failure. GCC/Clang checks passed on that initial head.

Windows CI subsequently passed the native tests, built and validated both
executables, but its final diagnostics upload failed because AppData was on
drive C while the workspace was on drive D. The workflow now copies the
application log into workspace diagnostics before upload. Native runtime
success is retained separately from artifact-upload success.

## Preservation and limits

The unchanged 74-file contract protects prior engineering code, protocols and
numerical evidence. The original technical README and journal remain intact.
No thresholds, estimator/gate/retry semantics, tuning, M14/M16 semantics, M17
scenarios, C equations, parity tolerances or historical datasets are revised.
New export headers use the existing version/provenance path.

The EXE is unsigned; SmartScreen may warn. SHA-256 is integrity evidence, not
code signing or a safety guarantee. Runtime dependencies retain their licenses.
Offscreen CI validates executable initialization, not every Windows display,
GPU or scaling configuration. The visible app is reviewed separately. Runs
cannot be cancelled mid-computation; close is deferred until completion.
No MCU deployment, target timing, hardware validation or MISRA claim is made.
Quality acceptance can coexist with biased estimates. Full dq transients may
enter the band earlier than M16's quasi-steady estimate.

PR #17 was merged before release finalization; v1.1.0 publication uses the validated native package workflow.
