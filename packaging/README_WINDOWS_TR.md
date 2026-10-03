# PMSM Engineering App — Windows başlangıç

1. ZIP dosyasının **tamamını** bir klasöre çıkartın. EXE'yi ZIP içinden çalıştırmayın.
2. `PMSM Engineering App.exe` dosyasına çift tıklayın. `_internal` klasörünü silmeyin.
3. Yerel uygulama tarayıcıda açılır. Python, pip veya Git gerekmez.
4. Varsayılan dil Türkçedir; sol menüden English seçilebilir.
5. Bitirmek için açılan konsolda Ctrl+C kullanın. Yalnızca tarayıcı sekmesini
   kapatmak sunucuyu durdurmaz. Konsolu kapatmak da uygulama sürecini sonlandırır.

Uygulama yalnızca `127.0.0.1:8501` üzerinde çalışır. Bu port doluysa hata
konsolda ve `%LOCALAPPDATA%\PMSMEngineering\logs\startup.log` dosyasında gösterilir.
Başka port için PowerShell'de `$env:PMSM_PORT='8502'` ayarlayıp EXE'yi çalıştırın.
CI için `PMSM_HEADLESS=1` tarayıcının açılmasını engeller.

**İmzasız EXE:** Kod imzalama yoktur; Windows SmartScreen uyarabilir. SHA-256,
dosya bütünlüğü kontrolüdür; kod imzası veya güvenlik garantisi değildir.
İmzasız ikili çalıştırmak istemiyorsanız depodaki Python kaynak yolunu kullanın.
Kaynak sürümü eşit derecede desteklenir. ZIP ile birlikte gelen
`SHA256SUMS.txt` dosyasını `Get-FileHash -Algorithm SHA256` ile karşılaştırabilirsiniz.

Bu bir benzetim/mühendislik uygulamasıdır; fiziksel motor sürücüsü veya MCU'ya
yüklenmiş firmware değildir. Kalite kapıları reddi gizlemez. İyi hız izleme,
doğru parametre kestirimini tek başına kanıtlamaz. Yarı durağan süre kestirimi
evrensel fiziksel alt sınır değildir.

Kaynak kod MIT lisanslıdır; pakette LICENSE bulunur. Bağımlılıkların kendi
lisansları geçerlidir. Sürüm ve derlenen kaynak bilgisi BUILD_INFO.json içindedir.
