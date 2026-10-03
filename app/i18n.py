"""Small UI-only localization layer for the engineering application."""

DEFAULT_LANGUAGE = "tr"

LANGUAGE_OPTIONS = {
    "Türkçe": "tr",
    "English": "en",
}

TRANSLATIONS = {
    # App shell
    "app_title": {"tr": "PMSM Otomatik Devreye Alma Mühendislik Uygulaması", "en": "Self-Commissioning PMSM Engineering"},
    "app_caption": {"tr": "v{version} — {status}. Yerel simülasyon çalışması; donanım üzerinde devreye alınmış değildir.", "en": "v{version} — {status}. Local simulation study; no hardware deployment."},
    "language": {"tr": "Dil / Language", "en": "Language / Dil"},
    "sidebar_note": {"tr": "Sonuçlar yalnızca “Devreye Almayı Başlat” düğmesine basıldığında değişir. Mevcut girişler ile son tamamlanan çalışma farklı olabilir.", "en": "Results change only when Run Commissioning is submitted. Current inputs and last completed run may differ."},
    "configure_hint": {"tr": "Bir simülasyon senaryosu yapılandırın ve “Devreye Almayı Başlat” seçeneğini kullanın. Parametre kestirimleri ve çalışma metrikleri mevcut mühendislik altyapısı tarafından hesaplanır.", "en": "Configure a simulation case and select Run Commissioning. Estimates and run metrics will be computed by the existing backend."},
    "pipeline": {"tr": "Ölçümler → Rs/Ld/Lq → ψf → J/B → kalite kapıları / denetleyici → yeniden ayarlama → M14/M16 analizi → simülasyon doğrulaması → M18 dışa aktarımı", "en": "Measurements → Rs/Ld/Lq → psi_f → J/B → gates/supervision → retuning → M14/M16 analysis → simulation validation → M18 export"},

    # Configuration
    "config_title": {"tr": "Sürücü / senaryo yapılandırması", "en": "Drive / scenario configuration"},
    "scenario": {"tr": "M17 simülasyon ön ayarı", "en": "M17 simulation preset"},
    "mode": {"tr": "Devreye alma modu", "en": "Commissioning mode"},
    "exposure": {"tr": "Bozulma / hata etkisinin uygulandığı aşama", "en": "Impairment exposure"},
    "seed": {"tr": "Deterministik tohum", "en": "Deterministic seed"},
    "pole_pairs": {"tr": "Bilinen kutup çifti sayısı [çift]", "en": "Known pole pairs [pairs]"},
    "dc_bus": {"tr": "Nominal DC bara gerilimi [V]", "en": "Nominal DC bus [V]"},
    "speed_target": {"tr": "Hız hedefi [rpm]", "en": "Speed target [rpm]"},
    "load": {"tr": "Harici çalışma yük momenti [N m]", "en": "External operating load [N m]"},
    "iq_limit": {"tr": "Çalışma iq referans sınırı [A]", "en": "Operating iq reference limit [A]"},
    "deadline": {"tr": "Dinamik süre sınırı [s]", "en": "Dynamic deadline [s]"},
    "hold": {"tr": "Gerekli kararlı kalma süresi [s]", "en": "Required dynamic hold [s]"},
    "ground_truth_expander": {"tr": "Simülasyon değerlendirmesi / gerçek değer — motor modeli", "en": "Simulation evaluation / ground truth — plant configuration"},
    "ground_truth_caption": {"tr": "Yalnızca simülatör girdileridir. Kestiriciler bu sabitleri değil örneklenmiş ölçüm kayıtlarını kullanır.", "en": "Simulator inputs only. Estimators receive sampled records, not these constants."},
    "prior_expander": {"tr": "Kestiricinin görebildiği başlangıç denetleyici varsayımları", "en": "Estimator-visible prior controller assumptions"},
    "excitation_expander": {"tr": "Devreye alma uyarımı / gürültü / doğrulama zamanlaması", "en": "Commissioning excitation / noise / validation timing"},
    "excitation_caption": {"tr": "Bunlar simülasyon tasarım kısıtlarıdır; fiziksel donanım güvenliği garantisi değildir. Mekanik devreye alma sırasında harici yük açıkça sıfır kabul edilir.", "en": "Simulation design constraints; no physical hardware-safety guarantee. Mechanical external load is explicitly zero."},
    "current_noise": {"tr": "Kaydedilen elektriksel akım gürültüsü std [A]", "en": "Recorded electrical current noise SD [A]"},
    "voltage_noise": {"tr": "Kaydedilen gerilim gürültüsü std [V]", "en": "Recorded voltage noise SD [V]"},
    "rotor_speed": {"tr": "Döndürülen rotor devreye alma hızı [rpm]", "en": "Driven-rotor commissioning speed [rpm]"},
    "excitation_scale": {"tr": "Duran rotor gerilim programı ölçeği [boyutsuz]", "en": "Standstill voltage-program scale [dimensionless]"},
    "duration": {"tr": "Kontrol doğrulama süresi [s]", "en": "Control-validation duration [s]"},
    "step_time": {"tr": "Çalışma yükü adım zamanı [s]", "en": "Operating load-step time [s]"},
    "run": {"tr": "Devreye Almayı Başlat", "en": "Run Commissioning"},
    "running": {"tr": "Örneklenmiş veriler üretiliyor, devreye alma çalıştırılıyor ve kabul edilen çalışma değerlendiriliyor…", "en": "Generating sampled data, commissioning and evaluating accepted operation…"},

    # Commissioning
    "commissioning_history": {"tr": "Örneklenmiş veri ile devreye alma / deneme geçmişi", "en": "Sampled-data commissioning / attempt history"},
    "no_attempt": {"tr": "Hiçbir kestirim denemesi tamamlanamadı. Aşağıdaki ölçüm / yapılandırma hatasına bakın.", "en": "No estimator attempt completed. See the measurement/configuration failure below."},
    "stage": {"tr": "{stage} aşaması", "en": "{stage} stage"},
    "stage_not_fitted": {"tr": "Bu aşama kestirilemedi; sonraki devreye alma adımları engellendi veya ölçüm üretimi başarısız oldu.", "en": "Stage not fitted; downstream commissioning was blocked or measurement generation failed."},
    "attempt_title": {"tr": "Deneme {number}: {quality} — ölçümleri / tanıları incele", "en": "Attempt {number}: {quality} — inspect measurements / diagnostics"},
    "residual_caption": {"tr": "Artık birimleri: elektriksel/akı aşamalarında V s, mekanik aşamada N m s. Yerel duyarlılıklar güven olasılığı değildir.", "en": "Residual units: V s for electrical/flux stages; N m s for mechanical. Local sensitivities are not confidence probabilities."},
    "measurement_failure": {"tr": "Ölçüm sağlayıcı hatası (deneme {number}): {error}", "en": "Measurement provider failure (attempt {number}): {error}"},

    # Operating analysis
    "operating_title": {"tr": "Çalışma analizi — devreye alma kalitesinden ayrı", "en": "Operating analysis — separate from commissioning quality"},
    "operating_unavailable": {"tr": "Kullanılamıyor: tam devreye alma reddedildi. Devreye alınmış bir çalışma sonucu uydurulmaz.", "en": "Unavailable: full commissioning rejected. No commissioned operation is fabricated."},
    "steady_title": {"tr": "M14 kararlı durum çalışma uygunluğu", "en": "M14 steady operating feasibility"},
    "steady_unavailable": {"tr": "Kararlı durum analizi kullanılamıyor; çalışma uyarılarına bakın.", "en": "Steady analysis unavailable; see run warnings."},
    "classification": {"tr": "Mevcut sınıflandırma: {value}", "en": "Existing classification: {value}"},
    "dynamic_title": {"tr": "M16 dinamik çalışma uygunluğu", "en": "M16 dynamic operating feasibility"},
    "dynamic_unavailable": {"tr": "Dinamik analiz kullanılamıyor; çalışma uyarılarına bakın.", "en": "Dynamic analysis unavailable; see run warnings."},
    "quasi_title": {"tr": "Yarı-kararlı model kestirimi", "en": "Quasi-steady model estimate"},
    "quasi_caption": {"tr": "Tam dq geçişleri hız bandına daha erken girebilir. Bu değer evrensel bir fiziksel alt sınır değildir.", "en": "Full dq transients can enter the band earlier. This quantity is not a universal physical lower bound."},
    "controller_prediction": {"tr": "Tanımlanan model üzerinde denetleyici-farkındalıklı kestirim", "en": "Controller-aware prediction on identified model"},
    "dynamic_request": {"tr": "Dinamik istek / tam analiz / varsayımlar", "en": "Dynamic request / complete analysis / assumptions"},
    "m16_caption": {"tr": "M16 yükü t=0’dan itibaren sabit kabul eder. Aşağıdaki doğrulama ise ayrı yapılandırılmış yük adımını uygular. M16 nominal bara/ideal algılama varsayar; yapılandırılmış M17 hataları gerçek bitki doğrulamasına ayrıca uygulanır.", "en": "M16 predicts a constant load from t=0. Validation below applies the separately configured load step. Nominal bus/ideal sensing are M16 assumptions; configured M17 errors affect the hidden-plant validation separately."},

    # Evaluation
    "evaluation_title": {"tr": "Kapalı çevrim doğrulaması — simülasyon değerlendirmesi / gerçek değer", "en": "Closed-loop validation — Simulation evaluation / ground truth"},
    "evaluation_caption": {"tr": "Aşağıdaki değerlendirme bilgileri devreye alma kabulünde veya yeniden deneme seçiminde hiçbir zaman kullanılmaz.", "en": "Evaluation-only information below is never used to accept commissioning or select retries."},
    "parameter": {"tr": "Parametre", "en": "Parameter"},
    "posthoc_error": {"tr": "Sonradan hesaplanan mutlak hata [%]", "en": "Post-hoc absolute error [%]"},
    "no_trace": {"tr": "Devreye alınmış denetleyici için doğrulama izi yok.", "en": "No commissioned validation trace is available."},
    "metrics_caption": {"tr": "Yük sonrası metrikler mevcut M17/M15 tanımlarını kullanır. iq izleme, gerçek akımları gerçek referans çerçevesine taşınmış referanslarla karşılaştırır. Bozulma ±10 rpm bandını terk etmezse toparlanma süresi sıfır olabilir; null sonlu toparlanma olmadığı anlamına gelir.", "en": "Post-load metrics use existing M17/M15 definitions. iq tracking compares true currents to references mapped into the true frame. Recovery can be zero when the disturbance stays inside ±10 rpm; null means no finite recovery."},

    # Firmware / parity
    "firmware_title": {"tr": "Firmware yapılandırması", "en": "Firmware configuration"},
    "firmware_caption": {"tr": "Taşınabilir, firmware’e hazır kontrol yapılandırmasıdır; MCU üzerinde çalıştırılmış firmware değildir. Hedef zamanlama, donanım doğrulaması veya MISRA uyumluluğu iddia edilmez.", "en": "Portable firmware-ready control configuration — not deployed MCU firmware. No target timing, hardware validation or MISRA compliance is claimed."},
    "firmware_expander": {"tr": "Dışa aktarılan binary32 motor / akım / hız sabitleri", "en": "Exported binary32 motor / current / speed constants"},
    "generate_header": {"tr": "C başlık dosyası oluştur", "en": "Generate C header"},
    "download_header": {"tr": "C başlık dosyasını indir", "en": "Download C header"},
    "firmware_unavailable": {"tr": "Firmware dışa aktarımı kullanılamıyor: tam devreye alma reddedildi veya dışa aktarma yapılandırması başarısız oldu. Başlangıç varsayımları, devreye alma sonucuymuş gibi dışa aktarılamaz.", "en": "Firmware export unavailable: full commissioning was rejected or the export configuration failed. Prior assumptions cannot be exported as commissioned estimates."},
    "parity_title": {"tr": "KAYITLI M18 DOĞRULAMA KANITI", "en": "COMMITTED M18 VALIDATION EVIDENCE"},
    "parity_caption": {"tr": "Taşınabilir C çekirdeği için sürümlenmiş kanıttır; bu çalışmanın yeni bir parity testi değildir. Arayüz etkileşiminde derleyici veya replay çalıştırılmaz.", "en": "Versioned evidence for the portable core; not a new parity test of this run. No compiler or replay executes on UI interaction."},
    "parity_full": {"tr": "Tam sürümlenmiş parity kaydı / derleyici bayrakları", "en": "Full versioned parity record / compiler flags"},
    "parity_unavailable": {"tr": "Kayıtlı parity kanıtı kullanılamıyor: {error}", "en": "Committed parity evidence unavailable: {error}"},

    # Main result/tabs
    "current_run": {"tr": "MEVCUT ÇALIŞMA SONUÇLARI: seed {seed} / {scenario} / {mode} / {exposure}", "en": "CURRENT RUN RESULTS: seed {seed} / {scenario} / {mode} / {exposure}"},
    "reproducibility": {"tr": "Tekrarlanabilirlik / kestiricinin görebildiği yapılandırma", "en": "Reproducibility / estimator-visible configuration"},
    "tab_commissioning": {"tr": "Devreye alma", "en": "Commissioning"},
    "tab_parameters": {"tr": "Parametreler / denetleyiciler", "en": "Parameters / controllers"},
    "tab_operating": {"tr": "Çalışma analizi", "en": "Operating analysis"},
    "tab_evaluation": {"tr": "Simülasyon değerlendirmesi", "en": "Simulation evaluation"},
    "tab_nonidealities": {"tr": "İdeal olmayan etkiler", "en": "Nonidealities"},
    "tab_firmware": {"tr": "Firmware / M18", "en": "Firmware / M18"},
    "parameters_title": {"tr": "Başlangıç → tanımlanan → etkin denetleyici", "en": "Prior → identified → active controller"},
    "parameters_caption": {"tr": "Motor değerleri ve kazançlar mevcut yeniden ayarlama / denetleyici kurucularından gelir. Reddedilme durumunda tüm başlangıç denetleyici parametreleri korunur.", "en": "Motor values and gains come from existing retuning/controller constructors. Rejection retains all prior controller parameters."},
    "nonidealities_title": {"tr": "M17 simülasyon gerilim / algılama / zamanlama hata modelleri", "en": "M17 simulation stress/error models"},
    "nonidealities_caption": {"tr": "Etki alanı devreye alma, çalışma veya ikisini birden seçer; Rs sürüklenmesi yalnızca çalışma sırasında uygulanır. Nominal-bara FOC komutu ile gerçek terminal gerilimi ayrıdır; gerçek bara kırpması nominal anti-windup’a gizlice geri beslenmez.", "en": "Exposure controls commissioning, operation, or both; Rs drift applies only during operation. Nominal-bus FOC command and true terminal voltage are distinct; extra actual-bus clipping is not fed back into nominal anti-windup."},
    "ground_truth_heading": {"tr": "Simülasyon değerlendirmesi / gerçek değer", "en": "Simulation evaluation / ground truth"},
    "curves_caption": {"tr": "Ölçülen/gerçek akım ve komut/terminal gerilim eğrileri Simülasyon değerlendirmesi sekmesindedir.", "en": "Measured/true current and commanded/terminal voltage curves are in the Simulation evaluation tab."},
    "prepare_bundle": {"tr": "Çalışma paketini hazırla", "en": "Prepare run bundle"},
    "bundle_running": {"tr": "Mevcut çalışmanın JSON/CSV/grafik/yapılandırma paketi yazılıyor…", "en": "Writing current-run JSON/CSV/plot/configuration bundle…"},
    "download_bundle": {"tr": "Çalışma paketini indir", "en": "Download run bundle"},

    # Table labels
    "Parameter": {"tr": "Parametre", "en": "Parameter"},
    "Unit": {"tr": "Birim", "en": "Unit"},
    "Prior assumption": {"tr": "Başlangıç varsayımı", "en": "Prior assumption"},
    "Identified / known": {"tr": "Tanımlanan / bilinen", "en": "Identified / known"},
    "Controller value": {"tr": "Denetleyici değeri", "en": "Controller value"},
    "Stage": {"tr": "Aşama", "en": "Stage"},
    "Attempt": {"tr": "Deneme", "en": "Attempt"},
    "Quality": {"tr": "Kalite", "en": "Quality"},
    "Estimator succeeded": {"tr": "Kestirim başarılı", "en": "Estimator succeeded"},
    "Reasons": {"tr": "Nedenler", "en": "Reasons"},
    "Estimator failure": {"tr": "Kestirim hatası", "en": "Estimator failure"},
    "Decision": {"tr": "Karar", "en": "Decision"},
    "Adaptive action": {"tr": "Uyarlamalı eylem", "en": "Adaptive action"},
    "Next configuration": {"tr": "Sonraki yapılandırma", "en": "Next configuration"},
    "Estimate": {"tr": "Kestirim", "en": "Estimate"},
    "Check": {"tr": "Kontrol", "en": "Check"},
    "Measured value": {"tr": "Ölçülen değer", "en": "Measured value"},
    "Limit": {"tr": "Sınır", "en": "Limit"},
    "Passed": {"tr": "Geçti", "en": "Passed"},
    "Loop": {"tr": "Çevrim", "en": "Loop"},
    "Constant": {"tr": "Sabit", "en": "Constant"},
    "Value": {"tr": "Değer", "en": "Value"},
    "Metric": {"tr": "Metrik", "en": "Metric"},
    "Quantity": {"tr": "Büyüklük", "en": "Quantity"},
    "unavailable": {"tr": "kullanılamıyor", "en": "unavailable"},

    # Parity table labels
    "Compiler": {"tr": "Derleyici", "en": "Compiler"},
    "Compared input samples": {"tr": "Karşılaştırılan giriş örnekleri", "en": "Compared input samples"},
    "Maximum absolute difference [V]": {"tr": "Maksimum mutlak fark [V]", "en": "Maximum absolute difference [V]"},
    "Maximum relative difference [ratio]": {"tr": "Maksimum göreli fark [oran]", "en": "Maximum relative difference [ratio]"},
    "Relative-worst signal": {"tr": "En kötü göreli fark sinyali", "en": "Relative-worst signal"},
    "Saturation agreement": {"tr": "Doygunluk kararı uyumu", "en": "Saturation agreement"},
    "Away-boundary agreement": {"tr": "Sınır bölgesi dışı uyum", "en": "Away-boundary agreement"},
    "Boundary disagreements": {"tr": "Sınır bölgesi uyuşmazlıkları", "en": "Boundary disagreements"},

    "artifact_sha": {"tr": "Artefakt SHA-256", "en": "Artifact SHA-256"},

    # M17 scenario display names
    "current_mild": {"tr": "Akım ölçümü — hafif", "en": "Current measurement — mild"},
    "current_strong": {"tr": "Akım ölçümü — güçlü", "en": "Current measurement — strong"},
    "voltage_mild": {"tr": "Gerilim ölçümü — hafif", "en": "Voltage measurement — mild"},
    "voltage_strong": {"tr": "Gerilim ölçümü — güçlü", "en": "Voltage measurement — strong"},
    "angle_mild": {"tr": "Elektriksel açı hatası — hafif", "en": "Electrical angle error — mild"},
    "angle_strong": {"tr": "Elektriksel açı hatası — güçlü", "en": "Electrical angle error — strong"},
    "inverter_mild": {"tr": "İnverter gerilim hatası — hafif", "en": "Inverter voltage error — mild"},
    "inverter_strong": {"tr": "İnverter gerilim hatası — güçlü", "en": "Inverter voltage error — strong"},
    "bus_sag_mild": {"tr": "DC bara çökmesi — hafif", "en": "DC bus sag — mild"},
    "bus_sag_strong": {"tr": "DC bara çökmesi — güçlü", "en": "DC bus sag — strong"},
    "rs_drift_mild": {"tr": "Rs sürüklenmesi — hafif", "en": "Rs drift — mild"},
    "rs_drift_strong": {"tr": "Rs sürüklenmesi — güçlü", "en": "Rs drift — strong"},
    "timing_one_sample": {"tr": "Zamanlama gecikmesi — 1 örnek", "en": "Timing delay — 1 sample"},
    "combined_mild": {"tr": "Birleşik hatalar — hafif", "en": "Combined errors — mild"},
    "combined_strong": {"tr": "Birleşik hatalar — güçlü", "en": "Combined errors — strong"},

    # Status/value translations
    "FULL ACCEPTED": {"tr": "TAM KABUL", "en": "FULL ACCEPTED"},
    "REJECTED": {"tr": "REDDEDİLDİ", "en": "REJECTED"},
    "ACCEPT": {"tr": "KABUL", "en": "ACCEPT"},
    "REJECT": {"tr": "RET", "en": "REJECT"},
    "standstill": {"tr": "Duran rotor", "en": "Standstill"},
    "rotating": {"tr": "Dönen rotor", "en": "Rotating"},
    "mechanical": {"tr": "Mekanik", "en": "Mechanical"},
    "Current": {"tr": "Akım", "en": "Current"},
    "Speed": {"tr": "Hız", "en": "Speed"},
    "ideal": {"tr": "Nominal (ideal)", "en": "Nominal (ideal)"},
    "one_shot": {"tr": "Tek deneme", "en": "One-shot"},
    "adaptive": {"tr": "Uyarlamalı", "en": "Adaptive"},
    "combined": {"tr": "Devreye alma + çalışma", "en": "Combined"},
    "commissioning_only": {"tr": "Yalnızca devreye alma", "en": "Commissioning only"},
    "operation_only": {"tr": "Yalnızca çalışma", "en": "Operation only"},
    "feasible": {"tr": "uygun", "en": "feasible"},
    "current_limited": {"tr": "akım sınırına takılıyor", "en": "current_limited"},
    "voltage_limited": {"tr": "gerilim sınırına takılıyor", "en": "voltage_limited"},
    "both": {"tr": "akım ve gerilim sınırına takılıyor", "en": "both"},
    "released": {"tr": "yayınlanmış", "en": "released"},
    "release candidate": {"tr": "sürüm adayı", "en": "release candidate"},
    "development": {"tr": "geliştirme", "en": "development"},
}


def text(language, key, **kwargs):
    language = language if language in ("tr", "en") else DEFAULT_LANGUAGE
    entry = TRANSLATIONS.get(key)
    template = entry.get(language, entry.get("en")) if entry else key
    return template.format(**kwargs)


def value_text(language, value):
    if value is None:
        return None
    return text(language, str(value))


def language_from_label(label):
    return LANGUAGE_OPTIONS.get(label, DEFAULT_LANGUAGE)
