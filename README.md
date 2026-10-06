[**Türkçe**](README.md) | [English](README.en.md)

# Self-Commissioning PMSM Drive

## PMSM Sürücü Devreye Alma ve Parametre Kestirimi

Bir PMSM sürücüsünde motor parametreleri yanlış biliniyorsa denetleyici nasıl
etkilenir? Bu proje, parametreleri simüle edilmiş ölçümlerden kestirip akım ve hız
PI denetleyicilerini yeniden ayarlayarak bu soruyu inceler.

PySide6/Qt masaüstü uygulamasında deneyleri çalıştırabilir, kestirimleri ve ret
nedenlerini inceleyebilir, kapalı çevrim yanıtını değerlendirebilirsiniz.
Başarılı devreye alma sonunda taşınabilir C99 kontrol çekirdeği için yapılandırma
başlığı dışa aktarılır.

![PMSM devreye alma sonuçları — Türkçe arayüz](docs/images/v1_1_dashboard_tr.png)

## Hızlı başlangıç

### Windows

1. [v1.1.0 sürüm sayfasından](https://github.com/terogra/self-commissioning-pmsm-drive/releases/tag/v1.1.0)
   `PMSM-Commissioning-Workbench-v1.1.0-Windows-x64.zip` ve `SHA256SUMS.txt` dosyalarını indirin.
2. ZIP'in tamamını çıkartın. `_internal` klasörünü EXE'nin yanında tutun.
3. `PMSM-Commissioning-Workbench.exe` dosyasını açın.

Python kurulumu gerekmez. EXE imzasızdır; Windows SmartScreen uyarı gösterebilir.
SHA-256 dosya bütünlüğünü kontrol eder, kod imzasının yerini tutmaz.
[Windows kullanım ve hata giderme notları](packaging/README_WINDOWS_TR.md).

### Kaynak kod

Python 3.11 veya 3.12 ile, Windows PowerShell'de:

```powershell
git clone https://github.com/terogra/self-commissioning-pmsm-drive.git
cd self-commissioning-pmsm-drive
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app
```

Etkinleştirme betiği engellenirse `.\.venv\Scripts\python.exe` ile doğrudan
`-m pip install -r requirements.txt` ve `-m app` komutlarını çalıştırabilirsiniz.
Linux/macOS'ta ortamı `source .venv/bin/activate` ile etkinleştirin.

## İlk deney

Varsayılan ayarlarla **Devreye Almayı Başlat** düğmesine basın. Altı motor
parametresini girmeniz gerekmez; uygulama bunları ölçüm kayıtlarından kestirir.
**Dil / Language** menüsüyle İngilizceye geçebilirsiniz.

| Aşama | Kestirilen parametreler | Yöntem |
| --- | --- | --- |
| Kilitli rotor | `Rs`, `Ld`, `Lq` | İki eksende gerilim uyartımı ve integral regresyon |
| Dönen rotor | `psi_f` | Gerilim, akım ve hız kayıtlarından akı kestirimi |
| Serbest rotor | `J`, `B` | Yeniden oluşturulan tork ve hız değişimiyle mekanik kestirim |

Ölçüm kalitesi yeterliyse denetleyici yeniden ayarlanır. Ret durumunda başlangıç
denetleyicisi korunur; kısmi kestirimler ve ret nedenleri sonuçlarda görünür,
firmware dışa aktarımı kapalı kalır. Uyarlamalı yöntem, belirli kalite sorunlarında
sınırlı sayıda yeni ölçüm denemesi yapar.

**Gelişmiş Simülasyon Ayarları**, sanal motoru, uyartımı ve ölçüm gürültüsünü
kontrol eder. Sanal motorun gerçek parametreleri kestiriciye verilmez; sonuçların
doğruluğunu değerlendirmek için kullanılır. **Başlangıç modeli: Özel** seçeneği
denetleyicinin başlangıç kabullerini açar.

Sonuç sekmelerinde parametreler, kazançlar, çalışma noktası, kapalı çevrim grafikler
ve hata senaryoları yer alır. **Çalışma paketini kaydet** JSON/CSV/grafik çıktıları
üretir; tam kabulde **C başlığını dışa aktar** açılır. Hesaplama bitmeden uygulama
penceresini kapatmayın.

## Deneyler ve doğrulama

```sh
python -m experiments.v1_demo --output demo-current
python -m pytest -q
```

Gösterim komutu bir nominal kabul ve bir ölçüm gecikmesi nedeniyle ret durumunu
hesaplar. Diğer deneyler parametre uyuşmazlığı, gerilim doyumu, gürültü, sensör
hataları, bara düşümü ve direnç değişimini inceler. Başarısız ve yanlı kestirimler
de sonuç kayıtlarında yer alır.

v1.0 doğrulama kaydı **265 Python testi**, **43 C doğrulaması** ve **31.484
Python/C karşılaştırma örneği** içerir. Tek duyarlıklı hesaplamadan kaynaklanan
**16 doyum sınırı farkı** ayrıca raporlanır. Güncel CI, Python 3.11/3.12,
GCC/Clang, Qt arayüzü ve paketlenmiş Windows uygulamasını kontrol eder.

## Varsayımlar ve sınırlar

Proje simülasyon tabanlıdır. Kutup çifti sayısı bilinir; mekanik kestirimde dış yükün
sıfır olduğu varsayılır. Bilinmeyen yük, Coulomb/statik sürtünme, değişen atalet ve
sensörün sistematik hataları kestirim doğruluğunu sınırlar. İyi hız izleme, motor
parametrelerinin doğru kestirildiğini tek başına göstermez. Devreye alma kabulü de
istenen hız ve yükün mevcut akım/gerilim sınırlarında sağlanacağını garanti etmez.

M16 süre hesabı yarı kararlı bir model kestirimidir; tam dq geçici rejimi hız
bandına daha erken girebilir. Teknik tanım: the quasi-steady estimate is **not a
physical minimum or universal lower bound**; the **full dq transient simulation**
can enter the band earlier.

C99 çekirdeği bilgisayarda doğrulanmıştır. MCU üzerinde çalışma, çevrebirim
sürücüleri, hedef zamanlaması, gerçek motor testleri ve MISRA uygunluğu henüz
bu çalışmanın kapsamında değildir.

## Teknik belgeler

- [Model, denklemler ve deney komutları](README.v1.0.md)
- [Mühendislik günlüğü](docs/engineering_log.md)
- [v1.0 doğrulama sonuçları](docs/v1_validation.md)
- [Masaüstü mimarisi](docs/desktop_architecture.md) ve [Windows derleme notları](docs/v1_1_productization.md)
- [Arayüz terminolojisi](docs/terminology.md), [değişiklik günlüğü](CHANGELOG.md) ve [sürüm notları](RELEASE_NOTES_v1.1.0.md)

Eski Streamlit arayüzü için `requirements-legacy.txt` bağımlılıklarını kurup
`python -m app.legacy` çalıştırın.

Kaynak kod [MIT lisanslıdır](LICENSE); bağımlılıkların kendi lisansları geçerlidir.
