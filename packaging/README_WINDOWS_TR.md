# PMSM Sürücü Devreye Alma Aracı — Windows

1. ZIP'in **tamamını** çıkartın; EXE'yi ZIP içinden çalıştırmayın.
2. `PMSM-Commissioning-Workbench.exe` dosyasına çift tıklayın. `_internal`
   klasörünü koruyun.
3. Bağımsız Qt masaüstü penceresi açılır. Tarayıcı, yerel web sunucusu, konsol,
   Python, pip veya Git gerekmez.
4. Türkçe varsayılandır; **Dil / Language** ile English seçilebilir.
5. Ayarları girip **Devreye Almayı Başlat** düğmesine basın. İşlem sırasında
   ikinci devreye alma engellenir. Bitirmek için işlemin tamamlanmasını bekleyip
   pencereyi kapatın.

Tam kabulde **C başlığını dışa aktar** yerel kaydetme iletişim kutusunu açar.
Ret durumunda düğme devre dışıdır; başlangıç denetleyicisi korunur. Başarısız
kestirimler ve ret kodları sonuçlarda görünür. Çalışma paketi ZIP olarak da
kaydedilebilir.

Başlatma/işlem sorunları
`%LOCALAPPDATA%/PMSMCommissioningWorkbench/logs/desktop.log` dosyasındadır.
Bu yol kullanılamazsa aynı göreli klasör geçici dizinde oluşturulur. Uygulama
EXE'yi taşıdığınızda `_internal` klasörü ve içeriği de taşınmalıdır.

**EXE imzasızdır; SmartScreen uyarabilir.** SHA-256 bütünlük kontrolüdür, kod
imzası veya güvenlik garantisi değildir. Kaynak kullanım yolu `python -m desktop`.
ZIP hash'ini `Get-FileHash -Algorithm SHA256` ile `SHA256SUMS.txt` ile karşılaştırın.

Bu bir simülasyon çalışmasıdır; donanım sürücüsü veya MCU'ya yüklenmiş firmware
değildir. İyi hız izleme tek başına doğru parametre kestirimini kanıtlamaz.
Yarı kararlı durum süre kestirimi evrensel bir fiziksel alt sınır değildir.
Kaynak MIT lisanslıdır; bağımlılıklar kendi lisanslarını korur. `BUILD_INFO.json`
sürümü ve derleme kaynak bilgisini kaydeder. v1.1.0 sürüm adayıdır.
