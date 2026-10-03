"""Streamlit presentation of real workflow results; import has no UI side effects."""

from dataclasses import replace
from pathlib import Path
import tempfile

import streamlit as st

from app.i18n import DEFAULT_LANGUAGE, LANGUAGE_OPTIONS, language_from_label, text, value_text
from app.presentation import (
    attempt_rows,
    controller_rows,
    estimate_rows,
    load_committed_parity_evidence,
    metric_rows,
    parameter_rows,
    record_rows,
)
from src.engineering_bundle import json_value, run_bundle_zip
from src.engineering_reporting import commissioning_figure, control_figure
from src.engineering_workflow import (
    EngineeringWorkflowConfig,
    MotorConfiguration,
    export_firmware_configuration,
    run_engineering_workflow,
    scenarios,
)
from src.version import __version__, RELEASE_STATUS


def _lang():
    return st.session_state.get("language", DEFAULT_LANGUAGE)


def _t(key, **kwargs):
    return text(_lang(), key, **kwargs)


def _value(value):
    return value_text(_lang(), value)


def _choice(value):
    translated = _value(value)
    if translated != str(value):
        return translated
    return str(value).replace("_", " ")


def _localized_selectbox(label_key, options, state_key):
    """Keep backend values stable while recreating localized selectboxes per language."""
    language = _lang()
    persisted_key = f"_{state_key}_value"
    current = st.session_state.get(persisted_key, options[0])
    if current not in options:
        current = options[0]

    # Streamlit/AppTest can retain widgets from the previous language for one
    # rerun. Capture the language in this widget's formatter so an old English
    # widget does not start formatting its values as Turkish (or vice versa).
    def fixed_choice(value, language=language):
        translated = value_text(language, value)
        if translated != str(value):
            return translated
        return str(value).replace("_", " ")

    selected = st.selectbox(
        text(language, label_key),
        options,
        index=options.index(current),
        format_func=fixed_choice,
        key=f"{state_key}_{language}",
    )
    st.session_state[persisted_key] = selected
    return selected


def _motor_inputs(default, prefix):
    values = {}
    steps = {"Rs": .001, "Ld": 1e-7, "Lq": 1e-7, "psi_f": 1e-6, "J": 1e-7, "B": 1e-7}
    for name, unit in (("Rs", "ohm"), ("Ld", "H"), ("Lq", "H"), ("psi_f", "Wb"), ("J", "kg m²"), ("B", "N m s/rad")):
        values[name] = st.number_input(
            f"{name} [{unit}]",
            min_value=0.0,
            step=steps[name],
            value=float(getattr(default, name)),
            format="%.7f",
            key=prefix+name,
        )
    return values


def configuration_form():
    default = EngineeringWorkflowConfig()
    with st.sidebar.form("drive_configuration"):
        st.subheader(_t("config_title"))
        scenario = _localized_selectbox("scenario", [s.name for s in scenarios()], "scenario")
        mode = _localized_selectbox("mode", ["one_shot", "adaptive"], "mode")
        exposure = _localized_selectbox(
            "exposure", ["combined", "commissioning_only", "operation_only"], "exposure"
        )
        seed = st.number_input(
            _t("seed"), min_value=0, max_value=2**31-3, value=default.seed, step=1, key="seed"
        )
        pairs = st.number_input(
            _t("pole_pairs"), min_value=1, max_value=32, value=4, step=1, key="pole_pairs"
        )
        bus = st.number_input(_t("dc_bus"), min_value=.1, value=24., key="bus")
        speed = st.number_input(_t("speed_target"), min_value=1., value=1000., key="target")
        load = st.number_input(_t("load"), min_value=0., value=.05, format="%.4f", key="load")
        limit = st.number_input(_t("iq_limit"), min_value=.01, value=5., key="limit")
        deadline = st.number_input(_t("deadline"), min_value=.01, max_value=5., value=.6, key="deadline")
        hold = st.number_input(
            _t("hold"), min_value=.001, step=.001, value=.1, format="%.3f", key="hold"
        )
        with st.expander(_t("ground_truth_expander")):
            st.caption(_t("ground_truth_caption"))
            truth = _motor_inputs(default.simulation_truth, "truth_")
        with st.expander(_t("prior_expander")):
            prior = _motor_inputs(default.prior_assumptions, "prior_")
        with st.expander(_t("excitation_expander")):
            st.caption(_t("excitation_caption"))
            current_noise = st.number_input(
                _t("current_noise"), min_value=0., value=.01, format="%.5f", key="noise_i"
            )
            voltage_noise = st.number_input(
                _t("voltage_noise"), min_value=0., value=.01, format="%.5f", key="noise_v"
            )
            rotor_speed = st.number_input(
                _t("rotor_speed"), min_value=100., max_value=1200., value=600., key="rotor_speed"
            )
            excitation_scale = st.number_input(
                _t("excitation_scale"), min_value=0., max_value=1.5, value=1., key="excitation"
            )
            duration = st.number_input(
                _t("duration"), min_value=.01, max_value=5., value=.6, key="duration"
            )
            step_time = st.number_input(
                _t("step_time"), min_value=0., value=.3, key="step_time"
            )
        submitted = st.form_submit_button(_t("run"), type="primary", key="run_commissioning")
    if not submitted:
        return None
    return EngineeringWorkflowConfig(
        simulation_truth=MotorConfiguration(**truth, pole_pairs=pairs),
        prior_assumptions=MotorConfiguration(**prior, pole_pairs=pairs),
        scenario=scenario,
        mode=mode,
        exposure=exposure,
        seed=seed,
        dc_bus_voltage_v=bus,
        speed_target_rpm=speed,
        load_torque_nm=load,
        current_limit_a=limit,
        deadline_s=deadline,
        hold_time_s=hold,
        simulation_duration_s=duration,
        load_step_time_s=step_time,
        standstill=replace(
            default.standstill,
            current_noise_std_a=current_noise,
            voltage_noise_std_v=voltage_noise,
            d_voltage_v=default.standstill.d_voltage_v*excitation_scale,
            q_voltage_v=default.standstill.q_voltage_v*excitation_scale,
        ),
        rotating=replace(
            default.rotating,
            current_noise_std_a=current_noise,
            voltage_noise_std_v=voltage_noise,
            speed_rpm=rotor_speed,
        ),
    )


def show_commissioning(result):
    language = _lang()
    st.subheader(_t("commissioning_history"))
    rows = attempt_rows(result, language)
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.warning(_t("no_attempt"))
    for stage in ("standstill", "rotating", "mechanical"):
        st.markdown("#### " + _t("stage", stage=_value(stage)))
        attempts = [a for a in result.attempts if a.stage.value == stage]
        if not attempts:
            st.info(_t("stage_not_fitted"))
        for attempt in attempts:
            quality = _value("ACCEPT" if attempt.quality.accepted else "REJECT")
            with st.expander(_t("attempt_title", number=attempt.number, quality=quality)):
                if attempt.estimate is not None:
                    st.dataframe(
                        estimate_rows(attempt, language),
                        hide_index=True,
                        width="stretch",
                        column_config={
                            text(language, "Estimate"): st.column_config.NumberColumn(format="%.8g")
                        },
                    )
                checks = [{
                    text(language, "Check"): c.name,
                    text(language, "Measured value"): c.value,
                    text(language, "Limit"): c.limit,
                    text(language, "Passed"): c.passed,
                } for c in attempt.quality.checks]
                st.dataframe(checks, hide_index=True, width="stretch")
                if attempt.quality.rejection_reasons:
                    st.error("; ".join(attempt.quality.rejection_reasons))
                if attempt.quality.estimator_failure:
                    st.error(attempt.quality.estimator_failure)
                if attempt.diagnostics is not None:
                    st.dataframe(
                        record_rows(attempt.diagnostics, language=language),
                        hide_index=True,
                        width="stretch",
                    )
                st.caption(_t("residual_caption"))
                st.json({
                    "excitation": json_value(attempt.config),
                    "next_retry_configuration": json_value(attempt.next_config),
                })
                record = next(
                    (r for r in result.measurement_records
                     if r.stage == attempt.stage and r.number == attempt.number),
                    None,
                )
                if record is not None:
                    fig = commissioning_figure(record, attempt.estimate, language=language)
                    st.pyplot(fig)
                    fig.clear()
        for record in result.measurement_records:
            if record.stage.value == stage and record.measurement_failure:
                st.error(_t(
                    "measurement_failure",
                    number=record.number,
                    error=record.measurement_failure,
                ))


def show_operating_analysis(result):
    language = _lang()
    st.subheader(_t("operating_title"))
    if not result.quality.accepted:
        st.warning(_t("operating_unavailable"))
        return
    steady = result.steady_feasibility
    st.markdown("#### " + _t("steady_title"))
    if steady is None:
        st.warning(_t("steady_unavailable"))
    else:
        st.info(_t("classification", value=_value(steady.classification)))
        st.dataframe(
            record_rows(steady, omit=("assumptions",), language=language),
            hide_index=True,
            width="stretch",
        )
    st.markdown("#### " + _t("dynamic_title"))
    dynamic = result.dynamic_feasibility
    if dynamic is None:
        st.warning(_t("dynamic_unavailable"))
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("**" + _t("quasi_title") + "**")
            st.caption(_t("quasi_caption"))
            st.dataframe(
                record_rows(dynamic.quasi_steady, omit=("trajectory",), language=language),
                hide_index=True,
                width="stretch",
            )
        with right:
            st.markdown("**" + _t("controller_prediction") + "**")
            st.dataframe(
                record_rows(dynamic.controller, omit=("trace",), language=language),
                hide_index=True,
                width="stretch",
            )
        with st.expander(_t("dynamic_request")):
            st.json(json_value(dynamic))
        st.caption(_t("m16_caption"))


def show_evaluation(result):
    language = _lang()
    st.subheader(_t("evaluation_title"))
    st.caption(_t("evaluation_caption"))
    st.dataframe(
        record_rows(result.simulation_evaluation.truth, language=language),
        hide_index=True,
        width="stretch",
    )
    st.dataframe([{
        _t("parameter"): name,
        _t("posthoc_error"): value,
    } for name, value in result.simulation_evaluation.parameter_absolute_error_percent.items()],
        hide_index=True, width="stretch")
    for warning in result.warnings:
        st.warning(warning)
    if result.control is None:
        st.info(_t("no_trace"))
        return
    st.dataframe(metric_rows(result, language), hide_index=True, width="stretch")
    st.caption(_t("metrics_caption"))
    figure = control_figure(result, language=language)
    st.pyplot(figure)
    figure.clear()


def show_firmware(result):
    language = _lang()
    st.subheader(_t("firmware_title"))
    st.caption(_t("firmware_caption"))
    if result.firmware_available:
        with st.expander(_t("firmware_expander")):
            st.json(json_value(result.firmware_config))
        if st.button(_t("generate_header"), key="generate_header"):
            with tempfile.TemporaryDirectory(prefix="pmsm-header-") as directory:
                path = export_firmware_configuration(
                    result, Path(directory)/"generated_motor_config.h"
                )
                st.session_state["header"] = path.read_text(encoding="utf-8")
        if "header" in st.session_state:
            st.code(st.session_state["header"], language="c")
            st.download_button(
                _t("download_header"),
                st.session_state["header"],
                "generated_motor_config.h",
                mime="text/plain",
            )
    else:
        st.warning(_t("firmware_unavailable"))
    show_parity()


def show_parity():
    language = _lang()
    st.markdown("#### " + _t("parity_title"))
    st.caption(_t("parity_caption"))
    try:
        evidence = load_committed_parity_evidence()
        flags = evidence["saturation_agreement"]
        labels = [
            ("Compiler", evidence["build"]["compiler"]),
            ("Compared input samples", evidence["compared_samples"]),
            ("Maximum absolute difference [V]", evidence["worst_absolute"]["max_absolute_error"]),
            ("Maximum relative difference [ratio]", evidence["worst_relative"]["max_relative_error"]),
            ("Relative-worst signal", evidence["worst_relative"]["signal"]),
            ("Saturation agreement", f"{flags['agreements']} / {flags['total']}"),
            ("Away-boundary agreement", f"{flags['nonboundary_agreements']} / {flags['nonboundary_comparisons']}"),
            ("Boundary disagreements", evidence["boundary_disagreements"]),
        ]
        st.dataframe(
            record_rows(
                {text(language, key): value for key, value in labels},
                language=language,
            ),
            hide_index=True,
            width="stretch",
        )
        boundary_note = (
            "Katı '>' doygunluk kararları float32 yuvarlama sınırlarında farklılaşabilir; "
            "tüm sınır probları korunmuştur."
            if language == "tr" else evidence["boundary_note"]
        )
        st.caption(boundary_note)
        st.caption(_t("artifact_sha") + ": " + evidence["artifact_sha256"])
        with st.expander(_t("parity_full")):
            st.json(evidence)
    except (OSError, ValueError, KeyError) as exc:
        st.error(_t("parity_unavailable", error=exc))


def main():
    st.set_page_config(
        page_title=text(DEFAULT_LANGUAGE, "app_title"),
        layout="wide",
    )
    st.session_state.setdefault("language", DEFAULT_LANGUAGE)

    labels = list(LANGUAGE_OPTIONS)
    current_label = next(
        (label for label, code in LANGUAGE_OPTIONS.items() if code == _lang()),
        "Türkçe",
    )
    selected_label = st.sidebar.selectbox(
        "Dil / Language",
        labels,
        index=labels.index(current_label),
        key="language_picker",
    )
    st.session_state["language"] = language_from_label(selected_label)

    st.title(_t("app_title"))
    st.caption(_t(
        "app_caption",
        version=__version__,
        status=_value(RELEASE_STATUS),
    ))
    st.sidebar.caption(_t("sidebar_note"))

    try:
        configuration = configuration_form()
    except ValueError as exc:
        st.session_state.pop("result", None)
        st.session_state.pop("header", None)
        st.session_state.pop("bundle", None)
        st.error(str(exc))
        return

    if configuration is not None:
        for key in ("result", "header", "bundle"):
            st.session_state.pop(key, None)
        with st.spinner(_t("running")):
            st.session_state["result"] = run_engineering_workflow(configuration)

    result = st.session_state.get("result")
    if result is None:
        st.info(_t("configure_hint"))
        st.markdown(_t("pipeline"))
        show_parity()
        return

    st.subheader(_value(result.status))
    if not result.quality.accepted:
        st.error("; ".join(result.quality.rejection_reasons))
    st.caption(_t(
        "current_run",
        seed=result.config.seed,
        scenario=_choice(result.config.scenario),
        mode=_choice(result.config.mode),
        exposure=_choice(result.config.exposure),
    ))

    with st.expander(_t("reproducibility")):
        configuration = json_value(result.config)
        configuration.pop("simulation_truth")
        st.json({
            "metadata": json_value(result.metadata),
            "configuration": configuration,
        })

    tabs = st.tabs([
        _t("tab_commissioning"),
        _t("tab_parameters"),
        _t("tab_operating"),
        _t("tab_evaluation"),
        _t("tab_nonidealities"),
        _t("tab_firmware"),
    ])

    with tabs[0]:
        show_commissioning(result)
    with tabs[1]:
        language = _lang()
        st.subheader(_t("parameters_title"))
        st.dataframe(
            parameter_rows(result, language),
            hide_index=True,
            width="stretch",
            column_config={
                text(language, name): st.column_config.NumberColumn(format="%.8g")
                for name in ("Prior assumption", "Identified / known", "Controller value")
            },
        )
        st.dataframe(
            controller_rows(result, language),
            hide_index=True,
            width="stretch",
            column_config={
                text(language, "Value"): st.column_config.NumberColumn(format="%.8g")
            },
        )
        st.caption(_t("parameters_caption"))
    with tabs[2]:
        show_operating_analysis(result)
    with tabs[3]:
        show_evaluation(result)
    with tabs[4]:
        st.subheader(_t("nonidealities_title"))
        st.json(json_value(result.nonidealities))
        st.caption(_t("nonidealities_caption"))
        st.markdown("#### " + _t("ground_truth_heading"))
        if result.control is not None:
            st.json({
                "nominal_bus_voltage_v": result.control.trace["dc_bus_voltage"],
                "actual_bus_voltage_v": result.control.trace["actual_dc_bus_voltage"],
                "terminal_command_discrepancy_rmse_v": result.control.metrics.get(
                    "terminal_command_discrepancy_rmse_v"
                ),
            })
            st.caption(_t("curves_caption"))
    with tabs[5]:
        show_firmware(result)

    if st.button(_t("prepare_bundle"), key="prepare_bundle"):
        with st.spinner(_t("bundle_running")):
            st.session_state["bundle"] = run_bundle_zip(result)
    if "bundle" in st.session_state:
        st.download_button(
            _t("download_bundle"),
            st.session_state["bundle"],
            f"pmsm_{result.config.scenario}_{result.config.seed}.zip",
            mime="application/zip",
        )


if __name__ == "__main__":
    main()
