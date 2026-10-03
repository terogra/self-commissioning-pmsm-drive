"""Presentation-only gettext-style catalogue. Machine identifiers stay unchanged.

English source messages are stable catalogue keys. A ContextVar scopes language
to a Streamlit script thread, avoiding cross-session global language state.
"""

from contextvars import ContextVar
from functools import partial
import re

DEFAULT_LANGUAGE = "tr"
LANGUAGES = {"tr": "Türkçe", "en": "English"}
_language = ContextVar("display_language", default=DEFAULT_LANGUAGE)

TR = {
    "PMSM engineering application": "PMSM mühendislik uygulaması",
    "Self-Commissioning PMSM Engineering": "PMSM Otomatik Devreye Alma ve Sürücü Mühendisliği",
    "release candidate": "sürüm adayı", "released": "yayımlandı",
    "Run Commissioning": "Devreye Almayı Başlat",
    "Drive / scenario configuration": "Sürücü / senaryo yapılandırması",
    "M17 simulation preset": "M17 benzetim senaryosu",
    "Commissioning mode": "Devreye alma yöntemi",
    "Impairment exposure": "İdeal olmayan etkilerin uygulandığı aşama",
    "Deterministic seed": "Tekrarlanabilir rastgelelik tohumu",
    "Known pole pairs [pairs]": "Bilinen kutup çifti sayısı [çift]",
    "Nominal DC bus [V]": "Nominal DC bara [V]",
    "Speed target [rpm]": "Hız hedefi [rpm]",
    "External operating load [N m]": "Çalışma sırasında dış yük [N m]",
    "Operating iq reference limit [A]": "Çalışma iq referans sınırı [A]",
    "Dynamic deadline [s]": "Dinamik hedef için süre sınırı [s]",
    "Required dynamic hold [s]": "Hız bandında kalma süresi [s]",
    "Simulation evaluation / ground truth — plant configuration": "Benzetim değerlendirmesi / gerçek değerler — motor yapılandırması",
    "Simulator inputs only. Estimators receive sampled records, not these constants.": "Yalnızca benzetici girdileridir. Kestiriciler bu sabitleri değil, örneklenmiş ölçümleri alır.",
    "Estimator-visible prior controller assumptions": "Kestiriciye açık başlangıç denetleyici varsayımları",
    "Commissioning excitation / noise / validation timing": "Devreye alma uyartımı / gürültü / doğrulama zamanlaması",
    "Simulation design constraints; no physical hardware-safety guarantee. Mechanical external load is explicitly zero.": "Benzetim tasarım sınırlarıdır; fiziksel donanım güvenliği garantisi değildir. Mekanik devreye almada dış yük açıkça sıfırdır.",
    "Recorded electrical current noise SD [A]": "Elektriksel akım ölçüm gürültüsü standart sapması [A]",
    "Recorded voltage noise SD [V]": "Gerilim ölçüm gürültüsü standart sapması [V]",
    "Driven-rotor commissioning speed [rpm]": "Döndürülen rotor devreye alma hızı [rpm]",
    "Standstill voltage-program scale [dimensionless]": "Duran rotor gerilim programı ölçeği [boyutsuz]",
    "Control-validation duration [s]": "Denetim doğrulama süresi [s]",
    "Operating load-step time [s]": "Çalışma yük basamağı zamanı [s]",
    "Sampled-data commissioning / attempt history": "Örneklenmiş verilerle devreye alma / deneme geçmişi",
    "No estimator attempt completed. See the measurement/configuration failure below.": "Tamamlanan kestirim denemesi yok. Aşağıdaki ölçüm/yapılandırma hatasını inceleyin.",
    "Stage not fitted; downstream commissioning was blocked or measurement generation failed.": "Bu aşamada kestirim yapılmadı; sonraki devreye alma aşaması engellendi veya ölçüm üretimi başarısız oldu.",
    "Residual units: V s for electrical/flux stages; N m s for mechanical. Local sensitivities are not confidence probabilities.": "Artık birimleri: elektriksel/akı aşamaları için V s; mekanik aşama için N m s. Yerel duyarlılıklar güven olasılığı değildir.",
    "Operating analysis — separate from commissioning quality": "Çalışma analizi — devreye alma kalitesinden ayrı",
    "Unavailable: full commissioning rejected. No commissioned operation is fabricated.": "Kullanılamıyor: tam devreye alma reddedildi. Devreye alınmış bir çalışma sonucu üretilmedi.",
    "#### M14 steady operating feasibility": "#### M14 sürekli çalışma noktası uygunluğu",
    "Steady analysis unavailable; see run warnings.": "Sürekli çalışma analizi kullanılamıyor; çalışma uyarılarını inceleyin.",
    "Existing classification: ": "Mevcut sınıflandırma: ",
    "#### M16 dynamic operating feasibility": "#### M16 dinamik çalışma uygunluğu",
    "Dynamic analysis unavailable; see run warnings.": "Dinamik analiz kullanılamıyor; çalışma uyarılarını inceleyin.",
    "**Quasi-steady model estimate**": "**Yarı durağan model kestirimi**",
    "Full dq transients can enter the band earlier. This quantity is not a universal physical lower bound.": "Tam dq geçici rejimi hız bandına daha erken girebilir. Bu nicelik evrensel bir fiziksel alt sınır değildir.",
    "**Controller-aware prediction on identified model**": "**Kestirilen model üzerinde denetleyiciyi içeren öngörü**",
    "Dynamic request / complete analysis / assumptions": "Dinamik istek / tam analiz / varsayımlar",
    "M16 predicts a constant load from t=0. Validation below applies the separately configured load step. Nominal bus/ideal sensing are M16 assumptions; configured M17 errors affect the hidden-plant validation separately.": "M16, t=0 anından itibaren sabit yük varsayar. Aşağıdaki doğrulamada ayrı yapılandırılan yük basamağı uygulanır. Nominal bara/ideal ölçüm M16 varsayımlarıdır; M17 hataları gizli motor modeli doğrulamasını ayrı etkiler.",
    "Closed-loop validation — Simulation evaluation / ground truth": "Kapalı çevrim doğrulama — benzetim değerlendirmesi / gerçek değerler",
    "Evaluation-only information below is never used to accept commissioning or select retries.": "Aşağıdaki bilgiler yalnızca değerlendirme içindir; devreye almayı kabul etmek veya yeniden deneme seçmek için kullanılmaz.",
    "No commissioned validation trace is available.": "Devreye alınmış denetleyici için doğrulama kaydı yok.",
    "Post-load metrics use existing M17/M15 definitions. iq tracking compares true currents to references mapped into the true frame. Recovery can be zero when the disturbance stays inside ±10 rpm; null means no finite recovery.": "Yük sonrası ölçütler mevcut M17/M15 tanımlarını kullanır. iq izleme, gerçek akımı gerçek eksen takımına dönüştürülmüş referansla karşılaştırır. Bozucu etki ±10 rpm içinde kalırsa toparlanma sıfır olabilir; null sonlu bir toparlanma bulunmadığını gösterir.",
    "Firmware configuration": "Firmware yapılandırması",
    "Portable firmware-ready control configuration — not deployed MCU firmware. No target timing, hardware validation or MISRA compliance is claimed.": "Taşınabilir firmware'e hazır denetim yapılandırmasıdır; MCU'ya yüklenmiş firmware değildir. Hedef zamanlaması, donanım doğrulaması veya MISRA uygunluğu iddiası yoktur.",
    "Exported binary32 motor / current / speed constants": "Dışa aktarılan binary32 motor / akım / hız sabitleri",
    "Generate C header": "C Başlık Dosyası Oluştur",
    "Download C header": "C Başlık Dosyasını İndir",
    "Firmware export unavailable: full commissioning was rejected or the export configuration failed. Prior assumptions cannot be exported as commissioned estimates.": "Firmware dışa aktarımı kullanılamıyor: tam devreye alma reddedildi veya dışa aktarım yapılandırması başarısız oldu. Başlangıç varsayımları devreye alma kestirimleri olarak dışa aktarılamaz.",
    "#### COMMITTED M18 VALIDATION EVIDENCE": "#### DEPOYA KAYDEDİLMİŞ M18 DOĞRULAMA KANITI",
    "Versioned evidence for the portable core; not a new parity test of this run. No compiler or replay executes on UI interaction.": "Taşınabilir çekirdek için sürümlenmiş kanıttır; bu çalışmaya ait yeni bir eşdeğerlik testi değildir. Arayüz etkileşiminde derleyici veya yeniden oynatma çalışmaz.",
    "Artifact SHA-256: ": "Dosya SHA-256 değeri: ",
    "Full versioned parity record / compiler flags": "Tam sürümlenmiş eşdeğerlik kaydı / derleyici seçenekleri",
    "Strict > saturation flags can disagree at float32 rounding boundaries; all probes were retained.": "Kesin > doyum karşılaştırmaları float32 yuvarlama sınırlarında farklı olabilir; bütün sınama örnekleri korundu.",
    "Results change only when Run Commissioning is submitted. Current inputs and last completed run may differ.": "Sonuçlar yalnızca Devreye Almayı Başlat seçildiğinde değişir. Güncel girdiler ve son tamamlanan çalışma farklı olabilir.",
    "Generating sampled data, commissioning and evaluating accepted operation…": "Örneklenmiş veriler üretiliyor, devreye alma ve kabul edilen çalışma değerlendiriliyor…",
    "Configure a simulation case and select Run Commissioning. Estimates and run metrics will be computed by the existing backend.": "Bir benzetim durumu yapılandırıp Devreye Almayı Başlat seçin. Kestirimler ve çalışma ölçütleri mevcut mühendislik altyapısında hesaplanır.",
    "Measurements → Rs/Ld/Lq → psi_f → J/B → gates/supervision → retuning → M14/M16 analysis → simulation validation → M18 export": "Ölçümler → Rs/Ld/Lq → psi_f → J/B → kalite kapıları/gözetim → yeniden ayarlama → M14/M16 analizi → benzetim doğrulaması → M18 dışa aktarımı",
    "Reproducibility / estimator-visible configuration": "Tekrarlanabilirlik / kestiriciye açık yapılandırma",
    "Commissioning": "Devreye Alma", "Parameters / controllers": "Parametreler / denetleyiciler",
    "Operating analysis": "Çalışma Noktası Uygunluğu", "Simulation evaluation": "Benzetim değerlendirmesi",
    "Nonidealities": "İdeal olmayan etkiler", "Firmware / M18": "Firmware / M18",
    "Prior → identified → active controller": "Başlangıç → kestirilen → etkin denetleyici",
    "Motor values and gains come from existing retuning/controller constructors. Rejection retains all prior controller parameters.": "Motor değerleri ve kazançlar mevcut yeniden ayarlama/denetleyici oluşturucularından gelir. Ret durumunda bütün başlangıç denetleyici parametreleri korunur.",
    "M17 simulation stress/error models": "M17 benzetim zorlanma/hata modelleri",
    "Exposure controls commissioning, operation, or both; Rs drift applies only during operation. Nominal-bus FOC command and true terminal voltage are distinct; extra actual-bus clipping is not fed back into nominal anti-windup.": "Etkiler devreye almaya, çalışmaya veya ikisine uygulanır; Rs sürüklenmesi yalnızca çalışmada geçerlidir. Nominal bara FOC komutu ve gerçek terminal gerilimi ayrıdır; gerçek bara kırpması nominal anti-windup'a geri beslenmez.",
    "#### Simulation evaluation / ground truth": "#### Benzetim değerlendirmesi / gerçek değerler",
    "Measured/true current and commanded/terminal voltage curves are in the Simulation evaluation tab.": "Ölçülen/gerçek akım ve komut/terminal gerilimi eğrileri Benzetim değerlendirmesi sekmesindedir.",
    "Prepare run bundle": "Çalışma Paketini Hazırla",
    "Writing current-run JSON/CSV/plot/configuration bundle…": "Güncel çalışma için JSON/CSV/grafik/yapılandırma paketi yazılıyor…",
    "Download run bundle": "Çalışma Paketini İndir",
    "Machine-readable identifiers and JSON keys are preserved in both languages.": "Makine tarafından okunan tanımlayıcılar ve JSON anahtarları her iki dilde de korunur.",
    "FULL ACCEPTED": "TAM KABUL", "REJECTED": "REDDEDİLDİ", "ACCEPT": "KABUL", "REJECT": "RET",
    "accepted": "kabul", "terminal": "sonlandırıldı", "one_shot": "Tek deneme", "adaptive": "Uyarlamalı gözetim",
    "combined": "Her iki aşama", "commissioning_only": "Yalnızca devreye alma", "operation_only": "Yalnızca çalışma",
    "standstill": "Duran rotor", "rotating": "Döndürülen rotor", "mechanical": "Mekanik",
    "ideal": "Nominal (ideal)", "current_mild": "Akım ölçümü — hafif", "current_strong": "Akım ölçümü — güçlü",
    "voltage_mild": "Gerilim yeniden oluşturma — hafif", "voltage_strong": "Gerilim yeniden oluşturma — güçlü",
    "angle_mild": "Açı yanlılığı — hafif", "angle_strong": "Açı yanlılığı — güçlü",
    "timing_one_sample": "Zamanlama — bir örnek gecikme", "inverter_mild": "İnverter gerilim hatası — hafif", "inverter_strong": "İnverter gerilim hatası — güçlü",
    "bus_sag_mild": "DC bara düşümü — hafif", "bus_sag_strong": "DC bara düşümü — güçlü",
    "rs_drift_mild": "Rs sürüklenmesi — hafif", "rs_drift_strong": "Rs sürüklenmesi — güçlü",
    "combined_mild": "Birleşik etkiler — hafif", "combined_strong": "Birleşik etkiler — güçlü",
    "Parameter": "Parametre", "Unit": "Birim", "Prior assumption": "Başlangıç varsayımı", "Identified / known": "Kestirilen / bilinen",
    "Controller value": "Denetleyici değeri", "Estimate": "Kestirim", "Stage": "Aşama", "Attempt": "Deneme", "Quality": "Kalite",
    "Estimator succeeded": "Kestirim tamamlandı", "Reasons": "Nedenler", "Estimator failure": "Kestirici hatası", "Decision": "Karar",
    "Adaptive action": "Uyarlamalı işlem", "Next configuration": "Sonraki yapılandırma", "Loop": "Çevrim", "Constant": "Sabit",
    "Value": "Değer", "Current": "Akım", "Speed": "Hız", "Metric": "Ölçüt", "Quantity": "Nicelik", "unavailable": "kullanılamıyor",
    "Check": "Kontrol", "Measured value": "Ölçülen değer", "Limit": "Sınır", "Passed": "Geçti",
    "Post-hoc absolute error [%]": "Değerlendirme sonrası mutlak hata [%]", "Compiler": "Derleyici",
    "Compared input samples": "Karşılaştırılan giriş örnekleri", "Maximum absolute difference [V]": "En büyük mutlak fark [V]",
    "Maximum relative difference [ratio]": "En büyük bağıl fark [oran]", "Relative-worst signal": "Bağıl farkı en büyük sinyal",
    "Saturation agreement": "Doyum durumu uyuşması", "Away-boundary agreement": "Sınır dışı uyuşma", "Boundary disagreements": "Sınırdaki farklılıklar",
    "feasible": "uygun", "voltage_limited": "gerilim sınırlı", "current_limited": "akım sınırlı", "evaluated": "değerlendirildi",
    "true": "doğru", "false": "yanlış",
    "Mechanical commissioning assumes explicitly known zero external load.": "Mekanik devreye alma, bilinen sıfır dış yük varsayar.",
    "M16 prediction uses constant load from t=0; closed-loop validation uses the configured load step.": "M16 öngörüsü t=0'dan itibaren sabit yük kullanır; kapalı çevrim doğrulama yapılandırılan yük basamağını kullanır.",
    "Rejected commissioning: prior parameters retained; commissioned operation and firmware export unavailable.": "Devreye alma reddedildi: başlangıç parametreleri korundu; devreye alınmış çalışma ve firmware dışa aktarımı kullanılamıyor.",
    "Configured M17 impairments are simulation stress/error models, not hardware specifications.": "M17 etkileri benzetim zorlanma/hata modelleridir; donanım özellikleri değildir.",
    "This run has good speed tracking but >10% post-hoc parameter error: speed tracking does not prove accurate commissioning.": "Bu çalışmada hız izleme iyi, ancak değerlendirme sonrası parametre hatası %10'dan büyük: iyi hız izleme, doğru devreye almayı kanıtlamaz.",
    "Simulated true speed": "Benzetilen gerçek hız", "Reference": "Referans", "Speed [rpm]": "Hız [rpm]",
    "True id": "Gerçek id", "Measured id": "Ölçülen id", "d current [A]": "d akımı [A]",
    "True iq": "Gerçek iq", "Measured iq": "Ölçülen iq", "q current [A]": "q akımı [A]",
    "Reference mapped to true frame": "Gerçek eksen takımına dönüştürülmüş referans", "Controller-frame reference": "Denetleyici eksen takımı referansı",
    "True electromagnetic torque": "Gerçek elektromanyetik tork", "External load": "Dış yük", "Torque [N m]": "Tork [N m]",
    "Requested dq magnitude": "İstenen dq genliği", "Applied terminal magnitude": "Uygulanan terminal genliği", "Limited FOC command": "Sınırlanmış FOC komutu",
    "Nominal bus limit": "Nominal bara sınırı", "Actual bus limit": "Gerçek bara sınırı", "Voltage magnitude [V]": "Gerilim genliği [V]",
    "Nominal FOC saturation": "Nominal FOC doyumu", "Actual-bus clipping": "Gerçek bara kırpması", "Saturation state [0/1]": "Doyum durumu [0/1]",
    "Simulation time [s]": "Benzetim zamanı [s]", "Plots sampled for display; metrics use the full trace": "Grafikler gösterim için seyreltilmiştir; ölçütler tam kaydı kullanır",
    "Sample time [s]": "Örnek zamanı [s]", "Current [A]": "Akım [A]", "Measured speed [rad/s]": "Ölçülen hız [rad/s]",
    "No measurements": "Ölçüm yok", "No fitted model available": "Kestirilen model yok", "Observed back-EMF integral": "Gözlenen ters EMK integrali",
    "Fitted": "Model uyumu", "Window time [s]": "Pencere zamanı [s]", "Back-EMF integral [V s]": "Ters EMK integrali [V s]",
    "Reconstructed torque integral": "Yeniden oluşturulan tork integrali", "Fitted J/B model": "Kestirilen J/B modeli", "Torque integral [N m s]": "Tork integrali [N m s]",
    "Prefix-fit time [s]": "Kümülatif kestirim zamanı [s]", "Estimate / final estimate [dimensionless]": "Kestirim / son kestirim [boyutsuz]",
    "Prior controller retained.\nCommissioned operation and firmware export unavailable.": "Başlangıç denetleyicisi korundu.\nDevreye alınmış çalışma ve firmware dışa aktarımı kullanılamıyor.",
    "Control validation unavailable; accepted controller update retained.": "Denetim doğrulaması kullanılamıyor; kabul edilen denetleyici güncellemesi korundu.",
    "v{version} — {status}. Local simulation study; no hardware deployment.": "v{version} — {status}. Yerel benzetim çalışmasıdır; donanıma yükleme yoktur.",
    "#### {stage} stage": "#### {stage} aşaması",
    "Attempt {number}: {status} — inspect measurements / diagnostics": "Deneme {number}: {status} — ölçümleri / tanı bilgilerini inceleyin",
    "Measurement provider failure (attempt {number}): {error}": "Ölçüm üretimi hatası (deneme {number}): {error}",
    "Committed parity evidence unavailable: {error}": "Depodaki eşdeğerlik kanıtı kullanılamıyor: {error}",
    "CURRENT RUN RESULTS: seed {seed} / {scenario} / {mode} / {exposure}": "GÜNCEL ÇALIŞMA SONUÇLARI: tohum {seed} / {scenario} / {mode} / {exposure}",
    "Current-run simulation evaluation / ground truth — {scenario}, seed {seed}": "Güncel benzetim değerlendirmesi / gerçek değerler — {scenario}, tohum {seed}",
    "Estimator-visible data — {stage}, attempt {number}": "Kestiriciye açık veriler — {stage}, deneme {number}",
}

# Field labels are presentation metadata only; original names remain available
# in JSON and diagnostic reason strings. Values/units are never converted.
TR.update({
    "control_iq_rmse_a": "Gerçek eksen takımında iq RMSE [A]", "max_speed_deviation_rpm": "En büyük hız sapması [rpm]", "recovery_time_s": "Toparlanma süresi [s]",
    "operation_status": "Çalışma değerlendirme durumu", "control_success": "Denetim başarısı", "true_id_rms_a": "Gerçek id RMS [A]",
    "controller_frame_iq_rmse_a": "Denetleyici eksen takımında iq RMSE [A]", "terminal_command_discrepancy_rmse_v": "Terminal/komut farkı RMSE [V]",
    "terminal_command_discrepancy_max_v": "En büyük terminal/komut farkı [V]", "nominal_bus_voltage_v": "Nominal bara gerilimi [V]",
    "actual_bus_voltage_v": "Gerçek bara gerilimi [V]", "final_speed_rpm": "Son hız [rpm]",
    "steady_state_feasible": "Sürekli çalışma uygun", "current_feasible": "Akım gereksinimi uygun", "voltage_feasible": "Gerilim gereksinimi uygun",
    "requested_speed_rpm": "İstenen hız [rpm]", "requested_load_torque_nm": "İstenen yük torku [N m]", "required_torque_nm": "Gerekli tork [N m]",
    "required_id_a": "Gerekli id [A]", "required_current_magnitude_a": "Gerekli akım genliği [A]", "current_margin_a": "Akım payı [A]",
    "current_utilization": "Akım kullanım oranı", "required_vd_v": "Gerekli vd [V]", "required_vq_v": "Gerekli vq [V]",
    "voltage_utilization": "Gerilim kullanım oranı", "electrical_speed_rad_s": "Elektriksel hız [rad/s]",
    "qualified_band_entry_time_s": "Koşulları sağlayan banda giriş zamanı [s]", "in_band_at_deadline": "Süre sınırında bandın içinde",
    "finite_signals": "Sinyaller sonlu", "current_reference_within_limit": "Akım referansı sınır içinde", "maximum_measured_current_a": "En büyük ölçülen akım [A]",
    "minimum_speed_rpm": "En düşük hız [rpm]", "maximum_voltage_utilization": "En büyük gerilim kullanım oranı", "saturation_fraction": "Doyum oranı",
    "effective_rank": "Etkin rank", "scaled_condition_number": "Ölçeklenmiş koşul sayısı", "noise_information_fraction": "Gürültü bilgi oranı",
    "split_relative_difference": "Bölünmüş kestirim bağıl farkı", "residual_rmse": "Artık RMSE", "relative_sensitivity": "Bağıl yerel duyarlılık", "component_snr": "Bileşen SNR",
    "control_speed_rmse_rpm": "Yük sonrası hız RMSE [rpm]", "control_iq_rmse_true_frame_a": "Gerçek eksen takımında iq RMSE [A]",
    "control_max_speed_deviation_rpm": "En büyük hız sapması [rpm]", "control_recovery_time_s": "Toparlanma süresi [s]",
    "command_saturation_fraction": "Komut doyum oranı", "actual_bus_saturation_fraction": "Gerçek bara doyum oranı",
    "true_current_peak_a": "En büyük gerçek akım [A]", "measured_current_peak_a": "En büyük ölçülen akım [A]",
    "command_voltage_utilization": "Komut gerilim kullanım oranı", "terminal_voltage_utilization": "Terminal gerilim kullanım oranı",
    "requested_rpm": "İstenen hız [rpm]", "load_torque_nm": "Yük torku [N m]", "required_iq_a": "Gerekli iq [A]",
    "required_voltage_magnitude_v": "Gerekli gerilim genliği [V]", "voltage_limit_v": "Gerilim sınırı [V]",
    "voltage_margin_v": "Gerilim payı [V]", "current_limit_a": "Akım sınırı [A]", "classification": "Sınıflandırma",
    "quasi_steady_transition_time_estimate_s": "Yarı durağan geçiş süresi kestirimi [s]",
    "quasi_steady_completion_time_estimate_s": "Yarı durağan tamamlanma süresi kestirimi [s]",
    "quasi_steady_deadline_met": "Yarı durağan modelde süre sınırı sağlandı", "quasi_steady_band_reachable": "Yarı durağan modelde banda erişilebilir",
    "predicted_closed_loop_success": "Öngörülen kapalı çevrim başarısı", "first_band_entry_time_s": "Banda ilk giriş zamanı [s]",
    "hold_completion_time_s": "Bantta kalma tamamlanma zamanı [s]", "reasons": "Nedenler",
    "kp_d": "Kp_d", "ki_d": "Ki_d", "kp_q": "Kp_q", "ki_q": "Ki_q", "kp": "Kp", "ki": "Ki",
    "anti_windup_gain": "Anti-windup kazancı", "torque_constant_nm_per_a": "Tork sabiti [N m/A]", "iq_limit_a": "iq sınırı [A]",
    "dc_bus_voltage_v": "DC bara gerilimi [V]", "pole_pairs": "Kutup çifti sayısı",
})

EN = {"ideal": "Nominal (ideal)", "one_shot": "One-shot", "adaptive": "Adaptive supervisor",
      "combined": "Both stages", "commissioning_only": "Commissioning only", "operation_only": "Operation only",
      "standstill": "Standstill", "rotating": "Rotating", "mechanical": "Mechanical"}
for family, label in (("current", "Current measurement"), ("voltage", "Voltage reconstruction"), ("angle", "Angle bias"),
                      ("inverter", "Inverter voltage error"), ("bus_sag", "Bus sag"), ("rs_drift", "Rs drift"), ("combined", "Combined")):
    for level in ("mild", "strong"):
        EN[f"{family}_{level}"] = f"{label} — {level}"
EN["timing_one_sample"] = "Timing — one-sample delay"


def set_language(language):
    if language not in LANGUAGES:
        raise ValueError("unsupported_display_language")
    _language.set(language)


def translate(message, language, **values):
    """Unknown codes/messages survive verbatim; English is the source catalogue."""
    template = TR.get(message, message) if language == "tr" else EN.get(message, message)
    return template.format(**values) if values else template


def t(message, **values):
    return translate(message, _language.get(), **values)


def display_formatter():
    # Widget serialization can happen outside the script thread (e.g. AppTest).
    # Capture the selected language rather than consulting a different context.
    return partial(translate, language=_language.get())


def display_rows(rows):
    return [{t(key): t(value) if isinstance(value, str) else value for key, value in row.items()} for row in rows]


def localize_figure(figure):
    """Translate text artists only. No signal data, gains or estimator changes."""
    from matplotlib.text import Text
    patterns = (
        (r"Current-run simulation evaluation / ground truth — (.*), seed (\d+)\n(.*)",
         lambda m: t("Current-run simulation evaluation / ground truth — {scenario}, seed {seed}", scenario=t(m[1]), seed=m[2])+"\n"+t(m[3])),
        (r"Estimator-visible data — (.*), attempt (\d+)",
         lambda m: t("Estimator-visible data — {stage}, attempt {number}", stage=t(m[1]), number=m[2])),
    )
    for artist in figure.findobj(Text):
        text = artist.get_text()
        translated = t(text) if text in TR else "\n".join(t(line) for line in text.split("\n"))
        for pattern, render in patterns:
            match = re.fullmatch(pattern, text)
            if match:
                translated = render(match)
        artist.set_text(translated)
    return figure
