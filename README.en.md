[Türkçe](README.md) | [**English**](README.en.md)

# Self-Commissioning PMSM Drive

## PMSM drive commissioning and parameter identification

How does a PMSM controller behave when its motor parameters are wrong? This
project investigates that question by estimating parameters from simulated
measurements and retuning the current and speed PI controllers.

The PySide6/Qt desktop application runs experiments, shows fits and rejection
reasons, and evaluates the closed-loop response. Accepted commissioning can
export a configuration header for the portable C99 control core.

![PMSM commissioning results — Turkish interface](docs/images/v1_1_dashboard_tr.png)

## Quick start

### Windows

1. Download `PMSM-Commissioning-Workbench-v1.1.0-Windows-x64.zip` and `SHA256SUMS.txt`
   from the [v1.1.0 release](https://github.com/terogra/self-commissioning-pmsm-drive/releases/tag/v1.1.0).
2. Extract the entire ZIP. Keep the `_internal` directory beside the EXE.
3. Open `PMSM-Commissioning-Workbench.exe`.

Python installation is not required. The EXE is unsigned, so Windows SmartScreen
may show a warning. SHA-256 verifies file integrity; it does not replace code signing.
See the [Windows usage and troubleshooting notes](packaging/README_WINDOWS_EN.md).

### Source code

With Python 3.11 or 3.12, in Windows PowerShell:

```powershell
git clone https://github.com/terogra/self-commissioning-pmsm-drive.git
cd self-commissioning-pmsm-drive
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app
```

If activation is blocked, use `.\.venv\Scripts\python.exe` directly with
`-m pip install -r requirements.txt` and `-m app`.
On Linux/macOS, activate the environment with `source .venv/bin/activate`.

## First experiment

Select **Run Commissioning** with the default settings. You do not need to enter
the six unknown motor parameters: the application estimates them from sampled
records. Choose English from **Dil / Language**.

| Stage | Estimated parameters | Method |
| --- | --- | --- |
| Locked rotor | `Rs`, `Ld`, `Lq` | Two-axis voltage excitation and integrated regression |
| Driven rotor | `psi_f` | Flux estimation from voltage, current and speed records |
| Free rotor | `J`, `B` | Mechanical estimation using reconstructed torque and speed changes |

Accepted measurements allow controller retuning. Rejection retains the prior
controller and blocks firmware export; partial fits and rejection reasons remain
visible. Adaptive commissioning requests a limited number of new measurements
for specific quality failures.

**Advanced Simulation Settings** controls the simulated motor, excitation and
measurement noise. True motor values are used to evaluate accuracy and are not
passed to the estimators. **Initial model: Custom** exposes the controller's
prior assumptions.

The result tabs show parameters, gains, operating-point analysis, closed-loop
plots and error scenarios. **Save run bundle** exports JSON, CSV and figures;
full acceptance enables **Export C header**. Wait for a running computation to
finish before closing the application.

## Experiments and validation

```sh
python -m experiments.v1_demo --output demo-current
python -m pytest -q
```

The demo computes a nominal accepted case and a rejected measurement-delay case.
Other experiments examine parameter mismatch, voltage saturation, measurement
noise, sensor errors, bus sag and resistance drift. Failed runs and biased
estimates remain in the result records.

The v1.0 validation record contains **265 Python tests**, **43 C assertions** and
**31,484 Python/C comparison samples**. It also reports **16 saturation-boundary
differences** from single-precision arithmetic. Current CI checks Python 3.11/3.12,
GCC/Clang, the Qt interface and the packaged Windows application.

## Assumptions and limits

This is a simulation study. Pole pairs are known, and mechanical identification
assumes known zero external load. Unknown load, Coulomb/static friction, changing
inertia and systematic sensor errors limit estimation accuracy. Good speed
tracking alone does not establish correct motor parameters. Accepted commissioning
does not guarantee that the requested speed and load fit the available current
and voltage limits.

The M16 quasi-steady timing estimate is **not a physical minimum or universal lower bound**;
the **full dq transient simulation** can enter the speed band earlier.

The C99 core is validated on a host computer. MCU execution, peripheral drivers,
target timing, physical motor tests and MISRA compliance remain outside the
current scope.

## Technical documentation

- [Model, equations and experiment commands](README.v1.0.md)
- [Engineering journal](docs/engineering_log.md)
- [v1.0 validation results](docs/v1_validation.md)
- [Desktop architecture](docs/desktop_architecture.md) and [Windows build notes](docs/v1_1_productization.md)
- [UI terminology](docs/terminology.md), [changelog](CHANGELOG.md) and [release notes](RELEASE_NOTES_v1.1.0.md)

For the legacy Streamlit interface, install `requirements-legacy.txt` and run
`python -m app.legacy`.

Source code is [MIT licensed](LICENSE); dependencies retain their own licenses.
