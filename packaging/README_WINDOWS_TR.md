# Windows hazır sürümü

Bu klasör, GitHub Releases üzerinden yayımlanan taşınabilir Windows paketinin
üretim dosyalarını içerir.

## Kullanıcı için

Hazır paketi kullanan kişinin Python, pip veya Git kurması gerekmez.

1. `PMSM-Engineering-App-vX.Y.Z-Windows-x64.zip` dosyasını indirin.
2. ZIP dosyasını tamamen çıkarın.
3. `PMSM Engineering App.exe` dosyasını çalıştırın.
4. Uygulama yerel olarak `127.0.0.1` üzerinde çalışır ve tarayıcı arayüzünü açar.

Hazır EXE kod imzalama sertifikasıyla imzalanmamıştır. Windows güvenlik uyarısı
gösterirse veya hazır ikili dosyaya güvenmek istemiyorsanız kaynak koddan
çalıştırma yöntemini kullanın. Her release paketinin SHA-256 özeti yayımlanır.

## Geliştirici için

Windows paketini yerelde üretmek için:

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller==6.22.3
python -m PyInstaller packaging/PMSM_Engineering_App.spec --noconfirm --clean
```

Dağıtım çıktısı `dist/PMSM-Engineering-App/` altında oluşur.

Bu paketleme katmanı mühendislik algoritmalarını değiştirmez; mevcut Streamlit
arayüzünü ve Python/C mühendislik backend'ini taşınabilir bir Windows klasörü
olarak paketler.
