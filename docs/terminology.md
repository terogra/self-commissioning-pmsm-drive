# UI terminology / Arayüz terminolojisi

This glossary defines display terminology for the commissioning workbench.
Use **PMSM Sürücü Devreye Alma Aracı** in Turkish and
**PMSM Drive Commissioning Workbench** in English. The repository name remains
**Self-Commissioning PMSM Drive**.

| English | Türkçe | Usage |
|---|---|---|
| Commissioning | Devreye Alma | Full measurement, quality and controller-update workflow |
| Parameter estimation / Parameter identification | Parametre kestirimi | Numerical estimation of motor parameters; use one term throughout the UI |
| Drive setup | Sürücü ayarları | Configuration, not a new controller design |
| Initial model: Default | Başlangıç modeli: Varsayılan | Existing fallback assumptions; no unknown parameter entry required |
| Custom | Özel | Explicitly reveals editable prior/fallback assumptions |
| Parameters to estimate | Kestirilecek parametreler | Rs, Ld, Lq, psi_f, J, B are unknown quantities, not required inputs |
| Advanced Simulation Settings | Gelişmiş Simülasyon Ayarları | Collapsed by default; simulation design inputs |
| Simulation Motor Model | Simülasyon Motor Modeli | Hidden validation ground truth used to generate measurements |
| Operating point | Çalışma noktası | Speed and load request |
| Operating request | Çalışma noktası | Sidebar input group; internal message identifier retained |
| Dynamic deadline [s] | Dinamik süre sınırı [s] | Existing M16 request deadline, in seconds |
| Available | Kullanılabilir | Firmware export availability |
| Blocked | Engellendi | Firmware export blocked by rejection |
| M17 simulation preset | M17 senaryosu | Existing M17 scenario selection; scenario codes unchanged |
| Simulation errors | İdeal olmayan etkiler | Sidebar group for existing M17 error models |
| Steady-state | Kararlı durum | M14 equilibrium model |
| Steady-state feasibility | Kararlı durum uygunluğu | Current/voltage requirements at equilibrium |
| Dynamic feasibility | Dinamik uygunluk | M16 deadline and hold requirement |
| Quasi-steady | Yarı kararlı durum | Approximate M16 model; never a universal physical lower bound |
| Controller-aware prediction | Denetleyici modeliyle öngörü | Existing controller simulation on identified parameters |
| Excitation | Uyartım | Commissioning voltage/current sequence |
| Locked rotor | Kilitli rotor | Standstill Rs/Ld/Lq stage |
| Residual | Model artığı | Measured response minus fitted-model response |
| Bias | Bias / sistematik hata | Persistent error; use *ofset* for an additive sensor/angle offset |
| Voltage saturation | Gerilim doyumu | dq voltage-vector limit |
| Current limit / Voltage limit | Akım sınırı / Gerilim sınırı | Keep the associated SI unit |
| DC bus | DC bara | Nominal and actual bus remain distinct |
| Ground truth | Gerçek simülasyon değerleri | Evaluation only; never estimator or quality-gate input |
| Validation | Doğrulama | Closed-loop or recorded Python/C checks |
| Retry | Yeniden deneme | A new bounded commissioning attempt |
| Supervisor | Gözetim | Existing adaptive retry logic |
| Nonidealities | İdeal olmayan etkiler | M17 measurement/drive error models |
| Transient | Geçici rejim | Full dq transient behavior |
| Diagnostics | Tanı bilgileri | Residual, conditioning, sensitivity and exact reason codes |
| Firmware export | Firmware dışa aktarımı | C99 configuration, not MCU deployment |

Use *simülasyon* in Turkish UI prose. Keep PMSM, FOC, dq, PI, PWM, RMSE,
ADC, MCU, C99, firmware and anti-windup. Use σ for configured noise standard
deviation; it does not establish statistical coverage.

English labels should use normal drives terminology: *Drive setup*,
*Parameters & control*, *Operating point*, *Validation*. Avoid product claims
such as “platform”, “comprehensive solution” or “powerful”.

The catalogue retains existing message/field identifiers where needed.
Display labels may change; scenario codes, diagnostic codes, JSON keys,
configured values, gates and numerical results do not. Unknown codes are shown
verbatim. SI values are displayed without unit conversion.
