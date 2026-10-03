"""Streamlit presentation of real workflow results; import has no UI side effects."""

from dataclasses import replace
from pathlib import Path
import tempfile

import streamlit as st

from app.presentation import attempt_rows, controller_rows, estimate_rows, load_committed_parity_evidence, metric_rows, parameter_rows, record_rows
from src.engineering_bundle import json_value, run_bundle_zip
from src.engineering_reporting import commissioning_figure, control_figure
from src.engineering_workflow import (
    EngineeringWorkflowConfig, MotorConfiguration, export_firmware_configuration,
    run_engineering_workflow, scenarios,
)
from src.version import __version__, RELEASE_STATUS


def _motor_inputs(default, prefix):
    values = {}
    steps = {"Rs": .001, "Ld": 1e-7, "Lq": 1e-7, "psi_f": 1e-6, "J": 1e-7, "B": 1e-7}
    for name, unit in (("Rs", "ohm"), ("Ld", "H"), ("Lq", "H"), ("psi_f", "Wb"), ("J", "kg m²"), ("B", "N m s/rad")):
        values[name] = st.number_input(f"{name} [{unit}]", min_value=0.0, step=steps[name], value=float(getattr(default, name)),
            format="%.7f", key=prefix+name)
    return values


def configuration_form():
    default = EngineeringWorkflowConfig()
    with st.sidebar.form("drive_configuration"):
        st.subheader("Drive / scenario configuration")
        scenario = st.selectbox("M17 simulation preset", [s.name for s in scenarios()],
            format_func=lambda value: "Nominal (ideal)" if value == "ideal" else value.replace("_", " "), key="scenario")
        mode = st.selectbox("Commissioning mode", ["one_shot", "adaptive"], key="mode")
        exposure = st.selectbox("Impairment exposure", ["combined", "commissioning_only", "operation_only"], key="exposure")
        seed = st.number_input("Deterministic seed", min_value=0, max_value=2**31-3, value=default.seed, step=1, key="seed")
        pairs = st.number_input("Known pole pairs [pairs]", min_value=1, max_value=32, value=4, step=1, key="pole_pairs")
        bus = st.number_input("Nominal DC bus [V]", min_value=.1, value=24., key="bus")
        speed = st.number_input("Speed target [rpm]", min_value=1., value=1000., key="target")
        load = st.number_input("External operating load [N m]", min_value=0., value=.05, format="%.4f", key="load")
        limit = st.number_input("Operating iq reference limit [A]", min_value=.01, value=5., key="limit")
        deadline = st.number_input("Dynamic deadline [s]", min_value=.01, max_value=5., value=.6, key="deadline")
        hold = st.number_input("Required dynamic hold [s]", min_value=.001, step=.001, value=.1, format="%.3f", key="hold")
        with st.expander("Simulation evaluation / ground truth — plant configuration"):
            st.caption("Simulator inputs only. Estimators receive sampled records, not these constants.")
            truth = _motor_inputs(default.simulation_truth, "truth_")
        with st.expander("Estimator-visible prior controller assumptions"):
            prior = _motor_inputs(default.prior_assumptions, "prior_")
        with st.expander("Commissioning excitation / noise / validation timing"):
            st.caption("Simulation design constraints; no physical hardware-safety guarantee. Mechanical external load is explicitly zero.")
            current_noise = st.number_input("Recorded electrical current noise SD [A]", min_value=0., value=.01, format="%.5f", key="noise_i")
            voltage_noise = st.number_input("Recorded voltage noise SD [V]", min_value=0., value=.01, format="%.5f", key="noise_v")
            rotor_speed = st.number_input("Driven-rotor commissioning speed [rpm]", min_value=100., max_value=1200., value=600., key="rotor_speed")
            excitation_scale = st.number_input("Standstill voltage-program scale [dimensionless]", min_value=0., max_value=1.5, value=1., key="excitation")
            duration = st.number_input("Control-validation duration [s]", min_value=.01, max_value=5., value=.6, key="duration")
            step_time = st.number_input("Operating load-step time [s]", min_value=0., value=.3, key="step_time")
        submitted = st.form_submit_button("Run Commissioning", type="primary", key="run_commissioning")
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
    st.subheader("Sampled-data commissioning / attempt history")
    rows = attempt_rows(result)
    if rows: st.dataframe(rows, hide_index=True, width="stretch")
    else: st.warning("No estimator attempt completed. See the measurement/configuration failure below.")
    for stage in ("standstill", "rotating", "mechanical"):
        st.markdown(f"#### {stage.title()} stage")
        attempts = [a for a in result.attempts if a.stage.value == stage]
        if not attempts: st.info("Stage not fitted; downstream commissioning was blocked or measurement generation failed.")
        for attempt in attempts:
            with st.expander(f"Attempt {attempt.number}: {'ACCEPT' if attempt.quality.accepted else 'REJECT'} — inspect measurements / diagnostics"):
                if attempt.estimate is not None:
                    st.dataframe(estimate_rows(attempt), hide_index=True, width="stretch",
                        column_config={"Estimate": st.column_config.NumberColumn(format="%.8g")})
                st.dataframe([{"Check": c.name, "Measured value": c.value, "Limit": c.limit, "Passed": c.passed}
                              for c in attempt.quality.checks], hide_index=True, width="stretch")
                if attempt.quality.rejection_reasons: st.error("; ".join(attempt.quality.rejection_reasons))
                if attempt.quality.estimator_failure: st.error(attempt.quality.estimator_failure)
                if attempt.diagnostics is not None: st.dataframe(record_rows(attempt.diagnostics), hide_index=True, width="stretch")
                st.caption("Residual units: V s for electrical/flux stages; N m s for mechanical. Local sensitivities are not confidence probabilities.")
                st.json({"excitation": json_value(attempt.config), "next_retry_configuration": json_value(attempt.next_config)})
                record = next((r for r in result.measurement_records if r.stage == attempt.stage and r.number == attempt.number), None)
                if record is not None:
                    fig = commissioning_figure(record, attempt.estimate)
                    st.pyplot(fig)
                    fig.clear()
        for record in result.measurement_records:
            if record.stage.value == stage and record.measurement_failure:
                st.error(f"Measurement provider failure (attempt {record.number}): {record.measurement_failure}")


def show_operating_analysis(result):
    st.subheader("Operating analysis — separate from commissioning quality")
    if not result.quality.accepted:
        st.warning("Unavailable: full commissioning rejected. No commissioned operation is fabricated.")
        return
    steady = result.steady_feasibility
    st.markdown("#### M14 steady operating feasibility")
    if steady is None: st.warning("Steady analysis unavailable; see run warnings.")
    else:
        st.info("Existing classification: "+steady.classification)
        st.dataframe(record_rows(steady, omit=("assumptions",)), hide_index=True, width="stretch")
    st.markdown("#### M16 dynamic operating feasibility")
    dynamic = result.dynamic_feasibility
    if dynamic is None: st.warning("Dynamic analysis unavailable; see run warnings.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("**Quasi-steady model estimate**")
            st.caption("Full dq transients can enter the band earlier. This quantity is not a universal physical lower bound.")
            st.dataframe(record_rows(dynamic.quasi_steady, omit=("trajectory",)), hide_index=True, width="stretch")
        with right:
            st.markdown("**Controller-aware prediction on identified model**")
            st.dataframe(record_rows(dynamic.controller, omit=("trace",)), hide_index=True, width="stretch")
        with st.expander("Dynamic request / complete analysis / assumptions"):
            st.json(json_value(dynamic))
        st.caption("M16 predicts a constant load from t=0. Validation below applies the separately configured load step. Nominal bus/ideal sensing are M16 assumptions; configured M17 errors affect the hidden-plant validation separately.")


def show_evaluation(result):
    st.subheader("Closed-loop validation — Simulation evaluation / ground truth")
    st.caption("Evaluation-only information below is never used to accept commissioning or select retries.")
    st.dataframe(record_rows(result.simulation_evaluation.truth), hide_index=True, width="stretch")
    st.dataframe([{"Parameter": name, "Post-hoc absolute error [%]": value}
                  for name, value in result.simulation_evaluation.parameter_absolute_error_percent.items()], hide_index=True, width="stretch")
    for warning in result.warnings: st.warning(warning)
    if result.control is None:
        st.info("No commissioned validation trace is available.")
        return
    st.dataframe(metric_rows(result), hide_index=True, width="stretch")
    st.caption("Post-load metrics use existing M17/M15 definitions. iq tracking compares true currents to references mapped into the true frame. Recovery can be zero when the disturbance stays inside ±10 rpm; null means no finite recovery.")
    figure = control_figure(result)
    st.pyplot(figure)
    figure.clear()


def show_firmware(result):
    st.subheader("Firmware configuration")
    st.caption("Portable firmware-ready control configuration — not deployed MCU firmware. No target timing, hardware validation or MISRA compliance is claimed.")
    if result.firmware_available:
        with st.expander("Exported binary32 motor / current / speed constants"):
            st.json(json_value(result.firmware_config))
        if st.button("Generate C header", key="generate_header"):
            with tempfile.TemporaryDirectory(prefix="pmsm-header-") as directory:
                path = export_firmware_configuration(result, Path(directory)/"generated_motor_config.h")
                st.session_state["header"] = path.read_text(encoding="utf-8")
        if "header" in st.session_state:
            st.code(st.session_state["header"], language="c")
            st.download_button("Download C header", st.session_state["header"], "generated_motor_config.h", mime="text/plain")
    else:
        st.warning("Firmware export unavailable: full commissioning was rejected or the export configuration failed. Prior assumptions cannot be exported as commissioned estimates.")
    show_parity()


def show_parity():
    st.markdown("#### COMMITTED M18 VALIDATION EVIDENCE")
    st.caption("Versioned evidence for the portable core; not a new parity test of this run. No compiler or replay executes on UI interaction.")
    try:
        evidence = load_committed_parity_evidence()
        flags = evidence["saturation_agreement"]
        st.dataframe(record_rows({"Compiler": evidence["build"]["compiler"],
            "Compared input samples": evidence["compared_samples"],
            "Maximum absolute difference [V]": evidence["worst_absolute"]["max_absolute_error"],
            "Maximum relative difference [ratio]": evidence["worst_relative"]["max_relative_error"],
            "Relative-worst signal": evidence["worst_relative"]["signal"],
            "Saturation agreement": f"{flags['agreements']} / {flags['total']}",
            "Away-boundary agreement": f"{flags['nonboundary_agreements']} / {flags['nonboundary_comparisons']}",
            "Boundary disagreements": evidence["boundary_disagreements"]}), hide_index=True, width="stretch")
        st.caption(evidence["boundary_note"])
        st.caption("Artifact SHA-256: "+evidence["artifact_sha256"])
        with st.expander("Full versioned parity record / compiler flags"): st.json(evidence)
    except (OSError, ValueError, KeyError) as exc: st.error(f"Committed parity evidence unavailable: {exc}")


def main():
    st.set_page_config(page_title="PMSM engineering application", layout="wide")
    st.title("Self-Commissioning PMSM Engineering")
    st.caption(f"v{__version__} — {RELEASE_STATUS}. Local simulation study; no hardware deployment.")
    st.sidebar.caption("Results change only when Run Commissioning is submitted. Current inputs and last completed run may differ.")
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
        with st.spinner("Generating sampled data, commissioning and evaluating accepted operation…"):
            st.session_state["result"] = run_engineering_workflow(configuration)
    result = st.session_state.get("result")
    if result is None:
        st.info("Configure a simulation case and select Run Commissioning. Estimates and run metrics will be computed by the existing backend.")
        st.markdown("Measurements → Rs/Ld/Lq → psi_f → J/B → gates/supervision → retuning → M14/M16 analysis → simulation validation → M18 export")
        show_parity()
        return
    st.subheader(result.status)
    if not result.quality.accepted: st.error("; ".join(result.quality.rejection_reasons))
    st.caption(f"CURRENT RUN RESULTS: seed {result.config.seed} / {result.config.scenario} / {result.config.mode} / {result.config.exposure}")
    with st.expander("Reproducibility / estimator-visible configuration"):
        configuration = json_value(result.config)
        configuration.pop("simulation_truth")
        st.json({"metadata": json_value(result.metadata), "configuration": configuration})
    tabs = st.tabs(["Commissioning", "Parameters / controllers", "Operating analysis", "Simulation evaluation", "Nonidealities", "Firmware / M18"])
    with tabs[0]: show_commissioning(result)
    with tabs[1]:
        st.subheader("Prior → identified → active controller")
        st.dataframe(parameter_rows(result), hide_index=True, width="stretch", column_config={
            name: st.column_config.NumberColumn(format="%.8g") for name in ("Prior assumption", "Identified / known", "Controller value")})
        st.dataframe(controller_rows(result), hide_index=True, width="stretch",
            column_config={"Value": st.column_config.NumberColumn(format="%.8g")})
        st.caption("Motor values and gains come from existing retuning/controller constructors. Rejection retains all prior controller parameters.")
    with tabs[2]: show_operating_analysis(result)
    with tabs[3]: show_evaluation(result)
    with tabs[4]:
        st.subheader("M17 simulation stress/error models")
        st.json(json_value(result.nonidealities))
        st.caption("Exposure controls commissioning, operation, or both; Rs drift applies only during operation. Nominal-bus FOC command and true terminal voltage are distinct; extra actual-bus clipping is not fed back into nominal anti-windup.")
        st.markdown("#### Simulation evaluation / ground truth")
        if result.control is not None:
            st.json({"nominal_bus_voltage_v": result.control.trace["dc_bus_voltage"],
                "actual_bus_voltage_v": result.control.trace["actual_dc_bus_voltage"],
                "terminal_command_discrepancy_rmse_v": result.control.metrics.get("terminal_command_discrepancy_rmse_v")})
            st.caption("Measured/true current and commanded/terminal voltage curves are in the Simulation evaluation tab.")
    with tabs[5]: show_firmware(result)
    if st.button("Prepare run bundle", key="prepare_bundle"):
        with st.spinner("Writing current-run JSON/CSV/plot/configuration bundle…"):
            st.session_state["bundle"] = run_bundle_zip(result)
    if "bundle" in st.session_state:
        st.download_button("Download run bundle", st.session_state["bundle"], f"pmsm_{result.config.scenario}_{result.config.seed}.zip", mime="application/zip")


if __name__ == "__main__": main()
