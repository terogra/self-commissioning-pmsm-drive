# v1.1.0 sürüm notları / release notes

[English below](#english)

## Türkçe

v1.1.0, v1.0.0'daki M1-M19 mühendislik altyapısını değiştirmeden projeyi daha
kolay erişilebilir ve daha rahat incelenebilir hale getirir.

### Öne çıkanlar

- Uygulamada **Türkçe / English** dil seçimi.
- Varsayılan Türkçe arayüz ve mühendislik terminolojisi.
- GitHub ana sayfasında Türkçe-first ürün anlatımı ve ayrı İngilizce README.
- İki eşit kullanım yolu:
  - hazır Windows x64 portable paket,
  - kaynak koddan `python -m app`.
- Windows paketi temiz GitHub Actions Windows runner'ında oluşturulur.
- Paketlenmiş uygulama release öncesi HTTP smoke testinden geçer.
- Her Windows ZIP'i için `SHA256SUMS.txt` üretilir.
- Hazır EXE zorunlu değildir ve şu anda kod imzalama sertifikasıyla
  imzalanmamıştır.

### Windows hızlı kullanım

Release **Assets** bölümünden
`PMSM-Engineering-App-v1.1.0-Windows-x64.zip` dosyasını indirin, ZIP'i tamamen
çıkarın ve `PMSM Engineering App.exe` dosyasını çalıştırın.

Hazır binary kullanmak istemiyorsanız kaynak koddan çalıştırma yöntemi README'de
ayrıntılı olarak verilmiştir.

### Mühendislik sınırı

Bu sürüm; PMSM modeli, parametre kestirim algoritmaları, kalite kapıları,
uyarlamalı yeniden deneme kuralları, çalışma uygunluğu algoritmaları veya C99
kontrol çekirdeğinin matematiğini değiştirmez.

Donanım üzerinde STM32 devreye alma, WCET, fiziksel inverter/motor doğrulaması,
MISRA veya fiziksel güvenlik sertifikasyonu hâlâ bu sürümün kapsamı dışındadır.

---

<a id="english"></a>

## English

v1.1.0 productizes the existing v1.0.0 M1-M19 engineering baseline without
changing the motor-control or commissioning algorithms.

### Highlights

- Turkish/English application language selector.
- Turkish-first repository landing page plus a full English README.
- Two equal usage paths: a ready Windows x64 portable package or direct
  source-code execution with `python -m app`.
- Reproducible Windows build on GitHub Actions.
- Packaged-app HTTP smoke test before publication.
- SHA-256 checksum published with the Windows ZIP.
- The convenience executable is currently unsigned and remains optional.

### Engineering boundary

No M1-M19 identification equation, quality threshold, adaptive action,
M14/M16 semantic, M17 stress definition or M18 Python/C parity budget is
changed by this release. Hardware deployment remains future work.
