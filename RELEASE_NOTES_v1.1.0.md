# v1.1.0

## Öne çıkanlar / Highlights

- Native **PySide6/Qt** masaüstü uygulaması; tarayıcı, localhost arayüzü veya kalıcı konsol yok.
- Türkçe varsayılan arayüz ve tam English seçeneği.
- Varsayılan kullanımda bilinmeyen `Rs, Ld, Lq, psi_f, J, B` değerlerini girme zorunluluğu yok; bunlar ölçümlerden kestirilir.
- Simülasyon gerçek değerleri **Gelişmiş Simülasyon Ayarları** altında gizlidir ve kestiriciye verilmez.
- `python -m app` ve Windows EXE aynı native uygulamayı açar.
- Windows x64 için doğrulanmış PyInstaller `onedir` paketi ve SHA-256 bütünlük dosyası.
- M1–M19 mühendislik algoritmaları, kalite eşikleri, M14/M16/M17 semantiği ve M18 C99 çekirdeği değiştirilmemiştir.

## Windows

Sürüm varlıkları:

- `PMSM-Commissioning-Workbench-v1.1.0-Windows-x64.zip`
- `SHA256SUMS.txt`
- GitHub source ZIP/tar.gz

ZIP'in tamamını çıkartın ve `PMSM-Commissioning-Workbench.exe` dosyasını çalıştırın.
`_internal` klasörünü EXE ile birlikte tutun. EXE imzasızdır; Windows SmartScreen
uyarabilir. SHA-256 bütünlük kontrolüdür, kod imzası değildir.

## Kaynaktan / From source

```powershell
python -m pip install -r requirements.txt
python -m app
```

Eski Streamlit arayüzü yalnızca geliştirme içindir ve `python -m app.legacy`
ile ayrı olarak çalıştırılır.

## Doğrulama / Validation

v1.1.0; Python 3.11/3.12 testleri, GCC/Clang C99 parity, native Qt kabul/ret
akışları, paketlenmiş Windows EXE başlangıcı ve boşluk içeren dizine çıkartılmış
ZIP tekrar testiyle doğrulanmıştır. Derleme tek başına kabul ölçütü değildir.

## Kapsam ve sınırlar / Scope and limits

Bu sürüm ürünleştirme ve dağıtım çalışmasıdır; **M20 değildir**. Uygulama halen
simülasyon tabanlıdır. MCU dağıtımı, gerçek motor doğrulaması, hedef zamanlama,
MISRA uygunluğu veya fiziksel güvenlik sertifikasyonu iddia edilmez. İyi hız
izleme tek başına doğru parametre kestirimini kanıtlamaz. M16 yarı kararlı süre
kestirimi evrensel bir fiziksel alt sınır değildir.
