# Self-Commissioning PMSM Drive

**Türkçe** | [English](README.en.md)

## PMSM Otomatik Devreye Alma ve Sürücü Mühendislik Platformu

PMSM motor parametrelerini örneklenmiş ölçümlerden kestiren, ölçüm kalitesini
kontrol eden, kabul edilen sonuçlarla denetleyiciyi yeniden ayarlayan ve istenen
çalışma noktasını değerlendiren açık kaynak bir mühendislik uygulamasıdır.

Bu proje yalnızca "motoru döndüren" bir FOC demosu değildir. Elektriksel ve
mekanik parametre kestirimi, kalite kapıları, sınırlı uyarlamalı yeniden deneme,
çalışma uygunluğu, gerçekçi simülasyon hataları ve Python/C sayısal doğrulamasını
tek bir uçtan uca akışta birleştirir.

> **v1.1.0:** Türkçe/İngilizce arayüz + Windows x64 hazır paketleme. M1-M19
> mühendislik algoritmaları ve doğrulama eşikleri değiştirilmez.

---

## Hızlı erişim

### 1. Hazır Windows sürümü — en hızlı inceleme

GitHub'da **Releases** bölümüne girin ve en güncel sürümün **Assets** alanından:

`PMSM-Engineering-App-vX.Y.Z-Windows-x64.zip`

dosyasını indirin. ZIP'i tamamen çıkardıktan sonra:

`PMSM Engineering App.exe`

dosyasını çalıştırın. Python, pip veya Git kurulumu gerekmez. Uygulama yalnızca
yerel bilgisayarda `127.0.0.1` adresinde çalışır ve tarayıcı arayüzünü açar.

**EXE zorunlu değildir.** Hazır Windows paketi kod imzalama sertifikasıyla
imzalanmamıştır. Hazır ikili dosya kullanmak istemeyenler aşağıdaki kaynak kod
yöntemiyle aynı uygulamayı doğrudan çalıştırabilir. Her Windows release paketinin
SHA-256 özeti de release varlıkları arasında yayımlanır.

### 2. Kaynak koddan çalıştırma

Python 3.11 veya 3.12 ile:

```powershell
git clone https://github.com/terogra/self-commissioning-pmsm-drive.git
cd self-commissioning-pmsm-drive

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app
```

Tarayıcı otomatik açılmazsa:

`http://127.0.0.1:8501`

adresini kullanabilirsiniz.

---

## Türkçe / English arayüz

Uygulama **Türkçe-first** tasarlanmıştır. Sol menüdeki **Dil / Language**
seçiminden anında Türkçe veya İngilizce kullanılabilir.

Türkçe mühendislik terminolojisinde özellikle:

- `commissioning` → **devreye alma**
- `parameter estimation` → **parametre kestirimi**
- `operating feasibility` → **çalışma noktası uygunluğu**
- `accepted / rejected` → **kabul / ret**
- FOC, dq, PI, PMSM, firmware ve DC bara gibi yerleşik teknik ifadeler gerektiği
  yerde korunur.

Backend hata kodları ve makine tarafından üretilen JSON alanları, yeniden
üretilebilirlik ve teknik teşhis amacıyla özgün adlarıyla gösterilebilir.

---

## Ne yapıyor?

Uygulamanın ana akışı:

```text
Örneklenmiş ölçümler
        ↓
Duran rotor: Rs / Ld / Lq kestirimi
        ↓
Dönen rotor: ψf kestirimi
        ↓
Serbest rotor: J / B kestirimi
        ↓
Ölçüm tabanlı kalite kapıları
        ↓
Gerekirse sınırlı uyarlamalı yeniden deneme
        ↓
FOC + hız çevrimi yeniden ayarlama
        ↓
M14 kararlı durum uygunluğu
        ↓
M16 dinamik uygunluk
        ↓
M17 ideal olmayan etki doğrulaması
        ↓
M18 C99 firmware yapılandırması
```

### Kestirilen / kullanılan motor parametreleri

| Parametre | Anlam |
| --- | --- |
| `Rs` | Stator direnci |
| `Ld` | d-ekseni endüktansı |
| `Lq` | q-ekseni endüktansı |
| `ψf` | Kalıcı mıknatıs akı bağlanımı |
| `J` | Atalet |
| `B` | Viskoz sürtünme katsayısı |
| `pole_pairs` | Bilinen kutup çifti sayısı |

---

## v1 mühendislik doğrulaması

v1.0 teknik baseline'ında:

- **265 Python testi** geçti.
- Python **3.11 / 3.12** CI doğrulaması yapıldı.
- GCC ve Clang ile strict C99 derleme/parity işleri geçti.
- **43 native C assertion** geçti.
- **31.484 Python/C parity örneği** karşılaştırıldı.
- Sınır bölgesi dışındaki doygunluk kararları **30.512 / 30.512** eşleşti.
- Float32 sınırında kalan 16 gerçek Boolean uyuşmazlığı özellikle saklandı ve
  raporlandı; sonuçları "mükemmel" göstermek için eşikler değiştirilmedi.

Ayrıntılı doğrulama:
[docs/v1_validation.md](docs/v1_validation.md)

Mühendislik günlüğü:
[docs/engineering_log.md](docs/engineering_log.md)

Mimari:
[docs/architecture.md](docs/architecture.md)

İngilizce ayrıntılı teknik README:
[README.en.md](README.en.md)

---

## Örnek senaryolar

Tarayıcı arayüzünde nominal senaryonun yanında akım/gerilim ölçüm hataları,
elektriksel açı hatası, zamanlama gecikmesi, inverter gerilim hatası, DC bara
çökmesi, Rs sürüklenmesi ve birleşik stres senaryoları denenebilir.

İki davranış özellikle korunur:

- **Kabul:** Kalite kapılarından geçen tam devreye alma, denetleyici yeniden
  ayarlaması, çalışma analizi ve firmware yapılandırmasına ilerleyebilir.
- **Ret:** Kalite kapısı başarısız olduğunda önceki denetleyici varsayımları
  korunur; sonraki sonuçlar varmış gibi üretilmez ve firmware dışa aktarımı
  engellenir.

Bu ayrım projenin temel mühendislik sınırlarından biridir.

---

## Tekrarlanabilir demo

Tarayıcı açmadan iki referans senaryoyu yeniden üretmek için:

```powershell
python -m experiments.v1_demo
```

Bu komut nominal kabul edilen örneği ve tek-örnek zamanlama gecikmesinde
reddedilen örneği aynı backend üzerinden yeniden hesaplar.

---

## Windows paketinin nasıl üretildiği

Hazır Windows paketi repodaki GitHub Actions iş akışıyla temiz bir Windows x64
runner üzerinde oluşturulur.

Özet süreç:

```text
Kaynak kod
  → Python 3.12
  → uygulama / çeviri testleri
  → PyInstaller portable build
  → paketlenmiş uygulama HTTP smoke testi
  → ZIP
  → SHA-256
  → GitHub Release asset
```

Yerel paketleme ayrıntıları:
[packaging/README_WINDOWS_TR.md](packaging/README_WINDOWS_TR.md)

---

## Kapsam ve sınırlar

Bu proje şu anda **simülasyon tabanlı ve firmware'e hazır** bir mühendislik
platformudur.

Şunları **iddia etmez**:

- STM32 üzerinde gerçek donanım devreye alma
- hedef MCU WCET / gerçek zaman deadline doğrulaması
- fiziksel motor/inverter doğrulaması
- MISRA uyumluluğu
- fiziksel güvenlik sertifikasyonu

M18'deki C99 kontrol çekirdeği host üzerinde doğrulanmıştır; gerçek MCU,
ADC/PWM/encoder çevre birimleri ve fiziksel motor testleri ilerideki
hardware-backed geliştirme aşamasına aittir.

---

## Lisans

Kaynak kod **MIT License** ile yayımlanır. Ayrıntılar için [LICENSE](LICENSE).

MIT lisansı insanların kodu kendi bilgisayarlarında kullanmasına,
değiştirmesine ve kendi kopyalarını/forklarını oluşturmasına izin verir.
GitHub deposunun `main` dalına yazma yetkisi ise lisansla değil GitHub
izinleri ve aktif branch ruleset ile kontrol edilir.
