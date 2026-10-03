# v1.1 productization / localization / Windows distribution

## Baseline and scope

Clean branch `codex/v1.1.0-productization` from exact stable main
`d3ae7f3ef62a814b5bc7a93ea737c73af1b819da`. PR #16 and its feature branch were
not used as implementation sources. Baseline: **265 passed in 189.66 s** locally
on Python 3.12.5. This is not M20 and adds no engineering algorithm.

## Localization

`app.localization` uses English source messages as gettext-style catalogue keys,
a Turkish catalogue, English enum display labels, and a thread-local ContextVar.
Turkish is the UI default. The sidebar selector uses stable language codes;
all existing widget keys and backend scenario/mode values remain unchanged.
Language reruns only presentation, preserving the typed result and header.
Inputs are ordinary stable-key widgets rather than a batched form, so edits
persist before commissioning is submitted. Only the explicit action invokes
computation. The language callback re-sends the same dropdown codes to refresh
selected frontend labels; it never touches engineering results.
Widget formatters capture the rendered language explicitly, including when
serialization happens outside the Streamlit script thread.
No language argument reaches a plant, estimator, gate, supervisor or controller.

Tables are translated copies, never mutated backend dictionaries. Plot
localization changes only text artists after existing figure functions run;
signals and numeric artists are unchanged. Unknown reason codes are preserved
verbatim. JSON, configuration fields, schemas, exported C constants and debug
reason strings remain machine-readable. Internal identifiers may therefore
appear alongside localized explanatory text.

## Portable launcher

`app.portable` calls the pinned Streamlit bootstrap **in-process**. A frozen
`sys.executable` is the application EXE, not a general Python interpreter; it
must not be invoked with `-m streamlit`. The source `python -m app` entry point
retains its supported Python subprocess path.

`app.runtime` resolves dashboard data from package `__file__`, matching source
and PyInstaller onedir layouts, independent of cwd or spaces. The spec bundles
the actual dashboard source, dynamically executed app/src/experiment modules,
Streamlit static/runtime assets, recursive dependency metadata, Matplotlib Agg
resources and committed M18 parity JSON. It does not bundle commissioning in C.

Normal mode opens the browser and has a console for Ctrl+C/error output. The
server binds exclusively to `127.0.0.1`; default port 8501, configured port via
`PMSM_PORT`. `PMSM_HEADLESS=1` disables browser launch. No network shutdown
endpoint is introduced. Closing the browser alone does not stop the server.
The CI test terminates its hidden standalone process and waits; no recursive
Python child is spawned.

Startup imports the real dashboard and validates packaged parity data before
serving, so readiness cannot conceal missing backend imports/resources.
Exceptions go to stderr and `%LOCALAPPDATA%/PMSMEngineering/logs/startup.log`.

## Build and verification

Pinned Python 3.12 Windows dependencies in `packaging/requirements-windows.txt`,
including PyInstaller **6.22.3** and hooks **2026.8**. Versions/source are fixed
inputs; ZIP timestamps and runtime provenance do not imply bit-identical builds.
`PYTHONNOUSERSITE=1` disables ambient user-site imports. `PYTHONUSERBASE` is set
to an isolated build directory because PyInstaller still enumerates the user-site
path when finding DLL parent directories, even with imports disabled.

```powershell
python -m pip install -r packaging/requirements-windows.txt
$env:PYTHONNOUSERSITE='1'
$env:PYTHONUSERBASE=Join-Path (Get-Location) 'build/isolated-user-site'
python -m PyInstaller --noconfirm --distpath dist --workpath build packaging/windows.spec
python packaging/smoke_test.py --exe "dist/PMSM Engineering App/PMSM Engineering App.exe" --output package-diagnostics/build
python packaging/archive.py --directory "dist/PMSM Engineering App" --output portable-artifacts --version 1.1.0 --smoke-result package-diagnostics/build/smoke_result.json
```

Windows CI runs localization/real app tests, builds onedir, starts the **actual
EXE**, requires health and application HTTP 200, terminates it, creates ZIP and
checksum, extracts into a directory with spaces and retests that EXE. Smoke cwd
is a separate temporary directory and Python path/home overrides are removed.
Failures print exit code, stdout, stderr and port diagnostics; logs upload even
on failure. Successful ZIP/checksum upload requires the runtime gate.
Timeout increases do not substitute for diagnosing an error.

Tag/source version must match. Files attach only to an **existing** matching
GitHub Release; tag push without a release retains workflow artifacts. Publishing
that release triggers verification/upload. This PR creates no tag/release, and
the workflow does not implicitly create a Release.

## Historical provenance boundary

Committed `results/` and existing engineering docs are not regenerated.
The original landing page is preserved verbatim in `README.v1.0.md`. Demo
reproduction continues to compare every computed field and header constant;
it permits exactly `project 1.0.0;` → current-version provenance substitution
in the header comment. New headers are also checked against the unchanged M18
exporter using current version. No numeric tolerance is loosened.

## Issues encountered

Actual packaged browser inspection found that Streamlit retained selected
Turkish dropdown wire labels after switching to English even though menu options
changed. Re-sending the unchanged backend values on the language callback updates
those labels. Ordinary input widgets also preserve pending edits across language
reruns; headless regression checks cover both retained results and pending edits.


The first local PyInstaller build failed inspecting an inaccessible unrelated
user-site directory under AppData/Roaming. The cause was build environment
discovery, not EXE startup or an engineering algorithm. Inspection showed that
PyInstaller unconditionally calls `site.getusersitepackages()` during DLL layout
discovery, so `PYTHONNOUSERSITE=1` alone did not fix it. An isolated
`PYTHONUSERBASE`, together with disabled user-site imports, resolves the path
dependency without patching the installed tool or changing engineering code.
Runtime failures/results are recorded after actual executable verification,
rather than inferred from build success.

The first EXE runtime test found a genuine launcher error: `bootstrap.run`
does not apply initial flag options. Unlike the CLI, our initial direct launcher
had omitted `bootstrap.load_config_options`, so default development/port/bind
settings were used. Load options before startup and verify every effective
setting, including loopback, port and headless mode. Regression coverage tests
that ambient `0.0.0.0` configuration cannot override the explicit loopback flag.
No timeout was increased. The failed EXE was terminated.

Windows temporary-cwd cleanup initially masked that readiness failure because
the process still held the directory. Kill/wait before directory removal and
preserve the original failure alongside any cleanup diagnostic. Startup logs
and exit status are always printed on smoke failure.

## Validation record

Local Python 3.12.5 full suite: **281 passed in 218.61 s**, including native
GCC C99/parity tests. Baseline was 265 tests; 16 focused localization/package
checks were added. Localization plus existing real headless app checks passed
(16 tests); portable launcher/package checks passed (8 tests).

The corrected onedir EXE returned HTTP 200 at `127.0.0.1:18511` in **4.406 s**.
The ZIP-extracted EXE returned HTTP 200 at `127.0.0.1:18512` in **2.765 s** from
a directory containing spaces, with an unrelated temporary cwd. Both ran with
browser launch disabled and were terminated after readiness. These are local
runtime observations; independent Windows CI evidence is recorded with the PR.
Python 3.11, Clang and the independently built CI ZIP are verified in Actions.

Smoke JSON
contains actual port, elapsed time, HTTP outcome and post-cleanup exit code.
The checksum is specific to that ZIP artifact, not a universal constant.

## Trust and remaining limits

The EXE is an optional unsigned convenience artifact. SmartScreen may warn.
SHA-256 checks integrity only; Actions provenance is not code signing. Source
execution is equally supported. Source is MIT licensed; runtime dependencies
retain their own licenses.

This remains simulation-based engineering. Quasi-steady timing is not a
universal physical lower bound; full dq transients can enter earlier. Quality
acceptance does not guarantee accuracy or operating feasibility. No hardware
deployment/timing validation, MISRA or safety claims are added. The dashboard
remains synchronous/local.

## Product-quality review on PR #17

The Turkish title is **PMSM Sürücü Devreye Alma Aracı**; the English title is
**PMSM Drive Commissioning Workbench**. [UI terminology](terminology.md) fixes
the vocabulary for identification, operating points, residuals, excitation,
bias/offset, quasi-steady models and controller-aware prediction. Existing
message identifiers remain catalogue keys; their displayed text is revised in
both languages. Unknown diagnostic codes are still shown exactly.

The sidebar groups motor parameters, commissioning setup, operating request,
validation timing and simulation errors. The result summary reads the existing
quality decision, scenario, speed/bus request, available estimates, M14/M16
results and firmware availability. It does not calculate a new quality or
feasibility decision. Rejected estimates are labelled as estimates with the
prior controller retained; firmware export remains blocked.

Headings are smaller and the run button uses Streamlit's neutral styling.
CSS styles our title/summary markup and reduces main-container top padding using
one stable Streamlit test ID. It does not target generated class names or
change widget behavior. Reason codes use monospace text. Numeric values and
SI units are unchanged.

The README screenshot is an actual default one-shot run: seed 1901, ideal
scenario, 1000 rpm, 24 V. To reproduce the view, run `python -m app`, leave the
defaults, select **Devreye Almayı Başlat**, and open **Parametreler ve kontrol**.
The screenshot is captured from the browser; it is not generated artwork.
Both landing pages embed it.

Focused tests protect canonical terms/titles, retained language-switch state,
unknown codes, and the accepted/rejected overview against the original result.
The full Python/compiler/headless/Windows runtime gates are rerun on this PR;
current head-specific results are recorded in the PR description. Packaging
sources, workflow, launch flags, runtime architecture and engineering backend
are unchanged by this review.
