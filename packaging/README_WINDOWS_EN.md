# PMSM Engineering App — Windows quickstart

1. Extract the **entire ZIP** into a folder. Do not run the EXE inside the ZIP.
2. Double-click `PMSM Engineering App.exe`. Keep the `_internal` folder intact.
3. The local application opens in your browser. No Python, pip or Git is required.
4. Turkish is the default; select English in the sidebar.
5. Stop the server with Ctrl+C in its console. Closing only the browser tab
   leaves the server running. Closing the console also ends the process.

The server binds only to `127.0.0.1:8501`. Startup errors appear in the console
and `%LOCALAPPDATA%\PMSMEngineering\logs\startup.log`. If the port is occupied,
set `$env:PMSM_PORT='8502'` in PowerShell before starting the EXE.
`PMSM_HEADLESS=1` disables automatic browser opening for CI.

**Unsigned executable:** There is no code signature; Windows SmartScreen may
warn. SHA-256 checks integrity, not signing or safety. Users who prefer not to
run an unsigned binary can use the equally supported Python source path.
Compare the ZIP using `Get-FileHash -Algorithm SHA256` and the accompanying
`SHA256SUMS.txt`.

This is a simulation/engineering application, not a hardware motor drive or
deployed MCU firmware. Rejections stay visible. Good tracking alone does not
prove accurate parameter estimates. Quasi-steady timing is not a universal
physical lower bound.

Source code is MIT licensed; LICENSE is included. Dependencies retain their own
licenses. BUILD_INFO.json records version and build-source metadata.
