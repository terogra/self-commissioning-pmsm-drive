"""Localization contract tests for the bilingual engineering UI."""

from app.i18n import DEFAULT_LANGUAGE, LANGUAGE_OPTIONS, text, value_text


def test_turkish_is_default_and_english_is_available():
    assert DEFAULT_LANGUAGE == "tr"
    assert LANGUAGE_OPTIONS["Türkçe"] == "tr"
    assert LANGUAGE_OPTIONS["English"] == "en"


def test_core_commissioning_terminology_is_engineering_turkish():
    assert text("tr", "run") == "Devreye Almayı Başlat"
    assert text("tr", "mode") == "Devreye alma modu"
    assert "komisyon" not in text("tr", "commissioning_history").lower()
    assert "devreye alma" in text("tr", "commissioning_history").lower()


def test_english_ui_keeps_original_engineering_terms():
    assert text("en", "run") == "Run Commissioning"
    assert text("en", "mode") == "Commissioning mode"
    assert text("en", "firmware_title") == "Firmware configuration"


def test_status_and_internal_values_have_bilingual_display_names():
    assert value_text("tr", "FULL ACCEPTED") == "TAM KABUL"
    assert value_text("tr", "REJECTED") == "REDDEDİLDİ"
    assert value_text("tr", "standstill") == "Duran rotor"
    assert value_text("en", "standstill") == "Standstill"


def test_unknown_backend_code_is_preserved_for_diagnostics():
    code = "standstill.excessive_residual"
    assert value_text("tr", code) == code
    assert value_text("en", code) == code
