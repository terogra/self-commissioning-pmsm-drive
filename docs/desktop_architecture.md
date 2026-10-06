# Desktop architecture — v1.1.0

`python -m app` and `PMSM-Commissioning-Workbench.exe` launch the same PySide6/Qt
application. The window delegates commissioning and analysis to the Python
backend. The [v1.0 architecture](architecture.md) describes the earlier Streamlit
interface, available through `python -m app.legacy`.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `desktop.configuration` | Input forms, backend defaults and advanced simulation settings |
| `desktop.services` | Build configuration and call computation/export APIs |
| `desktop.worker` | Run commissioning on a QThread and return results through signals |
| `desktop.main_window` | Display results, manage busy state and handle save dialogs |
| `desktop.tables` | Keep raw values separate from display precision |
| `desktop.plots` | Embed Matplotlib figures through FigureCanvasQTAgg |
| `app.localization`, `app.presentation` | Shared translations and result tables |
| `desktop.runtime` | Locate resources and diagnostic logs |

## Configuration and results

The default prior comes from `EngineeringWorkflowConfig().prior_assumptions`.
Selecting **Custom** reveals editable prior values. Switching back to **Default**
retains those edits in the form but ignores them for computation, including
invalid hidden edits. Simulation truth and excitation settings sit in the
collapsed advanced group; estimators receive sampled records.

A completed `EngineeringWorkflowResult` supplies every result tab. Changing
language rebuilds labels and views while retaining inputs, result identity,
scenario selection and export availability. Qt `UserRole` stores raw table
values; rounding affects display only. Diagnostic codes and JSON keys stay stable.

Rejection retains the prior controller and leaves partial fits available for
inspection. The firmware button follows `firmware_available`; the exporter also
checks acceptance before writing a header.

## Threading and errors

One QApplication owns one MainWindow. Commissioning runs on a worker thread;
widget and figure creation stays on the GUI thread. During computation, inputs
and export controls are disabled, overlapping runs are blocked, and closing is
deferred until the worker finishes. Mid-run cancellation is not implemented.

Failures restore the controls and write diagnostics to
`%LOCALAPPDATA%/PMSMCommissioningWorkbench/logs/desktop.log`. A temporary directory
is used when the normal log directory is unavailable. Error dialogs give a short
message; the log contains the traceback.

## Packaging and validation

The PyInstaller onedir build uses `console=False` and Windows GUI subsystem 2.
It packages Qt plugins, Matplotlib assets and the recorded M18 parity summary.
Resource paths derive from `__file__`, so startup is independent of the working
directory. Desktop dependencies are in `requirements.txt`; pinned Windows build
inputs are in `packaging/requirements-windows.txt`. Streamlit is optional through
`requirements-legacy.txt`.

Tests cover accepted/rejected threaded runs, language switching, raw table and
plot values, header output, export blocking and error recovery. The packaged EXE
is launched from an unrelated working directory with `QT_QPA_PLATFORM=offscreen`.
The runtime probe checks window initialization, clean exit, GUI subsystem and
excluded web imports. The ZIP is extracted to a path with spaces and tested again.

Offscreen tests do not cover every display, GPU or DPI setup. The README image
was captured from the visible packaged Qt window after a commissioning run.
Engineering results are simulation results; hardware validation and target timing
remain future work.
