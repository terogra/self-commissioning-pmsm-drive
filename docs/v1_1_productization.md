# v1.1 productization and distribution

v1.1 changes the way the existing engineering application is presented and
distributed. It does not introduce a new PMSM identification/control milestone.

## Goals

- Make Turkish the first-class default experience for the repository's primary
  audience while retaining a complete English path.
- Let a reviewer open the working application without installing Python.
- Keep source-code execution equally visible for users who do not want to trust
  an unsigned executable.
- Make the Windows binary reproducible from repository source and test it before
  publishing.
- Keep M1-M19 equations, thresholds and validation semantics unchanged.

## Localization boundary

`app/i18n.py` owns user-facing Turkish/English strings. Internal backend reason
codes, JSON field names and serialized schemas remain stable so that diagnostics
and reproducibility are not weakened by presentation localization.

The UI uses **devreye alma** for *commissioning*. Established engineering symbols
and abbreviations such as PMSM, FOC, dq, PI, firmware and DC bus/bara are kept
where translating them would reduce technical clarity.

Presentation tables accept an optional language argument and retain English as
their programmatic default for backward-compatible tests and non-UI callers.
Engineering figures accept the same optional display language; their numerical
data are unchanged.

## Windows distribution

The packaged application is a PyInstaller **onedir** portable bundle rather than
a single-file executable. This intentionally keeps the Streamlit runtime and
static assets explicit and makes startup/debugging more predictable.

`app/windows_launcher.py` embeds the pinned Streamlit runtime and serves the
same dashboard on loopback only. The packaged application is smoke-tested by
requesting its local HTTP endpoint on a clean GitHub-hosted Windows runner.

Release packaging produces:

- `PMSM-Engineering-App-vX.Y.Z-Windows-x64.zip`
- `SHA256SUMS.txt`

The executable is currently unsigned. Documentation therefore presents the
binary as an optional convenience path and keeps `python -m app` as an equal,
fully supported source-code path.

## Release automation

`.github/workflows/windows-package.yml`:

1. installs the pinned application requirements and PyInstaller,
2. runs localization/application regressions,
3. creates the Windows x64 portable build,
4. launches the packaged executable headlessly,
5. waits for an HTTP 200 response from `127.0.0.1`,
6. creates the ZIP and SHA-256 checksum,
7. uploads the build as a workflow artifact,
8. attaches the files to a matching tagged GitHub Release.

## Engineering boundary

No v1.1 change modifies:

- PMSM plant equations,
- Rs/Ld/Lq/psi_f/J/B estimators,
- measured-data quality thresholds,
- adaptive retry policy,
- controller tuning equations,
- M14/M16 definitions,
- M17 stress-model values,
- M18 C99 control equations or parity budgets.

Hardware deployment remains future work.
