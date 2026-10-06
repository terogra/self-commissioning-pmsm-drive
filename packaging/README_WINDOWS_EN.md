# PMSM Drive Commissioning Workbench — Windows

1. Extract the **entire ZIP**. Do not run the EXE inside the ZIP.
2. Double-click `PMSM-Commissioning-Workbench.exe`. Retain the `_internal` folder.
3. The desktop window opens. The package includes its runtime dependencies;
   Python installation is not required.
4. Turkish is the default; choose English using **Dil / Language**.
5. Configure inputs and select **Run Commissioning**. Overlapping runs are
   blocked. Wait for the active computation to finish, then close the window.

Full acceptance enables **Export C header**, using a native save dialog.
Rejection disables export and retains the prior controller. Failed estimates
and exact reason codes remain visible. Use **Save run bundle** for JSON, CSV and figures.

Startup/runtime diagnostics are in
`%LOCALAPPDATA%/PMSMCommissioningWorkbench/logs/desktop.log`, with a temporary
directory fallback. Moving the EXE requires moving its `_internal` directory
and contents as well.

**Unsigned EXE: SmartScreen may warn.** SHA-256 checks integrity, not signing or
safety. The source path is `python -m app`, opening the same native GUI. Compare the ZIP using
`Get-FileHash -Algorithm SHA256` against `SHA256SUMS.txt`.

This remains a simulation study, not a hardware drive or deployed MCU firmware.
Good speed tracking does not prove accurate commissioning. Quasi-steady timing
is not a universal physical lower bound. Source is MIT licensed; dependencies
retain their licenses. `BUILD_INFO.json` records version/build provenance.
v1.1.0 is the released version.
