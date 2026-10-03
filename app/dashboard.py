"""Streamlit presentation of real workflow results; import has no UI side effects."""

from dataclasses import replace
from pathlib import Path
import tempfile

import streamlit as st
from app.localization import DEFAULT_LANGUAGE, LANGUAGES, display_formatter, display_rows, localize_figure, set_language, t

from app.presentation import attempt_rows, controller_rows, estimate_rows, load_committed_parity_evidence, metric_rows, parameter_rows, record_rows
from src.engineering_bundle import json_value, run_bundle_zip
from src.engineering_reporting import commissioning_figure, control_figure
from src.engineering_workflow import (
    EngineeringWorkflowConfig, MotorConfiguration, export_firmware_configuration,
    run_engineering_workflow, scenarios,
)
from src.version import __version__, RELEASE_STATUS


def _table(rows, **options):
    columns = options.pop("column_config", {})
    return st.dataframe(display_rows(rows), column_config={t(k): v for k, v in columns.items()}, **options)


def _motor_inputs(default, prefix):
    values = {}
    steps = {"Rs": .001, "Ld": 1e-7, "Lq": 1e-7, "psi_f": 1e-6, "J": 1e-7, "B": 1e-7}
    for name, unit in (("Rs", "ohm"), ("Ld", "H"), ("Lq", "H"), ("psi_f", "Wb"), ("J", "kg m²"), ("B", "N m s/rad")):
        values[name] = st.number_input(f"{name} [{unit}]", min_value=0.0, step=steps[name], value=float(getattr(default, name)),
            format="%.7f", key=prefix+name)
    return values


def configuration_form():
    default = EngineeringWorkflowConfig()
    with st.sidebar.container():
        st.subheader(t("Drive / scenario configuration"))
        scenario = st.selectbox(t("M17 simulation preset"), [s.name for s in scenarios()],
            format_func=display_formatter(), key="scenario")
        mode = st.selectbox(t("Commissioning mode"), ["one_shot", "adaptive"], format_func=display_formatter(), key="mode")
        exposure = st.selectbox(t("Impairment exposure"), ["combined", "commissioning_only", "operation_only"], format_func=display_formatter(), key="exposure")
        seed = st.number_input(t("Deterministic seed"), min_value=0, max_value=2**31-3, value=default.seed, step=1, key="seed")
        pairs = st.number_input(t("Known pole pairs [pairs]"), min_value=1, max_value=32, value=4, step=1, key="pole_pairs")
        bus = st.number_input(t("Nominal DC bus [V]"), min_value=.1, value=24., key="bus")
        speed = st.number_input(t("Speed target [rpm]"), min_value=1., value=1000., key="target")
        load = st.number_input(t("External operating load [N m]"), min_value=0., value=.05, format="%.4f", key="load")
        limit = st.number_input(t("Operating iq reference limit [A]"), min_value=.01, value=5., key="limit")
        deadline = st.number_input(t("Dynamic deadline [s]"), min_value=.01, max_value=5., value=.6, key="deadline")
        hold = st.number_input(t("Required dynamic hold [s]"), min_value=.001, step=.001, value=.1, format="%.3f", key="hold")
        with st.expander(t("Simulation evaluation / ground truth — plant configuration")):
            st.caption(t("Simulator inputs only. Estimators receive sampled records, not these constants."))
            truth = _motor_inputs(default.simulation_truth, "truth_")
        with st.expander(t("Estimator-visible prior controller assumptions")):
            prior = _motor_inputs(default.prior_assumptions, "prior_")
        with st.expander(t("Commissioning excitation / noise / validation timing")):
            st.caption(t("Simulation design constraints; no physical hardware-safety guarantee. Mechanical external load is explicitly zero."))
            current_noise = st.number_input(t("Recorded electrical current noise SD [A]"), min_value=0., value=.01, format="%.5f", key="noise_i")
            voltage_noise = st.number_input(t("Recorded voltage noise SD [V]"), min_value=0., value=.01, format="%.5f", key="noise_v")
            rotor_speed = st.number_input(t("Driven-rotor commissioning speed [rpm]"), min_value=100., max_value=1200., value=600., key="rotor_speed")
            excitation_scale = st.number_input(t("Standstill voltage-program scale [dimensionless]"), min_value=0., max_value=1.5, value=1., key="excitation")
            duration = st.number_input(t("Control-validation duration [s]"), min_value=.01, max_value=5., value=.6, key="duration")
            step_time = st.number_input(t("Operating load-step time [s]"), min_value=0., value=.3, key="step_time")
        submitted = st.button(t("Run Commissioning"), type="primary", key="run_commissioning")
    if not submitted: return None
    # Build typed settings only. All computation occurs behind the orchestration API.
    return EngineeringWorkflowConfig(simulation_truth=MotorConfiguration(**truth, pole_pairs=pairs),
        prior_assumptions=MotorConfiguration(**prior, pole_pairs=pairs), scenario=scenario, mode=mode,
        exposure=exposure, seed=seed, dc_bus_voltage_v=bus, speed_target_rpm=speed, load_torque_nm=load,
        current_limit_a=limit, deadline_s=deadline, hold_time_s=hold, simulation_duration_s=duration,
        load_step_time_s=step_time,
        standstill=replace(default.standstill, current_noise_std_a=current_noise, voltage_noise_std_v=voltage_noise,
            d_voltage_v=default.standstill.d_voltage_v*excitation_scale, q_voltage_v=default.standstill.q_voltage_v*excitation_scale),
        rotating=replace(default.rotating, current_noise_std_a=current_noise, voltage_noise_std_v=voltage_noise, speed_rpm=rotor_speed))


def show_commissioning(result):
    st.subheader(t("Sampled-data commissioning / attempt history"))
    rows = attempt_rows(result)
    if rows: _table(rows, hide_index=True, width="stretch")
    else: st.warning(t("No estimator attempt completed. See the measurement/configuration failure below."))
    for stage in ("standstill", "rotating", "mechanical"):
        st.markdown(t("#### {stage} stage", stage=t(stage)))
        attempts = [a for a in result.attempts if a.stage.value == stage]
        if not attempts: st.info(t("Stage not fitted; downstream commissioning was blocked or measurement generation failed."))
        for attempt in attempts:
            with st.expander(t("Attempt {number}: {status} — inspect measurements / diagnostics", number=attempt.number, status=t('ACCEPT' if attempt.quality.accepted else 'REJECT'))):
                if attempt.estimate is not None:
                    _table(estimate_rows(attempt), hide_index=True, width="stretch",
                        column_config={"Estimate": st.column_config.NumberColumn(format="%.8g")})
                _table([{"Check": c.name, "Measured value": c.value, "Limit": c.limit, "Passed": c.passed}
                              for c in attempt.quality.checks], hide_index=True, width="stretch")
                if attempt.quality.rejection_reasons: st.error("; ".join(attempt.quality.rejection_reasons))
                if attempt.quality.estimator_failure: st.error(attempt.quality.estimator_failure)
                if attempt.diagnostics is not None: _table(record_rows(attempt.diagnostics), hide_index=True, width="stretch")
                st.caption(t("Residual units: V s for electrical/flux stages; N m s for mechanical. Local sensitivities are not confidence probabilities."))
                st.json({"excitation": json_value(attempt.config), "next_retry_configuration": json_value(attempt.next_config)})
                record = next((r for r in result.measurement_records if r.stage == attempt.stage and r.number == attempt.number), None)
                if record is not None:
                    fig = commissioning_figure(record, attempt.estimate)
                    st.pyplot(localize_figure(fig))
                    fig.clear()
        for record in result.measurement_records:
            if record.stage.value == stage and record.measurement_failure:
                st.error(t("Measurement provider failure (attempt {number}): {error}", number=record.number, error=record.measurement_failure))


def show_operating_analysis(result):
    st.subheader(t("Operating analysis — separate from commissioning quality"))
    if not result.quality.accepted:
        st.warning(t("Unavailable: full commissioning rejected. No commissioned operation is fabricated."))
        return
    steady = result.steady_feasibility
    st.markdown(t("#### M14 steady operating feasibility"))
    if steady is None: st.warning(t("Steady analysis unavailable; see run warnings."))
    else:
        st.info(t("Existing classification: ")+t(steady.classification)+f" ({steady.classification})")
        _table(record_rows(steady, omit=("assumptions",)), hide_index=True, width="stretch")
    st.markdown(t("#### M16 dynamic operating feasibility"))
    dynamic = result.dynamic_feasibility
    if dynamic is None: st.warning(t("Dynamic analysis unavailable; see run warnings."))
    else:
        left, right = st.columns(2)
        with left:
            st.markdown(t("**Quasi-steady model estimate**"))
            st.caption(t("Full dq transients can enter the band earlier. This quantity is not a universal physical lower bound."))
            _table(record_rows(dynamic.quasi_steady, omit=("trajectory",)), hide_index=True, width="stretch")
        with right:
            st.markdown(t("**Controller-aware prediction on identified model**"))
            _table(record_rows(dynamic.controller, omit=("trace",)), hide_index=True, width="stretch")
        with st.expander(t("Dynamic request / complete analysis / assumptions")):
            st.json(json_value(dynamic))
        st.caption(t("M16 predicts a constant load from t=0. Validation below applies the separately configured load step. Nominal bus/ideal sensing are M16 assumptions; configured M17 errors affect the hidden-plant validation separately."))


def show_evaluation(result):
    st.subheader(t("Closed-loop validation — Simulation evaluation / ground truth"))
    st.caption(t("Evaluation-only information below is never used to accept commissioning or select retries."))
    _table(record_rows(result.simulation_evaluation.truth), hide_index=True, width="stretch")
    _table([{"Parameter": name, "Post-hoc absolute error [%]": value}
                  for name, value in result.simulation_evaluation.parameter_absolute_error_percent.items()], hide_index=True, width="stretch")
    for warning in result.warnings: st.warning(t(warning))
    if result.control is None:
        st.info(t("No commissioned validation trace is available."))
        return
    _table(metric_rows(result), hide_index=True, width="stretch")
    st.caption(t("Post-load metrics use existing M17/M15 definitions. iq tracking compares true currents to references mapped into the true frame. Recovery can be zero when the disturbance stays inside ±10 rpm; null means no finite recovery."))
    figure = control_figure(result)
    st.pyplot(localize_figure(figure))
    figure.clear()


def show_firmware(result):
    st.subheader(t("Firmware configuration"))
    st.caption(t("Portable firmware-ready control configuration — not deployed MCU firmware. No target timing, hardware validation or MISRA compliance is claimed."))
    if result.firmware_available:
        with st.expander(t("Exported binary32 motor / current / speed constants")):
            st.json(json_value(result.firmware_config))
        if st.button(t("Generate C header"), key="generate_header"):
            with tempfile.TemporaryDirectory(prefix="pmsm-header-") as directory:
                path = export_firmware_configuration(result, Path(directory)/"generated_motor_config.h")
                st.session_state["header"] = path.read_text(encoding="utf-8")
        if "header" in st.session_state:
            st.code(st.session_state["header"], language="c")
            st.download_button(t("Download C header"), st.session_state["header"], "generated_motor_config.h", mime="text/plain")
    else:
        st.warning(t("Firmware export unavailable: full commissioning was rejected or the export configuration failed. Prior assumptions cannot be exported as commissioned estimates."))
    show_parity()


def show_parity():
    st.markdown(t("#### COMMITTED M18 VALIDATION EVIDENCE"))
    st.caption(t("Versioned evidence for the portable core; not a new parity test of this run. No compiler or replay executes on UI interaction."))
    try:
        evidence = load_committed_parity_evidence()
        flags = evidence["saturation_agreement"]
        _table(record_rows({"Compiler": evidence["build"]["compiler"],
            "Compared input samples": evidence["compared_samples"],
            "Maximum absolute difference [V]": evidence["worst_absolute"]["max_absolute_error"],
            "Maximum relative difference [ratio]": evidence["worst_relative"]["max_relative_error"],
            "Relative-worst signal": evidence["worst_relative"]["signal"],
            "Saturation agreement": f"{flags['agreements']} / {flags['total']}",
            "Away-boundary agreement": f"{flags['nonboundary_agreements']} / {flags['nonboundary_comparisons']}",
            "Boundary disagreements": evidence["boundary_disagreements"]}), hide_index=True, width="stretch")
        st.caption(t(evidence["boundary_note"]))
        st.caption(t("Artifact SHA-256: ")+evidence["artifact_sha256"])
        with st.expander(t("Full versioned parity record / compiler flags")): st.json(evidence)
    except (OSError, ValueError, KeyError) as exc: st.error(t("Committed parity evidence unavailable: {error}", error=exc))


def _refresh_display_labels():
    # Streamlit keeps the selected wire label when format_func changes. Re-send
    # the same backend values so the frontend updates labels without resetting.
    for key in ("scenario", "mode", "exposure"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def main():
    set_language(st.session_state.get("language", DEFAULT_LANGUAGE))
    st.set_page_config(page_title=t("PMSM engineering application"), layout="wide")
    st.sidebar.selectbox("Dil / Language", list(LANGUAGES), format_func=LANGUAGES.__getitem__, key="language", on_change=_refresh_display_labels)
    st.title(t("Self-Commissioning PMSM Engineering"))
    st.caption(t("v{version} — {status}. Local simulation study; no hardware deployment.", version=__version__, status=t(RELEASE_STATUS)))
    st.sidebar.caption(t("Results change only when Run Commissioning is submitted. Current inputs and last completed run may differ."))
    try:
        configuration = configuration_form()
    except ValueError as exc:
        st.session_state.pop("result", None)
        st.session_state.pop("header", None)
        st.session_state.pop("bundle", None)
        st.error(str(exc))
        return
    if configuration is not None:
        for key in ("result", "header", "bundle"): st.session_state.pop(key, None)
        with st.spinner(t("Generating sampled data, commissioning and evaluating accepted operation…")):
            st.session_state["result"] = run_engineering_workflow(configuration)
    result = st.session_state.get("result")
    if result is None:
        st.info(t("Configure a simulation case and select Run Commissioning. Estimates and run metrics will be computed by the existing backend."))
        st.markdown(t("Measurements → Rs/Ld/Lq → psi_f → J/B → gates/supervision → retuning → M14/M16 analysis → simulation validation → M18 export"))
        show_parity()
        return
    st.subheader(t(result.status))
    if not result.quality.accepted: st.error("; ".join(result.quality.rejection_reasons))
    st.caption(t("CURRENT RUN RESULTS: seed {seed} / {scenario} / {mode} / {exposure}", seed=result.config.seed, scenario=t(result.config.scenario), mode=t(result.config.mode), exposure=t(result.config.exposure)))
    with st.expander(t("Reproducibility / estimator-visible configuration")):
        configuration = json_value(result.config)
        configuration.pop("simulation_truth")
        st.caption(t("Machine-readable identifiers and JSON keys are preserved in both languages."))
        st.json({"metadata": json_value(result.metadata), "configuration": configuration})
    tabs = st.tabs([t("Commissioning"), t("Parameters / controllers"), t("Operating analysis"), t("Simulation evaluation"), t("Nonidealities"), t("Firmware / M18")])
    with tabs[0]: show_commissioning(result)
    with tabs[1]:
        st.subheader(t("Prior → identified → active controller"))
        _table(parameter_rows(result), hide_index=True, width="stretch", column_config={
            name: st.column_config.NumberColumn(format="%.8g") for name in ("Prior assumption", "Identified / known", "Controller value")})
        _table(controller_rows(result), hide_index=True, width="stretch",
            column_config={"Value": st.column_config.NumberColumn(format="%.8g")})
        st.caption(t("Motor values and gains come from existing retuning/controller constructors. Rejection retains all prior controller parameters."))
    with tabs[2]: show_operating_analysis(result)
    with tabs[3]: show_evaluation(result)
    with tabs[4]:
        st.subheader(t("M17 simulation stress/error models"))
        st.json(json_value(result.nonidealities))
        st.caption(t("Exposure controls commissioning, operation, or both; Rs drift applies only during operation. Nominal-bus FOC command and true terminal voltage are distinct; extra actual-bus clipping is not fed back into nominal anti-windup."))
        st.markdown(t("#### Simulation evaluation / ground truth"))
        if result.control is not None:
            st.json({"nominal_bus_voltage_v": result.control.trace["dc_bus_voltage"],
                "actual_bus_voltage_v": result.control.trace["actual_dc_bus_voltage"],
                "terminal_command_discrepancy_rmse_v": result.control.metrics.get("terminal_command_discrepancy_rmse_v")})
            st.caption(t("Measured/true current and commanded/terminal voltage curves are in the Simulation evaluation tab."))
    with tabs[5]: show_firmware(result)
    if st.button(t("Prepare run bundle"), key="prepare_bundle"):
        with st.spinner(t("Writing current-run JSON/CSV/plot/configuration bundle…")):
            st.session_state["bundle"] = run_bundle_zip(result)
    if "bundle" in st.session_state:
        st.download_button(t("Download run bundle"), st.session_state["bundle"], f"pmsm_{result.config.scenario}_{result.config.seed}.zip", mime="application/zip")


if __name__ == "__main__": main()
