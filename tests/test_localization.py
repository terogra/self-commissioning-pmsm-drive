"""Language is a presentation choice, never a commissioning input."""

import ast
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from app.localization import DEFAULT_LANGUAGE, LANGUAGES, TR, display_formatter, display_rows, localize_figure, set_language, t
from app.presentation import parameter_rows
from src.engineering_reporting import control_figure
from src.engineering_workflow import ROOT, run_engineering_workflow


@pytest.fixture(autouse=True)
def default_language():
    set_language(DEFAULT_LANGUAGE)
    yield
    set_language(DEFAULT_LANGUAGE)


def test_default_turkish_and_english_catalogue():
    assert DEFAULT_LANGUAGE == "tr" and set(LANGUAGES) == {"tr", "en"}
    assert t("Run Commissioning") == "Devreye Almayı Başlat"
    assert t("Commissioning") == "Devreye Alma"
    assert t("Self-Commissioning PMSM Engineering") == "PMSM Sürücü Devreye Alma Aracı"
    assert not any(term in text.lower() for text in TR.values()
                   for term in ("mühendislik platformu", "sürücü mühendisliği", "kapsamlı çözüm"))
    assert not any("komisyon" in text.lower() for text in TR.values())
    set_language("en")
    assert t("Self-Commissioning PMSM Engineering") == "PMSM Drive Commissioning Workbench"
    assert t("Run Commissioning") == "Run Commissioning"
    with pytest.raises(ValueError): set_language("fake")


def test_canonical_terms_match_glossary():
    glossary = (ROOT/"docs/terminology.md").read_text(encoding="utf-8")
    canonical = {
        "Commissioning": "Devreye Alma", "Parameter identification": "Parametre kestirimi",
        "Operating point": "Çalışma noktası", "Steady-state": "Kararlı durum",
        "Dynamic feasibility": "Dinamik uygunluk", "Voltage saturation": "Gerilim doyumu",
        "DC bus": "DC bara", "Excitation": "Uyartım", "Residual": "Model artığı",
        "Bias": "Bias / sistematik hata", "Quasi-steady": "Yarı kararlı durum",
        "Controller-aware prediction": "Denetleyici modeliyle öngörü",
        "Ground truth": "Gerçek simülasyon değerleri", "Retry": "Yeniden deneme",
    }
    for english, turkish in canonical.items():
        set_language("tr")
        assert t(english) == turkish
        assert turkish.lower() in glossary.lower()
        set_language("en")
        assert t(english) == english
        assert english.lower() in glossary.lower()
    readme_tr = (ROOT/"README.md").read_text(encoding="utf-8")
    readme_en = (ROOT/"README.en.md").read_text(encoding="utf-8")
    assert "PMSM Sürücü Devreye Alma ve Parametre Kestirimi" in readme_tr
    assert "PMSM drive commissioning and parameter identification" in readme_en
    assert "docs/images/v1_1_dashboard_tr.png" in readme_tr and "docs/images/v1_1_dashboard_tr.png" in readme_en


def test_unknown_machine_codes_and_row_values_survive():
    code = "future_stage.unknown_rejection"
    original = [{"Reasons": code, "Value": .00055, "Passed": False}]
    translated = display_rows(original)
    assert translated == [{"Nedenler": code, "Değer": .00055, "Sağlandı": False}]
    assert original[0]["Reasons"] == code
    assert t("standstill.excessive_residual") == "standstill.excessive_residual"
    set_language("en")
    assert display_rows(original) == original


def test_widget_formatter_keeps_rendered_language_across_contexts():
    formatter = display_formatter()
    set_language("en")
    assert formatter("adaptive") == "Uyarlamalı gözetim"
    assert display_formatter()("adaptive") == "Adaptive supervisor"


def test_all_scenarios_have_bilingual_display_names():
    from experiments.nonideality_robustness import scenarios
    for scenario in scenarios():
        assert scenario.name in TR
        assert t(scenario.name) != scenario.name
    set_language("en")
    assert t("timing_one_sample") == "Timing — one-sample delay"


def test_dashboard_static_messages_are_in_central_catalogue():
    tree = ast.parse((ROOT/"app/dashboard.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                assert node.args[0].value in TR, node.args[0].value


def test_plot_translation_does_not_change_numeric_artists_or_result():
    result = run_engineering_workflow()
    before = asdict(result.controller_parameters)
    figure = control_figure(result)
    lines = [line.get_ydata().copy() for ax in figure.axes for line in ax.lines]
    localize_figure(figure)
    assert figure.axes[0].get_ylabel() == "Hız [rpm]"
    for prior, line in zip(lines, [line for ax in figure.axes for line in ax.lines]):
        np.testing.assert_array_equal(prior, line.get_ydata())
    assert asdict(result.controller_parameters) == before
    figure.clear()


def test_language_switch_preserves_widgets_results_and_export():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT/"app/dashboard.py"), default_timeout=60).run()
    assert not app.exception and app.selectbox(key="language").value == "tr"
    assert app.button(key="run_commissioning").label == "Devreye Almayı Başlat"
    app.number_input(key="seed").set_value(1909)
    app.selectbox(key="mode").select("adaptive")
    app.button(key="run_commissioning").click().run()
    assert not app.exception
    accepted = app.session_state["result"]
    assert accepted.quality.accepted
    app.button(key="generate_header").click().run()
    header = app.session_state["header"]
    app.selectbox(key="language").select("en").run()
    assert not app.exception
    assert app.button(key="run_commissioning").label == "Run Commissioning"
    assert app.number_input(key="seed").value == 1909
    assert app.selectbox(key="mode").value == "adaptive"
    assert app.session_state["result"] is accepted  # no extra computation
    assert app.session_state["header"] == header
    assert app.selectbox(key="mode").proto.raw_value == "Adaptive supervisor"
    assert app.selectbox(key="mode").proto.set_value
    # Unsubmitted edits persist, but do not compute a new engineering run.
    app.number_input(key="target").set_value(900.).run()
    app.selectbox(key="language").select("tr").run()
    assert app.number_input(key="target").value == 900.
    assert app.session_state["result"] is accepted
    assert app.session_state["header"] == header
    app.selectbox(key="scenario").select("timing_one_sample")
    app.button(key="run_commissioning").click().run()
    rejected = app.session_state["result"]
    assert not app.exception and not rejected.quality.accepted
    assert not any(b.key == "generate_header" for b in app.button)
    app.selectbox(key="language").select("tr").run()
    assert not app.exception and app.session_state["result"] is rejected
    assert app.selectbox(key="scenario").value == "timing_one_sample"
    assert any("standstill.excessive_residual" in e.value for e in app.error)
    assert rejected.controller_parameters == rejected.config.prior_assumptions


def test_landing_pages_preserve_dynamic_model_caution():
    for name in ("README.md", "README.en.md"):
        text = (ROOT/name).read_text(encoding="utf-8")
        assert "full dq transient simulation" in text
        assert "not a physical minimum or universal lower bound" in text.replace("\n", " ")
